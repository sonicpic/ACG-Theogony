"""FastAPI 应用工厂。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from theogony.api.routers import (
    ai,
    characters,
    exports,
    games,
    graph,
    paths,
    prototypes,
    proxy,
    relationships,
    search,
    stats,
)
from theogony.core.config import get_settings
from theogony.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # DB 为空时自动从 raw 种子（本地零配置可跑）
    from sqlalchemy import func, select

    from theogony.core.db import get_session
    from theogony.core.orm import Character
    from theogony.core.seeding import seed_from_raw

    session = get_session()
    try:
        count = session.execute(select(func.count(Character.id))).scalar() or 0
        if count == 0:
            stats = seed_from_raw(session)
            print(f"[auto-seed] {stats}")
    finally:
        session.close()
    from theogony.core.graph import GraphService

    GraphService.instance()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ACG Theogony API",
        version="2.0.0",
        description="ACG × 神话原型 关系知识图谱 API",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for router in (
        characters.router,
        relationships.router,
        graph.router,
        paths.router,
        search.router,
        stats.router,
        games.router,
        prototypes.router,
        ai.router,
        exports.router,
        proxy.router,
    ):
        app.include_router(router, prefix="/api")
    return app


app = create_app()
