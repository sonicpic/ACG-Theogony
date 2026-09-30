"""反向收割管道：FGO 原型种子 → Wikidata 反查 → 跨媒体"同源角色/改编作品"入库。

思路（O(原型数) 而非 O(角色数)）：
  1. 种子：FGO 角色的 prototype 字段（392 个串，含神话本体名与 FGO 变体名两类）
  2. 种子 → QID：解析到神话/历史实体直接作为原型；解析到虚构实体（如 Fate 角色）
     则跟随其 P144/P1074 到达神话原型——两条路都通向统一的原型实体
  3. 反查：一条 SPARQL 批量拉取全部原型的虚构化身（P1074/P144 反向）
  4. 分类入库：ACG 角色并入 Character（去重：QID 或名称与 FGO 合并），
     作品入 works 表；原型本身成为 Character 节点（class_name=原型），
     FGO 角色与新收角色均挂 DERIVED_ON→原型 —— 同源角色雷达的骨干
  5. 全部关系带 source/evidence，结构化来源 status=approved

用法：
  python -u -m theogony.pipelines.harvest_prototypes --limit 20   # 试跑
  python -u -m theogony.pipelines.harvest_prototypes              # 全量
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
import unicodedata

from sqlalchemy import select

from theogony.core.db import get_session, init_db, rebuild_fts
from theogony.core.graph import GraphService
from theogony.core.orm import Alias, Character, Relationship, Work
from theogony.providers.wikidata import WikidataProvider

_REVERSE_SPARQL = """
SELECT ?proto ?fic ?ficLabel ?ficDesc WHERE {
  VALUES ?proto { %(protos)s }
  { ?fic wdt:P1074 ?proto } UNION { ?fic wdt:P144 ?proto }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "zh-hans,zh,en,ja". }
} LIMIT 2000
"""

_CHAR_CLASS_RE = re.compile(r"character|角色|虚构|fictional|架空|キャラクター", re.IGNORECASE)
_ACG_MEDIA_RE = re.compile(r"anime|manga|video game|visual novel|light novel|动画|漫画|游戏", re.IGNORECASE)
_WORK_CLASS_RE = re.compile(
    r"anime|manga|video game|visual novel|light novel|novel|film|movie|television|tv series|"
    r"comic|webcomic|animated series|anime and manga|"
    r"miniseries|fairy tale|literary work|opera|musical|painting|ballet|theatre|"
    r"动画|漫画|游戏|小说|电影|电视剧|影集|文學作品|文学作品|童话|音樂劇|音乐剧|畫作|画作|歌剧|戲劇",
    re.IGNORECASE,
)


# 中文音译常见变体折叠（同一人名的不同译法：恺撒/凯撒、阿蒂拉/阿提拉）
_TRANSLIT_FOLD = str.maketrans({
    "恺": "凯", "蒂": "提", "佛": "弗", "茨": "兹", "莎": "沙",
    "娅": "亚", "锹": "乔",
    "ō": "o", "ū": "u", "ā": "a", "ē": "e", "ī": "i",
    "ö": "o", "ü": "u", "é": "e", "á": "a",
})


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for ch in " \u3000·・.。'\"''\"·-‐–—_/／（）()〔〕[]":
        s = s.replace(ch, "")
    return s.lower().translate(_TRANSLIT_FOLD)


def _work_kind(class_text: str) -> str:
    t = class_text.lower()
    if re.search(r"anime|animated|动画", t):
        return "anime"
    if re.search(r"manga|comic|漫画", t):
        return "manga"
    if re.search(r"video game|visual novel|游戏", t):
        return "game"
    if re.search(r"novel|fairy tale|literary|小说|童话|文學|文学", t):
        return "literature"
    if re.search(r"film|movie|电视电影|电影", t):
        return "film"
    if re.search(r"television|tv series|miniseries|影集|电视剧", t):
        return "tv"
    if re.search(r"opera|musical|ballet|theatre|歌剧|音樂劇|音乐剧|戲劇", t):
        return "stage"
    if re.search(r"painting|畫作|画作", t):
        return "art"
    return "other"


def _has_cjk(s: str) -> bool:
    return any("\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff" for c in s or "")


# ──────────────────────────────────────────────
# 阶段 1：种子
# ──────────────────────────────────────────────

def load_seeds(limit: int | None) -> list[dict]:
    """种子 = FGO 角色本身（prototype 字段实测全部=自身名，不可用）。
    FGO 是神话浓度最高的语料：角色 Wikidata 实体普遍带 P144/P1074 → 神话原型。"""
    session = get_session()
    try:
        chars = session.execute(select(Character).where(Character.source == "fgo")).scalars().all()
        alias_map: dict[str, str] = {}
        for a in session.execute(select(Alias)).scalars().all():
            alias_map.setdefault(a.character_id, a.alias if a.alias else None)
        out = [{
            "char_id": c.id, "char_name": c.name, "mythology": c.mythology or "",
            "alias": alias_map.get(c.id),
        } for c in sorted(chars, key=lambda x: int(x.id[1:]) if x.id[1:].isdigit() else 0)]
    finally:
        session.close()
    if limit:
        out = out[:limit]
    print(f"[seeds] FGO 角色种子 {len(chars)} 个（本次处理 {len(out)}）")
    return out


# ──────────────────────────────────────────────
# 阶段 2：FGO 角色 → 原型 QID（正向解析：角色实体 → P144/P1074 → 神话目标）
# ──────────────────────────────────────────────

async def resolve_seeds(wd: WikidataProvider, seeds: list[dict]) -> list[dict]:
    hit_cache: dict[str, list[dict]] = {}
    for s in seeds:
        if s["char_name"] not in hit_cache:
            hits = await wd.search_entities(s["char_name"], language="zh", limit=8)
            # 别名始终补搜（日文/英文名覆盖另一批 zh 缺 label 的实体）
            if s.get("alias") and s["alias"] not in hit_cache:
                alias_lang = "ja" if _has_cjk(s["alias"]) else "en"
                extra = await wd.search_entities(s["alias"], language=alias_lang, limit=6)
                seen = {h["qid"] for h in hits}
                hits = hits + [h for h in extra if h["qid"] not in seen]
            hit_cache[s["char_name"]] = hits
        s["hits"] = hit_cache[s["char_name"]]

    all_qids = sorted({h["qid"] for s in seeds for h in s["hits"]})
    claims = await wd.resolve_claims(all_qids)
    # 目标二跳（P144/P1074 指向的神话实体）
    target_qids = sorted({
        t for cl in claims.values() for t in cl.get("p144", []) + cl.get("p1074", [])
    } - set(claims))
    if target_qids:
        claims.update(await wd.resolve_claims(target_qids))
    try:
        target_desc = await wd.labels_descriptions(target_qids) if target_qids else {}
        p31_ids = sorted({p for cl in claims.values() for p in cl.get("p31", [])})
        p31_meta = await wd.labels_descriptions(p31_ids) if p31_ids else {}
    except Exception:  # 离线：P31 类缺失时神话类判定退化为描述正则
        target_desc, p31_meta = {}, {}

    def norm(x: str) -> str:
        return normalize_name(x)

    resolved = 0
    for s in seeds:
        name_keys = {norm(s["char_name"])} | ({norm(s["alias"])} if s.get("alias") else set())

        def _exact(h: dict, _keys=frozenset(name_keys)) -> bool:
            return norm(h.get("label", "")) in _keys or norm(h.get("match_text", "")) in _keys
        # 与角色名精确同 label 的候选优先
        candidates = sorted(
            s["hits"],
            key=lambda h: 0 if _exact(h) else 1)
        for h in candidates:
            cl = claims.get(h["qid"], {})
            # 路径1：命中本身就是神话/历史实体且名称精确匹配（海伦娜·布拉瓦茨基 → Blavatsky）
            if _exact(h) and WikidataProvider.is_historic_or_mythic(
                    cl, h.get("description", ""), p31_meta):
                s["prototype_qid"] = h["qid"]
                s["char_qid"] = None
                s["prototype_label"] = h["label"]
                s["prototype_desc"] = h.get("description", "")
                resolved += 1
                break
            # 路径2：虚构实体（Fate 角色）跟随 P144/P1074 到神话目标
            for t in dict.fromkeys(cl.get("p144", []) + cl.get("p1074", [])):
                tcl = claims.get(t, {})
                tdesc = target_desc.get(t, {}).get("description", "")
                if WikidataProvider.is_historic_or_mythic(tcl, tdesc, p31_meta):
                    s["prototype_qid"] = t
                    s["char_qid"] = h["qid"]
                    s["prototype_label"] = target_desc.get(t, {}).get("label", t)
                    resolved += 1
                    break
            if s.get("prototype_qid"):
                break
    failed_names = [s["char_name"] for s in seeds if not s.get("prototype_qid")]
    print(f"[resolve] 角色解析到原型 {resolved}/{len(seeds)}（Tier A 正向链路）")
    if failed_names:
        print(f"[resolve] 未解析: {failed_names[:12]}{'…' if len(failed_names) > 12 else ''}")

    proto_qids = sorted({s["prototype_qid"] for s in seeds if s.get("prototype_qid")})
    try:
        meta = await wd.labels_descriptions(proto_qids) if proto_qids else {}
    except Exception:  # 离线重跑：标签查不到就用种子名兜底
        meta = {}
    for s in seeds:
        if s.get("prototype_qid"):
            m = meta.get(s["prototype_qid"], {})
            s["prototype_label"] = m.get("label") or s.get("prototype_label", "")
            s["prototype_desc"] = m.get("description", "")
    return [s for s in seeds if s.get("prototype_qid")]


# ──────────────────────────────────────────────
# 阶段 3+4：反查与入库
# ──────────────────────────────────────────────

async def harvest(wd: WikidataProvider, seeds: list[dict], max_per_proto: int, max_new: int) -> dict:
    proto_map: dict[str, dict] = {}  # qid → rec
    for s in seeds:
        rec = proto_map.setdefault(s["prototype_qid"], {
            "qid": s["prototype_qid"], "label": s.get("prototype_label") or s["prototype_qid"],
            "mythology": s["mythology"], "fgo_ids": [], "prototype_strs": set(),
        })
        rec["fgo_ids"].append(s["char_id"])
        rec["prototype_strs"].add(s["char_name"])

    # 批量反查（逐原型缓存 + 离线降级）
    qids = sorted(proto_map)
    rw_dir = wd._cache_dir
    fic_rows: list[dict] = []
    for q in qids:
        f = rw_dir / f"rw_{q}.json"
        if f.exists():
            fic_rows.extend(json.loads(f.read_text(encoding="utf-8")))
    missing = [q for q in qids if not (rw_dir / f"rw_{q}.json").exists()]
    for i in range(0, len(missing), 40):
        chunk = missing[i:i + 40]
        query = _REVERSE_SPARQL % {"protos": " ".join(f"wd:{q}" for q in chunk)}
        try:
            d = await wd._get("https://query.wikidata.org/sparql",
                              params={"query": query, "format": "json"},
                              headers={"Accept": "application/sparql-results+json"}, ttl=None)
        except Exception:
            print(f"[reverse] 网络失败：{len(chunk)} 个原型本轮跳过（缓存已有 {len(fic_rows)} 条，稍后重跑补齐）")
            break
        per_proto: dict[str, list[dict]] = {}
        for b in d.get("results", {}).get("bindings", []):
            qid = b["fic"]["value"].rsplit("/", 1)[-1]
            label = (b.get("ficLabel", {}).get("value") or "").strip()
            if not label or label == qid:
                continue  # 无 label 实体（多语言标签缺失），展示无意义
            per_proto.setdefault(b["proto"]["value"].rsplit("/", 1)[-1], []).append({
                "proto": b["proto"]["value"].rsplit("/", 1)[-1],
                "qid": qid,
                "label": label,
                "desc": b.get("ficDesc", {}).get("value", ""),
            })
        for q, rows in per_proto.items():
            (rw_dir / f"rw_{q}.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
            fic_rows.extend(rows)
    print(f"[reverse] 反查到 {len(fic_rows)} 条 虚构化身（含缓存）")

    fic_qids = sorted({r["qid"] for r in fic_rows})
    fic_claims = await wd.resolve_claims(fic_qids) if fic_qids else {}
    fic_p31 = sorted({p for cl in fic_claims.values() for p in cl.get("p31", [])})
    fic_p31_meta = await wd.labels_descriptions(fic_p31) if fic_p31 else {}

    def class_text(qid: str) -> str:
        return " ".join(
            f'{fic_p31_meta.get(p, {}).get("label", "")} {fic_p31_meta.get(p, {}).get("description", "")}'
            for p in fic_claims.get(qid, {}).get("p31", [])
        )

    # ── 入库 ──
    init_db()
    session = get_session()
    stats = {"prototypes": 0, "new_chars": 0, "merged_fgo": 0, "works": 0, "relations": 0, "skipped": 0}
    existing_by_qid: dict[str, str] = {
        c.wikidata_qid: c.id for c in session.execute(
            select(Character).where(Character.wikidata_qid.is_not(None))).scalars().all()
    }
    existing_by_name: dict[str, str] = {}
    for c in session.execute(select(Character)).scalars().all():
        existing_by_name.setdefault(normalize_name(c.name), c.id)
    for a in session.execute(select(Alias)).scalars().all():
        existing_by_name.setdefault(normalize_name(a.alias), a.character_id)

    def add_rel(src: str, dst: str, *, origin: str, evidence: str) -> None:
        exists = session.execute(
            select(Relationship).where(Relationship.source_id == src, Relationship.target_id == dst,
                                       Relationship.type == "DERIVED_FROM")
        ).scalar_one_or_none()
        if exists:
            return
        session.add(Relationship(
            source_id=src, target_id=dst, type="DERIVED_FROM", directed=True,
            confidence="verified", evidence=evidence[:400], origin=origin, status="approved"))
        stats["relations"] += 1

    try:
        for qid, rec in proto_map.items():
            proto_id = f"wp:{qid}"
            if not session.get(Character, proto_id):
                session.add(Character(
                    id=proto_id, wiki_id=0, name=rec["label"],
                    class_name="原型", mythology=rec["mythology"] or None,
                    source="wikidata", wikidata_qid=qid,
                    extra={"kind": "prototype", "qid": qid}))
                stats["prototypes"] += 1
            # FGO 角色 → 原型 骨干关系
            for fgo_id in rec["fgo_ids"]:
                add_rel(fgo_id, proto_id, origin="seed",
                        evidence=f'FGO 角色 Wikidata 实体 P144/P1074 → {rec["label"]} ({qid})')

        per_proto: dict[str, int] = {}
        for r in fic_rows:
            if stats["new_chars"] + stats["works"] >= max_new:
                break
            if per_proto.get(r["proto"], 0) >= max_per_proto:
                continue
            ct = class_text(r["qid"])
            norm = normalize_name(r["label"])
            # 角色类命中优先（类文本常同时含 media 词，如 "Touhou character, video game"）
            is_char = bool(_CHAR_CLASS_RE.search(ct))
            is_work = (not is_char) and bool(_WORK_CLASS_RE.search(ct))
            if not (is_char or is_work):
                stats["skipped"] += 1
                continue
            if is_char:
                media = "acg" if (_ACG_MEDIA_RE.search(ct) or _has_cjk(r["label"])) else "other-media"
                cid = existing_by_qid.get(r["qid"]) or existing_by_name.get(norm)
                if cid:  # 与 FGO 已有角色合并（只补 qid 与关系）
                    c = session.get(Character, cid)
                    if c and not c.wikidata_qid:
                        c.wikidata_qid = r["qid"]
                        stats["merged_fgo"] += 1
                else:
                    cid = f"wd:{r['qid']}"
                    session.add(Character(
                        id=cid, wiki_id=0, name=r["label"][:120],
                        mythology=proto_map[r["proto"]]["mythology"] or None,
                        description=r["desc"][:500], source="wikidata", wikidata_qid=r["qid"],
                        extra={"kind": "fictional", "media": media, "qid": r["qid"]}))
                    existing_by_qid[r["qid"]] = cid
                    existing_by_name.setdefault(norm, cid)
                    stats["new_chars"] += 1
                add_rel(cid, f"wp:{r['proto']}", origin="wikidata",
                        evidence=f'wikidata P144/P1074 → {r["proto"]}')
            else:
                wid = f"ww:{r['qid']}"
                if not session.get(Work, wid):
                    session.add(Work(
                        id=wid, name=r["label"][:250], kind=_work_kind(ct),
                        wikidata_qid=r["qid"], prototype_qid=r["proto"],
                        source="wikidata", extra={"desc": r["desc"][:300]}))
                    stats["works"] += 1
            per_proto[r["proto"]] = per_proto.get(r["proto"], 0) + 1
        session.commit()
    finally:
        session.close()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 个种子")
    parser.add_argument("--max-per-proto", type=int, default=40)
    parser.add_argument("--max-new", type=int, default=2000)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.time()
    wd = WikidataProvider()
    seeds = load_seeds(args.limit)
    seeds = await resolve_seeds(wd, seeds)
    if args.dry_run:
        for s in seeds[:20]:
            print(f"  {s['char_name']} → {s.get('prototype_label')} ({s['prototype_qid']})")
        return
    stats = await harvest(wd, seeds, args.max_per_proto, args.max_new)

    session = get_session()
    try:
        fts = rebuild_fts(session)
    finally:
        session.close()
    GraphService.instance().refresh()

    report = {"duration_sec": round(time.time() - t0, 1), **stats, "fts": fts}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    await wd.aclose()


if __name__ == "__main__":
    asyncio.run(main())
