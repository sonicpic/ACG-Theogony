"""AniList 作品关系链收割：搜索匹配 Bangumi/Wikidata 作品 → 拉取续作/前传/衍生关系。

链路：
  1. 遍历库内 works（bangumi/wikidata 来源），用名称搜 AniList → 存 anilist_id
  2. 对已匹配作品拉 relations（SEQUEL/PREQUEL/SPIN_OFF/ALTERNATIVE/SIDE_STORY/PARENT）
  3. 新发现的作品（如续作不在库中）也建 Work 节点（anilist 来源）
  4. 建作品间关系（work_relations 表）

用法：
  python -u -m theogony.pipelines.harvest_work_relations --limit 10  # 试跑
  python -u -m theogony.pipelines.harvest_work_relations
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from sqlalchemy import select

from theogony.core.db import get_session, init_db
from theogony.core.graph import GraphService
from theogony.core.orm import Work, WorkRelation
from theogony.providers.anilist import AniListProvider

_SEARCH_QUERY = """
query ($s: String) {
  Page(page: 1, perPage: 1) {
    media(search: $s, type: ANIME) { id title { romaji native } format }
  }
}
"""

_RELATIONS_QUERY = """
query ($id: Int) {
  Media(id: $id) {
    id
    title { romaji native }
    relations {
      edges { relationType }
      nodes { id title { romaji native } format startDate { year } }
    }
  }
}
"""

# 收录的关系类型（排除 CHARACTER/OTHER 噪声）
_KEEP_RELATIONS = {"SEQUEL", "PREQUEL", "SPIN_OFF", "ALTERNATIVE", "SIDE_STORY", "PARENT"}

_FORMAT_KIND = {
    "TV": "anime", "TV_SHORT": "anime", "MOVIE": "film", "SPECIAL": "anime",
    "OVA": "anime", "ONA": "anime", "MUSIC": "other",
    "MANGA": "manga", "NOVEL": "novel", "LIGHT_NOVEL": "novel",
    "ONE_SHOT": "manga", "COMIC": "manga",
}


async def harvest(al: AniListProvider, limit: int | None) -> dict:
    session = get_session()
    stats = {"matched": 0, "unmatched": 0, "new_works": 0, "relations": 0, "dup": 0}
    try:
        works = session.execute(select(Work)).scalars().all()
        by_alid = {w.anilist_id: w for w in works if w.anilist_id}
        pending = [w for w in works if not w.anilist_id and w.source == "bangumi"]
        if limit:
            pending = pending[:limit]
        print(f"[works] 库内 {len(works)} 部（已匹配 {len(by_alid)}），待匹配 {len(pending)}")

        # ① 名称匹配 AniList
        for w in pending:
            d = await al.raw_query(_SEARCH_QUERY, {"s": w.name}, ttl=86400 * 30)
            ms = d.get("data", {}).get("Page", {}).get("media", [])
            if ms:
                w.anilist_id = ms[0]["id"]
                by_alid[ms[0]["id"]] = w
                stats["matched"] += 1
            else:
                stats["unmatched"] += 1
        session.commit()
        print(f"[match] 匹配 {stats['matched']} / 未匹配 {stats['unmatched']}")

        # ② 拉关系 + ③ 新作品入库 + ④ 关系入库
        matched = [w for w in session.execute(select(Work).where(Work.anilist_id.is_not(None))).scalars().all()]
        existing_rels = {(r.source_id, r.target_id, r.relation_type)
                         for r in session.execute(select(WorkRelation)).scalars().all()}
        all_work_ids = {w.id for w in session.execute(select(Work)).scalars().all()}

        for w in matched:
            d = await al.raw_query(_RELATIONS_QUERY, {"id": w.anilist_id}, ttl=86400 * 30)
            media = d.get("data", {}).get("Media", {})
            edges = media.get("relations", {}).get("edges", [])
            nodes = media.get("relations", {}).get("nodes", [])
            for edge, node in zip(edges, nodes, strict=False):
                rt = edge.get("relationType", "")
                if rt not in _KEEP_RELATIONS:
                    continue
                nid = node.get("id")
                if not nid:
                    continue
                # 新作品入库
                nid_str = f"alw:{nid}"
                if nid_str not in all_work_ids:
                    title = node.get("title", {}).get("romaji") or node.get("title", {}).get("native") or f"al:{nid}"
                    fmt = node.get("format") or ""
                    session.add(Work(
                        id=nid_str, name=title[:250],
                        kind=_FORMAT_KIND.get(fmt, "other"),
                        anilist_id=nid, source="anilist",
                        extra={"year": (node.get("startDate") or {}).get("year")}))
                    all_work_ids.add(nid_str)
                    stats["new_works"] += 1
                # PREQUEL 反转为 SEQUEL（统一方向：source → target 表示 target 是 source 的续作）
                src_id, dst_id = w.id, nid_str
                rel_type = rt
                if rt == "PREQUEL":
                    src_id, dst_id = nid_str, w.id
                    rel_type = "SEQUEL"
                key = (src_id, dst_id, rel_type)
                rkey = (dst_id, src_id, rel_type)
                if key in existing_rels or rkey in existing_rels:
                    stats["dup"] += 1
                    continue
                session.add(WorkRelation(source_id=src_id, target_id=dst_id, relation_type=rel_type))
                existing_rels.add(key)
                stats["relations"] += 1
        session.commit()
    finally:
        session.close()
    GraphService.instance().refresh()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    t0 = time.time()
    init_db()
    al = AniListProvider()
    al.min_interval = 2.5  # AniList 降级态 30/min → 保守
    stats = await harvest(al, args.limit)
    print(json.dumps({"duration_sec": round(time.time() - t0, 1), **stats}, ensure_ascii=False, indent=2))
    await al.aclose()


if __name__ == "__main__":
    asyncio.run(main())
