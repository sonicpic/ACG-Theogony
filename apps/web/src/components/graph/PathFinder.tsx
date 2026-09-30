"use client";

/** 关系路径探索（六度分隔）：PathContent 供桌面卡与移动抽屉复用。 */

import { useMemo, useState } from "react";
import { ChevronDown, Route, X } from "lucide-react";
import { api } from "@/lib/api";
import type { GraphDTO, PathDTO } from "@/lib/types";
import { useGraphView } from "@/lib/store";

export function PathContent({ data }: { data: GraphDTO }) {
  const store = useGraphView();
  const [fromName, setFromName] = useState("");
  const [toName, setToName] = useState("");
  const [result, setResult] = useState<PathDTO | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const charNodes = useMemo(() => data.nodes.filter((n) => n.kind === "character"), [data.nodes]);

  function resolve(name: string): string | null {
    const q = name.trim();
    if (!q) return null;
    if (q.toLowerCase().startsWith("c") && /^\d+$/.test(q.slice(1))) return q;
    const exact = charNodes.find((n) => n.name === q);
    if (exact) return exact.id;
    const partial = charNodes.find((n) => n.name.includes(q));
    return partial?.id || null;
  }

  async function find(e: React.FormEvent) {
    e.preventDefault();
    const from = resolve(fromName);
    const to = resolve(toName);
    if (!from || !to) {
      setError("请输入两个都存在的角色名");
      setResult(null);
      return;
    }
    setBusy(true);
    setError("");
    try {
      const r = await api.paths(from, to);
      setResult(r);
      store.setPath(from, to, r);
      if (r.found) store.focus(r.nodes[Math.floor(r.nodes.length / 2)].id);
    } catch (err) {
      setError((err as Error).message.slice(0, 100));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <form onSubmit={find} className="space-y-2">
        <input
          value={fromName}
          onChange={(e) => setFromName(e.target.value)}
          placeholder="起点角色（如 吉尔伽美什）"
          list="path-characters"
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-emerald-500/50"
        />
        <input
          value={toName}
          onChange={(e) => setToName(e.target.value)}
          placeholder="终点角色（如 项羽）"
          list="path-characters"
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-emerald-500/50"
        />
        <datalist id="path-characters">
          {charNodes.slice(0, 200).map((n) => (
            <option key={n.id} value={n.name} />
          ))}
        </datalist>
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-lg bg-emerald-600/80 py-2 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? "探索中…" : "找到 TA 们的关系"}
        </button>
      </form>

      {error && <p className="mt-2 text-xs text-red-400">{error}</p>}

      {result && (
        <div className="fade-up mt-3 border-t border-zinc-800 pt-2.5">
          {result.found ? (
            <>
              <div className="text-xs text-zinc-400">
                最短路径：<span className="font-semibold text-emerald-400">{result.distance}</span> 步
              </div>
              <ol className="mt-2 space-y-1 text-xs">
                {result.nodes.map((n, i) => (
                  <li key={n.id} className="flex flex-wrap items-center gap-1.5">
                    <button
                      onClick={() => store.select(n.id)}
                      className="rounded px-1 py-0.5 text-sky-300 hover:bg-sky-500/10"
                    >
                      {n.name}
                    </button>
                    {result.steps[i] && (
                      <span className="text-[10px] text-zinc-500">—{result.steps[i].label}→</span>
                    )}
                  </li>
                ))}
              </ol>
            </>
          ) : (
            <p className="text-xs text-zinc-500">两人在已审核关系图中不连通（可等 LLM 挖掘更多关系后重试）。</p>
          )}
          <button
            onClick={() => {
              setResult(null);
              store.setPath(null, null, null);
            }}
            className="mt-2 flex items-center gap-1 text-[11px] text-zinc-500 hover:text-zinc-300"
          >
            <X size={11} /> 清除路径
          </button>
        </div>
      )}
    </div>
  );
}

/** 桌面版折叠卡：开合状态走 store（点边时自动展开） */
export function PathFinder({ data }: { data: GraphDTO }) {
  const open = useGraphView((s) => s.pathPanelOpen);
  const setOpen = useGraphView((s) => s.setPathPanelOpen);
  return (
    <div className="pointer-events-auto absolute right-3 top-3 z-20 hidden w-[300px] overflow-hidden rounded-xl border border-zinc-800 bg-zinc-950/95 shadow-2xl backdrop-blur md:block">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between px-3 py-2.5 text-sm font-semibold hover:text-sky-300"
      >
        <span className="flex items-center gap-1.5">
          <Route size={14} className="text-emerald-400" /> 关系路径探索
        </span>
        <ChevronDown size={14} className={`text-zinc-500 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="border-t border-zinc-800 p-3">
          <PathContent data={data} />
        </div>
      )}
    </div>
  );
}
