"use client";

/** GraphRAG 问答面板：图检索 + LLM 生成，答案高亮图谱子图。 */

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Bot, Send, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import { useGraphView } from "@/lib/store";
import type { AskResponse } from "@/lib/types";

interface QA {
  q: string;
  a: AskResponse;
}

export function AskPanel() {
  const store = useGraphView();
  const [input, setInput] = useState("");
  const [history, setHistory] = useState<QA[]>([]);
  const listRef = useRef<HTMLDivElement>(null);

  const ask = useMutation({
    mutationFn: (question: string) => api.ask(question),
    onSuccess: (a, question) => {
      setHistory((h) => [...h, { q: question, a }]);
      if (a.subgraph?.nodes.length) {
        store.setAskIds(a.subgraph.nodes.filter((n) => n.kind === "character").map((n) => n.id));
        if (a.subgraph.nodes[0]) store.focus(a.subgraph.nodes[0].id);
      }
      setTimeout(() => listRef.current?.scrollTo({ top: 999999, behavior: "smooth" }), 50);
    },
    onError: (e) => {
      setHistory((h) => [...h, { q: input, a: { answer: `调用失败：${(e as Error).message.slice(0, 100)}`, citations: [], subgraph: null, engine: "error" } }]);
    },
  });

  if (!store.askOpen) {
    return (
      <button
        onClick={() => store.setAskOpen(true)}
        className="pointer-events-auto absolute bottom-4 right-4 z-20 flex items-center gap-2 rounded-full bg-gradient-to-r from-violet-600 to-sky-600 px-4 py-2.5 text-sm font-medium shadow-lg shadow-violet-900/40 hover:brightness-110"
      >
        <Sparkles size={16} />
        问问图谱
      </button>
    );
  }

  return (
    <div className="pointer-events-auto absolute bottom-3 right-3 z-30 flex h-[440px] w-[360px] flex-col rounded-xl border border-zinc-800 bg-zinc-950/97 shadow-2xl backdrop-blur">
      <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2.5">
        <div className="flex items-center gap-1.5 text-sm font-semibold">
          <Bot size={15} className="text-violet-400" />
          GraphRAG 问答
          <span className="text-[10px] font-normal text-zinc-500">图检索 + LLM</span>
        </div>
        <div className="flex items-center gap-2">
          {store.askIds && (
            <button
              onClick={() => store.setAskIds(null)}
              className="text-[11px] text-zinc-500 hover:text-zinc-300"
            >
              清除高亮
            </button>
          )}
          <button onClick={() => store.setAskOpen(false)} className="text-zinc-500 hover:text-zinc-200">
            <X size={15} />
          </button>
        </div>
      </div>

      <div ref={listRef} className="flex-1 space-y-3 overflow-y-auto p-3 text-sm">
        {history.length === 0 && (
          <div className="space-y-2 text-xs text-zinc-500">
            <p>直接问神话关系，例如：</p>
            {["阿尔托莉雅和莫德雷德是什么关系？", "谁和赫克托尔交过手？", "介绍一下吉尔伽美什的盟友"].map((s) => (
              <button
                key={s}
                onClick={() => ask.mutate(s)}
                className="block w-full rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-1.5 text-left text-zinc-300 hover:border-violet-600/50"
              >
                {s}
              </button>
            ))}
          </div>
        )}
        {history.map(({ q, a }, i) => (
          <div key={i} className="space-y-1.5">
            <div className="ml-auto w-fit max-w-[85%] rounded-lg bg-sky-600/20 px-2.5 py-1.5 text-sky-100">{q}</div>
            <div className="max-w-[92%] whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-900 px-2.5 py-2 leading-relaxed text-zinc-200">
              {a.answer}
              {a.engine === "graph" && (
                <span className="mt-1.5 block text-[10px] text-zinc-500">· 纯图检索回答（配置 LLM Key 后升级为生成式回答）</span>
              )}
              {a.citations.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {a.citations.slice(0, 10).map((c) => (
                    <button
                      key={c.id + c.relation}
                      onClick={() => store.select(c.id)}
                      className="rounded-full bg-zinc-800 px-2 py-0.5 text-[10px] text-zinc-300 hover:bg-zinc-700"
                    >
                      {c.name}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {ask.isPending && <div className="text-xs text-zinc-500">检索图谱中…</div>}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!input.trim()) return;
          ask.mutate(input.trim());
          setInput("");
        }}
        className="flex gap-2 border-t border-zinc-800 p-2.5"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="问点神话八卦…"
          className="flex-1 rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-2 text-sm outline-none placeholder:text-zinc-600 focus:border-violet-500/50"
        />
        <button
          type="submit"
          disabled={ask.isPending}
          className="rounded-md bg-violet-600 px-3 hover:bg-violet-500 disabled:opacity-50"
        >
          <Send size={15} />
        </button>
      </form>
    </div>
  );
}
