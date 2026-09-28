"""路径探索端点（六度分隔）。"""

from __future__ import annotations

from fastapi import APIRouter

from theogony.api.deps import get_character_or_404
from theogony.core.graph import GraphService
from theogony.core.models import PathDTO

router = APIRouter(tags=["paths"])


@router.get("/paths", response_model=PathDTO)
def find_path(from_id: str, to_id: str, maxHops: int = 6):
    """from/to 为角色 ID（如 c1、c496）。"""
    get_character_or_404(from_id)
    get_character_or_404(to_id)
    gs = GraphService.instance()
    result = gs.shortest_path(from_id, to_id)
    if result["found"] and result["distance"] > maxHops:
        return {"found": False, "distance": 0, "nodes": [], "steps": []}
    return result
