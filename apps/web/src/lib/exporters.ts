"use client";

/** 客户端导出：PNG（Sigma 画布）/ SVG（自绘简化图）。 */

import type { GraphNode } from "./types";
import { mythColor, relColor } from "./constants";

export function exportPng(filename = "theogony-graph.png") {
  const getter = (window as unknown as Record<string, (() => HTMLCanvasElement | null) | undefined>).__theogonyExportPng;
  const canvas = getter?.();
  if (!canvas) {
    alert("导出失败：画布尚未就绪");
    return;
  }
  const url = canvas.toDataURL("image/png");
  download(url, filename);
}

export function exportSvg(nodes: GraphNode[], links: { source: string; target: string; type: string }[], filename = "theogony-graph.svg") {
  const W = 1600;
  const H = 1000;
  const pos = new Map<string, { x: number; y: number }>();
  nodes.forEach((n, i) => {
    const angle = i * 2.399963; // 黄金角散布
    const r = 60 + Math.sqrt(i + 1) * 16;
    pos.set(n.id, { x: W / 2 + Math.cos(angle) * r, y: H / 2 + Math.sin(angle) * r * 0.8 });
  });
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = links
    .map((l) => {
      const a = pos.get(l.source);
      const b = pos.get(l.target);
      if (!a || !b) return "";
      return `<line x1="${a.x.toFixed(1)}" y1="${a.y.toFixed(1)}" x2="${b.x.toFixed(1)}" y2="${b.y.toFixed(1)}" stroke="${relColor(l.type)}" stroke-opacity="0.5" stroke-width="1"/>`;
    })
    .join("\n  ");
  const circles = nodes
    .map((n) => {
      const p = pos.get(n.id)!;
      return `<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="${n.kind === "myth" ? 8 : 4}" fill="${n.kind === "myth" ? "#e4e4e7" : mythColor(n.mythology)}"><title>${esc(n.name)}</title></circle>`;
    })
    .join("\n  ");
  const svg = `<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
  <rect width="${W}" height="${H}" fill="#09090b"/>
  ${lines}
  ${circles}
</svg>`;
  download(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`, filename);
}

export function download(dataUrl: string, filename: string) {
  const a = document.createElement("a");
  a.href = dataUrl;
  a.download = filename;
  a.click();
}
