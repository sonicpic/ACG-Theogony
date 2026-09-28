"use client";

/** 审核后台：LLM/众包关系候选的批准与驳回。 */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, RefreshCw, XCircle } from "lucide-react";
import { api } from "@/lib/api";
import { relColor, relLabel } from "@/lib/constants";
import type { RelationshipDTO } from "@/lib/types";

export default function ReviewPage() {
  const [token, setToken] = useState(typeof window !== "undefined" ? localStorage.getItem("reviewToken") || "" : "");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["review-pending"],
    queryFn: () => api.reviewPending(token),
    refetchInterval: 30000,
  });
  const { data: stats } = useQuery({ queryKey: ["stats"], queryFn: api.stats });

  const decide = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "approve" | "reject" }) =>
      api.reviewDecide(id, action, token),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-pending"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      api.refreshGraph().then(() => qc.invalidateQueries({ queryKey: ["graph"] }));
    },
  });

  const batch = useMutation({
    mutationFn: (action: "approve" | "reject") => {
      const decisions: Record<string, string> = {};
      (data?.items || [])
        .filter((r) => r.confidence === "high")
        .forEach((r) => (decisions[String(r.id)] = action));
      return api.reviewBatch(decisions, token);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["review-pending"] });
      api.refreshGraph().then(() => qc.invalidateQueries({ queryKey: ["graph"] }));
    },
  });

  function saveToken(v: string) {
    setToken(v);
    localStorage.setItem("reviewToken", v);
  }

  return (
    <main className="mx-auto max-w-4xl px-4 py-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-bold">关系审核队列</h1>
          <p className="text-xs text-zinc-500">
            LLM 挖掘与众包提交的关系在此人工把关；批准后立即进入图谱
            {stats ? ` · 待审 ${stats.pending} 条 / 已批准 ${stats.approved} 条` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input
            value={token}
            onChange={(e) => saveToken(e.target.value)}
            placeholder="审核令牌（未设则留空）"
            className="rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-xs outline-none"
          />
          <button
            onClick={() => qc.invalidateQueries({ queryKey: ["review-pending"] })}
            className="rounded-md bg-zinc-900 p-2 text-zinc-400 hover:bg-zinc-800"
            title="刷新"
          >
            <RefreshCw size={14} />
          </button>
        </div>
      </div>

      {batch.isIdle ? null : null}
      {(data?.items.length || 0) > 0 && (
        <div className="mb-3 flex gap-2 text-xs">
          <button
            onClick={() => batch.mutate("approve")}
            className="rounded-md bg-emerald-600/80 px-3 py-1.5 hover:bg-emerald-500"
          >
            一键批准全部高置信度（{data?.items.filter((r) => r.confidence === "high").length || 0}）
          </button>
          <button
            onClick={() => batch.mutate("reject")}
            className="rounded-md bg-zinc-800 px-3 py-1.5 text-zinc-300 hover:bg-zinc-700"
          >
            一键驳回高置信度
          </button>
        </div>
      )}

      {isLoading && <p className="py-10 text-center text-sm text-zinc-500">加载中…</p>}

      {!isLoading && (data?.items.length || 0) === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-16 text-center text-sm text-zinc-500">
          队列为空 —— 运行 <code className="rounded bg-zinc-900 px-1.5 py-0.5 text-xs">npm run mine</code>{" "}
          让 LLM 挖掘新关系，或在角色页提交众包关系
        </div>
      )}

      <div className="space-y-2">
        {(data?.items || []).map((r: RelationshipDTO) => (
          <div key={r.id} className="fade-up flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3">
            <div className="min-w-0">
              <div className="text-sm">
                <a href={`/character/${r.sourceId}`} className="text-zinc-100 hover:underline">
                  {r.sourceName}
                </a>
                <span className="mx-2" style={{ color: relColor(r.type) }}>
                  —{relLabel(r.type)}→
                </span>
                <a href={`/character/${r.targetId}`} className="text-zinc-100 hover:underline">
                  {r.targetName}
                </a>
              </div>
              <div className="mt-1 flex items-center gap-2 text-[11px] text-zinc-500">
                <span
                  className={`rounded px-1.5 py-0.5 ${
                    r.confidence === "high" ? "bg-emerald-900/60 text-emerald-300" : "bg-amber-900/50 text-amber-300"
                  }`}
                >
                  {r.confidence === "high" ? "高置信" : "中置信"}
                </span>
                <span>{r.origin === "llm" ? "LLM 挖掘" : r.origin === "user" ? "众包提交" : r.origin}</span>
                {r.evidence && <span className="truncate">依据：{r.evidence}</span>}
              </div>
            </div>
            <div className="flex shrink-0 gap-1.5">
              <button
                onClick={() => decide.mutate({ id: r.id, action: "approve" })}
                disabled={decide.isPending}
                className="flex items-center gap-1 rounded-md bg-emerald-600/80 px-3 py-1.5 text-xs font-medium hover:bg-emerald-500 disabled:opacity-50"
              >
                <CheckCircle2 size={13} /> 批准
              </button>
              <button
                onClick={() => decide.mutate({ id: r.id, action: "reject" })}
                disabled={decide.isPending}
                className="flex items-center gap-1 rounded-md bg-zinc-800 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
              >
                <XCircle size={13} /> 驳回
              </button>
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
