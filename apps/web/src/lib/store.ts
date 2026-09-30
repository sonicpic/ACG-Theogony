"use client";

/** 全局视图状态（Zustand）：筛选 / 选择 / 路径 / 视图模式。 */

import { create } from "zustand";
import type { PathDTO } from "./types";

export type ViewMode = "force" | "geo" | "3d";
export type ColorBy = "mythology" | "cluster";

interface GraphViewState {
  // 筛选
  mythologies: string[];
  classes: string[];
  types: string[];
  gender: string;
  onlyRelated: boolean;
  showMythNodes: boolean;
  maxWikiId: number | null; // 时间轴（角色编号 ≈ 实装顺序）
  // 视图
  viewMode: ViewMode;
  colorBy: ColorBy;
  // 选择与高亮
  selectedId: string | null;
  hoveredId: string | null;
  focusId: string | null; // 触发相机聚焦
  focusNonce: number; // 显式定位计数（区分点选与定位）
  askIds: string[] | null; // RAG 子图高亮
  // 路径探索
  pathFrom: string | null;
  pathTo: string | null;
  pathResult: PathDTO | null;
  // 面板
  askOpen: boolean;
  // 移动端抽屉：filter | path | ask | null（桌面端不使用）
  mobilePanel: string | null;
  tourOpen: boolean;
  // 桌面路径面板展开（点边时自动展开）
  pathPanelOpen: boolean;
  // 布局纪元：静置后 bump 触发 Sigma 重建（恢复拾取/坐标系一致性）
  layoutEpoch: number;
  // 全局轻提示
  toast: { id: number; msg: string } | null;

  setFilters(partial: Partial<Pick<GraphViewState, "mythologies" | "classes" | "types" | "gender" | "onlyRelated" | "showMythNodes" | "maxWikiId">>): void;
  toggleMythology(m: string): void;
  toggleType(t: string): void;
  toggleClass(c: string): void;
  setViewMode(v: ViewMode): void;
  setColorBy(c: ColorBy): void;
  select(id: string | null): void;
  hover(id: string | null): void;
  focus(id: string | null): void;
  setAskIds(ids: string[] | null): void;
  setPath(from: string | null, to: string | null, result?: PathDTO | null): void;
  setAskOpen(open: boolean): void;
  setMobilePanel(panel: string | null): void;
  setTourOpen(open: boolean): void;
  setPathPanelOpen(open: boolean): void;
  bumpLayoutEpoch(): void;
  showToast(msg: string): void;
  resetFilters(): void;
}

export const useGraphView = create<GraphViewState>((set) => ({
  mythologies: [],
  classes: [],
  types: [],
  gender: "",
  onlyRelated: false,
  showMythNodes: true,
  maxWikiId: null,
  viewMode: "force",
  colorBy: "mythology",
  selectedId: null,
  hoveredId: null,
  focusId: null,
  focusNonce: 0,
  askIds: null,
  pathFrom: null,
  pathTo: null,
  pathResult: null,
  askOpen: false,
  mobilePanel: null,
  tourOpen: typeof window !== "undefined" && !localStorage.getItem("theogony-tour-done"),
  pathPanelOpen: false,
  layoutEpoch: 0,
  toast: null,

  setFilters: (partial) => set(partial),
  toggleMythology: (m) =>
    set((s) => ({
      mythologies: s.mythologies.includes(m) ? s.mythologies.filter((x) => x !== m) : [...s.mythologies, m],
    })),
  toggleType: (t) =>
    set((s) => ({
      types: s.types.includes(t) ? s.types.filter((x) => x !== t) : [...s.types, t],
    })),
  toggleClass: (c) =>
    set((s) => ({
      classes: s.classes.includes(c) ? s.classes.filter((x) => x !== c) : [...s.classes, c],
    })),
  setViewMode: (v) => set({ viewMode: v }),
  setColorBy: (c) => set({ colorBy: c }),
  select: (id) => set({ selectedId: id, focusId: id }),
  hover: (id) => set({ hoveredId: id }),
  focus: (id) => set((s) => ({ focusId: id, focusNonce: s.focusNonce + 1 })),
  setAskIds: (ids) => set({ askIds: ids }),
  setPath: (from, to, result = null) => set({ pathFrom: from, pathTo: to, pathResult: result }),
  setAskOpen: (open) => set({ askOpen: open }),
  setMobilePanel: (panel) => set({ mobilePanel: panel }),
  setPathPanelOpen: (open) => set({ pathPanelOpen: open }),
  bumpLayoutEpoch: () => set((s) => ({ layoutEpoch: s.layoutEpoch + 1 })),
  showToast: (msg) => {
    const id = Date.now();
    set({ toast: { id, msg } });
    setTimeout(() => {
      const t = useGraphView.getState().toast;
      if (t && t.id === id) set({ toast: null });
    }, 2600);
  },
  setTourOpen: (open) => {
    if (!open && typeof window !== "undefined") localStorage.setItem("theogony-tour-done", "1");
    set({ tourOpen: open });
  },
  resetFilters: () =>
    set({
      mythologies: [],
      classes: [],
      types: [],
      gender: "",
      onlyRelated: false,
      showMythNodes: false,
      maxWikiId: null,
      pathFrom: null,
      pathTo: null,
      pathResult: null,
      askIds: null,
    }),
}));

/** 当前生效的高亮节点集合（选择邻居 ∪ 路径 ∪ RAG 子图） */
export function highlightSets(state: GraphViewState): {
  primary: Set<string>;
  secondary: Set<string>;
  pathEdges: Set<string>;
} {
  const primary = new Set<string>();
  const secondary = new Set<string>();
  const pathEdges = new Set<string>();

  if (state.selectedId) primary.add(state.selectedId);
  if (state.pathResult?.found) {
    state.pathResult.nodes.forEach((n) => primary.add(n.id));
    state.pathResult.steps.forEach((s) => pathEdges.add(`${s.source}>${s.target}`));
  }
  if (state.askIds?.length) state.askIds.forEach((id) => secondary.add(id));
  return { primary, secondary, pathEdges };
}
