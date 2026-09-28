"""API 公共依赖与 DTO 转换。"""

from __future__ import annotations

from fastapi import Header, HTTPException

from theogony.core.config import get_settings
from theogony.core.db import get_session
from theogony.core.graph import GraphService
from theogony.core.orm import Character, Relationship


def char_dto(c: Character, aliases: list[str] | None = None) -> dict:
    gs = GraphService.instance()
    return {
        "id": c.id,
        "wikiId": c.wiki_id,
        "name": c.name,
        "aliases": aliases or [],
        "className": c.class_name,
        "prototype": c.prototype,
        "mythology": c.mythology,
        "description": c.description,
        "mythologyBackground": c.mythology_background,
        "alignment": c.alignment,
        "gender": c.gender,
        "imageUrl": c.image_url,
        "detailUrl": c.detail_url,
        "source": c.source,
        "extra": c.extra or {},
        "degree": gs.degree(c.id),
    }


def rel_dto(r: Relationship, name_map: dict[str, str] | None = None) -> dict:
    name_map = name_map or {}
    return {
        "id": r.id,
        "sourceId": r.source_id,
        "targetId": r.target_id,
        "type": r.type,
        "directed": r.directed,
        "confidence": r.confidence,
        "evidence": r.evidence,
        "origin": r.origin,
        "status": r.status,
        "sourceName": name_map.get(r.source_id, r.source_id),
        "targetName": name_map.get(r.target_id, r.target_id),
    }


def get_character_or_404(character_id: str) -> Character:
    session = get_session()
    try:
        char = session.get(Character, character_id)
        if char is None:
            raise HTTPException(404, f"角色不存在: {character_id}")
        return char
    finally:
        session.close()


def require_review_token(x_review_token: str | None = Header(default=None)) -> None:
    token = get_settings().review_token
    if token and x_review_token != token:
        raise HTTPException(403, "无效的审核令牌（X-Review-Token）")


def status_of(r: Relationship) -> str:
    return r.status
