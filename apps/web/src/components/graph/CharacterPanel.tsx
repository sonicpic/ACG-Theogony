"use client";

/** 图谱页右侧角色信息抽屉（点击节点弹出）。 */

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, MapPin, Shield, User, X } from "lucide-react";
import { api, } from "@/lib/api";
import { imgProxy } from "@/lib/types";
import { relColor, relLabel } from "@/lib/constants";
import { useGraphView } from "@/lib/store";

export function CharacterPanel() {
  const selectedId = useGraphView((s) => s.selectedId);
  const focus = useGraphView((s) => s.focus);
  const select = useGraphView((s) => s.select);

  const { data: char } = useQuery({
    queryKey: ["character", selectedId],
    queryFn: () => api.character(selectedId!),
    enabled: !!selectedId,
  });
  const { data: rels } = useQuery({
    queryKey: ["character-rels", selectedId],
    queryFn: () => api.characterRelationships(selectedId!),
    enabled: !!selectedId,
  });

  if (!selectedId) return null;

  return (
    <div className="fade-up pointer-events-auto absolute bottom-3 left-3 z-20 max-h-[55%] w-[340px] overflow-y-auto rounded-xl border border-zinc-800 bg-zinc-950/97 p-4 shadow-2xl backdrop-blur">
      <div className="flex items-start gap-3">
        {char?.imageUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={imgProxy(char.imageUrl)}
            alt={char.name}
            className="h-16 w-16 rounded-lg border border-zinc-800 object-cover"
          />
        )}
        <div className="min-w-0 flex-1">
          <div className="truncate text-base font-semibold">{char?.name || "…"}</div>
          <div className="mt-0.5 flex flex-wrap gap-1.5 text-[11px] text-zinc-400">
            {char?.className && (
              <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-amber-300">{char.className}</span>
            )}
            {char?.mythology && (
              <span className="flex items-center gap-0.5 rounded bg-zinc-800 px-1.5 py-0.5">
                <MapPin size={10} /> {char.mythology}
              </span>
            )}
            {char?.alignment && (
              <span className="flex items-center gap-0.5 rounded bg-zinc-800 px-1.5 py-0.5">
                <Shield size={10} /> {char.alignment}
              </span>
            )}
            {char?.gender && (
              <span className="flex items-center gap-0.5 rounded bg-zinc-800 px-1.5 py-0.5">
                <User size={10} /> {char.gender}
              </span>
            )}
          </div>
        </div>
        <button onClick={() => select(null)} className="text-zinc-500 hover:text-zinc-200">
          <X size={16} />
        </button>
      </div>

      {char?.description && (
        <p className="mt-3 text-xs leading-relaxed text-zinc-400">{char.description}</p>
      )}

      {rels && rels.length > 0 && (
        <div className="mt-3 border-t border-zinc-800 pt-2.5">
          <div className="mb-1.5 text-[11px] font-semibold text-zinc-500">关系（{rels.length}）</div>
          <div className="flex flex-wrap gap-1.5">
            {rels.slice(0, 14).map((r) => {
              const otherId = r.sourceId === selectedId ? r.targetId : r.sourceId;
              const otherName = r.sourceId === selectedId ? r.targetName : r.sourceName;
              return (
                <button
                  key={r.id}
                  onClick={() => focus(otherId)}
                  className="rounded-full border px-2 py-0.5 text-[11px] transition-transform hover:scale-105"
                  style={{ borderColor: relColor(r.type), color: relColor(r.type) }}
                  title={r.evidence}
                >
                  {relLabel(r.type)} · {otherName}
                </button>
              );
            })}
          </div>
        </div>
      )}
      {rels && rels.length === 0 && (
        <p className="mt-3 text-xs text-zinc-600">暂无已审核关系（去角色页提交，或等 LLM 挖掘审核）</p>
      )}

      <div className="mt-3 flex items-center gap-2">
        <Link
          href={`/character/${selectedId}`}
          className="flex flex-1 items-center justify-center gap-1 rounded-md bg-sky-600/80 py-1.5 text-xs font-medium hover:bg-sky-500"
        >
          <ExternalLink size={12} /> 角色星系页
        </Link>
        {char?.detailUrl && (
          <a
            href={char.detailUrl}
            target="_blank"
            rel="noreferrer"
            className="rounded-md bg-zinc-900 px-2.5 py-1.5 text-xs text-zinc-400 hover:bg-zinc-800"
          >
            Wiki
          </a>
        )}
      </div>
    </div>
  );
}
