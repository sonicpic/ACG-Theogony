"""同源角色雷达：原型 → 跨媒体化身矩阵 + 改编作品。"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from theogony.core.db import get_session
from theogony.core.graph import GraphService
from theogony.core.orm import Work

router = APIRouter(tags=["prototypes"])


class FgoIncarnation(BaseModel):
    id: str
    name: str
    className: str = ""
    imageUrl: str = ""


class OtherIncarnation(BaseModel):
    id: str
    name: str
    media: str = ""
    description: str = ""


class WorkItem(BaseModel):
    id: str
    name: str
    kind: str


class PrototypesResponse(BaseModel):
    items: list[dict]


@router.get("/prototypes", response_model=PrototypesResponse)
def list_prototypes():
    """全部原型及其化身（FGO/跨媒体）与改编作品，一次取全（量级 ~百）。"""
    snap = GraphService.instance().snapshot

    # DERIVED_FROM 是有向边（化身 → 原型），按 target 分组
    by_proto: dict[str, list[str]] = {}
    for src, dst, rtype, _conf in snap.edges:
        if rtype == "DERIVED_FROM":
            by_proto.setdefault(dst, []).append(src)

    session = get_session()
    try:
        works_by_qid: dict[str, list[WorkItem]] = {}
        for w in session.execute(select(Work).where(Work.prototype_qid.is_not(None))).scalars().all():
            works_by_qid.setdefault(w.prototype_qid, []).append(WorkItem(id=w.id, name=w.name, kind=w.kind))
    finally:
        session.close()

    items: list[dict] = []
    for cid, c in snap.characters.items():
        if c.class_name != "原型":
            continue
        fgo, others = [], []
        for src in by_proto.get(cid, []):
            s = snap.characters.get(src)
            if s is None:
                continue
            if s.source == "fgo":
                fgo.append(FgoIncarnation(id=s.id, name=s.name, className=s.class_name or "",
                                          imageUrl=s.image_url or "").model_dump())
            else:
                others.append(OtherIncarnation(
                    id=s.id, name=s.name,
                    media=(s.extra or {}).get("media", "other-media"),
                    description=(s.description or "")[:80]).model_dump())
        items.append({
            "id": cid,
            "name": c.name,
            "mythology": c.mythology or "",
            "qid": c.wikidata_qid or (c.extra or {}).get("qid", ""),
            "fgo": fgo,
            "others": others,
            "works": [w.model_dump() for w in works_by_qid.get(c.wikidata_qid or "", [])],
            "incarnationCount": len(fgo) + len(others),
            "worksCount": len(works_by_qid.get(c.wikidata_qid or "", [])),
        })
    items.sort(key=lambda x: -(x["incarnationCount"] + x["worksCount"]))
    return PrototypesResponse(items=items)
