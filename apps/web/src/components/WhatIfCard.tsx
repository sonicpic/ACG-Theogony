"use client";

/** What-if 对决推演卡片。 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Swords } from "lucide-react";
import { api } from "@/lib/api";

export function WhatIfCard({ selfId, selfName }: { selfId: string; selfName: string }) {
  const [opponent, setOpponent] = useState("");
  const [opponentId, setOpponentId] = useState<string | null>(null);

  const whatif = useMutation({
    mutationFn: async () => {
      const res = await api.search(opponent.trim(), 5);
      const hit = res.hits.find((h) => h.character.name === opponent.trim()) || res.hits[0];
      if (!hit) throw new Error("找不到对手");
      setOpponentId(hit.character.id);
      return api.whatif(selfId, hit.character.id);
    },
  });

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-zinc-300">
        <Swords size={13} className="text-red-400" />
        What-if 对决推演
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (opponent.trim()) whatif.mutate();
        }}
        className="flex gap-2"
      >
        <input
          value={opponent}
          onChange={(e) => setOpponent(e.target.value)}
          placeholder={`让 ${selfName} 和谁打一场？（如 吉尔伽美什）`}
          className="flex-1 rounded-md border border-zinc-800 bg-zinc-950 px-2.5 py-1.5 text-sm outline-none"
        />
        <button
          type="submit"
          disabled={whatif.isPending || !opponent.trim()}
          className="rounded-md bg-red-600/80 px-3 text-sm font-medium hover:bg-red-500 disabled:opacity-50"
        >
          {whatif.isPending ? "…" : "开打"}
        </button>
      </form>
      {whatif.isError && <p className="mt-2 text-xs text-red-400">{(whatif.error as Error).message.slice(0, 80)}</p>}
      {whatif.data && (
        <div className="fade-up mt-2.5 whitespace-pre-wrap rounded-md bg-zinc-950 p-3 text-xs leading-relaxed text-zinc-300">
          {whatif.data.narrative}
          {whatif.data.engine === "graph" && (
            <span className="mt-1.5 block text-[10px] text-zinc-600">· 模板生成（配置 LLM Key 后为完整剧情推演）</span>
          )}
        </div>
      )}
      {opponentId && whatif.data && (
        <a href={`/character/${opponentId}`} className="mt-1.5 inline-block text-[11px] text-sky-400 hover:underline">
          查看 {opponent} 的星系 →
        </a>
      )}
    </div>
  );
}
