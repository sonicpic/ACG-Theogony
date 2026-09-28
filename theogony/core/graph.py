"""内存图服务：子图构建 / BFS 路径 / Louvain 聚类 / 族谱抽取 / 统计 / 补全建议。"""

from __future__ import annotations

import hashlib
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import networkx as nx
from sqlalchemy import select

from theogony.core.db import get_session
from theogony.core.enums import (
    FAMILY_TYPES,
    MYTHOLOGY_GEO,
    RELATION_META,
    ReviewStatus,
)
from theogony.core.orm import Character, Relationship


@dataclass
class GraphSnapshot:
    characters: dict[str, Character] = field(default_factory=dict)
    name_index: dict[str, str] = field(default_factory=dict)  # 名称/别名 → id
    edges: list[tuple[str, str, str, str]] = field(default_factory=list)  # (src, dst, type, confidence)
    adjacency: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    loaded_at: float = 0.0


class GraphService:
    """单例图缓存（DB 变更后调用 refresh()）。"""

    _instance: GraphService | None = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.snapshot = GraphSnapshot()
        self.refresh()

    @classmethod
    def instance(cls) -> GraphService:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def refresh(self) -> None:
        session = get_session()
        try:
            chars = session.execute(select(Character)).scalars().all()
            rels = session.execute(
                select(Relationship).where(Relationship.status == ReviewStatus.APPROVED.value)
            ).scalars().all()
        finally:
            session.close()

        snap = GraphSnapshot(loaded_at=time.time())
        for c in chars:
            snap.characters[c.id] = c
            snap.name_index[c.name] = c.id
            if c.prototype:
                snap.name_index.setdefault(c.prototype, c.id)

        seen: set[tuple[str, str, str]] = set()
        for r in rels:
            if r.source_id == r.target_id:
                continue
            key = (r.source_id, r.target_id, r.type)
            rkey = (r.target_id, r.source_id, r.type)
            if key in seen or rkey in seen:
                continue
            if r.source_id not in snap.characters or r.target_id not in snap.characters:
                continue
            seen.add(key)
            snap.edges.append((r.source_id, r.target_id, r.type, r.confidence))
            snap.adjacency.setdefault(r.source_id, []).append((r.target_id, r.type, r.confidence))
            if not RELATION_META.get(r.type, {}).get("directed", True):
                snap.adjacency.setdefault(r.target_id, []).append((r.source_id, r.type, r.confidence))
            else:
                # 有向关系也允许反向遍历（回答"谁是我父母"）
                snap.adjacency.setdefault(r.target_id, []).append((r.source_id, r.type, r.confidence))

        self.snapshot = snap

    # ──────────────────────────────────────────
    # 视图构建
    # ──────────────────────────────────────────

    def degree(self, cid: str) -> int:
        return len({n for n, _, _ in self.snapshot.adjacency.get(cid, [])})

    def build_view(
        self,
        *,
        mythologies: list[str] | None = None,
        types: list[str] | None = None,
        classes: list[str] | None = None,
        search: str | None = None,
        gender: str | None = None,
        max_wiki_id: int | None = None,
        source: str | None = None,
        include_myth_nodes: bool = False,
        only_related: bool = False,
        ego_center: str | None = None,
        ego_hops: int = 1,
    ) -> dict:
        """按筛选条件构建子图（含派生神话节点，可选）。"""
        snap = self.snapshot
        myth_set = set(mythologies) if mythologies else None
        type_set = set(types) if types else None
        class_set = set(classes) if classes else None

        # 搜索命中集合（命中者及其邻居保留）
        search_ids: set[str] | None = None
        if search:
            search_ids = {cid for cid, c in snap.characters.items() if search in c.name or (c.prototype and search in c.prototype)}
            for cid in list(search_ids):
                for n, _, _ in snap.adjacency.get(cid, []):
                    search_ids.add(n)

        allowed_chars = {
            cid: c
            for cid, c in snap.characters.items()
            if (not myth_set or c.mythology in myth_set)
            and (not class_set or c.class_name in class_set)
            and (not gender or c.gender == gender)
            and (not max_wiki_id or c.wiki_id <= max_wiki_id)
            and (not source or c.source == source)
            and (not search_ids or cid in search_ids)
        }

        if ego_center and ego_center in snap.characters:
            keep = {ego_center}
            frontier = {ego_center}
            for _ in range(max(1, ego_hops)):
                nxt: set[str] = set()
                for cid in frontier:
                    for n, _, _ in snap.adjacency.get(cid, []):
                        if n not in keep:
                            nxt.add(n)
                keep |= nxt
                frontier = nxt
            allowed_chars = {cid: c for cid, c in allowed_chars.items() if cid in keep} or {
                ego_center: snap.characters[ego_center]
            }

        nodes_payload = []
        links_payload = []
        link_seen: set[tuple[str, str, str]] = set()
        degree_map: dict[str, int] = {}

        for src, dst, rtype, conf in snap.edges:
            if src not in allowed_chars or dst not in allowed_chars:
                continue
            if type_set and rtype not in type_set:
                continue
            key = (src, dst, rtype)
            rkey = (dst, src, rtype)
            if key in link_seen or rkey in link_seen:
                continue
            link_seen.add(key)
            links_payload.append(
                {
                    "source": src,
                    "target": dst,
                    "type": rtype,
                    "directed": RELATION_META.get(rtype, {}).get("directed", True),
                    "confidence": conf,
                }
            )
            degree_map[src] = degree_map.get(src, 0) + 1
            degree_map[dst] = degree_map.get(dst, 0) + 1

        linked_ids = set(degree_map)
        for cid, c in allowed_chars.items():
            if only_related and cid not in linked_ids:
                continue
            nodes_payload.append(
                {
                    "id": cid,
                    "name": c.name,
                    "kind": "character",
                    "mythology": c.mythology,
                    "className": c.class_name,
                    "imageUrl": c.image_url,
                    "degree": self.degree(cid),
                    "wikiId": c.wiki_id,
                }
            )

        # 派生神话节点
        if include_myth_nodes:
            by_myth: dict[str, list[str]] = {}
            for n in nodes_payload:
                m = n["mythology"] or "其他"
                by_myth.setdefault(m, []).append(n["id"])
            for myth, member_ids in by_myth.items():
                mid = f"m:{myth}"
                nodes_payload.append(
                    {
                        "id": mid,
                        "name": myth,
                        "kind": "myth",
                        "mythology": myth,
                        "className": "",
                        "imageUrl": "",
                        "degree": len(member_ids),
                        "wikiId": 0,
                    }
                )
                for cid in member_ids:
                    links_payload.append(
                        {"source": cid, "target": mid, "type": "BELONGS_TO", "directed": True, "confidence": "verified"}
                    )

        meta = {
            "nodeCount": len(nodes_payload),
            "linkCount": len(links_payload),
            "clusters": self.clusters(),
            "geo": {m: list(xy) for m, xy in MYTHOLOGY_GEO.items()},
        }
        return {"nodes": nodes_payload, "links": links_payload, "meta": meta}

    # ──────────────────────────────────────────
    # 路径探索（六度分隔）
    # ──────────────────────────────────────────

    def shortest_path(self, a: str, b: str, max_hops: int = 6) -> dict:
        snap = self.snapshot
        if a not in snap.characters or b not in snap.characters:
            return {"found": False, "distance": 0, "nodes": [], "steps": []}
        if a == b:
            return {
                "found": True,
                "distance": 0,
                "nodes": [self._node_payload(a)],
                "steps": [],
            }
        prev: dict[str, tuple[str, str] | None] = {a: None}
        queue: deque[str] = deque([a])
        while queue:
            cur = queue.popleft()
            for nxt, rtype, _ in snap.adjacency.get(cur, []):
                if nxt in prev:
                    continue
                prev[nxt] = (cur, rtype)
                if nxt == b:
                    return self._trace_path(prev, b)
                if len(prev) > 5000:
                    continue
                queue.append(nxt)
                if len(prev) > 20000:
                    return {"found": False, "distance": 0, "nodes": [], "steps": []}
        return {"found": False, "distance": 0, "nodes": [], "steps": []}

    def _trace_path(self, prev: dict, b: str) -> dict:
        path_ids: list[str] = []
        cursor: str | None = b
        while cursor:
            path_ids.append(cursor)
            step = prev.get(cursor)
            cursor = step[0] if step else None
        path_ids.reverse()
        steps = []
        for i in range(len(path_ids) - 1):
            rel = self._edge_label(path_ids[i], path_ids[i + 1])
            steps.append(
                {
                    "source": path_ids[i],
                    "target": path_ids[i + 1],
                    "type": rel[0],
                    "label": RELATION_META.get(rel[0], {}).get("label", rel[0]),
                }
            )
        return {
            "found": True,
            "distance": len(steps),
            "nodes": [self._node_payload(cid) for cid in path_ids],
            "steps": steps,
        }

    def _edge_label(self, a: str, b: str) -> tuple[str, str]:
        for src, dst, rtype, conf in self.snapshot.edges:
            if (src, dst) == (a, b) or (src, dst) == (b, a):
                return rtype, conf
        return "ALLY_OF", "low"

    def _node_payload(self, cid: str) -> dict:
        c = self.snapshot.characters[cid]
        return {
            "id": c.id,
            "name": c.name,
            "kind": "character",
            "mythology": c.mythology,
            "className": c.class_name,
            "imageUrl": c.image_url,
            "degree": self.degree(cid),
            "wikiId": c.wiki_id,
        }

    # ──────────────────────────────────────────
    # 聚类 / 族谱 / 建议 / 统计
    # ──────────────────────────────────────────

    def clusters(self) -> list[dict]:
        """Louvain 社区检测（只算角色-角色边）。"""
        snap = self.snapshot
        g = nx.Graph()
        for cid, c in snap.characters.items():
            g.add_node(cid, mythology=c.mythology or "其他")
        for src, dst, rtype, _ in snap.edges:
            if rtype == "BELONGS_TO":
                continue
            if g.has_edge(src, dst):
                g[src][dst]["weight"] += 1
            else:
                g.add_edge(src, dst, weight=1)
        try:
            communities = nx.algorithms.community.louvain_communities(g, seed=42, weight="weight")
        except Exception:
            communities = [set(g.nodes)]
        result = []
        for i, comm in enumerate(sorted(communities, key=len, reverse=True)[:40]):
            myth_count: dict[str, int] = {}
            for cid in comm:
                m = g.nodes[cid].get("mythology", "其他")
                myth_count[m] = myth_count.get(m, 0) + 1
            top = max(myth_count, key=myth_count.get) if myth_count else "其他"
            result.append(
                {"index": i, "size": len(comm), "topMythology": top, "members": sorted(comm)}
            )
        return result

    def family_tree(self, cid: str, max_gen: int = 3) -> dict:
        """抽取家族关系子图（父母/兄弟姐妹/配偶/恋人）。"""
        snap = self.snapshot
        if cid not in snap.characters:
            return {"center": None, "nodes": [], "links": []}

        keep = {cid}
        frontier = {cid}
        for _ in range(max_gen):
            nxt = set()
            for cur in frontier:
                for n, rtype, _ in snap.adjacency.get(cur, []):
                    if rtype in FAMILY_TYPES and n not in keep:
                        nxt.add(n)
            keep |= nxt
            frontier = nxt

        nodes = [self._node_payload(c) for c in keep if c in snap.characters]
        links = [
            {"source": s, "target": t, "type": rt, "directed": RELATION_META[rt]["directed"], "confidence": cf}
            for s, t, rt, cf in snap.edges
            if rt in FAMILY_TYPES and s in keep and t in keep
        ]
        return {"center": cid, "nodes": nodes, "links": links}

    def suggest_completions(self, limit: int = 20) -> list[dict]:
        """图谱补全建议：同神话体系 + 有共同邻居 + 尚无直连。"""
        snap = self.snapshot
        edge_set = {(s, t) for s, t, _, _ in snap.edges} | {(t, s) for s, t, _, _ in snap.edges}
        neighbors: dict[str, set[str]] = {}
        for s, t, rt, _ in snap.edges:
            if rt == "BELONGS_TO":
                continue
            neighbors.setdefault(s, set()).add(t)
            neighbors.setdefault(t, set()).add(s)

        suggestions = []
        ids = sorted(snap.characters)
        for i, a in enumerate(ids):
            myth_a = snap.characters[a].mythology
            if not myth_a or not neighbors.get(a):
                continue
            for b in ids[i + 1 :]:
                if (a, b) in edge_set:
                    continue
                if snap.characters[b].mythology != myth_a:
                    continue
                common = neighbors.get(a, set()) & neighbors.get(b, set())
                if len(common) >= 1:
                    score = len(common) * (2.0 if myth_a else 1.0)
                    suggestions.append(
                        {
                            "sourceId": a,
                            "targetId": b,
                            "commonNeighbors": sorted(common)[:6],
                            "sameMythology": True,
                            "score": round(score + len(common) * 0.1, 2),
                        }
                    )
        suggestions.sort(key=lambda x: -x["score"])
        return suggestions[:limit]

    def stats(self) -> dict:
        snap = self.snapshot
        session = get_session()
        try:
            total_rels = session.execute(select(Relationship)).scalars().all()
        finally:
            session.close()

        char_count = len(snap.characters)
        linked = set(snap.adjacency)
        myth_dist: dict[str, int] = {}
        class_dist: dict[str, int] = {}
        enriched = 0
        missing_myth = 0
        missing_desc = 0
        for c in snap.characters.values():
            m = c.mythology or "未归类"
            myth_dist[m] = myth_dist.get(m, 0) + 1
            if c.class_name:
                class_dist[c.class_name] = class_dist.get(c.class_name, 0) + 1
            if c.enriched_at:
                enriched += 1
            if not c.mythology:
                missing_myth += 1
            if not c.description:
                missing_desc += 1

        rel_dist: dict[str, int] = {}
        conf_dist: dict[str, int] = {}
        origin_dist: dict[str, int] = {}
        pending = 0
        approved = 0
        for r in total_rels:
            rel_dist[r.type] = rel_dist.get(r.type, 0) + 1
            conf_dist[r.confidence] = conf_dist.get(r.confidence, 0) + 1
            origin_dist[r.origin] = origin_dist.get(r.origin, 0) + 1
            if r.status == ReviewStatus.PENDING.value:
                pending += 1
            if r.status == ReviewStatus.APPROVED.value:
                approved += 1

        return {
            "characters": char_count,
            "relationships": len(total_rels),
            "approved": approved,
            "pending": pending,
            "enriched": enriched,
            "missingMythology": missing_myth,
            "missingDescription": missing_desc,
            "orphanNodes": char_count - len(linked),
            "relationDist": rel_dist,
            "confidenceDist": conf_dist,
            "mythologyDist": myth_dist,
            "classDist": class_dist,
            "originDist": origin_dist,
        }

    def subgraph_around(self, ids: list[str], hops: int = 1, cap: int = 80) -> dict:
        """以若干角色为中心抽 k-hop 子图（GraphRAG 上下文用）。"""
        snap = self.snapshot
        keep: set[str] = set()
        frontier = {i for i in ids if i in snap.characters}
        keep |= frontier
        for _ in range(hops):
            nxt: set[str] = set()
            for cid in frontier:
                for n, _, _ in snap.adjacency.get(cid, []):
                    if n not in keep:
                        nxt.add(n)
            keep |= nxt
            frontier = nxt
            if len(keep) >= cap:
                break
        keep = set(sorted(keep)[:cap])
        nodes = [self._node_payload(c) for c in keep if c in snap.characters]
        links = []
        for s, t, rt, cf in snap.edges:
            if s in keep and t in keep:
                links.append(
                    {"source": s, "target": t, "type": rt, "directed": RELATION_META.get(rt, {}).get("directed", True), "confidence": cf}
                )
        return {"nodes": nodes, "links": links, "meta": {}}

    def deterministic_id(self, seed_text: str, pool: list[str]) -> str:
        """确定性随机选择（每日猜角色等场景，按日期稳定）。"""
        digest = hashlib.sha256(seed_text.encode("utf-8")).hexdigest()
        return pool[int(digest[:8], 16) % len(pool)]
