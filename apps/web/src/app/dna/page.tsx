"use client";

/** 我的 ACG 神话 DNA：选择喜欢的角色 → 神话谱系分布 + 同源洞察 + 守护神 + 分享卡。 */

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Dna, Search, Shuffle, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import { imgProxy } from "@/lib/types";
import { mythColor } from "@/lib/constants";

const STORAGE_KEY = "theogony-dna-selection";

function loadSelection(): string[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
  } catch {
    return [];
  }
}

export default function DnaPage() {
  const { data } = useQuery({ queryKey: ["graph", "full"], queryFn: () => api.graph({ includeMythNodes: true }), staleTime: Infinity });
  const [selected, setSelected] = useState<string[]>(loadSelection);
  const [query, setQuery] = useState("");

  const nodes = useMemo(() => new Map((data?.nodes || []).map((n) => [n.id, n])), [data]);

  const persist = (ids: string[]) => {
    setSelected(ids);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
  };

  const toggle = (id: string) =>
    persist(selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id]);

  const randomize = () => {
    const chars = (data?.nodes || []).filter((n) => n.kind === "character" && n.className !== "原型" && n.className !== "神话人物" && n.mythology);
    const pool = [...chars].sort(() => Math.random() - 0.5).slice(0, 20);
    persist(pool.map((n) => n.id));
  };

  const searchHits = useMemo(() => {
    const kw = query.trim().toLowerCase();
    if (!kw || !data) return [];
    return data.nodes
      .filter((n) => n.kind === "character" && n.className !== "原型" && n.className !== "神话人物" && n.name.toLowerCase().includes(kw))
      .slice(0, 8);
  }, [query, data]);

  // ── DNA 计算 ──
  const analysis = useMemo(() => {
    if (!data || selected.length === 0) return null;
    const sel = selected.map((id) => nodes.get(id)).filter(Boolean);
    const dist = new Map<string, number>();
    for (const n of sel) dist.set(n!.mythology || "未归类", (dist.get(n!.mythology || "未归类") || 0) + 1);

    // 同源组：选中角色经 DERIVED_FROM 汇聚到同一原型
    const protoOf = new Map<string, string>(); // charId → protoId
    for (const l of data.links) {
      if (l.type === "DERIVED_FROM" && nodes.has(l.source) && nodes.has(l.target)) {
        const t = nodes.get(l.target)!;
        if (t.className === "原型") protoOf.set(l.source, l.target);
      }
    }
    const groups = new Map<string, string[]>();
    for (const n of sel) {
      const pid = protoOf.get(n!.id);
      if (pid) groups.set(pid, [...(groups.get(pid) || []), n!.id]);
    }
    const sameProto = [...groups.entries()]
      .filter(([, ids]) => ids.length >= 2)
      .map(([pid, ids]) => ({ proto: nodes.get(pid)?.name || pid, members: ids.map((i) => nodes.get(i)?.name || "") }));

    // 守护神：选中角色汇聚最多的原型（并列随机）
    const ranked = [...groups.entries()].sort((a, b) => b[1].length - a[1].length);
    const guardian = ranked.length
      ? { name: nodes.get(ranked[0][0])?.name || "", mythology: nodes.get(ranked[0][0])?.mythology || "", count: ranked[0][1].length }
      : null;

    const classDist = new Map<string, number>();
    for (const n of sel) if (n!.className) classDist.set(n!.className, (classDist.get(n!.className) || 0) + 1);
    const topClasses = [...classDist.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);

    const diversity = +(dist.size / Math.max(1, sel.length)).toFixed(2);
    return {
      total: sel.length,
      dist: [...dist.entries()].sort((a, b) => b[1] - a[1]),
      sameProto,
      guardian,
      topClasses,
      diversity,
    };
  }, [data, selected, nodes]);

  const shareText = analysis
    ? `【我的 ACG 神话 DNA】分析了 ${analysis.total} 个本命角色：` +
      analysis.dist.slice(0, 3).map(([m, n]) => `${m} ${Math.round((n / analysis.total) * 100)}%`).join(" · ") +
      (analysis.guardian ? `｜二次元守护神：${analysis.guardian.name}` : "") +
      " → 来测测你的：/dna"
    : "";

  return (
    <main className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-1 flex items-center gap-2">
        <Dna size={18} className="text-violet-400" />
        <h1 className="text-lg font-bold">我的 ACG 神话 DNA</h1>
      </div>
      <p className="mb-6 text-xs text-zinc-500">
        选出你喜欢的角色（或随机 20 个），看看你的二次元审美背后是哪些神话谱系
      </p>

      {/* 选择器 */}
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="搜索角色加入分析…"
            className="w-full rounded-lg border border-zinc-800 bg-zinc-900 py-2 pl-9 pr-3 text-sm outline-none placeholder:text-zinc-600 focus:border-violet-500/50"
          />
          {searchHits.length > 0 && (
            <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 shadow-xl">
              {searchHits.map((n) => (
                <button
                  key={n.id}
                  onClick={() => { toggle(n.id); setQuery(""); }}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-zinc-200 hover:bg-zinc-900"
                >
                  {n.imageUrl ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={imgProxy(n.imageUrl)} alt="" className="h-6 w-6 rounded-full object-cover" />
                  ) : (
                    <span className="h-6 w-6 rounded-full" style={{ background: mythColor(n.mythology) }} />
                  )}
                  {n.name}
                  <span className="ml-auto text-[10px] text-zinc-500">{n.mythology}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <button onClick={randomize} className="flex items-center gap-1.5 rounded-lg border border-zinc-700 px-3 py-2 text-xs text-zinc-300 hover:border-violet-500/60 hover:text-violet-200">
          <Shuffle size={12} /> 随机 20 个
        </button>
        {selected.length > 0 && (
          <button onClick={() => persist([])} className="flex items-center gap-1.5 rounded-lg border border-zinc-800 px-3 py-2 text-xs text-zinc-500 hover:text-red-300">
            <Trash2 size={12} /> 清空
          </button>
        )}
      </div>

      {/* 已选 chips */}
      {selected.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-1.5">
          {selected.map((id) => {
            const n = nodes.get(id);
            if (!n) return null;
            return (
              <button key={id} onClick={() => toggle(id)} className="group flex items-center gap-1.5 rounded-full border border-zinc-700 py-0.5 pl-0.5 pr-2.5 text-[11px] text-zinc-300 hover:border-red-500/50">
                {n.imageUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={imgProxy(n.imageUrl)} alt="" className="h-5 w-5 rounded-full object-cover" />
                ) : (
                  <span className="h-5 w-5 rounded-full" style={{ background: mythColor(n.mythology) }} />
                )}
                {n.name}
                <span className="text-zinc-600 group-hover:hidden">×</span>
              </button>
            );
          })}
        </div>
      )}

      {!analysis && selected.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-20 text-center text-sm text-zinc-600">
          还没有选择角色 —— 搜索加入，或点「随机 20 个」
        </div>
      )}

      {/* 结果 */}
      {analysis && (
        <div className="space-y-5">
          <section className="rounded-xl border border-zinc-800 bg-gradient-to-br from-violet-950/30 to-zinc-900/40 p-5">
            <div className="mb-3 text-xs font-semibold text-zinc-400">神话谱系分布（{analysis.total} 个角色）</div>
            <div className="space-y-2">
              {analysis.dist.map(([m, n]) => (
                <div key={m} className="flex items-center gap-3 text-xs">
                  <span className="w-24 shrink-0 truncate text-right text-zinc-300">{m}</span>
                  <div className="h-3.5 flex-1 overflow-hidden rounded-full bg-zinc-800/60">
                    <div
                      className="h-full rounded-full transition-all"
                      style={{ width: `${(n / analysis.total) * 100}%`, background: mythColor(m) }}
                    />
                  </div>
                  <span className="w-14 shrink-0 tabular-nums text-zinc-400">
                    {Math.round((n / analysis.total) * 100)}% · {n}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-3 text-[11px] text-zinc-500">谱系多样性：{analysis.diversity}（1.0 = 每个角色来自不同神话）</div>
          </section>

          {analysis.guardian && (
            <section className="rounded-xl border border-violet-700/40 bg-violet-950/20 p-5 text-center">
              <div className="text-xs text-zinc-400">你的二次元守护神</div>
              <div className="mt-1 text-2xl font-bold text-violet-200">{analysis.guardian.name}</div>
              <div className="mt-1 text-[11px] text-zinc-500">
                {analysis.guardian.mythology} · 你喜欢的 {analysis.guardian.count} 个角色都是 TA 的化身
              </div>
            </section>
          )}

          {analysis.sameProto.length > 0 && (
            <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <div className="mb-2 text-xs font-semibold text-zinc-400">隐藏亲缘（你选的角色里，藏着同一个人）</div>
              <div className="space-y-1.5">
                {analysis.sameProto.map((g, i) => (
                  <div key={i} className="text-xs text-zinc-300">
                    <span className="text-sky-300">{g.proto}</span> 的化身：{g.members.join("、")}
                  </div>
                ))}
              </div>
            </section>
          )}

          {analysis.topClasses.length > 0 && (
            <section className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5">
              <div className="mb-2 text-xs font-semibold text-zinc-400">职阶偏好 Top3</div>
              <div className="flex flex-wrap gap-1.5">
                {analysis.topClasses.map(([c, n]) => (
                  <span key={c} className="rounded-full bg-zinc-800 px-2.5 py-1 text-[11px] text-zinc-300">
                    {c} × {n}
                  </span>
                ))}
              </div>
            </section>
          )}

          <button
            onClick={() => {
              navigator.clipboard.writeText(shareText);
              alert("战报已复制到剪贴板");
            }}
            className={clsx(
              "w-full rounded-lg bg-gradient-to-r from-violet-600 to-sky-600 py-2.5 text-sm font-medium",
              "hover:opacity-90"
            )}
          >
            复制我的神话 DNA 战报
          </button>
        </div>
      )}
    </main>
  );
}
