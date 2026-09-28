"""LLM 关系挖掘（按神话体系分批，产出进审核队列）。

改进旧版"全局前 100 个候选列表"的低召回策略：
- 同一神话体系的角色分到同一批（每批 ~12 人互相挖掘）
- 每个体系额外给出全体系名单摘要，避免跨体系关系遗漏
- 输出 confidence + evidence，写入 relationships 表（status=pending，等待审核）

用法：
    uv run python -m theogony.pipelines.mine_relations [--limit-batches N] [--provider deepseek|luna]
"""

from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import select

from theogony.core.db import session_scope
from theogony.core.enums import RELATION_META, RelationOrigin, ReviewStatus
from theogony.core.llm import chat_json, get_provider
from theogony.core.models import RelCandidate
from theogony.core.orm import Character, Relationship
from theogony.core.seeding import normalize_relationship

MINE_PROMPT = """你是全球神话关系专家。以下是同一神话体系（{myth}）内的 FGO 角色列表：

{batch_members}

同体系其他角色（可跨批建立关系）：{others}

任务：找出「成员列表内部」以及「成员与同体系其他角色」之间真实存在的神话/传说/FGO 剧情关系。
只返回高置信度（high）或中置信度（medium）的关系；宁缺毋滥，没有则返回空数组。

可用关系类型：{types}
（注意方向：PARENT_OF 的 source 是父母；MASTER_OF 的 source 是主人；MENTOR_OF 的 source 是师傅）

输出 JSON：{{"candidates": [{{"source_name": "...", "target_name": "...", "relationship": "...", "confidence": "high|medium", "evidence": "≤20字依据"}}]}}
名称必须与列表完全一致。"""


async def run(limit_batches: int | None, provider_name: str | None, concurrency: int) -> None:
    provider = get_provider(provider_name)
    if provider is None:
        print("[✗] 未配置任何 LLM 提供方")
        return
    print(f"[*] 使用提供方: {provider.name} / 模型 {provider.model}")

    with session_scope() as session:
        chars = session.execute(select(Character)).scalars().all()
        by_myth: dict[str, list[Character]] = {}
        for c in chars:
            if c.mythology and c.mythology != "其他":
                by_myth.setdefault(c.mythology, []).append(c)

        batches: list[tuple[str, list[Character]]] = []
        for myth, members in sorted(by_myth.items(), key=lambda kv: -len(kv[1])):
            for i in range(0, len(members), 12):
                batches.append((myth, members[i : i + 12]))
        if limit_batches:
            batches = batches[:limit_batches]
        print(f"[*] 共 {len(batches)} 批（按体系分组，每批 ≤12 人）")

        sem = asyncio.Semaphore(concurrency)
        all_results: list[tuple[str, list[RelCandidate]]] = []

        async def mine_batch(myth: str, members: list[Character]) -> None:
            async with sem:
                member_names = sorted({m.name for m in members})
                others = sorted(
                    {c.name for c in by_myth.get(myth, []) if c.name not in member_names}
                )[:60]
                prompt = MINE_PROMPT.format(
                    myth=myth,
                    batch_members="\n".join(f"- {m.name}（原型: {m.prototype}）" for m in members),
                    others="、".join(others) if others else "（无）",
                    types="、".join(RELATION_META),
                )

                class BatchOut(__import__("pydantic").BaseModel):
                    candidates: list[RelCandidate] = []

                out = await chat_json(provider, BatchOut, prompt, temperature=0.2, max_tokens=1600)
                if out:
                    all_results.append((myth, out.candidates))
                    print(f"  ✓ [{myth}] {len(out.candidates)} 条候选")

        await asyncio.gather(*(mine_batch(m, mem) for m, mem in batches))

        # 名称 → id 解析（含别名）
        name_to_id: dict[str, str] = {}
        for c in chars:
            name_to_id[c.name] = c.id
            if c.prototype:
                name_to_id.setdefault(c.prototype, c.id)
        from theogony.core.orm import Alias

        for alias, cid in session.execute(select(Alias.alias, Alias.character_id)):
            name_to_id.setdefault(alias, cid)

        existing = {
            (r.source_id, r.target_id, r.type)
            for r in session.execute(select(Relationship)).scalars()
        }
        existing_rev = {(t, s, t_) for s, t, t_ in existing}

        added, skipped = 0, 0
        for myth, candidates in all_results:
            for cand in candidates:
                src = name_to_id.get(cand.source_name.strip())
                dst = name_to_id.get(cand.target_name.strip())
                if not src or not dst or src == dst:
                    skipped += 1
                    continue
                normalized = normalize_relationship(src, dst, cand.relationship)
                if not normalized:
                    skipped += 1
                    continue
                s, t, rtype = normalized
                if (s, t, rtype) in existing or (t, s, rtype) in existing_rev:
                    skipped += 1
                    continue
                existing.add((s, t, rtype))
                session.add(
                    Relationship(
                        source_id=s,
                        target_id=t,
                        type=rtype,
                        directed=RELATION_META[rtype].get("directed", True),
                        confidence=cand.confidence if cand.confidence in ("high", "medium", "low") else "medium",
                        evidence=(cand.evidence or "")[:200],
                        origin=RelationOrigin.LLM.value,
                        status=ReviewStatus.PENDING.value,
                    )
                )
                added += 1

    print(f"[✓] 新增候选关系 {added} 条（进入审核队列），跳过 {skipped} 条")
    print("    前端 /review 审核通过后即进入图谱；或 GET /api/relationships?status=pending 查看")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 关系挖掘")
    parser.add_argument("--limit-batches", type=int, help="限制批次数（测试用）")
    parser.add_argument("--provider", choices=["deepseek", "luna"])
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()
    asyncio.run(run(args.limit_batches, args.provider, args.concurrency))


if __name__ == "__main__":
    main()
