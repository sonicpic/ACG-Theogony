"use client";

/**
 * Sigma.js (WebGL) 图谱渲染 —— 视觉与动效重做版。
 *
 * - FA2 主线程活布局：加载后星云式有机聚拢（入场动画），静置后自动停
 * - 贝塞尔曲线边（@sigma/edge-curve），归属边呈大弧度环绕枢纽
 * - 节点可拖拽（preventSigmaDefault 阻断相机联动），拖拽即时生效
 * - 悬停浮卡（头像+信息）、选中邻居高亮、路径高亮、RAG 子图高亮
 * - 力导向 ↔ 神话星系 两种布局间 700ms 缓动变形
 */

import { useEffect, useMemo, useRef, useState } from "react";
import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import Sigma from "sigma";
import EdgeCurveProgram from "@sigma/edge-curve";
import { api } from "@/lib/api";
import type { GraphDTO, GraphNode } from "@/lib/types";
import { imgProxy } from "@/lib/types";
import { CLUSTER_PALETTE, MYTH_NODE_COLOR, RELATION_META, mythColor, relColor } from "@/lib/constants";
import { highlightSets, useGraphView } from "@/lib/store";

// ──────────────────────────────────────────────
// 工具
// ──────────────────────────────────────────────

const easeInOutCubic = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

/** 悬停浮卡：节点卡 或 边关系卡 */
type HoverTooltip =
  | { x: number; y: number; node: GraphNode; edge?: undefined }
  | { x: number; y: number; edge: { label: string; from: string; to: string }; node?: undefined };

// 布局静置后的位置缓存：重建 Sigma 时复用（保证拾取与坐标系一致）
const settledPositions = new Map<string, { x: number; y: number }>();
let stableMode = false;

function hash32(seed: string): number {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** 星系半径（与 galaxyPositions 的 2.4*sqrt(i+1) 同构） */
const galaxyRadius = (count: number) => 2.6 * Math.sqrt(count + 1) + 2;

/** 神话锚点斥力松弛：推开距离 = 双方星系半径之和（避免星系互相穿插） */
function relaxAnchors(geo: Record<string, [number, number]>, counts: Map<string, number>): Record<string, [number, number]> {
  const names = Object.keys(geo);
  const pos = new Map(names.map((m) => [m, [...geo[m]] as [number, number]]));
  for (let iter = 0; iter < 80; iter++) {
    for (let i = 0; i < names.length; i++) {
      for (let j = i + 1; j < names.length; j++) {
        const a = pos.get(names[i])!;
        const b = pos.get(names[j])!;
        const need = (galaxyRadius(counts.get(names[i]) || 5) + galaxyRadius(counts.get(names[j]) || 5)) / 90;
        const dx = b[0] - a[0];
        const dy = b[1] - a[1];
        const d = Math.hypot(dx, dy) || 0.001;
        if (d < need) {
          const push = (need - d) / 2;
          const ux = (dx / d) * push;
          const uy = (dy / d) * push;
          a[0] -= ux; a[1] -= uy;
          b[0] += ux; b[1] += uy;
        }
      }
    }
  }
  const out: Record<string, [number, number]> = {};
  pos.forEach((v, k) => (out[k] = v));
  return out;
}

/** 神话星系布局：每个体系一个螺旋星系（黄金角散布，半径 ∝ √人数） */
function galaxyPositions(data: GraphDTO): Map<string, { x: number; y: number }> {
  const byMyth0 = new Map<string, number>();
  for (const n of data.nodes) {
    if (n.kind !== "character") continue;
    const m = n.mythology || "其他";
    byMyth0.set(m, (byMyth0.get(m) || 0) + 1);
  }
  const anchors = relaxAnchors(data.meta.geo || {}, byMyth0);
  const G = 90;
  const result = new Map<string, { x: number; y: number }>();
  const byMyth = new Map<string, GraphNode[]>();
  for (const n of data.nodes) {
    if (n.kind !== "character") continue;
    const m = n.mythology || "其他";
    if (!byMyth.has(m)) byMyth.set(m, []);
    byMyth.get(m)!.push(n);
  }
  for (const [myth, members] of byMyth) {
    const anchor = anchors[myth] || [0.5, 0.85];
    const cx = anchor[0] * G;
    const cy = anchor[1] * G;
    const phase = (hash32(myth) % 628) / 100;
    members.forEach((n, i) => {
      const r = 2.6 * Math.sqrt(i + 1);
      const angle = i * 2.399963 + phase;
      result.set(n.id, { x: cx + Math.cos(angle) * r, y: cy + Math.sin(angle) * r * 0.92 });
    });
  }
  for (const n of data.nodes) {
    if (n.kind === "myth") {
      const anchor = anchors[n.name] || [0.5, 0.85];
      result.set(n.id, { x: anchor[0] * G, y: anchor[1] * G });
    }
  }
  return result;
}

const FA2_SETTINGS = {
  linLogMode: true,
  outboundAttractionDistribution: true,
  adjustSizes: true,
  edgeWeightInfluence: 0.6,
  scalingRatio: 2.2,
  gravity: 2.0, // 向心重力：净收缩趋势，入场即"星云聚拢"且快速收敛（低重力会持续膨胀）
  slowDown: 2.2,
  barnesHutOptimize: true,
} as const;

// ──────────────────────────────────────────────
// 主组件
// ──────────────────────────────────────────────

export function SigmaGraph({ data }: { data: GraphDTO }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sigmaRef = useRef<Sigma | null>(null);
  const graphRef = useRef<Graph | null>(null);
  const layoutRafRef = useRef<number | null>(null);
  const rafRef = useRef<number | null>(null);
  const hoverEdgeRef = useRef<string | null>(null);
  const centeringRef = useRef(false);
  const viewModeRef = useRef<string>("force");
  const tooltipLiveRef = useRef(false);

  const [tooltip, setTooltip] = useState<HoverTooltip | null>(null);

  const clusterColor = useMemo(() => {
    const map = new Map<string, string>();
    data.meta.clusters?.forEach((c) => {
      const color = CLUSTER_PALETTE[c.index % CLUSTER_PALETTE.length];
      c.members.forEach((m) => map.set(m, color));
    });
    return map;
     
  }, [data.meta.clusters]);

  // ── 建图 + 渲染器（仅数据变化时重建）──
  useEffect(() => {
    if (!containerRef.current || !data.nodes.length) return;
    viewModeRef.current = useGraphView.getState().viewMode;
    const graph = new Graph({ multi: false, type: "directed" });
    const start = viewModeRef.current === "geo" ? galaxyPositions(data) : null;

    for (const node of data.nodes) {
      if (graph.hasNode(node.id)) continue;
      const isMyth = node.kind === "myth";
      let pos = start?.get(node.id) || settledPositions.get(node.id);
      if (!pos) {
        const i = hash32(node.id) % 9973;
        const r = 2.0 * Math.sqrt(i + 1); // 撒开：初始取景框即覆盖布局活动期，FA2 向心聚拢成入场动画
        const ang = i * 2.399963;
        pos = { x: Math.cos(ang) * r, y: Math.sin(ang) * r };
      }
      graph.addNode(node.id, {
        label: node.name,
        size: isMyth ? 9 + Math.log2(node.degree + 1) * 1.6 : 3.6 + Math.sqrt(node.degree) * 2.4,
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
        graph.addEdge(sid, tid, {
          type: "curved",
          color: link.type === "BELONGS_TO" ? "#1c2130" : relColor(link.type),
          size: link.type === "BELONGS_TO" ? 0.5 : 1.5,
          curvature: link.type === "BELONGS_TO" ? 0.5 : 0.2,
          relLabel: link.type === "BELONGS_TO" ? "归属" : RELATION_META[link.type]?.label || link.type,
        });
      } catch {
        /* 平行边忽略 */
      }
    }

    const sigma = new Sigma(graph, containerRef.current, {
      allowInvalidContainer: true,
      minCameraRatio: 0.02,
      maxCameraRatio: 14,
      enableEdgeEvents: true,
      renderEdgeLabels: false,
      labelFont: "system-ui, 'Microsoft YaHei', sans-serif",
      labelColor: { color: "#cbd5e1" },
      labelWeight: "500",
      labelRenderedSizeThreshold: 15,
      labelGridCellSize: 140,
      edgeProgramClasses: { curved: EdgeCurveProgram },
      defaultEdgeType: "curved",
      zIndex: true,
      stagePadding: 32,
    });
    sigmaRef.current = sigma;
    graphRef.current = graph;

    /** 静置：保存位置 → bump 纪元触发 Sigma 重建（拾取恢复一致） */
    function saveAndReinstance() {
      normalizePositions();
      graph.forEachNode((n, a) => settledPositions.set(n, { x: a.x, y: a.y }));
      store.getState().bumpLayoutEpoch();
    }

    function fitCamera(duration = 900) {
      // Sigma v3 相机 x/y 是归一化取景空间坐标：(0.5,0.5)=画面中心，(0,0)=取景框角落
      void sigma.getCamera().animate(
        { x: 0.5, y: 0.5, ratio: 1.02 },
        { duration, easing: (t) => easeInOutCubic(t) }
      );
    }

    // FA2 活布局（星云式聚拢，静置后自动停）
    // 主线程 rAF 布局循环（484 节点每帧 ~1ms；不用 worker——在部分构建器下会让 WebGL 渲染静默失效）
    let userTookOver = false;
    const stopLayout = () => {
      userTookOver = true;
      if (layoutRafRef.current) {
        cancelAnimationFrame(layoutRafRef.current);
        layoutRafRef.current = null;
      }
    };
    const startLayout = (autoStopMs?: number) => {
      stopLayout();
      userTookOver = false;
      const startedAt = performance.now();
      const tick = () => {
        forceAtlas2.assign(graph, { iterations: 2, settings: { ...FA2_SETTINGS } });
        const elapsed = performance.now() - startedAt;
        if (elapsed < (autoStopMs ?? 15000) && !userTookOver) {
          layoutRafRef.current = requestAnimationFrame(tick);
        } else {
          layoutRafRef.current = null;
        }
      };
      layoutRafRef.current = requestAnimationFrame(tick);
    };
    /** 位置归一化：仅在布局静置后统一尺度（中心 0,0，最大半径 12）。
     *  活布局期间绝不调用——与 FA2 膨胀趋势打架会产生帧级锯齿（抖动）。 */
    const normalizePositions = () => {
      let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      graph.forEachNode((_, a) => {
        x0 = Math.min(x0, a.x); x1 = Math.max(x1, a.x);
        y0 = Math.min(y0, a.y); y1 = Math.max(y1, a.y);
      });
      if (!Number.isFinite(x0)) return;
      const cx = (x0 + x1) / 2;
      const cy = (y0 + y1) / 2;
      const maxR = Math.max((x1 - x0) / 2, (y1 - y0) / 2, 0.001);
      const k = 12 / maxR;
      graph.forEachNode((id, a) => {
        graph.setNodeAttribute(id, "x", (a.x - cx) * k);
        graph.setNodeAttribute(id, "y", (a.y - cy) * k);
      });
    };
    stableMode = settledPositions.size > 0 && viewModeRef.current !== "geo";
    if (stableMode) {
      fitCamera(50);
    } else if (viewModeRef.current !== "geo") {
      startLayout(5000);
    }

    const fitTimer1 = stableMode ? undefined : window.setTimeout(() => fitCamera(1100), 2400);
    const fitTimer2 = window.setTimeout(() => {
      if (!stableMode && viewModeRef.current === "force") {
        stopLayout();
        saveAndReinstance();
      }
    }, 5500);

    // ── 布局变形动画 ──
    async function tweenPositions(target: Map<string, { x: number; y: number }> | null) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      const from = new Map<string, { x: number; y: number }>();
      graph.forEachNode((n, a) => from.set(n, { x: a.x, y: a.y }));
      const D = 700;
      const t0 = performance.now();
      await new Promise<void>((resolve) => {
        const step = () => {
          const k = Math.min(1, (performance.now() - t0) / D);
          const e = easeInOutCubic(k);
          graph.forEachNode((n, a) => {
            const f = from.get(n)!;
            if (target) {
              const to = target.get(n) || f;
              graph.setNodeAttribute(n, "x", f.x + (to.x - f.x) * e);
              graph.setNodeAttribute(n, "y", f.y + (to.y - f.y) * e);
            } else if (k < 1) {
              graph.setNodeAttribute(n, "x", a.x + Math.sin((hash32(n) % 7) + k * 3) * 1.2);
            }
          });
          if (k < 1) rafRef.current = requestAnimationFrame(step);
          else resolve();
        };
        rafRef.current = requestAnimationFrame(step);
      });
    }

    /** 相机聚焦：目标图坐标 → 屏幕像素 → 归一化取景坐标（相机语义），飞向目标并轻微放大。
     *  依赖 graphToViewport（矩阵须已暖；显式定位时用户已交互过）。 */
    async function centerOnGraphPoint(gx: number, gy: number, duration = 650) {
      if (centeringRef.current) return;
      centeringRef.current = true;
      try {
        if (!matrixWarmed) {
          sigma.refresh();
          await new Promise((r) => requestAnimationFrame(r));
        }
        const el = containerRef.current!;
        const p = sigma.graphToViewport({ x: gx, y: gy });
        const cam = sigma.getCamera();
        await cam.animate(
          { x: p.x / el.clientWidth, y: p.y / el.clientHeight, ratio: Math.min(cam.ratio, 0.72) },
          { duration, easing: (t) => easeInOutCubic(t) }
        );
      } finally {
        centeringRef.current = false;
      }
    }

    async function morphLayout(mode: string) {
      viewModeRef.current = mode;
      if (mode === "geo") {
        stopLayout();
        await tweenPositions(galaxyPositions(data));
      } else {
        await tweenPositions(null);
        startLayout(5000);
        window.setTimeout(() => {
          stopLayout();
          saveAndReinstance();
        }, 5500);
        return;
      }
      fitCamera(800);
      saveAndReinstance();
    }

    function recolor(mode: string) {
      graph.forEachNode((nid, attrs) => {
        const node = attrs.nodeData as GraphNode;
        if (node.kind === "myth") {
          graph.setNodeAttribute(nid, "color", MYTH_NODE_COLOR);
          return;
        }
        graph.setNodeAttribute(
          nid,
          "color",
          mode === "cluster" ? clusterColor.get(nid) || mythColor(node.mythology) : mythColor(node.mythology)
        );
      });
      sigma.refresh();
    }

    // ── 交互 ──
    const store = useGraphView;
    let dragNode: string | null = null;
    let pointerPos = { x: 0, y: 0 };
    // 拖动/点击区分：累计拖动像素，超阈值则抑制随后的 click（拖动不改高亮）
    let dragStart: { x: number; y: number } | null = null;
    let dragMovedPx = 0;
    let suppressClickUntil = 0;
    // 边悬停提示：悬停 2s 后才显示，避免掠过时标签乱跳
    let edgeTipTimer: number | undefined;
    // 触屏判定：主输入为粗指针（手机/平板）时，不截获 down 事件 → 双指缩放/平移交给 sigma 原生
    const coarsePointer = typeof window !== "undefined" && window.matchMedia?.("(pointer: coarse)").matches;

    /** 高亮门控：选中/路径/问答态下，仅高亮集合（本体+邻居+路径+RAG）内节点可交互 */
    const isInteractable = (node: string): boolean => {
      const state = store.getState();
      if (!state.selectedId && !state.pathResult?.found && !state.askIds?.length) return true;
      if (state.selectedId === node) return true;
      const { primary, secondary } = highlightSets(state);
      if (primary.has(node) || secondary.has(node)) return true;
      const nb = neighborIds(graph, state.selectedId);
      return !!nb?.has(node);
    };

    /** 数学最近邻命中测试（原始，不设门控）：WebGL 拾取在部分环境不可靠时的全平台兜底 */
    const hitTestAny = (px: number, py: number): string | null => {
      let best: string | null = null;
      let bestD = Infinity;
      graph.forEachNode((n, a) => {
        const sc = sigma.graphToViewport({ x: a.x, y: a.y });
        const d = Math.hypot(sc.x - px, sc.y - py);
        const r = Math.max(14, (a.size || 4) + 8);
        if (d < r && d < bestD) {
          bestD = d;
          best = n;
        }
      });
      return best;
    };
    /** 门控版：高亮态下只返回可交互节点 */
    const hitTest = (px: number, py: number): string | null => {
      const hit = hitTestAny(px, py);
      return hit && isInteractable(hit) ? hit : null;
    };

    /** graphToViewport 的归一化矩阵在重建后是未初始化状态（所有点坍缩到中心）；
     *  sigma.refresh() 异步落地后矩阵才正确——本 tick 内重试无效，必须等一帧。 */
    let matrixWarmed = false;
    const warmMatrix = () => {
      if (matrixWarmed) return;
      matrixWarmed = true;
      sigma.refresh();
    };

    const selectNode = (node: string) => {
      const g = graph.getNodeAttributes(node) as { nodeData: GraphNode };
      store.getState().showToast(`已选中 ${g.nodeData.name} · 关系已高亮`);
      store.getState().select(node);
    };

    const beginDrag = (node: string, x: number, y: number) => {
      dragNode = node;
      dragStart = { x, y };
      dragMovedPx = 0;
      graph.setNodeAttribute(node, "fixed", true);
      stopLayout(); // 用户接管布局
      containerRef.current!.style.cursor = "grabbing";
    };

    sigma.on("downNode", ({ node, event }) => {
      if (coarsePointer) return; // 触屏：down 不截获，双指缩放/平移交给 sigma 原生；tap 由 clickNode 承担
      if (!isInteractable(node)) return; // 高亮态下灰点不可拖
      event.preventSigmaDefault();
      beginDrag(node, event.x, event.y);
    });
    sigma.on("downStage", ({ event }) => {
      if (coarsePointer) return;
      if (!matrixWarmed) {
        warmMatrix();
        return; // 首次交互只暖矩阵；拖拽由 downNode 原生路径承担
      }
      const hit = hitTest(event.x, event.y);
      if (hit) beginDrag(hit, event.x, event.y);
    });

    let lastHoverProbe = 0;
    sigma.on("moveBody", (e) => {
      pointerPos = { x: e.event.x, y: e.event.y };
      if (tooltipLiveRef.current) {
        setTooltip((t) => (t ? { ...t, x: e.event.x, y: e.event.y } : t));
      }
      if (dragNode) {
        e.preventSigmaDefault();
        if (dragStart) {
          dragMovedPx = Math.max(dragMovedPx, Math.hypot(e.event.x - dragStart.x, e.event.y - dragStart.y));
        }
        const p = sigma.viewportToGraph({ x: e.event.x, y: e.event.y });
        graph.setNodeAttribute(dragNode, "x", p.x);
        graph.setNodeAttribute(dragNode, "y", p.y);
        return;
      }
      if (coarsePointer) return; // 触屏无悬停概念
      // 悬停兜底（节流 80ms）：原生 enterNode 失效时用命中测试
      const now = performance.now();
      if (now - lastHoverProbe > 80) {
        lastHoverProbe = now;
        if (!matrixWarmed) {
          warmMatrix(); // 本帧暖矩阵，下一帧起悬停即准确
          return;
        }
        const hit = hitTest(e.event.x, e.event.y);
        if (hit) {
          const attrs = graph.getNodeAttributes(hit) as { nodeData: GraphNode };
          tooltipLiveRef.current = true;
          setTooltip((t) =>
            t && t.node && t.node.id === hit
              ? { ...t, x: e.event.x, y: e.event.y }
              : { x: e.event.x, y: e.event.y, node: attrs.nodeData }
          );
          containerRef.current!.style.cursor = "grab";
        } else if (tooltipLiveRef.current) {
          tooltipLiveRef.current = false;
          setTooltip(null);
          containerRef.current!.style.cursor = "default";
        }
      }
    });

    const endDrag = () => {
      if (dragNode) {
        graph.removeNodeAttribute(dragNode, "fixed");
        if (dragMovedPx > 5) suppressClickUntil = performance.now() + 400; // 拖动 ≠ 点击：不改高亮
        dragNode = null;
        dragStart = null;
        containerRef.current!.style.cursor = "grab";
      }
    };
    window.addEventListener("mouseup", endDrag);

    // 用户一旦交互，取消所有自动对焦（否则会在点击后突然把画面挪走）
    const cancelAutoFit = () => {
      if (fitTimer1) clearTimeout(fitTimer1);
      clearTimeout(fitTimer2);
    };

    sigma.on("clickNode", ({ node }) => {
      cancelAutoFit();
      if (performance.now() < suppressClickUntil) return; // 刚拖完：忽略，保持高亮
      if (!isInteractable(node)) return; // 高亮态下灰点不可点
      setTooltip(null);
      tooltipLiveRef.current = false;
      selectNode(node);
    });
    sigma.on("clickStage", ({ event }) => {
      cancelAutoFit();
      if (performance.now() < suppressClickUntil) return; // 刚拖完空白：这是平移，不是点击
      const px = event.x;
      const py = event.y;
      const finish = () => {
        const raw = hitTestAny(px, py);
        if (raw) {
          if (isInteractable(raw)) selectNode(raw);
          // else：命中高亮态下的灰点 → 完全忽略（点击灰点既不选中也不取消高亮）
        } else {
          tooltipLiveRef.current = false;
          setTooltip(null);
          store.getState().select(null); // 真空白点击才取消
        }
      };
      if (!matrixWarmed) {
        warmMatrix();
        requestAnimationFrame(finish); // refresh 落地要等一帧，矩阵才可信
      } else {
        finish();
      }
    });
    sigma.on("enterNode", ({ node }) => {
      if (edgeTipTimer) {
        clearTimeout(edgeTipTimer);
        edgeTipTimer = undefined;
      }
      if (coarsePointer) return; // 触屏无悬停卡
      containerRef.current!.style.cursor = "grab";
      const attrs = graph.getNodeAttributes(node) as { nodeData: GraphNode };
      tooltipLiveRef.current = true;
      setTooltip({ x: pointerPos.x, y: pointerPos.y, node: attrs.nodeData });
    });
    sigma.on("leaveNode", () => {
      containerRef.current!.style.cursor = "default";
      tooltipLiveRef.current = false;
      setTooltip(null);
    });
    sigma.on("clickEdge", ({ edge }) => {
      cancelAutoFit();
      const [s, t] = graph.extremities(edge);
      store.getState().setPath(s, t, null);
      // 自动展开路径面板并提示（否则用户不知道发生了什么）
      if (window.innerWidth < 768) {
        store.getState().setMobilePanel("path");
      } else {
        store.getState().setPathPanelOpen(true);
      }
      void api.paths(s, t).then((r) => {
        store.getState().setPath(s, t, r);
        const names = graph.getNodeAttributes(s).nodeData as GraphNode;
        const namet = graph.getNodeAttributes(t).nodeData as GraphNode;
        store.getState().showToast(
          r.found ? `${names.name} → ${namet.name}：${r.distance} 步` : `${names.name} 与 ${namet.name} 不连通`
        );
      });
    });
    sigma.on("enterEdge", ({ edge }) => {
      hoverEdgeRef.current = edge;
      sigma.refresh();
      if (coarsePointer) return; // 触屏无悬停
      if (edgeTipTimer) clearTimeout(edgeTipTimer);
      edgeTipTimer = window.setTimeout(() => {
        edgeTipTimer = undefined;
        const [s2, t2] = graph.extremities(edge);
        const label = (graph.getEdgeAttributes(edge) as { relLabel?: string }).relLabel || "关系";
        const from = (graph.getNodeAttributes(s2) as { nodeData: GraphNode }).nodeData.name;
        const to = (graph.getNodeAttributes(t2) as { nodeData: GraphNode }).nodeData.name;
        tooltipLiveRef.current = true;
        setTooltip({ x: pointerPos.x, y: pointerPos.y, edge: { label, from, to } });
      }, 2000); // 悬停 2s 才显示，鼠标掠过不跳
    });
    sigma.on("leaveEdge", () => {
      hoverEdgeRef.current = null;
      sigma.refresh();
      if (edgeTipTimer) {
        clearTimeout(edgeTipTimer);
        edgeTipTimer = undefined;
      }
      setTooltip((t) => (t && t.edge ? null : t)); // 只清边提示
      tooltipLiveRef.current = false;
    });

    // ── 高亮 reducer（一次性注册；内部实时读 store）──
    sigma.setSetting("nodeReducer", (node, attrs) => {
      const state = useGraphView.getState();
      const { primary, secondary } = highlightSets(state);
      if (primary.size === 0 && secondary.size === 0) return attrs;
      if (state.selectedId === node || primary.has(node)) {
        return { ...attrs, zIndex: 3, highlighted: true, forceLabel: true };
      }
      const neighbors = neighborIds(graph, state.selectedId);
      if (neighbors?.has(node) || secondary.has(node)) {
        return { ...attrs, zIndex: 2, forceLabel: true };
      }
      return { ...attrs, color: "#232634", label: null, zIndex: 0 };
    });
    sigma.setSetting("edgeReducer", (edge, attrs) => {
      const state = useGraphView.getState();
      if (hoverEdgeRef.current === edge) {
        return { ...attrs, color: "#fbbf24", size: 3, forceLabel: true, hidden: false };
      }
      const { primary, pathEdges } = highlightSets(state);
      if (primary.size === 0) return attrs;
      const [s, t] = graph.extremities(edge);
      const onPath = pathEdges.has(`${s}>${t}`) || pathEdges.has(`${t}>${s}`);
      const touchesSel = state.selectedId === s || state.selectedId === t;
      if (onPath) return { ...attrs, color: "#f59e0b", size: 3.4, hidden: false };
      if (touchesSel) return { ...attrs, color: "#38bdf8", size: 2.4, hidden: false };
      return { ...attrs, hidden: true };
    });

    // ── store 订阅：定向刷新（修复之前的刷新风暴）──
    const unsubStore = store.subscribe((state, prev) => {
      if (
        state.selectedId !== prev.selectedId ||
        state.pathResult !== prev.pathResult ||
        state.askIds !== prev.askIds
      ) {
        sigma.refresh();
      }
      // 平移居中只服务显式定位（focus() 触发 nonce）；普通点选不挪画面，保持视图稳定
      if (state.focusNonce !== prev.focusNonce && state.focusId) {
        const attrs = graph.getNodeAttributes(state.focusId);
        if (Number.isFinite(attrs.x)) {
          void centerOnGraphPoint(attrs.x, attrs.y);
        }
      }
      // 取消高亮：力导向模式恢复活布局（节点重新浮动）
      if (state.cancelFocusNonce !== prev.cancelFocusNonce) {
        if (viewModeRef.current === "force") startLayout(5000);
      }
      // 重置视图：恢复静置布局 + 归一化 + 相机回中心全景
      if (state.resetViewNonce !== prev.resetViewNonce) {
        const restore = viewModeRef.current === "geo" ? galaxyPositions(data) : settledPositions;
        if (restore.size) {
          graph.forEachNode((n) => {
            const pos = restore.get(n);
            if (pos) {
              graph.setNodeAttribute(n, "x", pos.x);
              graph.setNodeAttribute(n, "y", pos.y);
            }
          });
        }
        void sigma.getCamera().animate(
          { x: 0.5, y: 0.5, ratio: 1.02 },
          { duration: 700, easing: (t) => easeInOutCubic(t) }
        );
        if (viewModeRef.current === "force") startLayout(5000);
        sigma.refresh();
      }
      if (state.viewMode !== prev.viewMode) void morphLayout(state.viewMode);
      if (state.colorBy !== prev.colorBy) recolor(state.colorBy);
    });

    // PNG 导出句柄
    (window as unknown as Record<string, unknown>).__theogonyExportPng = () => {
      const s = sigmaRef.current as unknown as { toCanvas?: () => HTMLCanvasElement } | null;
      if (s?.toCanvas) return s.toCanvas();
      return containerRef.current?.querySelector("canvas") ?? null;
    };

    return () => {
      if (fitTimer1) clearTimeout(fitTimer1);
      clearTimeout(fitTimer2);
      window.removeEventListener("mouseup", endDrag);
      unsubStore();
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (layoutRafRef.current) cancelAnimationFrame(layoutRafRef.current);
      sigma.kill();
      sigmaRef.current = null;
      graphRef.current = null;
    };
     
  }, [data, clusterColor]);

  return (
    <div className="absolute inset-0 overflow-hidden">
      <div ref={containerRef} className="absolute inset-0" />
      {/* 星云辉光 + 暗角 */}
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          background:
            "radial-gradient(ellipse at 50% 40%, rgba(56,89,168,0.10) 0%, rgba(9,9,17,0) 45%)," +
            "radial-gradient(ellipse at 50% 115%, rgba(120,60,160,0.09) 0%, rgba(9,9,17,0) 55%)," +
            "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 58%, rgba(0,0,0,0.4) 100%)",
        }}
      />
      {/* 悬停浮卡（节点 / 边关系） */}
      {tooltip && tooltip.node && (
        <div
          className="pointer-events-none fixed z-40 w-56 overflow-hidden rounded-xl border border-zinc-700/80 bg-zinc-950/95 shadow-2xl backdrop-blur"
          style={{
            left: Math.min(tooltip.x + 16, (typeof window !== "undefined" ? window.innerWidth : 1920) - 240),
            top: Math.min(tooltip.y + 14, (typeof window !== "undefined" ? window.innerHeight : 1080) - 170),
          }}
        >
          <div className="flex items-center gap-2.5 p-2.5">
            {tooltip.node.imageUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={imgProxy(tooltip.node.imageUrl)}
                alt=""
                className="h-11 w-11 rounded-lg border border-zinc-700 object-cover"
              />
            ) : (
              <span className="h-11 w-11 rounded-lg" style={{ background: mythColor(tooltip.node.mythology) }} />
            )}
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-zinc-100">{tooltip.node.name}</div>
              <div className="mt-0.5 flex items-center gap-1.5 text-[10px]">
                <span
                  className="rounded px-1.5 py-0.5 text-zinc-950"
                  style={{ background: mythColor(tooltip.node.mythology) }}
                >
                  {tooltip.node.mythology || "未归类"}
                </span>
                {tooltip.node.className && <span className="text-amber-300">{tooltip.node.className}</span>}
                <span className="text-zinc-500">· {tooltip.node.degree} 关系</span>
              </div>
            </div>
          </div>
        </div>
      )}
      {tooltip && tooltip.edge && (
        <div
          className="pointer-events-none fixed z-40 rounded-xl border border-zinc-700/80 bg-zinc-950/95 px-3 py-2 shadow-2xl backdrop-blur"
          style={{
            left: Math.min(tooltip.x + 16, (typeof window !== "undefined" ? window.innerWidth : 1920) - 220),
            top: Math.min(tooltip.y + 14, (typeof window !== "undefined" ? window.innerHeight : 1080) - 90),
          }}
        >
          <div className="flex items-center gap-2 text-xs">
            <span className="rounded bg-amber-500/20 px-1.5 py-0.5 font-medium text-amber-300">
              {tooltip.edge.label}
            </span>
            <span className="text-zinc-300">{tooltip.edge.from}</span>
            <span className="text-zinc-500">↔</span>
            <span className="text-zinc-300">{tooltip.edge.to}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function neighborIds(graph: Graph | null, id: string | null): Set<string> | null {
  if (!graph || !id || !graph.hasNode(id)) return null;
  const set = new Set<string>();
  graph.forEachNeighbor(id, (n) => set.add(n));
  return set;
}
