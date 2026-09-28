"""语义嵌入层（可选）：为 RAG 提供向量召回，未配置时自动禁用。"""

from __future__ import annotations

import json

from openai import AsyncOpenAI
from sqlalchemy import text

from theogony.core.config import get_settings
from theogony.core.db import get_session


def _client() -> AsyncOpenAI | None:
    s = get_settings()
    if not (s.embeddings_api_key and s.embeddings_api_base and s.embeddings_model):
        return None
    return AsyncOpenAI(api_key=s.embeddings_api_key, base_url=s.embeddings_api_base)


async def embed_texts_async(texts: list[str]) -> list[list[float]]:
    client = _client()
    if client is None:
        raise RuntimeError("未配置嵌入服务（EMBEDDINGS_*）")
    s = get_settings()
    resp = await client.embeddings.create(model=s.embeddings_model, input=texts)
    return [item.embedding for item in resp.data]


def embed_texts(texts: list[str]) -> list[list[float]]:
    import asyncio

    return asyncio.run(embed_texts_async(texts))


def build_embeddings(batch_size: int = 32) -> int:
    """为全部角色构建嵌入（名称+体系+描述截断）。幂等：已存在且模型一致则跳过。"""
    s = get_settings()
    client = _client()
    if client is None:
        return 0
    import asyncio

    session = get_session()
    try:
        chars = session.execute(
            text("SELECT id, name, mythology, prototype, description FROM characters")
        ).fetchall()
        existing = {
            row[0]
            for row in session.execute(text("SELECT character_id FROM embeddings WHERE model = :m"), {"m": s.embeddings_model})
        }
        todo = [(r[0], f"{r[1]}｜{r[2] or ''}｜{r[3] or ''}｜{(r[4] or '')[:200]}") for r in chars if r[0] not in existing]
        count = 0
        for i in range(0, len(todo), batch_size):
            batch = todo[i : i + batch_size]
            vectors = asyncio.run(embed_texts_async([t for _, t in batch]))
            for (cid, _), vec in zip(batch, vectors, strict=False):
                session.execute(
                    text(
                        "INSERT OR REPLACE INTO embeddings (character_id, model, dim, vector) "
                        "VALUES (:cid, :model, :dim, :vec)"
                    ),
                    {"cid": cid, "model": s.embeddings_model, "dim": len(vec), "vec": json.dumps(vec)},
                )
                count += 1
            session.commit()
        return count
    finally:
        session.close()
