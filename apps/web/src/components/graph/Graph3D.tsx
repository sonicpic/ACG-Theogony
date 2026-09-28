"use client";

/** 3D 沉浸模式（react-force-graph-3d + three）。经 dynamic import 按需加载。 */

import { useEffect, useRef } from "react";
import ForceGraph3D from "react-force-graph-3d";
import type { GraphDTO } from "@/lib/types";
import { mythColor, relColor } from "@/lib/constants";
import { useGraphView } from "@/lib/store";

export default function Graph3D({ data }: { data: GraphDTO }) {
  const fgRef = useRef<{ camera: () => unknown; controls: () => { autoRotate: boolean } } | null>(null);

  useEffect(() => {
    const controls = (fgRef.current as unknown as { controls?: () => { autoRotate: boolean; update: () => void } })?.controls?.();
    if (controls) {
      controls.autoRotate = true;
      controls.update?.();
    }
  }, []);

  const nodes = data.nodes.map((n) => ({
    id: n.id,
    name: n.name,
    color: n.kind === "myth" ? "#e4e4e7" : mythColor(n.mythology),
    val: n.kind === "myth" ? 8 : 2 + Math.sqrt(n.degree),
    nodeData: n,
  }));
  const links = data.links
    .map((l) => ({
      source: l.source,
      target: l.target,
      color: relColor(l.type),
    }))
    .filter((l) => nodes.some((n) => n.id === l.source) && nodes.some((n) => n.id === l.target));

  return (
    <ForceGraph3D
      ref={fgRef as never}
      graphData={{ nodes, links }}
      backgroundColor="#09090b"
      nodeLabel="name"
      nodeColor="color"
      nodeVal="val"
      linkColor="color"
      linkOpacity={0.35}
      nodeOpacity={0.95}
      onNodeClick={(node: { id?: string }) => {
        if (node.id) useGraphView.getState().select(node.id);
      }}
      cooldownTicks={120}
      width={typeof window !== "undefined" ? window.innerWidth : 1200}
      height={typeof window !== "undefined" ? window.innerHeight - 48 : 800}
    />
  );
}
