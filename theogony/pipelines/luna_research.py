"""gpt-luna-5.6 联网研究管道：用检索增强补齐 LLM 知识盲区。

两种模式：
1. --character <名称|ID>：研究单个角色（抓取 wiki 资料 → 结构化入库）
2. --ask <问题>：自由研究问答（输出到终端）

需要 .env 配置 LUNA_API_KEY / LUNA_API_BASE。未配置时提示并退出。
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime

from sqlalchemy import select

from theogony.core.db import rebuild_fts, session_scope
from theogony.core.enums import Mythology
from theogony.core.llm import chat_json, get_provider, luna_research
from theogony.core.models import EnrichResult
from theogony.core.orm import Character
from theogony.core.seeding import normalize_region

RESEARCH_PROMPT = """请联网研究 Fate/Grand Order 角色「{name}」（原型: {prototype}）的资料，
优先参考 fgo.wiki（Mooncell）、维基百科等来源，然后严格输出以下 JSON：
- region: 所属神话体系（必须从：{mythologies} 中选择）
- description: 100-150 字简介（基于查证资料，注明关键事实）
- mythology_background: 30-60 字神话背景
- alignment: FGO 阵营（如"秩序·善"）
- gender: 男/女/未知
- noble_phantasms: 代表宝具名列表（≤3）
- aliases: 别名/真名列表（≤5）"""


async def research_character(name_or_id: str) -> None:
    provider = get_provider("luna")
    if provider is None:
        print("[✗] 未配置 LUNA_API_KEY / LUNA_API_BASE（.env），无法联网研究。")
        return

    with session_scope() as session:
        chars = session.execute(select(Character)).scalars().all()
        target = next(
            (c for c in chars if c.id == name_or_id or c.name == name_or_id or name_or_id in (c.prototype or "")),
            None,
        )
        if target is None:
            print(f"[✗] 找不到角色: {name_or_id}")
            return

        prompt = RESEARCH_PROMPT.format(
            name=target.name,
            prototype=target.prototype or target.name,
            mythologies="、".join(m.value for m in Mythology),
        )
        print(f"[*] 联网研究: {target.name} ...")
        # 先让 Luna 带工具研究，再结构化输出
        research_notes = await luna_research(provider, f"研究 FGO 角色「{target.name}」（原型 {target.prototype}）的出典、神话体系、阵营、代表宝具，列出要点与来源。")
        result = await chat_json(
            provider,
            EnrichResult,
            prompt + f"\n\n已查证的研究笔记：\n{research_notes[:4000]}",
            temperature=0.2,
        )
        if result is None:
            print("[✗] 结构化输出失败，保留原数据。")
            return

        region = normalize_region(result.region)
        if region in Mythology._value2member_map_:
            target.mythology = region
            target.myth_source = "wiki"
        if result.description:
            target.description = result.description
        if result.mythology_background:
            target.mythology_background = result.mythology_background
        if result.alignment:
            target.alignment = result.alignment
        if result.gender:
            target.gender = result.gender
        if result.noble_phantasms:
            target.extra = {**(target.extra or {}), "noble_phantasms": result.noble_phantasms}
        target.enriched_at = datetime.now(UTC)
        target.enrich_model = "gpt-luna-research"
        rebuild_fts(session)
        print(f"[✓] 已更新 {target.name}: region={target.mythology}")
        print(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))


async def ask(question: str) -> None:
    provider = get_provider("luna") or get_provider()
    if provider is None:
        print("[✗] 未配置任何 LLM 提供方。")
        return
    answer = await luna_research(provider, question)
    print(answer)


def main() -> None:
    parser = argparse.ArgumentParser(description="gpt-luna-5.6 联网研究")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--character", help="研究单个角色（名称或 ID）并入库")
    group.add_argument("--ask", help="自由研究问答")
    args = parser.parse_args()
    if args.character:
        asyncio.run(research_character(args.character))
    else:
        asyncio.run(ask(args.ask))


if __name__ == "__main__":
    main()
