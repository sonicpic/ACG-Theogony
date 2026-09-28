"use client";

/** 众包关系提交表单（进入审核队列）。 */

import { useState } from "react";
import { Plus } from "lucide-react";
import { RELATION_META } from "@/lib/constants";
import { api } from "@/lib/api";

export function RelationEditor({ sourceId, sourceName }: { sourceId: string; sourceName: string }) {
  const [open, setOpen] = useState(false);
  const [targetName, setTargetName] = useState("");
  const [type, setType] = useState("ALLY_OF");
  const [evidence, setEvidence] = useState("");
  const [contributor, setContributor] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
    try {
      // 目标按名称搜索解析
      const res = await api.search(targetName.trim(), 5);
      const hit = res.hits.find((h) => h.character.name === targetName.trim()) || res.hits[0];
      if (!hit) throw new Error("找不到目标角色");
      await api.submitRelation({
        sourceId,
        targetId: hit.character.id,
        type,
        evidence: evidence || `${sourceName} 与 ${hit.character.name} 的${RELATION_META[type]?.label || type}关系`,
        contributor: contributor || "匿名",
      });
      setMsg("✓ 已提交审核队列，通过后将显示在图谱中");
      setTargetName("");
      setEvidence("");
    } catch (err) {
      setMsg(`提交失败：${(err as Error).message.slice(0, 100)}`);
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
      >
        <Plus size={13} /> 补充一条关系
      </button>
    );
  }

  return (
    <form onSubmit={submit} className="fade-up space-y-2 rounded-lg border border-zinc-800 bg-zinc-900/60 p-3">
      <div className="text-xs font-semibold text-zinc-300">为 {sourceName} 提交关系（待人工审核）</div>
      <div className="flex gap-2">
        <input
          value={targetName}
          onChange={(e) => setTargetName(e.target.value)}
          placeholder="对方角色名称"
          className="flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-sm outline-none"
        />
        <select
          value={type}
          onChange={(e) => setType(e.target.value)}
          className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1.5 text-sm"
        >
          {Object.entries(RELATION_META)
            .filter(([t]) => t !== "BELONGS_TO")
            .map(([t, m]) => (
              <option key={t} value={t}>
                {m.label}
              </option>
            ))}
        </select>
      </div>
      <input
        value={evidence}
        onChange={(e) => setEvidence(e.target.value)}
        placeholder="依据（可选，如：伊阿宋远征的同伴）"
        className="w-full rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-sm outline-none"
      />
      <div className="flex gap-2">
        <input
          value={contributor}
          onChange={(e) => setContributor(e.target.value)}
          placeholder="你的昵称（可选）"
          className="flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-sm outline-none"
        />
        <button
          type="submit"
          disabled={busy || !targetName.trim()}
          className="rounded-md bg-emerald-600 px-4 text-sm font-medium hover:bg-emerald-500 disabled:opacity-50"
        >
          {busy ? "…" : "提交"}
        </button>
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded-md bg-zinc-800 px-3 text-sm text-zinc-400 hover:bg-zinc-700"
        >
          收起
        </button>
      </div>
      {msg && <p className="text-xs text-zinc-400">{msg}</p>}
    </form>
  );
}
