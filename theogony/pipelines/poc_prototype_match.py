"""PoC：多源 ACG 角色 → Wikidata 原型匹配率验证。

回答一个问题：随机一批热门动画角色中，有多少能"零 LLM / 低成本"关联到
神话/历史原型？方法论（成本从低到高）：

  Tier A 结构化：角色名 → Wikidata 角色实体 → P144(based on)/P1074 链接 → 原型实体
                 （零推理，conf=1.0，method=wikidata_structured）
  Tier B 名称匹配：角色名/别名 → wbsearchentities → 命中"现实/神话人物"实体
                 （零推理，exact-label conf=0.7，method=name_match）

流程：AniList 人气动画批量收角色（去重）→ 每角色两轮实体搜索（原名+罗马音）
     → 候选 QID 汇总后 SPARQL 批量解析 P31/P144/P1074 → 分类统计 → 报告落盘。

用法：
  python -u -m theogony.pipelines.poc_prototype_match --chars 1000
  python -u -m theogony.pipelines.poc_prototype_match --limit 50   # 小样本试跑
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import unicodedata
from collections import Counter

from theogony.core.config import get_settings
from theogony.providers.anilist import AniListProvider
from theogony.providers.wikidata import WikidataProvider


def normalize_name(s: str) -> str:
    """名称归一化：NFKC（全半角）、去空白/中间点/引号、小写。"""
    s = unicodedata.normalize("NFKC", s or "")
    for ch in " \u3000·・.。'\"''\"·-‐–—_/／":
        s = s.replace(ch, "")
    return s.lower()


def name_variants(char: dict) -> list[tuple[str, str]]:
    """(名称, 语言) 列表：日文原名→ja 优先，罗马音→en。"""
    out: list[tuple[str, str]] = []
    if char.get("char_native"):
        out.append((char["char_native"].strip(), "ja"))
    if char.get("char_name"):
        out.append((char["char_name"].strip(), "en"))
    for alt in char.get("char_alt") or []:
        alt = (alt or "").strip()
        if len(alt) >= 2:
            out.append((alt, "ja" if _has_cjk(alt) else "en"))
    # 去重保序
    seen: set[str] = set()
    uniq = []
    for n, lang in out:
        k = normalize_name(n)
        if k and k not in seen:
            seen.add(k)
            uniq.append((n, lang))
    return uniq[:6]


def _has_cjk(s: str) -> bool:
    return any("\u3040" <= c <= "\u30ff" or "\u4e00" <= c <= "\u9fff" for c in s)


async def harvest(anilist: AniListProvider, target: int) -> list[dict]:
    """AniList 人气动画主要角色（按 char_id 去重）。"""
    chars: dict[int, dict] = {}
    page = 1
    while len(chars) < target and page <= 12:
        rows = await anilist.popular_media_characters(page, per_page=25, char_per_page=8)
        if not rows:
            break
        for r in rows:
            chars.setdefault(r["char_id"], r)
        page += 1
    out = list(chars.values())[:target]
    print(f"[harvest] AniList 热门动画角色（去重后）: {len(out)}")
    return out


async def search_stage(wd: WikidataProvider, chars: list[dict], concurrency: int = 4) -> dict:
    """每角色对名称变体做 wbsearchentities，汇总候选。"""
    sem = asyncio.Semaphore(concurrency)
    results: dict[int, dict] = {}

    async def one(char: dict) -> None:
        variants = name_variants(char)
        if not variants:
            results[char["char_id"]] = {"hits": [], "exact": set()}
            return
        hits: dict[str, dict] = {}
        exact: set[str] = set()
        norm_keys = {normalize_name(n) for n, _ in variants}
        async with sem:
            for name, lang in variants:
                try:
                    found = await wd.search_entities(name, language=lang, limit=10)
                except Exception:
                    continue
                for h in found:
                    rec = hits.setdefault(h["qid"], {**h, "langs": set()})
                    rec["langs"].add(lang)
                    if normalize_name(h["label"]) in norm_keys:
                        exact.add(h["qid"])
        results[char["char_id"]] = {
            "hits": [{**h, "langs": sorted(h["langs"])} for h in hits.values()],
            "exact": sorted(exact),
        }

    await asyncio.gather(*(one(c) for c in chars))
    return results


def classify(char: dict, search: dict, claims: dict[str, dict],
             target_meta: dict[str, dict], p31_meta: dict[str, dict]) -> dict:
    """Tier A 结构化（需角色名精确同 label + 原型目标为历史/神话人物）→ Tier B 名称匹配 → 未命中。"""
    hits = search["hits"]
    exact = set(search["exact"])
    variants_norm = {normalize_name(n) for n, _ in name_variants(char)}

    # Tier A：与角色名精确同 label 的候选实体，其 P144/P1074 目标为历史/神话人物
    for h in hits:
        if normalize_name(h["label"]) not in variants_norm:
            continue  # 命中的必须是这个角色本人（排除同名作品/其他角色）
        cl = claims.get(h["qid"], {})
        raw_targets = list(dict.fromkeys(cl.get("p144", []) + cl.get("p1074", [])))
        valid = [
            t for t in raw_targets
            if WikidataProvider.is_historic_or_mythic(
                claims.get(t, {}), target_meta.get(t, {}).get("description", ""), p31_meta)
        ]
        if valid:
            names = [f'{target_meta.get(t, {}).get("label", t)}' for t in valid]
            return {
                "char": char["char_name"], "native": char.get("char_native"),
                "media": char.get("media_title"), "method": "wikidata_structured",
                "char_qid": h["qid"], "prototype_qids": valid,
                "matched_name": " ⇐ ".join(names), "confidence": 1.0,
            }

    # Tier B：候选中有"历史/神话人物"实体（须为人类 Q5 或神话侧实体类）
    best = None
    for h in hits:
        cl = claims.get(h["qid"], {})
        if WikidataProvider.is_historic_or_mythic(cl, h.get("description", ""), p31_meta):
            is_exact = h["qid"] in exact or normalize_name(h["label"]) in variants_norm
            score = 0.7 if is_exact else 0.5
            if best is None or score > best["confidence"]:
                best = {
                    "char": char["char_name"], "native": char.get("char_native"),
                    "media": char.get("media_title"),
                    "method": "name_match_exact" if is_exact else "name_match_loose",
                    "char_qid": None, "prototype_qids": [h["qid"]],
                    "matched_name": f'{h["label"]}（{h.get("description", "")[:30]}）',
                    "confidence": score,
                }

    if best:
        return best
    return {
        "char": char["char_name"], "native": char.get("char_native"),
        "media": char.get("media_title"), "method": "unmatched",
        "char_qid": None, "prototype_qids": [],
        "matched_name": "", "confidence": 0.0,
    }


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chars", type=int, default=1000)
    parser.add_argument("--limit", type=int, default=None, help="小样本试跑")
    parser.add_argument("--concurrency", type=int, default=4)
    args = parser.parse_args()
    target = args.limit or args.chars

    t0 = time.time()
    anilist = AniListProvider()
    wd = WikidataProvider()

    chars = await harvest(anilist, target)

    print(f"[search] 实体搜索（变体×角色，并发 {args.concurrency}）…")
    search = await search_stage(wd, chars, concurrency=args.concurrency)

    all_qids = sorted({h["qid"] for s in search.values() for h in s["hits"]})
    print(f"[sparql] 候选实体 {len(all_qids)} 个，批量解析 P31/P144/P1074/P569 …")
    claims = await wd.resolve_claims(all_qids)

    # Tier A 二跳：精确同 label 候选的原型目标 → 取目标实体 claims 与 label/description
    target_ids: set[str] = set()
    for c in chars:
        variants_norm = {normalize_name(n) for n, _ in name_variants(c)}
        for h in search[c["char_id"]]["hits"]:
            if normalize_name(h["label"]) not in variants_norm:
                continue
            cl = claims.get(h["qid"], {})
            target_ids.update(cl.get("p144", []) + cl.get("p1074", []))
    target_ids -= set(claims)
    if target_ids:
        print(f"[sparql] Tier A 原型目标 {len(target_ids)} 个，解析属性与描述 …")
        claims.update(await wd.resolve_claims(sorted(target_ids)))
    target_meta = await wd.labels_descriptions(sorted(target_ids)) if target_ids else {}

    # P31 实体类的 label（神话生物/神祇/传奇人物等类名判定）
    p31_ids = sorted({p for cl in claims.values() for p in cl.get("p31", [])})
    p31_meta = await wd.labels_descriptions(p31_ids) if p31_ids else {}

    rows = [classify(c, search[c["char_id"]], claims, target_meta, p31_meta) for c in chars]

    # ── 统计 ──
    n = len(rows)
    methods = Counter(r["method"] for r in rows)
    matched = [r for r in rows if r["method"] != "unmatched"]
    report = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_sec": round(time.time() - t0, 1),
        "cohort": "AniList 热门动画主要角色（按人气倒序，char 去重）",
        "total": n,
        "any_wd_entity": sum(1 for s in search.values() if s["hits"]),
        "method_counts": dict(methods),
        "pct_structured": round(methods["wikidata_structured"] / n * 100, 1) if n else 0,
        "pct_name_exact": round(methods["name_match_exact"] / n * 100, 1) if n else 0,
        "pct_name_loose": round(methods["name_match_loose"] / n * 100, 1) if n else 0,
        "pct_matched_total": round(len(matched) / n * 100, 1) if n else 0,
        "samples_structured": [r for r in rows if r["method"] == "wikidata_structured"][:15],
        "samples_name_exact": [r for r in rows if r["method"] == "name_match_exact"][:15],
        "samples_unmatched": [r for r in rows if r["method"] == "unmatched"][:10],
    }
    out_file = get_settings().data_dir / "exports" / "poc_prototype_match_report.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n════ PoC 结果 ════")
    print(f"样本: {n} 角色（{report['cohort']}）")
    print(f"有任何 Wikidata 候选: {report['any_wd_entity']} ({report['any_wd_entity']/n*100:.1f}%)")
    for k, v in methods.items():
        print(f"  {k:20} {v:5}  ({v/n*100:.1f}%)")
    print(f"合计可低成本关联原型: {len(matched)} ({report['pct_matched_total']}%)")
    print(f"耗时 {report['duration_sec']}s；报告 → {out_file}")
    print("\n── 结构化样例 ──")
    for r in report["samples_structured"][:8]:
        print(f"  {r['char']} ({r['media']}) → {r['matched_name']} ⇒ {r['prototype_qids']}")
    print("── 名称精确匹配样例 ──")
    for r in report["samples_name_exact"][:8]:
        print(f"  {r['char']} ({r['media']}) → {r['matched_name']}")

    await anilist.aclose()
    await wd.aclose()


if __name__ == "__main__":
    asyncio.run(main())
