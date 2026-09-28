"""图端点：子图 / 聚类 / 图谱刷新。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from theogony.core.graph import GraphService
from theogony.core.models import GraphDTO

router = APIRouter(tags=["graph"])


@router.get("/graph", response_model=GraphDTO)
def get_graph(
    mythologies: list[str] | None = Query(default=None),
    types: list[str] | None = Query(default=None),
    classes: list[str] | None = Query(default=None),
    gender: str | None = None,
    search: str | None = None,
    onlyRelated: bool = False,
    includeMythNodes: bool = False,
    egoCenter: str | None = None,
    egoHops: int = Query(default=1, ge=1, le=3),
    maxWikiId: int | None = Query(default=None, ge=0),
    source: str | None = None,
):
    gs = GraphService.instance()
    return gs.build_view(
        mythologies=mythologies,
        types=types,
        classes=classes,
        gender=gender,
        search=search,
        only_related=onlyRelated,
        include_myth_nodes=includeMythNodes,
        ego_center=egoCenter,
        ego_hops=egoHops,
        max_wiki_id=maxWikiId,
        source=source,
    )


@router.get("/graph/clusters")
def get_clusters():
    gs = GraphService.instance()
    return {"clusters": gs.clusters()}


@router.post("/graph/refresh")
def refresh_graph():
    gs = GraphService.instance()
    gs.refresh()
    return {"ok": True, "nodes": len(gs.snapshot.characters), "edges": len(gs.snapshot.edges)}
