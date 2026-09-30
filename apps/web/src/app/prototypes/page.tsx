"use client";

/** 同源角色雷达：神话/历史原型 → 跨作品化身矩阵 + 改编作品。 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import { Radar, Search, GitCompare, X } from "lucide-react";
import { api } from "@/lib/api";
import { imgProxy } from "@/lib/types";
import { mythColor } from "@/lib/constants";
import { useGraphView } from "@/lib/store";

const KIND_LABEL: Record<string, string> = {
  anime: "动画",
  manga: "漫画",
  game: "游戏",
  novel: "小说",
  literature: "文学",
  film: "电影",
  tv: "电视剧",
  stage: "戏剧",
  art: "美术",
  other: "其他",
};

export default function PrototypesPage() {
  const router = useRouter();
  const select = useGraphView((s) => s.select);
  const focus = useGraphView((s) => s.focus);
  const { data, isLoading } = useQuery({
    queryKey: ["prototypes"],
    queryFn: api.prototypes,
    staleTime: Infinity,
  });
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const items = useMemo(() => {
    if (!data) return [];
    const kw = q.trim().toLowerCase();
    if (!kw) return data.items;
    return data.items.filter(
      (p) =>
        p.name.toLowerCase().includes(kw) ||
        p.mythology.includes(kw) ||
        p.fgo.some((f) => f.name.toLowerCase().includes(kw)) ||
        p.works.some((w) => w.name.toLowerCase().includes(kw))
    );
  }, [data, q]);

  const selected = items.find((p) => p.id === selectedId) || data?.items.find((p) => p.id === selectedId) || null;

  const { data: evo } = useQuery({
    queryKey: ["evolution", selectedId],
    queryFn: () => api.evolution(selectedId!),
    enabled: !!selectedId,
    staleTime: Infinity,
  });
  const [showEvo, setShowEvo] = useState(false);

  const openInGraph = (id: string) => {
    select(id);
    focus(id); // 显式定位：全景缩放 + 高亮
    router.push("/");
  };

  return (
    <main className="mx-auto max-w-7xl px-4 py-8">
      <div className="mb-1 flex items-center gap-2">
        <Radar size={18} className="text-sky-400" />
        <h1 className="text-lg font-bold">同源角色雷达</h1>
        <span className="text-xs text-zinc-500">{data ? `${data.items.length} 个原型` : "…"}</span>
      </div>
      <p className="mb-5 text-xs text-zinc-500">
        同一个神话/历史原型，在不同作品里被改编成了什么样子 —— 化身矩阵与改编谱系来自
        Wikidata 结构化数据（P144/P1074）
      </p>

      <div className="relative mb-5 max-w-md">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="搜原型 / 神话体系 / 作品名…"
          className="w-full rounded-lg border border-zinc-800 bg-zinc-900 py-2 pl-9 pr-3 text-sm outline-none placeholder:text-zinc-600 focus:border-sky-500/50"
        />
      </div>

      {isLoading && <div className="py-20 text-center text-sm text-zinc-500">装载原型宇宙…</div>}

      <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
        {/* 原型卡片网格 */}
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {items.map((p) => (
            <button
              key={p.id}
              onClick={() => setSelectedId(p.id === selectedId ? null : p.id)}
              className={clsx(
                "group rounded-xl border p-4 text-left transition-colors",
                p.id === selectedId
                  ? "border-sky-500/60 bg-sky-950/20"
                  : "border-zinc-800 bg-zinc-900/40 hover:border-zinc-600"
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-zinc-100 group-hover:text-white">{p.name}</div>
                  {p.mythology && (
                    <span
                      className="mt-1 inline-block rounded px-1.5 py-0.5 text-[10px] text-zinc-950"
                      style={{ background: mythColor(p.mythology) }}
                    >
                      {p.mythology}
                    </span>
                  )}
                </div>
                <div className="shrink-0 text-right text-[11px] text-zinc-500">
                  <div className="text-sky-300">{p.incarnationCount} 化身</div>
                  <div>{p.worksCount} 作品</div>
                </div>
              </div>
              {p.fgo.length > 0 && (
                <div className="mt-3 flex -space-x-2">
                  {p.fgo.slice(0, 6).map((f) =>
                    f.imageUrl ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        key={f.id}
                        src={imgProxy(f.imageUrl)}
                        alt={f.name}
                        title={f.name}
                        className="h-8 w-8 rounded-full border-2 border-zinc-900 object-cover"
                      />
                    ) : (
                      <span
                        key={f.id}
                        className="h-8 w-8 rounded-full border-2 border-zinc-900"
                        style={{ background: mythColor(p.mythology) }}
                      />
                    )
                  )}
                  {p.fgo.length > 6 && (
                    <span className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-zinc-900 bg-zinc-800 text-[10px] text-zinc-300">
                      +{p.fgo.length - 6}
                    </span>
                  )}
                </div>
              )}
            </button>
          ))}
          {items.length === 0 && !isLoading && (
            <div className="col-span-full py-16 text-center text-sm text-zinc-600">没有匹配的原型</div>
          )}
        </div>

        {/* 详情面板 */}
        {selected && (
          <aside className="fade-up h-fit rounded-xl border border-zinc-800 bg-zinc-900/50 p-4 lg:sticky lg:top-16">
            <div className="flex items-start justify-between">
              <div>
                <div className="text-lg font-bold text-zinc-100">{selected.name}</div>
                <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-500">
                  {selected.mythology && <span>{selected.mythology}</span>}
                  {selected.qid && (
                    <a
                      href={`https://www.wikidata.org/wiki/${selected.qid}`}
                      target="_blank"
                      rel="noreferrer"
                      className="text-sky-400 hover:underline"
                    >
                      {selected.qid}
                    </a>
                  )}
                </div>
              </div>
              <button onClick={() => setSelectedId(null)} className="text-zinc-500 hover:text-zinc-200">
                <X size={16} />
              </button>
            </div>

            <div className="mt-3 flex gap-2">
              <button
                onClick={() => openInGraph(selected.id)}
                className="flex-1 rounded-lg bg-sky-600/80 py-2 text-xs font-medium hover:bg-sky-500"
              >
                在图谱中查看
              </button>
              <button
                onClick={() => setShowEvo(!showEvo)}
                className={
                  "flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium " +
                  (showEvo ? "bg-amber-600/80" : "border border-zinc-700 text-zinc-300 hover:border-amber-500/60")
                }
              >
                <GitCompare size={12} /> 演化对比
              </button>
            </div>

            {showEvo && evo && evo.rows.length > 0 && (
              <section className="mt-4">
                <div className="mb-2 text-xs font-semibold text-zinc-400">
                  化身演化矩阵（{evo.rows.length} 个化身）
                </div>
                <div className="overflow-x-auto rounded-lg border border-zinc-800">
                  <table className="w-full text-left text-[11px]">
                    <thead>
                      <tr className="border-b border-zinc-800 bg-zinc-900/60 text-zinc-500">
                        <th className="px-2 py-1.5">化身</th>
                        <th className="px-2 py-1.5">性别</th>
                        <th className="px-2 py-1.5">职阶</th>
                        <th className="px-2 py-1.5">阵营</th>
                        <th className="px-2 py-1.5">来源</th>
                      </tr>
                    </thead>
                    <tbody>
                      {evo.rows.map((r) => (
                        <tr key={r.id} className="border-b border-zinc-800/50">
                          <td className="max-w-[140px] truncate px-2 py-1.5">
                            {r.source === "fgo" ? (
                              <Link href={`/character/${r.id}`} className="text-zinc-200 hover:text-sky-300">
                                {r.name}
                              </Link>
                            ) : (
                              <span className="text-zinc-400">{r.name}</span>
                            )}
                          </td>
                          <td className="px-2 py-1.5 text-zinc-300">{r.gender || "—"}</td>
                          <td className="px-2 py-1.5 text-amber-300/80">{r.className || "—"}</td>
                          <td className="px-2 py-1.5 text-zinc-400">{r.alignment || "—"}</td>
                          <td className="px-2 py-1.5">
                            <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                              {r.source === "fgo" ? "FGO" : r.media === "acg" ? "ACG" : "其他媒体"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {evo.rows.some((r) => r.works.length > 0) && (
                  <div className="mt-1.5 text-[10px] text-zinc-600">
                    {evo.rows.filter((r) => r.works.length > 0).slice(0, 3).map((r) =>
                      `${r.name}: ${r.works.slice(0, 2).join("、")}`).join(" ｜ ")}
                  </div>
                )}
              </section>
            )}

            {selected.fgo.length > 0 && (
              <section className="mt-4">
                <div className="mb-2 text-xs font-semibold text-zinc-400">
                  Fate/GO 化身（{selected.fgo.length}）
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {selected.fgo.map((f) => (
                    <Link
                      key={f.id}
                      href={`/character/${f.id}`}
                      className="flex items-center gap-1.5 rounded-full border border-zinc-700 py-0.5 pl-0.5 pr-2.5 text-[11px] text-zinc-300 transition-colors hover:border-sky-500/60 hover:text-sky-200"
                    >
                      {f.imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={imgProxy(f.imageUrl)} alt="" className="h-5 w-5 rounded-full object-cover" />
                      ) : (
                        <span className="h-5 w-5 rounded-full" style={{ background: mythColor(selected.mythology) }} />
                      )}
                      <span title={f.works?.map((w) => w.name).join("、")}>{f.name}</span>
                    </Link>
                  ))}
                </div>
              </section>
            )}

            {selected.others.length > 0 && (
              <section className="mt-4">
                <div className="mb-2 text-xs font-semibold text-zinc-400">
                  其他媒体化身（{selected.others.length}）
                </div>
                <div className="space-y-1.5">
                  {selected.others.map((o) => (
                    <div key={o.id} className="flex items-center justify-between gap-2 text-xs">
                      <span className="min-w-0 truncate text-zinc-200">
                        {o.name}
                        {o.works?.length > 0 && (
                          <span className="ml-1.5 text-[10px] text-zinc-500">
                            《{o.works[0].name}》
                            {o.works.length > 1 ? ` 等${o.works.length}部` : ""}
                          </span>
                        )}
                      </span>
                      <span className="shrink-0 rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] text-zinc-400">
                        {o.media === "acg" ? "ACG" : "影视/文学"}
                      </span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {selected.works.length > 0 && (
              <section className="mt-4">
                <div className="mb-2 text-xs font-semibold text-zinc-400">
                  改编作品（{selected.works.length}）
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {selected.works.slice(0, 24).map((w) => (
                    <span key={w.id} className="rounded-full border border-zinc-700 px-2 py-0.5 text-[11px] text-zinc-300">
                      {w.name}
                      <span className="ml-1 text-[9px] text-zinc-500">{KIND_LABEL[w.kind] || w.kind}</span>
                    </span>
                  ))}
                  {selected.works.length > 24 && (
                    <span className="py-0.5 text-[11px] text-zinc-500">+{selected.works.length - 24} 部</span>
                  )}
                </div>
              </section>
            )}
          </aside>
        )}
      </div>
    </main>
  );
}
