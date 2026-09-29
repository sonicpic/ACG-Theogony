"use client";

/** 主页：全局图谱探索器。 */

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { useGraphQuery } from "@/components/graph/useGraphQuery";
import { ControlPanel } from "@/components/graph/ControlPanel";
import { PathFinder } from "@/components/graph/PathFinder";
import { AskPanel } from "@/components/graph/AskPanel";
import { CharacterPanel } from "@/components/graph/CharacterPanel";
import { useGraphView } from "@/lib/store";

// WebGL 组件只能在客户端加载（SSR 无 WebGL 上下文）
const SigmaGraph = dynamic(() => import("@/components/graph/SigmaGraph").then((m) => m.SigmaGraph), {
  ssr: false,
  loading: () => <div className="absolute inset-0 animate-pulse bg-zinc-900/40" />,
});
const Graph3D = dynamic(() => import("@/components/graph/Graph3D"), { ssr: false });

export default function GraphExplorerPage() {
  const { data, isLoading, error } = useGraphQuery();
  const store = useGraphView();

  // 客户端筛选（全量数据一次拉取，交互零延迟）
  const filtered = useMemo(() => {
    if (!data) return null;
    const mythSet = new Set(store.mythologies);
    const typeSet = new Set(store.types);
    const classSet = new Set(store.classes);

    const nodes = data.nodes.filter((n) => {
      if (n.kind === "myth") return store.showMythNodes;
      if (store.maxWikiId && n.wikiId > store.maxWikiId) return false;
      if (mythSet.size && !mythSet.has(n.mythology || "")) return false;
      if (classSet.size && !classSet.has(n.className)) return false;
      return true;
    });
    const ids = new Set(nodes.map((n) => n.id));
    const links = data.links.filter((l) => {
      if (typeSet.size && !typeSet.has(l.type)) return false;
      if (!ids.has(l.source) || !ids.has(l.target)) return false;
      return true;
    });
    const linkedIds = new Set(links.flatMap((l) => [l.source, l.target]));
    const finalNodes = store.onlyRelated
      ? nodes.filter((n) => n.kind === "myth" || linkedIds.has(n.id) || n.id.startsWith("m:"))
      : nodes;
    return { ...data, nodes: finalNodes, links };
  }, [data, store.mythologies, store.types, store.classes, store.showMythNodes, store.maxWikiId, store.onlyRelated]);

  const stats = useMemo(() => {
    if (!filtered) return null;
    const chars = filtered.nodes.filter((n) => n.kind === "character");
    return {
      characters: chars.length,
      myths: filtered.nodes.filter((n) => n.kind === "myth").length,
      links: filtered.links.filter((l) => l.type !== "BELONGS_TO").length,
    };
  }, [filtered]);

  if (isLoading) {
    return (
      <div className="flex h-[calc(100vh-48px)] items-center justify-center">
        <div className="text-center text-zinc-500">
          <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-sky-400" />
          正在加载 465 位英灵的神话宇宙…
        </div>
      </div>
    );
  }
  if (error || !data || !filtered) {
    return (
      <div className="flex h-[calc(100vh-48px)] flex-col items-center justify-center gap-3 text-center">
        <p className="text-zinc-400">图谱加载失败：{(error as Error | null)?.message?.slice(0, 120) || "未知错误"}</p>
        <p className="text-xs text-zinc-600">请确认 FastAPI 已启动（npm run api）且已执行 npm run db:build</p>
      </div>
    );
  }

  return (
    <main className="relative h-[calc(100vh-48px)] overflow-hidden">
      <div className="absolute inset-0">
        {store.viewMode === "3d" ? <Graph3D data={filtered} /> : <SigmaGraph data={filtered} />}
      </div>

      <ControlPanel data={data} />
      <PathFinder data={data} />
      <CharacterPanel />
      <AskPanel />

      {/* 底部统计条 */}
      <div className="pointer-events-none absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-zinc-800 bg-zinc-950/90 px-4 py-1.5 text-xs text-zinc-400 backdrop-blur">
        角色 <span className="font-semibold text-sky-400">{stats?.characters}</span> · 体系{" "}
        <span className="font-semibold text-emerald-400">{stats?.myths}</span> · 关系{" "}
        <span className="font-semibold text-amber-400">{stats?.links}</span>
        <span className="ml-2 text-zinc-600">点击节点看邻居 · 点边找路径</span>
      </div>
    </main>
  );
}
