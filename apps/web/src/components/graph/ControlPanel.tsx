"use client";

/**
 * 左侧控制面板（桌面浮动卡，md 以上）+ FilterContent（供移动端抽屉复用）。
 * 搜索 / 自然语言常驻；筛选细节折叠收纳，导出图标化。
 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { ChevronDown, FileDown, Image as ImageIcon, Network, RotateCcw, Search, Sparkles, Waypoints } from "lucide-react";
import { api } from "@/lib/api";
import { CATEGORY_LABEL, RELATION_META, mythColor } from "@/lib/constants";
import type { GraphDTO } from "@/lib/types";
import { useGraphView } from "@/lib/store";
import { exportPng, exportSvg } from "@/lib/exporters";

/** 筛选内容（桌面折叠区 / 移动端抽屉共用） */
export function FilterContent({ data }: { data: GraphDTO }) {
  const store = useGraphView();
  const options = useQuery({ queryKey: ["options"], queryFn: api.options });

  const presentTypes = useMemo(() => {
    const present = new Set(data.links.map((l) => l.type).filter((t) => t !== "BELONGS_TO"));
    return Array.from(present).sort((a, b) => {
      const ma = RELATION_META[a];
      const mb = RELATION_META[b];
      return (ma?.category || "").localeCompare(mb?.category || "") || a.localeCompare(b);
    });
  }, [data.links]);

  const presentMyths = useMemo(() => {
    const count = new Map<string, number>();
    data.nodes.forEach((n) => {
      if (n.kind === "character" && n.mythology) count.set(n.mythology, (count.get(n.mythology) || 0) + 1);
    });
    return Array.from(count.entries()).sort((a, b) => b[1] - a[1]);
  }, [data.nodes]);

  return (
    <div className="space-y-4">
      {/* 视图模式（分段控件） */}
      <div className="grid grid-cols-3 gap-1 rounded-lg bg-zinc-900 p-1">
        {(
          [
            ["force", "力导向"],
            ["geo", "神话星系"],
            ["3d", "3D"],
          ] as const
        ).map(([mode, label]) => (
          <button
            key={mode}
            onClick={() => store.setViewMode(mode)}
            className={clsx(
              "rounded-md px-2 py-1.5 text-xs font-medium transition-all",
              store.viewMode === mode
                ? "bg-sky-600 text-white shadow"
                : "text-zinc-400 hover:text-zinc-200"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      {/* 着色 */}
      <div className="flex items-center gap-2 text-xs">
        <span className="text-zinc-500">着色</span>
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-zinc-900 p-1 flex-1">
          {(["mythology", "cluster"] as const).map((c) => (
            <button
              key={c}
              onClick={() => store.setColorBy(c)}
              className={clsx(
                "rounded-md px-2 py-1 transition-all",
                store.colorBy === c ? "bg-zinc-700 text-white" : "text-zinc-500 hover:text-zinc-300"
              )}
            >
              {c === "mythology" ? "按体系" : "按社区"}
            </button>
          ))}
        </div>
      </div>

      {/* 时间轴 */}
      <div>
        <div className="mb-1 flex justify-between text-[11px] text-zinc-400">
          <span className="font-semibold">时间轴 · 实装顺序</span>
          <span className="text-zinc-500">{store.maxWikiId ? `No.${store.maxWikiId} 前` : "全部"}</span>
        </div>
        <input
          type="range"
          min={0}
          max={Math.max(...data.nodes.map((n) => n.wikiId), 100)}
          value={store.maxWikiId ?? 0}
          onChange={(e) => store.setFilters({ maxWikiId: Number(e.target.value) || null })}
          className="w-full accent-sky-500"
        />
      </div>

      {/* 神话体系 */}
      <div>
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-[11px] font-semibold text-zinc-400">
            神话体系·点击筛选 {store.mythologies.length > 0 && <span className="text-sky-400">· 已选 {store.mythologies.length}</span>}
          </span>
          {store.mythologies.length > 0 && (
            <button
              onClick={() => store.setFilters({ mythologies: [] })}
              className="text-[10px] text-zinc-500 underline-offset-2 hover:text-zinc-200 hover:underline"
            >
              清除
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-1">
          {presentMyths.map(([m, count]) => (
            <button
              key={m}
              onClick={() => store.toggleMythology(m)}
              className={clsx(
                "flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-all",
                store.mythologies.includes(m)
                  ? "border-transparent font-medium text-zinc-950"
                  : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
              )}
              style={store.mythologies.includes(m) ? { background: mythColor(m) } : undefined}
            >
              <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: mythColor(m) }} />
              {m}
              <span className="opacity-60">{count}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 关系类型 */}
      {presentTypes.length > 0 && (
        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <span className="text-[11px] font-semibold text-zinc-400">
              关系类型·点击筛选 {store.types.length > 0 && <span className="text-sky-400">· 已选 {store.types.length}</span>}
            </span>
            {store.types.length > 0 && (
              <button
                onClick={() => store.setFilters({ types: [] })}
                className="text-[10px] text-zinc-500 underline-offset-2 hover:text-zinc-200 hover:underline"
              >
                清除
              </button>
            )}
          </div>
          <div className="space-y-1.5">
            {(["myth", "family", "social"] as const).map((cat) => {
              const rels = presentTypes.filter((t) => RELATION_META[t]?.category === cat);
              if (!rels.length) return null;
              return (
                <div key={cat}>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-600">{CATEGORY_LABEL[cat]}</div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {rels.map((t) => (
                      <button
                        key={t}
                        onClick={() => store.toggleType(t)}
                        className={clsx(
                          "rounded-full border px-2 py-0.5 text-[11px] transition-all",
                          store.types.length === 0 || store.types.includes(t)
                            ? "border-zinc-700 text-zinc-300"
                            : "border-zinc-800 text-zinc-600"
                        )}
                        style={
                          store.types.length === 0 || store.types.includes(t)
                            ? { borderColor: RELATION_META[t].color, color: RELATION_META[t].color }
                            : undefined
                        }
                      >
                        {RELATION_META[t].label}
                      </button>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 显示选项 + 职阶 */}
      <div className="flex flex-wrap gap-x-4 gap-y-2 text-xs text-zinc-400">
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={store.onlyRelated} onChange={(e) => store.setFilters({ onlyRelated: e.target.checked })} />
          隐藏孤立角色
        </label>
        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={store.showMythNodes} onChange={(e) => store.setFilters({ showMythNodes: e.target.checked })} />
          体系枢纽
        </label>
        {options.data && options.data.classes.length > 0 && (
          <label className="flex items-center gap-1.5">
            职阶
            <select
              value={store.classes[0] || ""}
              onChange={(e) => store.setFilters({ classes: e.target.value ? [e.target.value] : [] })}
              className="rounded border border-zinc-800 bg-zinc-900 px-1.5 py-0.5 text-xs"
            >
              <option value="">全部</option>
              {options.data.classes.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {/* 导出 + 重置 */}
      <div className="flex items-center gap-1.5 border-t border-zinc-800 pt-3">
        <button
          onClick={() => exportPng()}
          className="flex flex-1 items-center justify-center gap-1 rounded-md bg-zinc-900 px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          title="导出 PNG 图片"
        >
          <ImageIcon size={13} /> PNG
        </button>
        <button
          onClick={() => exportSvg(data.nodes, data.links)}
          className="flex flex-1 items-center justify-center gap-1 rounded-md bg-zinc-900 px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          title="导出 SVG 矢量图"
        >
          <Waypoints size={13} /> SVG
        </button>
        <a
          href="/api/export/graphml"
          className="flex flex-1 items-center justify-center gap-1 rounded-md bg-zinc-900 px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
          title="导出 Gephi GraphML"
        >
          <FileDown size={13} /> Gephi
        </a>
        <button
          onClick={() => store.resetFilters()}
          className="flex items-center justify-center rounded-md bg-zinc-900 p-2 text-zinc-400 hover:bg-zinc-800"
          title="重置全部筛选"
        >
          <RotateCcw size={13} />
        </button>
      </div>
    </div>
  );
}

/** 桌面版：搜索 + NLQ 常驻，筛选可折叠 */
export function ControlPanel({ data }: { data: GraphDTO }) {
  const [query, setQuery] = useState("");
  const [nlqText, setNlqText] = useState("");
  const [nlqBusy, setNlqBusy] = useState(false);
  const [nlqNote, setNlqNote] = useState("");
  const [expanded, setExpanded] = useState(true);

  const store = useGraphView();

  async function runSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    const res = await api.search(query.trim(), 5);
    if (res.hits.length) {
      store.select(res.hits[0].character.id);
      store.focus(res.hits[0].character.id); // 显式定位：平移居中
      setNlqNote("");
    } else {
      setNlqNote("没有找到相关角色");
    }
  }

  async function runNlq(e: React.FormEvent) {
    e.preventDefault();
    if (!nlqText.trim()) return;
    setNlqBusy(true);
    setNlqNote("");
    try {
      const filters = await api.nlq(nlqText.trim());
      store.setFilters({
        mythologies: filters.mythologies || [],
        types: filters.types || [],
        classes: filters.classes || [],
        gender: filters.gender || "",
      });
      setNlqNote(filters.explanation || "已应用过滤");
    } catch (err) {
      setNlqNote(`解析失败：${(err as Error).message.slice(0, 80)}`);
    } finally {
      setNlqBusy(false);
    }
  }

  return (
    <div className="pointer-events-auto absolute left-3 top-3 z-20 hidden max-h-[calc(100vh-76px)] w-[320px] flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/95 shadow-2xl backdrop-blur md:flex">
      {/* 搜索 */}
      <div className="p-3 pb-2">
        <form onSubmit={runSearch} className="flex gap-2">
          <div className="flex flex-1 items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5">
            <Search size={14} className="shrink-0 text-zinc-500" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索角色（名称 / 别名 / 拼音）"
              className="w-full bg-transparent py-2 text-sm outline-none placeholder:text-zinc-600"
            />
          </div>
          <button type="submit" className="rounded-lg bg-sky-600 px-3 text-sm font-medium hover:bg-sky-500">
            定位
          </button>
        </form>
      </div>

      {/* 自然语言查图 */}
      <div className="px-3 pb-3">
        <div className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold text-zinc-400">
          <Sparkles size={12} className="text-amber-400" />
          自然语言查图
        </div>
        <form onSubmit={runNlq} className="flex gap-2">
          <input
            value={nlqText}
            onChange={(e) => setNlqText(e.target.value)}
            placeholder="如：希腊神话的父子关系"
            className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-amber-500/50"
          />
          <button
            type="submit"
            disabled={nlqBusy}
            className="rounded-lg bg-amber-600/80 px-3 text-sm font-medium hover:bg-amber-500 disabled:opacity-50"
          >
            {nlqBusy ? "…" : "解析"}
          </button>
        </form>
        {nlqNote && <p className="mt-1.5 text-[11px] leading-relaxed text-zinc-500">{nlqNote}</p>}
      </div>

      {/* 折叠的筛选区 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center justify-between border-t border-zinc-800 px-3 py-2 text-xs font-semibold text-zinc-400 hover:text-zinc-200"
      >
        <span className="flex items-center gap-1.5">
          <Network size={12} /> 筛选 · 视图 · 导出
        </span>
        <ChevronDown size={14} className={`transition-transform ${expanded ? "rotate-180" : ""}`} />
      </button>
      {expanded && (
        <div className="overflow-y-auto border-t border-zinc-800 p-3">
          <FilterContent data={data} />
        </div>
      )}
    </div>
  );
}
