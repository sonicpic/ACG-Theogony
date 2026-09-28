"use client";

/** 每日猜角色（Wordle 式）：逐条线索揭示，6 次机会。 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Trophy } from "lucide-react";
import { api } from "@/lib/api";

export default function GamePage() {
  const { data, isLoading } = useQuery({ queryKey: ["daily"], queryFn: api.daily });
  const [attempts, setAttempts] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState<"playing" | "won" | "lost">("playing");
  const [answer, setAnswer] = useState<{ id: string; name: string } | null>(null);

  const guess = useMutation({
    mutationFn: (name: string) => api.guess(name),
    onSuccess: (res, name) => {
      if (res.correct) {
        setStatus("won");
        setAnswer({ id: res.answerId, name: res.answerName });
      } else if (!res.matchedId) {
        // 未匹配角色：不消耗次数
        setInput("");
      } else {
        setAttempts((a) => [...a, name]);
        setInput("");
        if ((data?.maxAttempts || 6) - attempts.length - 1 <= 0) {
          setStatus("lost");
          api.reveal().then((r) => setAnswer({ id: r.answerId, name: r.answerName }));
        }
      }
    },
  });

  const visibleClues = useMemo(() => {
    if (!data) return [] as string[];
    return data.allClues.slice(0, Math.min(data.allClues.length, 2 + attempts.length));
  }, [data, attempts]);

  if (isLoading || !data) {
    return <div className="py-20 text-center text-sm text-zinc-500">出题中…</div>;
  }

  const remaining = (data.maxAttempts || 6) - attempts.length;

  return (
    <main className="mx-auto max-w-2xl px-4 py-8">
      <div className="mb-1 flex items-center gap-2">
        <Trophy size={18} className="text-amber-400" />
        <h1 className="text-lg font-bold">每日猜角色</h1>
        <span className="text-xs text-zinc-500">{data.date}</span>
      </div>
      <p className="mb-6 text-xs text-zinc-500">
        根据逐条线索猜出今日英灵 · 每答错一次解锁一条新线索 · 共 {data.maxAttempts} 次机会
      </p>

      {/* 线索 */}
      <div className="mb-5 space-y-2">
        {visibleClues.map((clue, i) => (
          <div key={i} className="tile-flip rounded-lg border border-zinc-800 bg-zinc-900/50 px-4 py-2.5 text-sm text-zinc-200">
            <span className="mr-2 text-[10px] text-zinc-600">线索 {i + 1}</span>
            {clue}
          </div>
        ))}
      </div>

      {/* 尝试记录 */}
      {attempts.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {attempts.map((a, i) => (
            <span key={i} className="rounded-full bg-red-950/60 px-2.5 py-1 text-xs text-red-300">
              ✗ {a}
            </span>
          ))}
        </div>
      )}

      {status === "playing" && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            const name = input.trim();
            if (!name || attempts.includes(name)) return;
            guess.mutate(name);
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="输入角色名后回车"
            autoFocus
            className="flex-1 rounded-md border border-zinc-800 bg-zinc-900 px-3 py-2.5 text-sm outline-none focus:border-amber-500/50"
          />
          <button
            type="submit"
            disabled={guess.isPending}
            className="rounded-md bg-amber-600 px-5 text-sm font-semibold hover:bg-amber-500 disabled:opacity-50"
          >
            猜！
          </button>
        </form>
      )}
      {status === "playing" && guess.data && !guess.data.correct && guess.data.hint && (
        <p className="mt-2 text-xs text-zinc-500">{guess.data.hint}</p>
      )}

      {status !== "playing" && answer && (
        <div className="fade-up rounded-xl border border-amber-700/50 bg-gradient-to-br from-amber-950/40 to-zinc-900/60 p-5 text-center">
          <div className="text-sm text-zinc-400">{status === "won" ? "🎉 猜对了！今日角色是" : "答案是"}</div>
          <div className="mt-1 text-2xl font-bold text-amber-300">{answer.name}</div>
          <div className="mt-4 flex justify-center gap-2">
            <Link
              href={`/character/${answer.id}`}
              className="rounded-md bg-sky-600/80 px-4 py-2 text-sm font-medium hover:bg-sky-500"
            >
              查看星系图
            </Link>
            <button
              onClick={() => {
                const text = `【神谱图谱·每日猜角色 ${data.date}】我用了 ${attempts.length + 1} 次${status === "won" ? "猜中" : "没能猜中"}今日英灵！你也来试试 → localhost:3000/game`;
                navigator.clipboard.writeText(text);
                alert("战报已复制到剪贴板");
              }}
              className="rounded-md bg-zinc-800 px-4 py-2 text-sm text-zinc-200 hover:bg-zinc-700"
            >
              复制战报
            </button>
          </div>
        </div>
      )}

      {status === "playing" && (
        <p className="mt-4 text-center text-xs text-zinc-600">
          剩余机会：{"●".repeat(remaining)}
          {"○".repeat(Math.max(0, (data.maxAttempts || 6) - remaining))}
        </p>
      )}
    </main>
  );
}
