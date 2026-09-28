"use client";

/** 数据质量看板。 */

import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api";
import { MYTHOLOGY_COLORS, mythColor, relColor, relLabel } from "@/lib/constants";

export default function StatsPage() {
  const { data } = useQuery({ queryKey: ["stats"], queryFn: api.stats, refetchInterval: 60000 });

  if (!data) return <div className="py-20 text-center text-sm text-zinc-500">加载中…</div>;

  const relData = Object.entries(data.relationDist).map(([k, v]) => ({ name: relLabel(k), key: k, count: v }));
  const mythData = Object.entries(data.mythologyDist)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([k, v]) => ({ name: k, count: v }));
  const confData = Object.entries(data.confidenceDist).map(([k, v]) => ({ name: k, count: v }));
  const originData = Object.entries(data.originDist).map(([k, v]) => ({
    name: k === "manual" ? "人工" : k === "llm" ? "LLM" : k === "user" ? "众包" : k,
    count: v,
  }));

  const cards = [
    { label: "角色总数", value: data.characters, color: "text-sky-400" },
    { label: "关系总数", value: data.relationships, color: "text-amber-400" },
    { label: "已批准", value: data.approved, color: "text-emerald-400" },
    { label: "待审核", value: data.pending, color: "text-rose-400" },
    { label: "LLM 已增强", value: data.enriched, color: "text-violet-400" },
    { label: "孤立节点", value: data.orphanNodes, color: "text-zinc-400" },
    { label: "缺神话归属", value: data.missingMythology, color: "text-orange-400" },
    { label: "缺描述", value: data.missingDescription, color: "text-yellow-400" },
  ];

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <h1 className="mb-1 text-lg font-bold">数据质量看板</h1>
      <p className="mb-5 text-xs text-zinc-500">数据飞轮的仪表盘：增强覆盖率、审核积压、孤立节点趋势</p>

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
            <div className="text-xs text-zinc-500">{c.label}</div>
            <div className={`mt-1 text-2xl font-bold ${c.color}`}>{c.value}</div>
          </div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="关系类型分布">
          <BarChart data={relData}>
            <XAxis dataKey="name" tick={{ fill: "#a1a1aa", fontSize: 11 }} />
            <YAxis tick={{ fill: "#a1a1aa", fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
              labelStyle={{ color: "#e4e4e7" }}
            />
            <Bar dataKey="count" radius={[4, 4, 0, 0]}>
              {relData.map((d) => (
                <Cell key={d.key} fill={relColor(d.key)} />
              ))}
            </Bar>
          </BarChart>
        </ChartCard>

        <ChartCard title="神话体系分布（Top 12）">
          <BarChart data={mythData} layout="vertical">
            <XAxis type="number" tick={{ fill: "#a1a1aa", fontSize: 11 }} allowDecimals={false} />
            <YAxis type="category" dataKey="name" width={110} tick={{ fill: "#a1a1aa", fontSize: 11 }} />
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
              labelStyle={{ color: "#e4e4e7" }}
            />
            <Bar dataKey="count" radius={[0, 4, 4, 0]}>
              {mythData.map((d) => (
                <Cell key={d.name} fill={mythColor(d.name) || MYTHOLOGY_COLORS["其他"]} />
              ))}
            </Bar>
          </BarChart>
        </ChartCard>

        <ChartCard title="置信度构成">
          <PieChart>
            <Pie
              data={confData}
              dataKey="count"
              nameKey="name"
              label={({ name }) => name}
              labelLine={false}
            >
              {confData.map((d) => (
                <Cell
                  key={d.name}
                  fill={
                    d.name === "verified" ? "#10b981" : d.name === "high" ? "#22d3ee" : d.name === "medium" ? "#f59e0b" : "#71717a"
                  }
                />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
            />
          </PieChart>
        </ChartCard>

        <ChartCard title="数据来源构成">
          <PieChart>
            <Pie data={originData} dataKey="count" nameKey="name" label={({ name }) => name} labelLine={false}>
              {originData.map((d) => (
                <Cell key={d.name} fill={d.name === "人工" ? "#818cf8" : d.name === "LLM" ? "#c084fc" : "#34d399"} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ background: "#18181b", border: "1px solid #3f3f46", borderRadius: 8 }}
            />
          </PieChart>
        </ChartCard>
      </div>
    </main>
  );
}

function ChartCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
      <div className="mb-3 text-sm font-semibold text-zinc-300">{title}</div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          {children as never}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
