"use client";

/**
 * Sigma.js (WebGL) 全局力导向图。
 * - FA2 同步布局（位置按节点缓存，避免反复重排）
 * - 神话/聚类着色、地理布局模式、选中邻居高亮、路径高亮、RAG 子图高亮
 */

import { useEffect, useMemo, useRef } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import { api } from "@/lib/api";
import type { GraphDTO, GraphNode } from "@/lib/types";
import { CLUSTER_PALETTE, MYTH_NODE_COLOR, mythColor, relColor } from "@/lib/constants";
import { highlightSets, useGraphView } from "@/lib/store";

// 跨渲染的节点位置缓存（保持布局稳定）
const positionCache = new Map<string, { x: number; y: number }>();

function hashJitter(seed: string, scale = 0.12): [number, number] {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0;
  return [((h & 0xffff) / 0xffff - 0.5) * scale, (((h >>> 16) & 0xffff) / 0xffff - 0.5) * scale];
}

export function SigmaGraph({ data }: { data: GraphDTO }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);

  const viewMode = useGraphView((s) => s.viewMode);
  const colorBy = useGraphView((s) => s.colorBy);
  const geo = data.meta.geo || {};

  // 聚类着色映射
  const clusterColor = useMemo(() => {
    const map = new Map<string, string>();
    data.meta.clusters?.forEach((c) => {
      const color = CLUSTER_PALETTE[c.index % CLUSTER_PALETTE.length];
      c.members.forEach((m) => map.set(m, color));
    });
    return map;
  }, [data.meta.clusters]);

  // 建图 + 渲染器
  useEffect(() => {
    if (!containerRef.current || !data.nodes.length) return;

    const graph = new Graph({ multi: false, type: "directed" });
    for (const node of data.nodes) {
      if (graph.hasNode(node.id)) continue;
      let pos = positionCache.get(node.id);
      if (!pos) {
        if (viewMode === "geo" && node.kind === "character") {
          const anchor = geo[node.mythology || "其他"] || [0.5, 0.5];
          const [jx, jy] = hashJitter(node.id);
          pos = { x: (anchor[0] + jx) * 100, y: (anchor[1] + jy) * 100 };
        } else {
          pos = { x: Math.random() * 50 - 25, y: Math.random() * 50 - 25 };
        }
        positionCache.set(node.id, pos);
      }
      const isMyth = node.kind === "myth";
      graph.addNode(node.id, {
        label: node.name,
        size: isMyth ? Math.min(11, 5.5 + Math.log2(node.degree + 1)) : 4.5 + Math.sqrt(node.degree) * 2.2,
        color: isMyth ? MYTH_NODE_COLOR : mythColor(node.mythology),
        x: pos.x,
        y: pos.y,
        nodeData: node,
      });
    }
    for (const link of data.links) {
      const sid = typeof link.source === "string" ? link.source : (link.source as never as GraphNode).id;
      const tid = typeof link.target === "string" ? link.target : (link.target as never as GraphNode).id;
      if (!graph.hasNode(sid) || !graph.hasNode(tid)) continue;
      try {
        graph.addEdge(sid, tid, { color: relColor(link.type), size: 1, type: link.directed ? "arrow" : "line" });
      } catch {
        // 平行边：忽略
      }
    }

    if (viewMode !== "geo") {
      forceAtlas2.assign(graph, {
        iterations: 120,
        settings: {
          barnesHutOptimize: true,
          gravity: 0.06,
          scalingRatio: 18,
          slowDown: 8,
          linLogMode: false,
        },
      });
      graph.forEachNode((nid, attrs) => positionCache.set(nid, { x: attrs.x, y: attrs.y }));
    }

    const sigma = new Sigma(graph, containerRef.current, {
      allowInvalidContainer: true,
      minCameraRatio: 0.05,
      maxCameraRatio: 12,
      labelRenderedSizeThreshold: 7,
      labelFont: "system-ui, 'Microsoft YaHei', sans-serif",
      labelColor: { color: "#d4d4d8" },
      labelGridCellSize: 90,
      renderEdgeLabels: false,
      defaultEdgeType: "line",
      zIndex: true,
      stagePadding: 24,
    });
    sigmaRef.current = sigma;
    graphRef.current = graph;

    // 交互
    const store = useGraphView;
    sigma.on("clickNode", ({ node }) => store.getState().select(node));
    sigma.on("enterNode", ({ node }) => {
      store.getState().hover(node);
      containerRef.current!.style.cursor = "pointer";
    });
    sigma.on("leaveNode", () => {
      store.getState().hover(null);
      containerRef.current!.style.cursor = "default";
    });
    sigma.on("clickStage", () => store.getState().select(null));
    sigma.on("clickEdge", ({ edge }) => {
      const [s, t] = graph.extremities(edge);
      store.getState().setPath(s, t, null); // 便捷：点边设为路径起止
      void api.paths(s, t).then((r) => store.getState().setPath(s, t, r));
    });

    // 相机聚焦
    const unsub = store.subscribe((state, prev) => {
      if (state.focusId && state.focusId !== prev.focusId) {
        const attrs = graph.getNodeAttributes(state.focusId);
        const camera = sigma.getCamera();
        camera.animate({ x: attrs.x, y: attrs.y, ratio: Math.min(camera.ratio, 1.6) }, { duration: 600 });
      }
    });

    return () => {
      unsub();
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, viewMode]);

  // 着色切换（不重建布局）
  useEffect(() => {
    const graph = graphRef.current;
    if (!graph) return;
    graph.forEachNode((nid, attrs) => {
      const node = attrs.nodeData as GraphNode;
      if (node.kind === "myth") {
        graph.setNodeAttribute(nid, "color", MYTH_NODE_COLOR);
        return;
      }
      graph.setNodeAttribute(
        nid,
        "color",
        colorBy === "cluster" ? clusterColor.get(nid) || mythColor(node.mythology) : mythColor(node.mythology)
      );
    });
    sigmaRef.current?.refresh({ skipIndexation: false });
  }, [colorBy, clusterColor]);

  // 高亮 reducer（选择/路径/RAG）
  useEffect(() => {
    const graph = graphRef.current;
    const sigma = sigmaRef.current;
    if (!graph || !sigma) return;

    const neighborIds = new Set<string>();
    const sel = useGraphView.getState().selectedId;
    if (sel) {
      try {
        graph.forEachNeighbor(sel, (n) => neighborIds.add(n));
      } catch {
        /* node filtered out */
      }
    }

    sigma.setSetting("nodeReducer", (node, attrs) => {
      const state = useGraphView.getState();
      const { primary, secondary } = highlightSets(state);
      if (primary.size === 0 && secondary.size === 0) return attrs;
      if (state.selectedId === node || primary.has(node)) {
        return { ...attrs, zIndex: 2, highlighted: true };
      }
      if (neighborIds.has(node) || secondary.has(node)) {
        return { ...attrs, zIndex: 1 };
      }
      return { ...attrs, color: "#27272a", label: null, zIndex: 0 };
    });
    sigma.setSetting("edgeReducer", (edge, attrs) => {
      const state = useGraphView.getState();
      const { primary, pathEdges } = highlightSets(state);
      if (primary.size === 0) return attrs;
      const [s, t] = graph.extremities(edge);
      const onPath = pathEdges.has(`${s}>${t}`) || pathEdges.has(`${t}>${s}`);
      const touchesSel = state.selectedId === s || state.selectedId === t;
      if (onPath) return { ...attrs, color: "#f59e0b", size: 3.2 };
      if (touchesSel) return { ...attrs, color: "#fbbf24", size: 2.2 };
      return { ...attrs, hidden: true };
    });
    sigma.refresh();
  });

  // 导出画布句柄（PNG）
  useEffect(() => {
    (window as unknown as Record<string, unknown>).__theogonyExportPng = () => {
      const sigma = sigmaRef.current as unknown as { toCanvas?: () => HTMLCanvasElement } | null;
      if (sigma?.toCanvas) return sigma.toCanvas();
      const canvas = containerRef.current?.querySelector("canvas");
      return canvas ?? null;
    };
  }, []);

  return <div ref={containerRef} className="absolute inset-0" />;
}
