"use client";

/** 家谱树视图：家族关系（父母/兄弟/配偶）按代分层（dagre 自动布局）。 */

import { useMemo } from "react";
import { ReactFlow, Background, type Edge, type Node } from "@xyflow/react";
import dagre from "@dagrejs/dagre";
import "@xyflow/react/dist/style.css";
import Link from "next/link";
import { imgProxy } from "@/lib/types";
import { relLabel } from "@/lib/constants";

interface FamilyData {
  center: string | null;
  nodes: { id: string; name: string; mythology: string | null; imageUrl: string; kind: string }[];
  links: { source: string; target: string; type: string; label?: string }[];
}

function TreeNode({ data }: { data: Record<string, unknown> }) {
  const isCenter = data.isCenter as boolean;
  return (
    <Link
      href={`/character/${data.id}`}
      className={`flex items-center gap-2 rounded-lg border px-2.5 py-1.5 text-xs transition-colors ${
        isCenter ? "border-emerald-400 bg-emerald-950/70" : "border-zinc-700 bg-zinc-900 hover:border-zinc-500"
      }`}
    >
      {data.imageUrl ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={imgProxy(data.imageUrl as string)} alt="" className="h-7 w-7 rounded-full object-cover" />
      ) : (
        <span className="h-7 w-7 rounded-full bg-zinc-700" />
      )}
      <span className="font-medium">{data.name as string}</span>
    </Link>
  );
}

const nodeTypes = { treeNode: TreeNode };

export function FamilyTree({ data }: { data: FamilyData }) {
  const { nodes, edges } = useMemo(() => {
    if (!data.nodes.length) return { nodes: [], edges: [] };
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 70, marginx: 20, marginy: 20 });
    g.setDefaultEdgeLabel(() => ({}));

    data.nodes.forEach((n) => g.setNode(n.id, { width: 130, height: 44 }));
    data.links.forEach((l) => {
      // PARENT_OF: source 是父母 → 边向下
      g.setEdge(l.source, l.target);
    });

    dagre.layout(g);

    const rfNodes: Node[] = data.nodes.map((n) => {
      const pos = g.node(n.id);
      return {
        id: n.id,
        type: "treeNode",
        position: { x: pos.x - pos.width / 2, y: pos.y - pos.height / 2 },
        data: { ...n, isCenter: n.id === data.center },
      };
    });
    const rfEdges: Edge[] = data.links.map((l, i) => ({
      id: `f${i}`,
      source: l.source,
      target: l.target,
      label: l.label || relLabel(l.type),
      labelStyle: { fill: "#a1a1aa", fontSize: 9 },
      labelBgStyle: { fill: "#18181b" },
      type: "smoothstep",
      style: { stroke: "#52525b" },
    }));
    return { nodes: rfNodes, edges: rfEdges };
  }, [data]);

  if (!nodes.length) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-zinc-600">
        暂无家族关系记录
      </div>
    );
  }

  return (
    <div className="h-[360px] w-full overflow-hidden rounded-lg border border-zinc-800">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.2}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background color="#18181b" gap={24} />
      </ReactFlow>
    </div>
  );
}
