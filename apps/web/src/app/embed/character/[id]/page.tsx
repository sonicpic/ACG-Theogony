"use client";

/** 轻量嵌入页（iframe 卡片）：仅角色 ego 星系 + 名称。 */

import { useParams } from "next/navigation";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { imgProxy } from "@/lib/types";
import { mythColor } from "@/lib/constants";
import { EgoGalaxy } from "@/components/galaxy/EgoGalaxy";

export default function EmbedCharacter() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const { data: char } = useQuery({ queryKey: ["character", id], queryFn: () => api.character(id) });
  const { data: ego } = useQuery({ queryKey: ["ego", id], queryFn: () => api.ego(id, 1) });

  if (!char) return <div className="p-6 text-center text-sm text-zinc-500">加载中…</div>;

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-zinc-950 p-4">
      <div className="mb-2 flex items-center gap-3">
        {char.imageUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={imgProxy(char.imageUrl)} alt="" className="h-10 w-10 rounded-full border border-zinc-700 object-cover" />
        )}
        <div>
          <div className="text-sm font-semibold">{char.name}</div>
          <div className="flex gap-1.5 text-[10px] text-zinc-500">
            {char.className && <span>{char.className}</span>}
            {char.mythology && (
              <span className="rounded px-1" style={{ background: mythColor(char.mythology), color: "#0c0d14" }}>
                {char.mythology}
              </span>
            )}
          </div>
        </div>
        <Link
          href={`/character/${id}`}
          target="_blank"
          className="ml-auto rounded-md bg-sky-600/80 px-2.5 py-1 text-xs hover:bg-sky-500"
        >
          查看完整星系 →
        </Link>
      </div>
      <div className="min-h-0 flex-1">
        {ego ? <EgoGalaxy data={ego} centerId={id} /> : null}
      </div>
    </div>
  );
}
