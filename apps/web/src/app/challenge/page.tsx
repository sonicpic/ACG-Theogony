"use client";

/** 每日六度挑战：把两个看似无关的角色用尽量少的步数连起来（只用角色间关系，不走神话枢纽）。 */

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Link2, Lightbulb, RotateCcw } from "lucide-react";
import { api } from "@/lib/api";
import { imgProxy } from "@/lib/types";
import { mythColor } from "@/lib/constants";

/** date 种子伪随机（与后端猜角色同思路，前端确定性选题） */
function seededPick<T>(arr: T[], seed: string): T {
  let h = 2166136261;
  for (let i = 0; i < seed.length; i++) {
    h ^= seed.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return arr[Math.abs(h) % arr.length];
}

/** BFS：起点到全图的最短跳数与前驱 */
function bfs(adj: Map<string, string[]>, start: string) {
  const dist = new Map([[start, 0]]);
  const prev = new Map<string, string>();
  const queue = [start];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const next of adj.get(cur) || []) {
      if (!dist.has(next)) {
        dist.set(next, dist.get(cur)! + 1);
        prev.set(next, cur);
        queue.push(next);
      }
    }
  }
  return { dist, prev };
}

function reconstruct(prev: Map<string, string>, from: string, to: string): string[] {
  const path = [to];
  let cur = to;
  while (cur !== from) {
    cur = prev.get(cur)!;
    path.unshift(cur);
  }
  return path;
}

function EndpointCard({ n, label }: { n: { name: string; mythology: string | null; imageUrl: string }; label: string }) {
  return (
    <div className="flex-1 rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 text-center">
      <div className="text-[10px] text-zinc-500">{label}</div>
      {n.imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imgProxy(n.imageUrl)} alt="" className="mx-auto mt-2 h-16 w-16 rounded-full border-2 border-zinc-700 object-cover" />
      ) : (
        <div className="mx-auto mt-2 h-16 w-16 rounded-full border-2 border-zinc-700" style={{ background: mythColor(n.mythology) }} />
      )}
      <div className="mt-2 font-semibold text-zinc-100">{n.name}</div>
      <div className="text-[10px] text-zinc-500">{n.mythology}</div>
    </div>
  );
}

export default function ChallengePage() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const doneKey = `theogony-challenge-${today}`;
  const { data } = useQuery({
    queryKey: ["graph", "full"],
    queryFn: () => api.graph({ includeMythNodes: true }),
    staleTime: Infinity,
  });

  // 角色邻接（排除 BELONGS_TO：神话枢纽会让一切两步可达）
  const { nodes, adj, edgeSet } = useMemo(() => {
    const nodes = new Map((data?.nodes || []).map((n) => [n.id, n]));
    const adj = new Map<string, string[]>();
    const edgeSet = new Set<string>();
    for (const l of data?.links || []) {
      if (l.type === "BELONGS_TO") continue;
      const s = String(l.source);
      const t = String(l.target);
      adj.set(s, [...(adj.get(s) || []), t]);
      adj.set(t, [...(adj.get(t) || []), s]);
      edgeSet.add(`${s}>${t}`);
      edgeSet.add(`${t}>${s}`);
    }
    return { nodes, adj, edgeSet };
  }, [data]);

  // 每日题目：距离 3-5 的确定性角色对
  const puzzle = useMemo(() => {
    if (!data || adj.size === 0) return null;
    const chars = data.nodes.filter((n) => n.kind === "character" && n.className !== "原型" && (adj.get(n.id)?.length || 0) >= 2);
    for (let attempt = 0; attempt < 12; attempt++) {
      const from = seededPick(chars, `${today}-from-${attempt}`);
      const { dist, prev } = bfs(adj, from.id);
      const candidates = [...dist.entries()].filter(([id, d]) => {
        if (d < 3 || d > 5) return false;
        const n = nodes.get(id);
        return n && n.kind === "character" && n.className !== "原型" && id !== from.id;
      });
      if (candidates.length >= 3) {
        const [toId] = seededPick(candidates, `${today}-to-${attempt}`);
        return { from: from.id, to: toId, optimal: reconstruct(prev, from.id, toId).length - 1, prev };
      }
    }
    return null;
  }, [data, adj, nodes, today]);

  const [rawChain, setRawChain] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [hints, setHints] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [done, setDone] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const suggestions = useMemo(() => {
    const kw = query.trim().toLowerCase();
    if (!kw) return [];
    return [...nodes.values()]
      .filter((n) => n.kind === "character" && n.name.toLowerCase().includes(kw))
      .sort((a, b) => (a.className === "原型" ? 1 : 0) - (b.className === "原型" ? 1 : 0))
      .slice(0, 7);
  }, [query, nodes]);

  useEffect(() => {
    // localStorage 读取（SSR 后客户端同步）
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDone(localStorage.getItem(doneKey) === "1");
  }, [doneKey]);

  if (!data) {
    return <div className="py-20 text-center text-sm text-zinc-500">装载图谱…</div>;
  }
  if (!puzzle) {
    return <div className="py-20 text-center text-sm text-zinc-500">今日题目生成失败，明天再来</div>;
  }
  const pz = puzzle;
  const chain = rawChain.length ? rawChain : [pz.from];

  const fromN = nodes.get(pz.from)!;
  const toN = nodes.get(pz.to)!;
  const current = chain[chain.length - 1];
  const currentN = nodes.get(current)!;



  const optimalPath = revealed ? reconstruct(pz.prev, pz.from, pz.to) : null;

  function submitGuess(id: string) {
    if (id === current) return;
    if (!edgeSet.has(`${current}>${id}`)) {
      setError(`「${nodes.get(id)?.name}」与「${currentN.name}」之间没有关系边，换个思路`);
      setQuery("");
      return;
    }
    setError("");
    setQuery("");
    const next = [...chain, id];
    setRawChain(next);
    // 到达任一同名化身即胜利（FGO 多版本常同名）
    if (id === pz.to || nodes.get(id)?.name === toN.name) {
      setDone(true);
      localStorage.setItem(doneKey, "1");
    }
  }

  function useHint() {
    if (revealed || done) return;
    // 揭示最优路径的下一跳
    const { prev } = bfs(adj, pz.to);
    let cur = current;
    const rev: string[] = [];
    while (cur !== pz.to) {
      cur = prev.get(cur)!;
      rev.unshift(cur);
    }
    const nextHop = rev[0];
    if (nextHop) {
      setHints((h) => h + 1);
      setError(`💡 提示：试着找「${nodes.get(nextHop)?.name}」`);
    }
  }

  function reset() {
    setRawChain([pz.from]);
    setError("");
    setQuery("");
  }


  return (
    <main className="mx-auto max-w-3xl px-4 py-8">
      <div className="mb-1 flex items-center gap-2">
        <Link2 size={18} className="text-emerald-400" />
        <h1 className="text-lg font-bold">每日六度挑战</h1>
        <span className="text-xs text-zinc-500">{today}</span>
      </div>
      <p className="mb-6 text-xs text-zinc-500">
        用尽量少的步数把两个角色连起来 —— 每步的两个角色之间必须有直接关系
        （含「同原型」链），走神话枢纽不算。最优 {pz.optimal} 步。
      </p>

      <div className="mb-5 flex items-center gap-3">
        <EndpointCard n={fromN} label="起点" />
        <div className="text-2xl text-zinc-600">→</div>
        <EndpointCard n={toN} label="终点" />
      </div>

      {/* 路径链 */}
      <div className="mb-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
        <div className="mb-2 flex items-center justify-between text-xs text-zinc-500">
          <span>当前路径：{chain.length - 1} 步{hints > 0 ? ` · 提示 ${hints} 次` : ""}</span>
          <button onClick={reset} className="flex items-center gap-1 hover:text-zinc-200">
            <RotateCcw size={11} /> 重走
          </button>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 text-xs">
          {chain.map((id, i) => {
            const n = nodes.get(id)!;
            return (
              <span key={i} className="flex items-center gap-1.5">
                {i > 0 && <span className="text-zinc-600">→</span>}
                <button
                  onClick={() => i < chain.length - 1 && setRawChain(chain.slice(0, i + 1))}
                  className={clsx(
                    "rounded-full px-2.5 py-1",
                    id === pz.to
                      ? "bg-emerald-600/30 text-emerald-200"
                      : id === pz.from
                        ? "bg-sky-600/20 text-sky-200"
                        : "bg-zinc-800 text-zinc-300"
                  )}
                  title={i < chain.length - 1 ? "截断到这里" : undefined}
                >
                  {n.name}
                </button>
              </span>
            );
          })}
        </div>
      </div>

      {done ? (
        <div className="rounded-xl border border-emerald-700/50 bg-emerald-950/30 p-4 text-center">
          <div className="text-sm font-semibold text-emerald-200">
            🎉 到达！用了 {chain.length - 1} 步（最优 {pz.optimal} 步）
            {hints > 0 && `，${hints} 次提示`}
          </div>
          <button
            onClick={() => {
              const text = `【神谱图谱·六度挑战 ${today}】${fromN.name} → ${toN.name}，我用 ${chain.length - 1} 步连起来了（最优 ${pz.optimal}）！ → /challenge`;
              navigator.clipboard.writeText(text);
              alert("战报已复制");
            }}
            className="mt-3 rounded-lg bg-emerald-600/80 px-4 py-2 text-xs font-medium hover:bg-emerald-500"
          >
            复制战报
          </button>
        </div>
      ) : (
        <div className="relative">
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`从「${currentN.name}」出发，下一站是…`}
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-2.5 text-sm outline-none placeholder:text-zinc-600 focus:border-emerald-500/50"
          />
          {suggestions.length > 0 && (
            <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 shadow-xl">
              {suggestions.map((n) => {
                const linked = edgeSet.has(`${current}>${n.id}`);
                return (
                  <button
                    key={n.id}
                    onClick={() => submitGuess(n.id)}
                    className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900"
                  >
                    <span className={clsx("h-1.5 w-1.5 rounded-full", linked ? "bg-emerald-400" : "bg-zinc-600")} />
                    {n.name}
                    {n.className === "原型" && <span className="text-[9px] text-amber-400/80">原型</span>}
                    <span className="ml-auto text-[10px] text-zinc-500">{n.mythology}</span>
                  </button>
                );
              })}
            </div>
          )}
          {error && <p className="mt-2 text-xs text-amber-400">{error}</p>}
          <div className="mt-3 flex gap-2">
            <button onClick={useHint} className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-amber-500/60 hover:text-amber-200">
              <Lightbulb size={12} /> 提示下一跳
            </button>
            <button onClick={() => setRevealed(true)} className="rounded-lg border border-zinc-800 px-3 py-2 text-xs text-zinc-500 hover:text-zinc-200">
              揭示最优路径
            </button>
          </div>
        </div>
      )}

      {optimalPath && (
        <div className="mt-4 rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-xs text-zinc-400">
          最优路径（{pz.optimal} 步）：
          <div className="mt-2 flex flex-wrap items-center gap-1">
            {optimalPath.map((id, i) => (
              <span key={i} className="flex items-center gap-1">
                {i > 0 && <span className="text-zinc-600">→</span>}
                <span className={clsx("rounded-full bg-zinc-800 px-2 py-0.5 text-zinc-300", id === pz.to && "text-emerald-300")}>
                  {nodes.get(id)?.name}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}
    </main>
  );
}
