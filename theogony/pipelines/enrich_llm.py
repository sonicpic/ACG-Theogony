"""LLM 角色数据增强（异步并发版，DeepSeek / Luna 均可）。

- 结构化输出：JSON mode + Pydantic 校验，失败自动重试
- 并发 8 + 信号量限流，465 角色约 1 分钟
- 断点续传：已增强角色默认跳过（--force 强制重跑）
- 结果直接写 DB 并刷新 FTS

用法：
    uv run python -m theogony.pipelines.enrich_llm [--limit N] [--force] [--provider deepseek|luna]
"""

from __future__ import annotations

import argparse
import asyncio
import time
from datetime import UTC, datetime

from sqlalchemy import select

from theogony.core.db import rebuild_fts, session_scope
from theogony.core.enums import Mythology
from theogony.core.llm import chat_json, get_provider
from theogony.core.models import EnrichResult
from theogony.core.orm import Alias, Character
from theogony.core.seeding import build_aliases, normalize_region

ENRICH_PROMPT = """分析以下 Fate/Grand Order 角色，补充神话资料。角色信息：
- 名称: {name}
- 职阶: {char_class}
- 原型: {prototype}
- Wiki 地域: {region}

标准神话体系（region 必须精确匹配其中之一）：
{mythologies}

规则：
1. 现代虚构角色（如玛修）region 用"现代创作"；真实历史人物用"史实人物"
2. description 80-120 字：身份 + 主要神话事迹 + 在 FGO 中的特点
3. mythology_background 30-60 字的神话背景
4. alignment 用 FGO 阵营格式（如"秩序·善"）
5. noble_phantasms 列出代表宝具名（最多 3 个）
6. aliases 列出常见别名/真名/译名（最多 5 个）
7. 不确定的字段留空"""


async def enrich_one(provider, sem: asyncio.Semaphore, char: Character, force: bool) -> dict:
    async with sem:
        prompt = ENRICH_PROMPT.format(
            name=char.name,
            char_class=char.class_name or "未知",
            prototype=char.prototype or char.name,
            region=normalize_region(getattr(char, "_region_hint", "") or "") or char.mythology or "未知",
            mythologies="、".join(m.value for m in Mythology),
        )
        result = await chat_json(provider, EnrichResult, prompt, temperature=0.2, max_tokens=900)
        if result is None:
            return {"id": char.id, "name": char.name, "ok": False}
        region = normalize_region(result.region)
        if region not in Mythology._value2member_map_:
            region = region if region else (char.mythology or "")
        return {
            "id": char.id,
            "ok": True,
            "region": region,
            "data": result,
        }


async def run(limit: int | None, force: bool, provider_name: str | None, concurrency: int) -> None:
    provider = get_provider(provider_name)
    if provider is None:
        print("[✗] 未配置任何 LLM 提供方（.env: DEEPSEEK_API_KEY 或 LUNA_API_KEY）")
        return
    print(f"[*] 使用提供方: {provider.name} / 模型 {provider.model}")

    with session_scope() as session:
        query = select(Character).order_by(Character.wiki_id)
        chars = session.execute(query).scalars().all()
        todo = [c for c in chars if force or not c.enriched_at]
        if limit:
            todo = todo[:limit]
        # 把当前值带出 session（detached 对象访问属性会触发加载，先物化）
        payload = [
            {"id": c.id, "name": c.name, "class": c.class_name, "proto": c.prototype, "myth": c.mythology, "region_hint": ""}
            for c in todo
        ]
        print(f"[*] 待增强 {len(payload)}/{len(chars)} 个角色")

        sem = asyncio.Semaphore(concurrency)
        started = time.time()
        ok_count = 0
        fail_ids: list[str] = []
        results: list[dict] = []

        class _CharStub:
            pass

        tasks = []
        for p in payload:
            stub = _CharStub()
            stub.id, stub.name, stub.class_name, stub.prototype, stub.mythology = (
                p["id"], p["name"], p["class"], p["proto"], p["myth"]
            )
            tasks.append(enrich_one(provider, sem, stub, force))

        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            result = await coro
            results.append(result)
            if result["ok"]:
                ok_count += 1
            else:
                fail_ids.append(result["id"])
            if i % 20 == 0 or i == len(tasks):
                print(f"  … {i}/{len(tasks)} 成功 {ok_count}")

        # 写回
        by_id = {c.id: c for c in session.execute(select(Character)).scalars()}
        now = datetime.now(UTC)
        for result in results:
            if not result.get("ok"):
                continue
            c = by_id.get(result["id"])
            if not c:
                continue
            data: EnrichResult = result["data"]
            if result.get("region"):
                c.mythology = result["region"]
                c.myth_source = "llm"
            if data.description:
                c.description = data.description
            if data.mythology_background:
                c.mythology_background = data.mythology_background
            if data.alignment:
                c.alignment = data.alignment
            if data.gender:
                c.gender = data.gender
            if data.noble_phantasms:
                c.extra = {**(c.extra or {}), "noble_phantasms": data.noble_phantasms}
            c.enriched_at = now
            c.enrich_model = provider.model
            # 合并 LLM 别名
            existing = {a.alias for a in c.aliases}
            for alias in build_aliases(c.name, c.prototype, data.aliases or []):
                if alias not in existing:
                    session.add(Alias(character_id=c.id, alias=alias))
                    existing.add(alias)

        fts_count = rebuild_fts(session)
        print(f"[*] FTS 索引重建: {fts_count} 条")

    elapsed = time.time() - started
    print(f"[✓] 完成：成功 {ok_count}，失败 {len(fail_ids)}，耗时 {elapsed:.0f}s")
    if fail_ids:
        print(f"    失败示例: {fail_ids[:10]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM 角色数据增强")
    parser.add_argument("--limit", type=int, help="限制处理数量（测试用）")
    parser.add_argument("--force", action="store_true", help="重跑已增强角色")
    parser.add_argument("--provider", choices=["deepseek", "luna"])
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    asyncio.run(run(args.limit, args.force, args.provider, args.concurrency))


if __name__ == "__main__":
    main()
