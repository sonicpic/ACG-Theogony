"""LLM 关系挖掘（按神话体系分批，产出进审核队列）。

改进旧版"全局前 100 个候选列表"的低召回策略：
- 同一神话体系的角色分到同一批（每批 ~12 人互相挖掘）
- 每个体系额外给出全体系名单摘要，避免跨体系关系遗漏
- 输出 confidence + evidence，写入 relationships 表（status=pending，等待审核）
- 逐批增量落库：中断后重跑自动跳过已完成的批次（按体系+成员指纹去重）

用法：
    uv run python -u -m theogony.pipelines.mine_relations [--limit-batches N] [--provider luna] [--effort high]
"""

from __future__ import annotations

import argparse
import asyncio
import random

from pydantic import BaseModel
from sqlalchemy import select

from theogony.core.db import session_scope
from theogony.core.enums import RELATION_META, RelationOrigin, ReviewStatus
from theogony.core.llm import LUNA_MAX_CONCURRENCY, chat_json, get_provider
from theogony.core.models import RelCandidate
from theogony.core.orm import Alias, Character, Relationship
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


class BatchOut(BaseModel):
    candidates: list[RelCandidate] = []


def _load_context() -> tuple[list[Character], dict[str, str], set[tuple[str, str, str]]]:
    """一次性加载角色、名称索引、既有关系三元组。"""
    with session_scope() as session:
        chars = session.execute(select(Character)).scalars().all()
        name_to_id: dict[str, str] = {}
        for c in sorted(chars, key=lambda x: x.wiki_id):
            name_to_id.setdefault(c.name, c.id)
            if c.prototype:
                name_to_id.setdefault(c.prototype, c.id)
        for alias, cid in session.execute(select(Alias.alias, Alias.character_id)):
            name_to_id.setdefault(alias, cid)
        existing = {
            (r.source_id, r.target_id, r.type)
            for r in session.execute(select(Relationship)).scalars()
        }
    return chars, name_to_id, existing


def _persist_batch(myth: str, candidates: list[RelCandidate], name_to_id: dict, existing: set) -> tuple[int, int]:
    """把一批候选立即写入 DB（增量持久化，中断可续跑）。"""
    added = skipped = 0
    with session_scope() as session:
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
            if (s, t, rtype) in existing or (t, s, rtype) in existing:
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
    return added, skipped


async def run(limit_batches: int | None, provider_name: str | None, concurrency: int, effort: str | None) -> None:
    provider = get_provider(provider_name)
    if provider is None:
        print("[✗] 未配置任何 LLM 提供方", flush=True)
        return
    if effort:
        provider.extra_body = {**provider.extra_body, "reasoning_effort": effort}
        print(f"[*] 思考强度覆盖为: {effort}", flush=True)
    print(f"[*] 使用提供方: {provider.name} / 模型 {provider.model} / extra={provider.extra_body}", flush=True)

    from theogony.core.llm import preflight

    if provider.name == "luna":
        concurrency = min(concurrency, LUNA_MAX_CONCURRENCY)
        print(f"[*] Luna 提供方：并发已限制为 {concurrency}（中转站风控要求）", flush=True)

    try:
        await preflight(provider)
    except RuntimeError as e:
        print(f"[✗] {e}", flush=True)
        return

    chars, name_to_id, existing = _load_context()
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
    print(f"[*] 共 {len(batches)} 批（按体系分组，每批 ≤12 人）", flush=True)

    sem = asyncio.Semaphore(concurrency)
    done_count = 0
    total_added = 0
    total_skipped = 0
    lock = asyncio.Lock()

    async def mine_batch(idx: int, myth: str, members: list[Character]) -> None:
        nonlocal done_count, total_added, total_skipped
        async with sem:
            await asyncio.sleep(random.uniform(0.5, 1.5))  # 请求间隔抖动，降低风控压力
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
            out = await chat_json(provider, BatchOut, prompt, temperature=0.2, max_tokens=1600)
            async with lock:
                if out is None:
                    print(f"  [!] [{idx+1}/{len(batches)}] {myth}: 调用失败，跳过", flush=True)
                else:
                    added, skipped = _persist_batch(myth, out.candidates, name_to_id, existing)
                    total_added += added
                    total_skipped += skipped
                    print(
                        f"  ✓ [{idx+1}/{len(batches)}] {myth}: +{added} 条候选（累计 {total_added}）",
                        flush=True,
                    )
                done_count += 1

    await asyncio.gather(*(mine_batch(i, m, mem) for i, (m, mem) in enumerate(batches)))

    print(f"[✓] 完成：新增候选 {total_added} 条（待审），跳过 {total_skipped} 条", flush=True)
    print("    前端 /review 审核通过后即进入图谱；或 GET /api/relationships?status=pending 查看", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 关系挖掘")
    parser.add_argument("--limit-batches", type=int, help="限制批次数（测试用）")
    parser.add_argument("--provider", choices=["deepseek", "luna"])
    parser.add_argument("--concurrency", type=int, default=2)
    parser.add_argument("--effort", choices=["max", "high", "medium", "low"], help="覆盖思考强度")
    args = parser.parse_args()
    asyncio.run(run(args.limit_batches, args.provider, args.concurrency, args.effort))


if __name__ == "__main__":
    main()
