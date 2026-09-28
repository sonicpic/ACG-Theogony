"""数据质量看板端点。"""

from __future__ import annotations

from fastapi import APIRouter

from theogony.core.graph import GraphService
from theogony.core.models import StatsDTO

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsDTO)
def get_stats():
    return GraphService.instance().stats()
