"""Bangumi ACG 侧收割：原型别名 → 同名 ACG 角色 → 出演作品。

补充雷达的"ACG 化身"密度：Wikidata 反查偏欧美影视/美术，Bangumi 直接给出
动画/漫画/游戏里的同名改编角色及其作品（如 亚瑟王 → 各动画游戏里的亚瑟）。

链路（纯结构化 + 精确名匹配，零 LLM）：
  1. 原型（class_name=原型）→ Wikidata 全部别名（zh/ja/en 变体）
  2. 逐别名 Bangumi 角色搜索 → 归一化精确同名者为化身候选
  3. 候选 → 出演作品（subject type → kind）入 works + appearances
  4. 化身入库：与既有角色（含 FGO）按名合并，否则新建（bg:id）；
     DERIVED_FROM → 原型（origin=bangumi，名字精确匹配证据）

用法：
  python -u -m theogony.pipelines.harvest_bangumi --limit 8   # 试跑
  python -u -m theogony.pipelines.harvest_bangumi
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import unicodedata

from sqlalchemy import select

from theogony.core.db import get_session, init_db, rebuild_fts
from theogony.core.graph import GraphService
from theogony.core.orm import Alias, Appearance, Character, Relationship, Work
from theogony.providers.bangumi import BangumiProvider
from theogony.providers.wikidata import WikidataProvider

# Bangumi subject type → 作品 kind
_SUBJECT_KIND = {1: "novel", 2: "anime", 3: "manga", 4: "game", 6: "tv"}


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for ch in " \u3000·・.。'\"''\"·-‐–—_/／（）()〔〕[]":
        s = s.replace(ch, "")
    return s.lower()


def load_prototypes(limit: int | None) -> list[dict]:
    session = get_session()
    try:
        protos = session.execute(
            select(Character).where(Character.class_name == "原型")).scalars().all()
    finally:
        session.close()
    out = [{"id": c.id, "name": c.name, "qid": c.wikidata_qid or "",
            "mythology": c.mythology or ""} for c in sorted(protos, key=lambda x: x.id)]
    if limit:
        out = out[:limit]
    print(f"[prototypes] {len(out)} 个原型")
    return out


async def harvest(bg: BangumiProvider, wd: WikidataProvider, protos: list[dict],
                  max_chars_per_proto: int, max_total: int) -> dict:
    aliases_map = await wd.entity_aliases([p["qid"] for p in protos if p["qid"]])
    for p in protos:
        names = {p["name"]}
        for a in aliases_map.get(p["qid"], []):
            if 2 <= len(a) <= 30:
                names.add(a)
        p["search_names"] = sorted(names)[:8]  # 每原型至多 8 个搜索词

    stats = {"searches": 0, "candidates": 0, "new_chars": 0, "merged": 0,
             "works": 0, "appearances": 0, "relations": 0}
    init_db()
    session = get_session()
    try:
        name_index: dict[str, str] = {}
        for c in session.execute(select(Character)).scalars().all():
            name_index.setdefault(normalize_name(c.name), c.id)
        for a in session.execute(select(Alias)).scalars().all():
            name_index.setdefault(normalize_name(a.alias), a.character_id)

        def add_rel(src: str, dst: str, evidence: str) -> None:
            if session.execute(select(Relationship).where(
                    Relationship.source_id == src, Relationship.target_id == dst,
                    Relationship.type == "DERIVED_FROM")).scalar_one_or_none():
                return
            session.add(Relationship(
                source_id=src, target_id=dst, type="DERIVED_FROM", directed=True,
                confidence="verified", evidence=evidence[:400],
                origin="bangumi", status="approved"))
            stats["relations"] += 1

        for p in protos:
            if stats["new_chars"] + stats["merged"] >= max_total:
                break
            proto_keys = {normalize_name(n) for n in p["search_names"]}
            seen_bg: set[int] = set()
            picked = 0
            for term in p["search_names"]:
                if picked >= max_chars_per_proto:
                    break
                try:
                    hits = await bg.search_characters(term, limit=20)
                except Exception:
                    continue
                stats["searches"] += 1
                for h in hits:
                    if picked >= max_chars_per_proto or h["id"] in seen_bg:
                        continue
                    if normalize_name(h.get("name", "")) not in proto_keys:
                        continue  # 仅精确同名（归一化后），防"名字含原型"的误配
                    seen_bg.add(h["id"])
                    cid = name_index.get(normalize_name(h["name"]))
                    if cid:
                        c = session.get(Character, cid)
                        if c and "bangumi_id" not in (c.extra or {}):
                            c.extra = {**(c.extra or {}), "bangumi_id": h["id"]}
                            stats["merged"] += 1
                        add_rel(cid, p["id"], f'bangumi 精确同名 {h["name"]} (bg:{h["id"]})')
                    else:
                        cid = f"bg:{h['id']}"
                        session.add(Character(
                            id=cid, wiki_id=0, name=h["name"][:120],
                            mythology=p["mythology"] or None, source="bangumi",
                            description=(h.get("summary") or "")[:500],
                            extra={"kind": "fictional", "media": "acg", "bangumi_id": h["id"]}))
                        name_index[normalize_name(h["name"])] = cid
                        add_rel(cid, p["id"], f'bangumi 精确同名 {h["name"]} (bg:{h["id"]})')
                        stats["new_chars"] += 1
                    picked += 1
                    # 出演作品
                    try:
                        subjects = await bg.character_subjects(h["id"])
                    except Exception:
                        continue
                    for subj in subjects[:5]:
                        s_name = (subj.get("name") or "").strip()
                        if not s_name:
                            continue
                        wid = f"bgw:{subj['id']}"
                        if not session.get(Work, wid):
                            session.add(Work(
                                id=wid, name=s_name[:250],
                                kind=_SUBJECT_KIND.get(subj.get("type"), "other"),
                                source="bangumi",
                                extra={"bangumi_id": subj["id"]}))
                            stats["works"] += 1
                        if not session.execute(select(Appearance).where(
                                Appearance.character_id == cid,
                                Appearance.work_id == wid)).scalar_one_or_none():
                            session.add(Appearance(character_id=cid, work_id=wid, source="bangumi"))
                            stats["appearances"] += 1
            session.commit()
    finally:
        session.close()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--max-per-proto", type=int, default=6)
    parser.add_argument("--max-total", type=int, default=600)
    args = parser.parse_args()

    t0 = time.time()
    bg = BangumiProvider()
    wd = WikidataProvider()
    protos = load_prototypes(args.limit)
    stats = await harvest(bg, wd, protos, args.max_per_proto, args.max_total)

    session = get_session()
    try:
        rebuild_fts(session)
    finally:
        session.close()
    GraphService.instance().refresh()
    print(json.dumps({"duration_sec": round(time.time() - t0, 1), **stats}, ensure_ascii=False, indent=2))
    await bg.aclose()
    await wd.aclose()


if __name__ == "__main__":
    asyncio.run(main())
