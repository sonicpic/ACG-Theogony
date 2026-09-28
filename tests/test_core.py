"""核心算法与 API 冒烟测试（基于真实种子数据）。"""

from __future__ import annotations

import os

os.environ.setdefault("THEOGONY_TEST", "1")

import pytest
from fastapi.testclient import TestClient

from theogony.core.config import get_settings
from theogony.core.db import init_db, session_scope
from theogony.core.graph import GraphService
from theogony.core.nlq import rule_parse
from theogony.core.seeding import seed_from_raw


@pytest.fixture(scope="session", autouse=True)
def seeded_db(tmp_path_factory):
    """测试库：独立 SQLite，自动种子。"""
    settings = get_settings()
    db_file = tmp_path_factory.mktemp("db") / "test.db"
    settings.db_path = db_file
    init_db()
    with session_scope() as session:
        seed_from_raw(session, preserve_reviews=False)
    GraphService._instance = None  # 重置单例以加载测试库
    yield settings


@pytest.fixture(scope="session")
def client(seeded_db):
    from theogony.api.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


# ── 图算法 ──────────────────────────────────────────

def test_graph_loaded(seeded_db):
    gs = GraphService.instance()
    assert len(gs.snapshot.characters) >= 400
    assert len(gs.snapshot.edges) >= 5


def test_shortest_path(seeded_db):
    gs = GraphService.instance()
    snap = gs.snapshot
    ids = sorted(snap.characters)
    a, b = ids[0], ids[-1]
    result = gs.shortest_path(a, a)
    assert result["found"]
    # 任意两点 BFS 不崩溃
    gs.shortest_path(a, b)


def test_path_api(client):
    graph = client.get("/api/graph").json()
    assert graph["nodes"], "图不应为空"
    nid = graph["nodes"][0]["id"]
    resp = client.get("/api/paths", params={"from_id": nid, "to_id": nid})
    assert resp.status_code == 200
    assert resp.json()["found"] is True


def test_clusters(seeded_db):
    clusters = GraphService.instance().clusters()
    assert isinstance(clusters, list)
    assert all("members" in c for c in clusters)


def test_family_tree(seeded_db):
    gs = GraphService.instance()
    snap = gs.snapshot
    # 找一个有家族关系的角色
    target = None
    for src, dst, rtype, _ in snap.edges:
        if rtype in ("PARENT_OF", "SPOUSE_OF", "SIBLING_OF"):
            target = src
            break
    if target:
        tree = gs.family_tree(target)
        assert tree["center"] == target
        assert tree["nodes"]


# ── 搜索 / NLQ ──────────────────────────────────────

def test_search_api(client):
    resp = client.get("/api/search", params={"q": "阿尔托莉雅"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["hits"], "应能搜到阿尔托莉雅"


def test_search_pinyin(client):
    resp = client.get("/api/search", params={"q": "mashu"})
    assert resp.status_code == 200


def test_nlq_rules():
    filters = rule_parse("显示希腊神话里的父子关系")
    assert "希腊神话" in filters.get("mythologies", [])
    assert "PARENT_OF" in filters.get("types", [])
    filters2 = rule_parse("北欧的敌对关系和配偶")
    assert "北欧神话" in filters2.get("mythologies", [])
    assert "ENEMY_OF" in filters2["types"]
    assert "SPOUSE_OF" in filters2["types"]


def test_nlq_api(client):
    resp = client.post("/api/ai/nlq", json={"query": "日本神话的师徒关系"})
    assert resp.status_code == 200
    data = resp.json()
    assert "日本神话" in data.get("mythologies", [])
    assert "MENTOR_OF" in data.get("types", [])


# ── 关系/审核流 ─────────────────────────────────────

def test_relationship_flow(client):
    graph = client.get("/api/graph").json()
    chars = [n for n in graph["nodes"] if n["kind"] == "character"]
    assert len(chars) >= 2
    a, b = chars[0]["id"], chars[1]["id"]
    # 提交（众包）
    resp = client.post(
        "/api/relationships",
        json={"sourceId": a, "targetId": b, "type": "ALLY_OF", "evidence": "测试提交", "contributor": "pytest"},
    )
    assert resp.status_code == 201
    rel_id = resp.json()["id"]
    # 审核队列可见
    pending = client.get("/api/review/pending").json()
    assert any(item["id"] == rel_id for item in pending["items"])
    # 批准
    decision = client.post(f"/api/review/{rel_id}", json={"action": "approve"})
    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"
    # 图刷新后计入
    client.post("/api/graph/refresh")
    graph2 = client.get("/api/graph").json()
    assert graph2["meta"]["linkCount"] >= graph["meta"]["linkCount"]


# ── 游戏 ────────────────────────────────────────────

def test_daily_game(client):
    daily = client.get("/api/games/daily").json()
    assert daily["date"]
    assert daily["clues"]
    guess = client.post("/api/games/daily/guess", json={"guess": "绝不存在的角色名xyz"})
    assert guess.status_code == 200
    assert guess.json()["correct"] is False
    reveal = client.post("/api/games/daily/reveal").json()
    correct = client.post("/api/games/daily/guess", json={"guess": reveal["answerId"]})
    assert correct.json()["correct"] is True


# ── 其余端点冒烟 ────────────────────────────────────

def test_characters_endpoints(client):
    options = client.get("/api/characters/meta/options").json()
    assert options["classes"]
    listing = client.get("/api/characters", params={"limit": 5}).json()
    assert len(listing) == 5
    cid = listing[0]["id"]
    detail = client.get(f"/api/characters/{cid}").json()
    assert detail["name"]
    rels = client.get(f"/api/characters/{cid}/relationships").json()
    assert isinstance(rels, list)
    family = client.get(f"/api/characters/{cid}/family")
    assert family.status_code == 200


def test_stats(client):
    stats = client.get("/api/stats").json()
    assert stats["characters"] >= 400
    assert "relationDist" in stats


def test_graph_filters(client):
    resp = client.get(
        "/api/graph",
        params={"mythologies": ["不存在的神话"], "onlyRelated": "true"},
    )
    assert resp.status_code == 200
    resp2 = client.get("/api/graph", params={"includeMythNodes": "true"})
    assert any(n["kind"] == "myth" for n in resp2.json()["nodes"])


def test_ai_ask_offline(client):
    """无 LLM Key 时应返回纯图回答（不 500）。"""
    resp = client.post("/ai/ask".replace("/ai", "/api/ai"), json={"question": "玛修是谁？"})
    assert resp.status_code == 200
    assert resp.json()["engine"] in ("graph", "deepseek", "luna")


def test_suggest(client):
    resp = client.get("/api/ai/suggest", params={"limit": 5})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_exports(client):
    graphml = client.get("/api/export/graphml")
    assert graphml.status_code == 200 and "graphml" in graphml.text
    csv_data = client.get("/api/export/csv")
    assert csv_data.status_code == 200 and "source_name" in csv_data.text
