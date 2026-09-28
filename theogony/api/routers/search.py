"""搜索端点：FTS5 + 拼音 + 可选语义混合检索。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from theogony.api.deps import char_dto
from theogony.core.db import get_session
from theogony.core.models import SearchHitDTO, SearchResponseDTO
from theogony.core.orm import Character
from theogony.core.search import hybrid_search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponseDTO)
def search(q: str = Query(min_length=1), limit: int = Query(default=10, le=50)):
    ranked, semantic_used = hybrid_search(q, limit=limit)
    session = get_session()
    try:
        hits = []
        for cid, score in ranked:
            char = session.get(Character, cid)
            if char is None:
                continue
            dto = char_dto(char)
            hits.append(
                SearchHitDTO(
                    character={
                        "id": dto["id"],
                        "name": dto["name"],
                        "className": dto["className"],
                        "mythology": dto["mythology"],
                        "imageUrl": dto["imageUrl"],
                        "degree": dto["degree"],
                        "hasRelation": dto["degree"] > 0,
                    },
                    score=round(score, 4),
                    matchedOn="semantic+fts" if semantic_used else "fts",
                )
            )
        return SearchResponseDTO(query=q, semantic=semantic_used, hits=hits)
    finally:
        session.close()
