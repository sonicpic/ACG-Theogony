"use client";

/** 首次访问引导教程：6 步卡片，localStorage 记忆；帮助按钮可随时重看。 */

import { useState } from "react";
import { HelpCircle, X, ChevronLeft, ChevronRight, MousePointerClick, Route, Sparkles, Search, Globe2, Clock } from "lucide-react";

const STEPS = [
  {
    icon: MousePointerClick,
    title: "点击节点，看见关系",
    body: "点任意角色（彩色圆点），与它相关的角色和关系会亮起，其余淡出；再点空白处恢复。白色大节点是神话体系枢纽。",
  },
  {
    icon: Search,
    title: "搜索与自然语言",
    body: "左上角可按名字/别名/拼音搜索定位；\"自然语言查图\"直接输入如「希腊神话的父子关系」，图谱自动过滤。",
  },
  {
    icon: Route,
    title: "六度分隔探索",
    body: "右上角「关系路径探索」：输入两个角色，找出他们之间最短的关系链（例如吉尔伽美什如何连到项羽）。",
  },
  {
    icon: Globe2,
    title: "三种视图",
    body: "力导向（整体关系星云）、神话星系（按体系分成 20 个星系，对应现实地理）、3D 沉浸模式。布局切换有平滑变形动画。",
  },
  {
    icon: Clock,
    title: "时间轴与筛选",
    body: "拖动时间轴按实装顺序回放图谱生长；体系/关系类型/职阶筛选可组合使用；节点可以直接拖拽摆放。",
  },
  {
    icon: Sparkles,
    title: "问问图谱（GraphRAG）",
    body: "右下角「问问图谱」用自然语言提问（如「谁和赫克托尔交过手？」），答案会高亮相关子图。还有每日猜角色小游戏！",
  },
];

export function TourGuide({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [step, setStep] = useState(0);
  if (!open) return null;
  const cur = STEPS[step];
  const Icon = cur.icon;
  const isLast = step === STEPS.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        className="fade-up mx-4 w-full max-w-sm overflow-hidden rounded-2xl border border-zinc-700 bg-zinc-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative bg-gradient-to-br from-sky-500/20 via-violet-500/10 to-transparent px-6 pb-5 pt-6">
          <button onClick={onClose} className="absolute right-3 top-3 text-zinc-500 hover:text-zinc-200" aria-label="关闭引导">
            <X size={18} />
          </button>
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-zinc-900 ring-1 ring-zinc-700">
            <Icon size={24} className="text-sky-400" />
          </div>
          <div className="mt-3 text-xs text-zinc-400">
            使用指引 {step + 1} / {STEPS.length}
          </div>
          <h2 className="mt-0.5 text-xl font-bold">{cur.title}</h2>
        </div>
        <p className="px-6 py-4 text-sm leading-relaxed text-zinc-300">{cur.body}</p>
        <div className="flex items-center justify-between border-t border-zinc-800 px-6 py-4">
          <div className="flex gap-1.5">
            {STEPS.map((_, i) => (
              <button
                key={i}
                onClick={() => setStep(i)}
                className={`h-1.5 rounded-full transition-all ${i === step ? "w-5 bg-sky-400" : "w-1.5 bg-zinc-700"}`}
                aria-label={`第 ${i + 1} 步`}
              />
            ))}
          </div>
          <div className="flex gap-2">
            {step > 0 && (
              <button
                onClick={() => setStep(step - 1)}
                className="flex items-center gap-1 rounded-lg bg-zinc-900 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-800"
              >
                <ChevronLeft size={14} /> 上一步
              </button>
            )}
            <button
              onClick={() => (isLast ? onClose() : setStep(step + 1))}
              className="flex items-center gap-1 rounded-lg bg-sky-600 px-4 py-1.5 text-sm font-medium hover:bg-sky-500"
            >
              {isLast ? "开始探索" : "下一步"} {isLast ? null : <ChevronRight size={14} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/** 帮助按钮（桌面悬浮右下，与问答 FAB 错开；手机在 Dock 里） */
export function HelpFab({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="pointer-events-auto absolute bottom-4 left-4 z-20 hidden h-10 w-10 items-center justify-center rounded-full border border-zinc-700 bg-zinc-950/90 text-zinc-300 shadow-lg backdrop-blur hover:bg-zinc-800 md:flex"
      title="使用指引"
    >
      <HelpCircle size={18} />
    </button>
  );
}
