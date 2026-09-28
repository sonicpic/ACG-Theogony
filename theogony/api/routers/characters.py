"""角色端点。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from theogony.api.deps import char_dto
from theogony.core.db import get_session
from theogony.core.enums import RELATION_META
from theogony.core.graph import GraphService
from theogony.core.models import CharacterDTO, CharacterListItem, RelationshipDTO
from theogony.core.orm import Alias, Character, Relationship

router = APIRouter(tags=["characters"])


@router.get("/characters", response_model=list[CharacterListItem])
def list_characters(
    mythology: str | None = None,
    className: str | None = None,
    gender: str | None = None,
    hasRelation: bool | None = None,
    search: str | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
):
    gs = GraphService.instance()
    session = get_session()
    try:
        q = select(Character).order_by(Character.wiki_id)
        if mythology:
            q = q.where(Character.mythology == mythology)
        if className:
            q = q.where(Character.class_name == className)
        if gender:
            q = q.where(Character.gender == gender)
        if search:
            q = q.where(Character.name.like(f"%{search}%"))
        chars = session.execute(q).scalars().all()
        items = []
        for c in chars:
            deg = gs.degree(c.id)
            if hasRelation is True and deg == 0:
                continue
            if hasRelation is False and deg > 0:
                continue
            items.append(
                CharacterListItem(
                    id=c.id,
                    name=c.name,
                    className=c.class_name,
                    mythology=c.mythology,
                    imageUrl=c.image_url,
                    degree=deg,
                    hasRelation=deg > 0,
                )
            )
        return items[offset : offset + limit]
    finally:
        session.close()


@router.get("/characters/meta/options")
def character_options():
    """筛选项元数据（职阶/体系/来源列表）。注意：必须在 /{character_id} 之前声明。"""
    session = get_session()
    try:
        classes = sorted({c for (c,) in session.execute(select(Character.class_name)) if c})
        myths = sorted({m for (m,) in session.execute(select(Character.mythology)) if m})
        sources = sorted({s for (s,) in session.execute(select(Character.source)) if s})
        return {"classes": classes, "mythologies": myths, "sources": sources}
    finally:
        session.close()


@router.get("/characters/{character_id}", response_model=CharacterDTO)
def get_character(character_id: str):
    session = get_session()
    try:
        char = session.get(Character, character_id)
        if char is None:
            raise HTTPException(404, f"角色不存在: {character_id}")
        aliases = [a.alias for a in session.execute(select(Alias).where(Alias.character_id == character_id)).scalars()]
        return char_dto(char, aliases)
    finally:
        session.close()


@router.get("/characters/{character_id}/relationships", response_model=list[RelationshipDTO])
def character_relationships(character_id: str, includePending: bool = False):
    session = get_session()
    try:
        gs = GraphService.instance()
        snap = gs.snapshot
        rows = (
            session.execute(
                select(Relationship).where(
                    (Relationship.source_id == character_id) | (Relationship.target_id == character_id)
                )
            )
            .scalars()
            .all()
        )
        name_map = {cid: c.name for cid, c in snap.characters.items()}
        result = []
        for r in rows:
            if not includePending and r.status != "approved":
                continue
            result.append(
                RelationshipDTO(
                    **{
                        "id": r.id,
                        "sourceId": r.source_id,
                        "targetId": r.target_id,
                        "type": r.type,  # type: ignore[arg-type]
                        "directed": r.directed,
                        "confidence": r.confidence,  # type: ignore[arg-type]
                        "evidence": r.evidence,
                        "origin": r.origin,  # type: ignore[arg-type]
                        "status": r.status,  # type: ignore[arg-type]
                        "sourceName": name_map.get(r.source_id, ""),
                        "targetName": name_map.get(r.target_id, ""),
                    }
                )
            )
        return result
    finally:
        session.close()


@router.get("/characters/{character_id}/family")
def character_family(character_id: str):
    gs = GraphService.instance()
    tree = gs.family_tree(character_id)
    if tree["center"] is None:
        raise HTTPException(404, f"角色不存在: {character_id}")
    labels = {t: m["label"] for t, m in RELATION_META.items()}
    for link in tree["links"]:
        link["label"] = labels.get(link["type"], link["type"])
    return tree


@router.get("/characters/{character_id}/ego")
def character_ego(character_id: str, hops: int = Query(default=1, ge=1, le=3)):
    gs = GraphService.instance()
    return gs.build_view(ego_center=character_id, ego_hops=hops)
