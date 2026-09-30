"use client";

/** 移动端底部 Dock + 抽屉容器：筛选 / 路径 / AI 问答 / 帮助，替代互相遮挡的浮动卡片。 */

import { HelpCircle, Route, SlidersHorizontal, Sparkles, X } from "lucide-react";
import { useGraphView } from "@/lib/store";
import { useGraphQuery } from "./useGraphQuery";
import { FilterContent } from "./ControlPanel";
import { PathContent } from "./PathFinder";

export function BottomDock() {
  const { data } = useGraphQuery();
  const mobilePanel = useGraphView((s) => s.mobilePanel);
  const setMobilePanel = useGraphView((s) => s.setMobilePanel);
  const setTourOpen = useGraphView((s) => s.setTourOpen);
  const askOpen = useGraphView((s) => s.askOpen);
  const setAskOpen = useGraphView((s) => s.setAskOpen);

  const items = [
    { key: "filter", label: "筛选", icon: SlidersHorizontal },
    { key: "path", label: "路径", icon: Route },
    { key: "ask", label: "问AI", icon: Sparkles },
  ] as const;

  return (
    <>
      {/* 抽屉 */}
      {mobilePanel && mobilePanel !== "ask" && (
        <div className="fade-up fixed inset-x-0 bottom-0 z-40 max-h-[68vh] overflow-y-auto rounded-t-2xl border-t border-zinc-700 bg-zinc-950/98 pb-20 shadow-2xl">
          <div className="sticky top-0 z-10 flex items-center justify-between border-b border-zinc-800 bg-zinc-950/95 px-4 py-3 backdrop-blur">
            <div className="text-sm font-semibold">
              {mobilePanel === "filter" ? "筛选与视图" : "关系路径探索"}
            </div>
            <button onClick={() => setMobilePanel(null)} className="rounded-md bg-zinc-900 p-1.5 text-zinc-400" aria-label="关闭">
              <X size={16} />
            </button>
          </div>
          <div className="px-4 py-3">
            {mobilePanel === "filter" ? <FilterContent data={data!} /> : <PathContent data={data!} />}
          </div>
        </div>
      )}

      {/* Dock（AI 面板打开时隐藏，避免叠加） */}
      <nav
        className={`fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-zinc-800 bg-zinc-950/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden ${
          askOpen || (mobilePanel === "ask") ? "hidden" : "flex"
        }`}
      >
        {items.map(({ key, label, icon: Icon }) => {
          const active = mobilePanel === key || (key === "ask" && askOpen);
          return (
            <button
              key={key}
              onClick={() => {
                if (key === "ask") {
                  setMobilePanel(null);
                  setAskOpen(!askOpen);
                } else {
                  setAskOpen(false);
                  setMobilePanel(mobilePanel === key ? null : key);
                }
              }}
              className={`flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] transition-colors ${
                active ? "text-sky-400" : "text-zinc-500"
              }`}
            >
              <Icon size={20} />
              {label}
            </button>
          );
        })}
        <button
          onClick={() => setTourOpen(true)}
          className="flex flex-1 flex-col items-center gap-1 py-2.5 text-[11px] text-zinc-500"
        >
          <HelpCircle size={20} />
          指引
        </button>
      </nav>
    </>
  );
}
