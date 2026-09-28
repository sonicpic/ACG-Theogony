"use client";

/** 角色星系页：资料卡 + ego 关系星系 + 家谱树 + What-if + 众包提交 + 分享。 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Share2, Sparkles } from "lucide-react";
import { api } from "@/lib/api";
import { imgProxy } from "@/lib/types";
import { mythColor, relColor, relLabel } from "@/lib/constants";
import { EgoGalaxy } from "@/components/galaxy/EgoGalaxy";
import { FamilyTree } from "@/components/galaxy/FamilyTree";
import { RelationEditor } from "@/components/RelationEditor";
import { WhatIfCard } from "@/components/WhatIfCard";

export default function CharacterPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;

  const { data: char, isLoading } = useQuery({ queryKey: ["character", id], queryFn: () => api.character(id) });
  const { data: ego } = useQuery({ queryKey: ["ego", id], queryFn: () => api.ego(id, 2) });
  const { data: family } = useQuery({ queryKey: ["family", id], queryFn: () => api.family(id) });
  const { data: rels } = useQuery({ queryKey: ["character-rels", id], queryFn: () => api.characterRelationships(id) });

  async function share() {
    const url = window.location.href;
    if (navigator.share) {
      try {
        await navigator.share({ title: `${char?.name} · 神谱图谱`, url });
      } catch {
        /* 取消 */
      }
    } else {
      await navigator.clipboard.writeText(url);
      alert("链接已复制");
    }
  }

  if (isLoading) {
    return <div className="flex h-[60vh] items-center justify-center text-zinc-500">加载中…</div>;
  }
  if (!char) {
    return (
      <div className="flex h-[60vh] flex-col items-center justify-center gap-2 text-zinc-500">
        <p>角色不存在</p>
        <Link href="/" className="text-sky-400 hover:underline">
          返回图谱
        </Link>
      </div>
    );
  }

  const nps = (char.extra?.noble_phantasms as string[]) || [];

  return (
    <main className="mx-auto max-w-6xl px-4 py-6">
      <div className="mb-4 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200">
          <ArrowLeft size={15} /> 返回图谱
        </Link>
        <button
          onClick={share}
          className="flex items-center gap-1.5 rounded-md bg-zinc-900 px-3 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800"
        >
          <Share2 size={13} /> 分享
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[340px_1fr]">
        {/* 左：资料卡 */}
        <div className="space-y-4">
          <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/40">
            {char.imageUrl && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={imgProxy(char.imageUrl)} alt={char.name} className="h-56 w-full object-cover" />
            )}
            <div className="p-4">
              <h1 className="text-xl font-bold">{char.name}</h1>
              <div className="mt-2 flex flex-wrap gap-1.5 text-[11px]">
                {char.className && <span className="rounded bg-zinc-800 px-2 py-0.5 text-amber-300">{char.className}</span>}
                {char.mythology && (
                  <span
                    className="rounded px-2 py-0.5 text-zinc-950"
                    style={{ background: mythColor(char.mythology) }}
                  >
                    {char.mythology}
                  </span>
                )}
                {char.alignment && <span className="rounded bg-zinc-800 px-2 py-0.5">{char.alignment}</span>}
                {char.gender && <span className="rounded bg-zinc-800 px-2 py-0.5">{char.gender}</span>}
                <span className="rounded bg-zinc-800 px-2 py-0.5 text-sky-300">关系数 {char.degree}</span>
              </div>
              {char.aliases.length > 0 && (
                <div className="mt-2 text-[11px] text-zinc-500">别名：{char.aliases.join(" / ")}</div>
              )}
              {char.description && (
                <p className="mt-3 text-sm leading-relaxed text-zinc-300">{char.description}</p>
              )}
              {char.mythologyBackground && (
                <p className="mt-2 text-xs leading-relaxed text-zinc-500">
                  <Sparkles size={11} className="mr-1 inline text-amber-400" />
                  {char.mythologyBackground}
                </p>
              )}
              {nps.length > 0 && (
                <div className="mt-3 border-t border-zinc-800 pt-2 text-xs text-zinc-400">
                  <span className="text-zinc-500">宝具：</span>
                  {nps.join("、")}
                </div>
              )}
              {char.detailUrl && (
                <a
                  href={char.detailUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-block text-xs text-sky-400 hover:underline"
                >
                  在 Mooncell Wiki 查看 →
                </a>
              )}
            </div>
          </div>

          <WhatIfCard selfId={char.id} selfName={char.name} />
          <RelationEditor sourceId={char.id} sourceName={char.name} />
        </div>

        {/* 右：星系图 + 家谱 */}
        <div className="space-y-6">
          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-300">关系星系（二度邻居）</h2>
            {ego ? <EgoGalaxy data={ego} centerId={char.id} /> : <div className="h-64 animate-pulse rounded-lg bg-zinc-900/50" />}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-300">家族树</h2>
            {family ? <FamilyTree data={family} /> : <div className="h-36 animate-pulse rounded-lg bg-zinc-900/50" />}
          </section>

          <section>
            <h2 className="mb-2 text-sm font-semibold text-zinc-300">全部关系（{rels?.length || 0}）</h2>
            <div className="overflow-hidden rounded-lg border border-zinc-800">
              {(rels || []).map((r) => {
                const isSource = r.sourceId === char.id;
                const otherId = isSource ? r.targetId : r.sourceId;
                const otherName = isSource ? r.targetName : r.sourceName;
                const arrow = r.directed ? (isSource ? "→" : "←") : "↔";
                return (
                  <Link
                    key={r.id}
                    href={`/character/${otherId}`}
                    className="flex items-center justify-between border-b border-zinc-800/60 px-3 py-2 text-sm last:border-0 hover:bg-zinc-900/60"
                  >
                    <span className="text-zinc-200">
                      {char.name} <span style={{ color: relColor(r.type) }}>{arrow} {relLabel(r.type)} {arrow}</span> {otherName}
                    </span>
                    <span className="text-[10px] text-zinc-600">
                      {r.confidence === "verified" ? "已验证" : r.confidence} · {r.origin}
                    </span>
                  </Link>
                );
              })}
              {rels && rels.length === 0 && (
                <div className="px-3 py-6 text-center text-xs text-zinc-600">暂无已审核关系</div>
              )}
            </div>
          </section>
        </div>
      </div>
    </main>
  );
}
