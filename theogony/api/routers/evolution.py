"""原型演化对比：同一原型的全部化身属性矩阵（性别/职阶/阵营/体系/作品）。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from theogony.core.db import get_session
from theogony.core.graph import GraphService
from theogony.core.orm import Appearance, Work

router = APIRouter(tags=["prototypes"])


class EvolutionRow(BaseModel):
    id: str
    name: str
    source: str  # fgo | wikidata | bangumi
    media: str = ""  # acg | other-media | ""
    className: str = ""
    gender: str = ""
    alignment: str = ""
    mythology: str = ""
    works: list[str] = []


class EvolutionResponse(BaseModel):
    prototype: dict
    rows: list[EvolutionRow]


@router.get("/prototypes/{pid}/evolution", response_model=EvolutionResponse)
def prototype_evolution(pid: str):
    """同一原型的化身属性对比矩阵（用户最初的产品愿景：改编程度差异）。"""
    snap = GraphService.instance().snapshot
    proto = snap.characters.get(pid)
    if proto is None or proto.class_name not in ("原型",):
        raise HTTPException(404, "原型不存在")

    # 化身 = 指向原型的 DERIVED_FROM 边的 source
    incarnations: list[str] = []
    for src, dst, rtype, _conf in snap.edges:
        if rtype == "DERIVED_FROM" and dst == pid:
            incarnations.append(src)

    session = get_session()
    try:
        works_by_char: dict[str, list[str]] = {}
        work_names = {w.id: w.name for w in session.execute(select(Work)).scalars().all()}
        for ap in session.execute(select(Appearance)).scalars().all():
            name = work_names.get(ap.work_id)
            if name:
                works_by_char.setdefault(ap.character_id, []).append(name)
    finally:
        session.close()

    rows = []
    for cid in incarnations:
        c = snap.characters.get(cid)
        if c is None:
            continue
        rows.append(EvolutionRow(
            id=c.id,
            name=c.name,
            source=c.source or "",
            media=(c.extra or {}).get("media", ""),
            className=c.class_name or "",
            gender=c.gender or "",
            alignment=c.alignment or "",
            mythology=c.mythology or "",
            works=works_by_char.get(cid, [])[:5],
        ))
    # FGO 化身优先（属性最全），其次按名称
    rows.sort(key=lambda r: (0 if r.source == "fgo" else 1, r.name))

    return EvolutionResponse(
        prototype={"id": pid, "name": proto.name,
                   "mythology": proto.mythology or "",
                   "qid": proto.wikidata_qid or ""},
        rows=rows,
    )
