"use client";

/** 图谱浮动操作：取消高亮（仅高亮态出现）+ 重置视图（回中心全景）。 */

import { Focus, RotateCcw } from "lucide-react";
import { useGraphView } from "@/lib/store";

export function FloatingActions() {
  const hasFocus = useGraphView(
    (s) => !!(s.selectedId || s.pathResult?.found || s.askIds?.length)
  );
  const cancelFocus = useGraphView((s) => s.cancelFocus);
  const resetView = useGraphView((s) => s.resetView);

  return (
    <div className="absolute bottom-24 right-4 z-20 flex flex-col items-end gap-2 md:bottom-16">
      {hasFocus && (
        <button
          onClick={cancelFocus}
          className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-sky-500/40 bg-zinc-950/90 px-3.5 py-2 text-xs font-medium text-sky-300 shadow-lg backdrop-blur transition-colors hover:border-sky-400 hover:text-sky-200"
        >
          <Focus size={13} /> 取消高亮
        </button>
      )}
      <button
        onClick={resetView}
        className="pointer-events-auto flex items-center gap-1.5 rounded-full border border-zinc-700/70 bg-zinc-950/90 px-3.5 py-2 text-xs font-medium text-zinc-300 shadow-lg backdrop-blur transition-colors hover:border-zinc-500 hover:text-zinc-100"
      >
        <RotateCcw size={13} /> 重置视图
      </button>
    </div>
  );
}
