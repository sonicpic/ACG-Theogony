"use client";

/** Ego 星系图：以角色为中心的二度关系星系（React Flow 径向布局）。 */

import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import Link from "next/link";
import type { GraphDTO } from "@/lib/types";
import { imgProxy } from "@/lib/types";
import { mythColor, relColor, relLabel } from "@/lib/constants";

function CharacterNode({ data }: { data: Record<string, unknown> }) {
  const isCenter = data.isCenter as boolean;
  const name = data.name as string;
  const mythology = data.mythology as string | null;
  const imageUrl = data.imageUrl as string;
  return (
    <Link
      href={`/character/${data.id}`}
      className={`flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 transition-transform hover:scale-105 ${
        isCenter ? "border-sky-400 bg-sky-950/80 shadow-lg shadow-sky-900/50" : "border-zinc-700 bg-zinc-900"
      }`}
    >
      {imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imgProxy(imageUrl)} alt={name} className="h-8 w-8 rounded-full border border-zinc-700 object-cover" />
      ) : (
        <span className="h-8 w-8 rounded-full" style={{ background: mythColor(mythology) }} />
      )}
      <span className="text-xs font-medium">{name}</span>
    </Link>
  );
}

const nodeTypes = { character: CharacterNode };

export function EgoGalaxy({ data, centerId }: { data: GraphDTO; centerId: string }) {
  const { nodes, edges } = useMemo(() => {
    const center = data.nodes.find((n) => n.id === centerId);
    const others = data.nodes.filter((n) => n.id !== centerId);
    const R = 260;
    const rfNodes: Node[] = [];
    if (center) {
      rfNodes.push({
        id: center.id,
        type: "character",
        position: { x: 0, y: 0 },
        data: { ...center, isCenter: true },
      });
    }
    others.forEach((n, i) => {
      const angle = (i / Math.max(others.length, 1)) * Math.PI * 2 - Math.PI / 2;
      const r = R * (0.55 + (n.degree % 3) * 0.22);
      rfNodes.push({
        id: n.id,
        type: "character",
        position: { x: Math.cos(angle) * r, y: Math.sin(angle) * r },
        data: { ...n, isCenter: false },
      });
    });
    const rfEdges: Edge[] = data.links.map((l, i) => ({
      id: `e${i}`,
      source: l.source,
      target: l.target,
      label: relLabel(l.type),
      labelStyle: { fill: "#a1a1aa", fontSize: 9 },
      labelBgStyle: { fill: "#18181b" },
      style: { stroke: relColor(l.type), strokeWidth: l.source === centerId || l.target === centerId ? 2 : 1 },
      animated: l.source === centerId || l.target === centerId,
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [data, centerId]);

  if (!nodes.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-zinc-600">
        暂无关系数据 —— 可以在下方提交一条，或等待 LLM 挖掘审核
      </div>
    );
  }

  return (
    <div className="h-[380px] w-full overflow-hidden rounded-lg border border-zinc-800">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        maxZoom={2.5}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background color="#18181b" gap={24} />
        <Controls showInteractive={false} className="!fill-zinc-400 !text-zinc-400" />
      </ReactFlow>
    </div>
  );
}
