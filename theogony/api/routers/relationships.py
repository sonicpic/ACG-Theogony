"""关系端点 + 众包提交 + 审核工作流。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from theogony.api.deps import rel_dto, require_review_token
from theogony.core.db import get_session, session_scope
from theogony.core.enums import RELATION_META, RelationOrigin, ReviewStatus
from theogony.core.graph import GraphService
from theogony.core.models import RelationshipSubmit, ReviewDecision
from theogony.core.orm import Character, Relationship
from theogony.core.seeding import normalize_relationship

router = APIRouter(tags=["relationships"])


def _name_map(session) -> dict[str, str]:
    return {c.id: c.name for c in session.query(Character).all()}


@router.get("/relationships")
def list_relationships(
    status: str | None = None,
    origin: str | None = None,
    type: str | None = None,
    confidence: str | None = None,
    characterId: str | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = 0,
):
    session = get_session()
    try:
        q = session.query(Relationship)
        if status:
            q = q.filter(Relationship.status == status)
        if origin:
            q = q.filter(Relationship.origin == origin)
        if type:
            q = q.filter(Relationship.type == type)
        if confidence:
            q = q.filter(Relationship.confidence == confidence)
        if characterId:
            q = q.filter(
                (Relationship.source_id == characterId) | (Relationship.target_id == characterId)
            )
        rows = q.order_by(Relationship.id.desc()).all()
        total = len(rows)
        name_map = _name_map(session)
        return {
            "total": total,
            "items": [rel_dto(r, name_map) for r in rows[offset : offset + limit]],
        }
    finally:
        session.close()


@router.post("/relationships", status_code=201)
def submit_relationship(payload: RelationshipSubmit):
    """众包提交关系（进入审核队列）。"""
    normalized = normalize_relationship(payload.sourceId, payload.targetId, payload.type)
    if not normalized:
        raise HTTPException(422, f"无效的关系类型: {payload.type}")
    s, t, rtype = normalized
    with session_scope() as session:
        exists = (
            session.query(Relationship)
            .filter(
                Relationship.source_id == s,
                Relationship.target_id == t,
                Relationship.type == rtype,
            )
            .first()
        )
        if exists:
            raise HTTPException(409, "该关系已存在（或方向相反）")
        rel = Relationship(
            source_id=s,
            target_id=t,
            type=rtype,
            directed=RELATION_META[rtype].get("directed", True),
            confidence="medium",
            evidence=payload.evidence or f"用户 {payload.contributor} 提交",
            origin=RelationOrigin.USER.value,
            status=ReviewStatus.PENDING.value,
        )
        session.add(rel)
        session.flush()
        name_map = _name_map(session)
        return rel_dto(rel, name_map)


@router.get("/review/pending")
def review_pending(
    limit: int = Query(default=50, le=200),
    _: None = Depends(require_review_token),
):
    session = get_session()
    try:
        rows = (
            session.query(Relationship)
            .filter(Relationship.status == ReviewStatus.PENDING.value)
            .order_by(Relationship.id.desc())
            .limit(limit)
            .all()
        )
        name_map = _name_map(session)
        return {"total": len(rows), "items": [rel_dto(r, name_map) for r in rows]}
    finally:
        session.close()


@router.post("/review/{relationship_id}")
def review_decide(
    relationship_id: int,
    decision: ReviewDecision,
    _: None = Depends(require_review_token),
):
    with session_scope() as session:
        rel = session.get(Relationship, relationship_id)
        if rel is None:
            raise HTTPException(404, f"关系不存在: {relationship_id}")
        # approve 只能作用于待审；reject 还能撤销已批准（批量批准的安全阀）
        if decision.action == "approve" and rel.status != ReviewStatus.PENDING.value:
            raise HTTPException(409, f"该关系已处理（{rel.status}）")
        rel.status = (
            ReviewStatus.APPROVED.value if decision.action == "approve" else ReviewStatus.REJECTED.value
        )
        if decision.action == "approve":
            rel.confidence = "verified"
        if decision.note:
            rel.evidence = f"{rel.evidence}｜审核备注: {decision.note}"[:500]
        result = rel_dto(rel, _name_map(session))
    GraphService.instance().refresh()
    return result


@router.post("/review/batch")
def review_batch(
    decisions: dict[str, str],
    _: None = Depends(require_review_token),
):
    """批量审核：{"<id>": "approve"|"reject", ...}（reject 可撤销已批准项）"""
    approved, rejected, missing = 0, 0, 0
    with session_scope() as session:
        for rid_str, action in decisions.items():
            rel = session.get(Relationship, int(rid_str))
            if rel is None or (action == "approve" and rel.status != ReviewStatus.PENDING.value):
                missing += 1
                continue
            if action == "approve":
                rel.status = ReviewStatus.APPROVED.value
                rel.confidence = "verified"
                approved += 1
            elif action == "reject":
                rel.status = ReviewStatus.REJECTED.value
                rejected += 1
    GraphService.instance().refresh()
    return {"approved": approved, "rejected": rejected, "skipped": missing}
