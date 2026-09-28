"""混合检索：FTS5 词法（中文+拼音前缀）+ 可选语义向量。"""

from __future__ import annotations

import re

from pypinyin import lazy_pinyin
from sqlalchemy import text

from theogony.core.db import get_session
from theogony.core.orm import Character


def pinyin_of(text: str) -> str:
    if not text:
        return ""
    return " ".join(lazy_pinyin(text))


def _tokenize(query: str) -> list[str]:
    """中文按 2 字滑窗 + 连续拉丁/数字串，构造 FTS 前缀查询。"""
    tokens: list[str] = []
    for latin in re.findall(r"[A-Za-z0-9]+", query):
        tokens.append(latin.lower())
    cjk = re.findall(r"[\u4e00-\u9fff]+", query)
    for seg in cjk:
        if len(seg) <= 2:
            tokens.append(seg)
        else:
            tokens.extend(seg[i : i + 2] for i in range(len(seg) - 1))
    return tokens


def fts_search(session, query: str, limit: int = 20) -> list[tuple[str, float]]:
    """FTS5 BM25 检索，返回 (character_id, score)，分值越小越相关。"""
    tokens = _tokenize(query)
    if not tokens:
        return []
    match_expr = " OR ".join(f'"{t}"*' for t in tokens[:12])
    sql = text(
        "SELECT character_id, bm25(fts_characters, 1.0, 2.0, 1.5, 1.0, 0.5, 1.2, 1.2) AS score "
        "FROM fts_characters WHERE fts_characters MATCH :m "
        "ORDER BY score LIMIT :lim"
    )
    try:
        rows = session.execute(sql, {"m": match_expr, "lim": limit}).fetchall()
    except Exception:
        rows = []
    if not rows:
        # 回退：名称/别名 LIKE
        like = f"%{query.strip()}%"
        rows = (
            session.execute(
                text(
                    "SELECT f.character_id, 10.0 FROM fts_characters f "
                    "WHERE f.name LIKE :l OR f.aliases LIKE :l OR f.name_py LIKE :l "
                    "LIMIT :lim"
                ),
                {"l": like, "lim": limit},
            ).fetchall()
        )
    return [(r[0], float(r[1])) for r in rows]


def semantic_available() -> bool:
    from theogony.core.config import get_settings

    s = get_settings()
    return bool(s.embeddings_api_key and s.embeddings_api_base and s.embeddings_model)


def semantic_search(session, query: str, limit: int = 20) -> list[tuple[str, float]]:
    """向量相似检索（未配置嵌入服务时返回空）。"""
    if not semantic_available():
        return []
    from theogony.core.semantic import embed_texts

    try:
        qvec = embed_texts([query])[0]
    except Exception:
        return []
    rows = session.execute(
        text("SELECT character_id, vector FROM embeddings")
    ).fetchall()
    scored: list[tuple[str, float]] = []
    import json as _json

    for cid, vec_json in rows:
        try:
            vec = _json.loads(vec_json)
        except _json.JSONDecodeError:
            continue
        dot = sum(a * b for a, b in zip(qvec, vec, strict=False))
        na = sum(a * a for a in qvec) ** 0.5 or 1.0
        nb = sum(b * b for b in vec) ** 0.5 or 1.0
        scored.append((cid, dot / (na * nb)))
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


def hybrid_search(query: str, limit: int = 10) -> tuple[list[tuple[str, float]], bool]:
    """词法 + 语义融合（语义可用时权重 0.4）。返回 ([(id, score)], semantic_used)。"""
    session = get_session()
    try:
        lex = fts_search(session, query, limit=limit * 2)
        sem = semantic_search(session, query, limit=limit * 2) if semantic_available() else []
        if not lex and not sem:
            # 最后回退：名称前缀
            rows = (
                session.query(Character)
                .filter(Character.name.like(f"%{query.strip()}%"))
                .limit(limit)
                .all()
            )
            return [(c.id, 0.0) for c in rows], False

        combined: dict[str, float] = {}
        max_lex = max((s for _, s in lex), default=1.0) or 1.0
        for cid, score in lex:
            combined[cid] = combined.get(cid, 0.0) + 0.6 * (1.0 / (1.0 + score / max_lex))
        if sem:
            for cid, score in sem:
                combined[cid] = combined.get(cid, 0.0) + 0.4 * max(score, 0.0)
        ranked = sorted(combined.items(), key=lambda kv: -kv[1])[:limit]
        return ranked, bool(sem)
    finally:
        session.close()
