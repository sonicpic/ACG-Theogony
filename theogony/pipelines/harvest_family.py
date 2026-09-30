"""Wikidata 神话家谱收割：从已有 Wikidata 锚点拉取家族关系（父/母/配偶/兄弟/子女）。

确定性数据（结构化属性，零 LLM）：
  P22 父 → PARENT_OF   P25 母 → PARENT_OF   P40 子女 → PARENT_OF
  P26 配偶 → SPOUSE_OF  P3373 兄弟姐妹 → SIBLING_OF

家族成员（克洛诺斯/瑞亚/尤瑟王/桂妮薇儿…）建为 Character 节点：
  class_name="神话人物"（区别于"原型"——不进雷达卡片，但进图谱与家谱树），
  mythology 继承自锚点角色。

用法：
  python -u -m theogony.pipelines.harvest_family --dry-run
  python -u -m theogony.pipelines.harvest_family
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

from sqlalchemy import select

from theogony.core.db import get_session, init_db, rebuild_fts
from theogony.core.graph import GraphService
from theogony.core.orm import Character, Relationship
from theogony.providers.wikidata import WikidataProvider

_FAMILY_SPARQL = """
SELECT ?anchor ?rel ?member WHERE {
  VALUES ?anchor { %s }
  { ?anchor wdt:P22 ?member BIND("P22" AS ?rel) }
  UNION { ?anchor wdt:P25 ?member BIND("P25" AS ?rel) }
  UNION { ?anchor wdt:P26 ?member BIND("P26" AS ?rel) }
  UNION { ?anchor wdt:P3373 ?member BIND("P3373" AS ?rel) }
  UNION { ?anchor wdt:P40 ?member BIND("P40" AS ?rel) }
} LIMIT 4000
"""

# (属性, 关系类型, anchor_is_source)  anchor_is_source: 属性主语是关系 source？
_PROP_MAP = {
    "P22": ("PARENT_OF", False),   # anchor 的父亲是 member → member PARENT_OF anchor
    "P25": ("PARENT_OF", False),
    "P40": ("PARENT_OF", True),    # anchor 的子女 → anchor PARENT_OF member
    "P26": ("SPOUSE_OF", True),
    "P3373": ("SIBLING_OF", True),
}


async def harvest(wd: WikidataProvider, dry_run: bool) -> dict:
    session = get_session()
    try:
        chars = session.execute(select(Character)).scalars().all()
        by_qid = {c.wikidata_qid: c for c in chars if c.wikidata_qid}
        anchors = [c for c in chars
                   if c.wikidata_qid and (
                       c.class_name in ("原型", "神话人物") or c.source == "fgo")]
        # 去重锚点 qid（多角色可能共享）
        anchor_map: dict[str, Character] = {}
        for c in anchors:
            anchor_map.setdefault(c.wikidata_qid, c)
        print(f"[anchors] {len(anchor_map)} 个 Wikidata 锚点（原型/带qid角色）")

        qids = sorted(anchor_map)
        rows: list[dict] = []
        for i in range(0, len(qids), 60):
            chunk = qids[i:i + 60]
            values = " ".join(f"wd:{q}" for q in chunk)
            d = await wd._get("https://query.wikidata.org/sparql",
                              params={"query": _FAMILY_SPARQL % values, "format": "json"},
                              headers={"Accept": "application/sparql-results+json"}, ttl=None)
            for b in d.get("results", {}).get("bindings", []):
                rows.append({
                    "anchor_qid": b["anchor"]["value"].rsplit("/", 1)[-1],
                    "rel": b["rel"]["value"],
                    "member_qid": b["member"]["value"].rsplit("/", 1)[-1],
                })
        # 每锚点至多 15 个家族成员（防赫拉克勒斯式子女洪水）
        from collections import Counter
        per_anchor: Counter = Counter()
        capped: list[dict] = []
        for r in rows:
            if per_anchor[r["anchor_qid"]] < 15:
                capped.append(r)
                per_anchor[r["anchor_qid"]] += 1
        rows = capped
        print(f"[family] 拉到 {len(rows)} 条家族关系（截断后）")

        member_qids = sorted({r["member_qid"] for r in rows} - set(by_qid))
        meta = await wd.labels_descriptions(member_qids) if member_qids else {}
        member_claims = await wd.resolve_claims(member_qids) if member_qids else {}
        p31s = sorted({p for cl in member_claims.values() for p in cl.get("p31", [])})
        p31_meta = await wd.labels_descriptions(p31s) if p31s else {}

        stats = {"members_new": 0, "members_fictional_skipped": 0, "rels": 0, "dup": 0}
        if dry_run:
            for r in rows[:15]:
                a = anchor_map.get(r["anchor_qid"])
                m = meta.get(r["member_qid"], {})
                print(f"  {a.name if a else r['anchor_qid']} --{_PROP_MAP[r['rel']][0]}--> {m.get('label', r['member_qid'])} ({r['rel']})")
            print(f"[dry-run] 将新建成员节点 ~{len(member_qids)}，关系 ~{len(rows)}")
            return stats

        init_db()
        for qid in member_qids:
            m = meta.get(qid, {})
            label = m.get("label") or qid
            # 门槛：必须是神话/历史人物（过滤木乃伊、纯虚构角色、现代人）
            cl = member_claims.get(qid, {})
            if not WikidataProvider.is_historic_or_mythic(cl, m.get("description", ""), p31_meta):
                stats["members_fictional_skipped"] += 1
                continue
            anchor_myth = None
            for r in rows:
                if r["member_qid"] == qid:
                    a = anchor_map.get(r["anchor_qid"])
                    if a:
                        anchor_myth = a.mythology
                        break
            session.add(Character(
                id=f"wd:{qid}", wiki_id=0, name=label[:120],
                class_name="神话人物", mythology=anchor_myth, source="wikidata",
                wikidata_qid=qid, description=(m.get("description") or "")[:500],
                extra={"kind": "myth-person", "qid": qid}))
            by_qid[qid] = None  # 占位（id 尚未提交，关系写入用 id 字符串）
            stats["members_new"] += 1

        def char_id_of(qid: str) -> str | None:
            if qid in anchor_map:
                return anchor_map[qid].id
            if f"wd:{qid}" in {c.id for c in session.new} or session.get(Character, f"wd:{qid}"):
                return f"wd:{qid}"
            return None

        existing = {(r.source_id, r.target_id, r.type) for r in
                    session.execute(select(Relationship)).scalars().all()}
        for r in rows:
            rtype, anchor_is_src = _PROP_MAP[r["rel"]]
            a = anchor_map.get(r["anchor_qid"])
            if not a:
                continue
            mid = char_id_of(r["member_qid"])
            if not mid or mid == a.id:
                continue
            src, dst = (a.id, mid) if anchor_is_src else (mid, a.id)
            key = (src, dst, rtype)
            rkey = (dst, src, rtype)
            if key in existing or rkey in existing:
                stats["dup"] += 1
                continue
            session.add(Relationship(
                source_id=src, target_id=dst, type=rtype,
                directed=(rtype == "PARENT_OF"), confidence="verified",
                evidence=f"wikidata:{r['rel']} 结构化家族属性", origin="wikidata",
                status="approved"))
            existing.add(key)
            stats["rels"] += 1
        session.commit()
        rebuild_fts(session)
    finally:
        session.close()
    GraphService.instance().refresh()
    return stats


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    t0 = time.time()
    wd = WikidataProvider()
    stats = await harvest(wd, args.dry_run)
    print(json.dumps({"duration_sec": round(time.time() - t0, 1), **stats}, ensure_ascii=False, indent=2))
    await wd.aclose()


if __name__ == "__main__":
    asyncio.run(main())
