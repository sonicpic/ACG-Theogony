"use client";

/** 全局轻提示：所有交互动作给出即时反馈。 */

import { useGraphView } from "@/lib/store";

export function Toast() {
  const toast = useGraphView((s) => s.toast);
  if (!toast) return null;
  return (
    <div
      key={toast.id}
      className="fade-up pointer-events-none fixed left-1/2 top-16 z-50 -translate-x-1/2 rounded-full border border-zinc-700 bg-zinc-950/95 px-4 py-2 text-sm text-zinc-100 shadow-xl backdrop-blur"
    >
      {toast.msg}
    </div>
  );
}
