"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { ForceGraphMethods } from "react-force-graph-2d";
import type { GraphData, GraphLink, GraphNode } from "@/types";

type NodeId = string;

type LinkLike = {
  source: string | GraphNode;
  target: string | GraphNode;
};

const DEFAULT_DATA: GraphData = { nodes: [], links: [] };

function getNodeId(node: string | GraphNode): NodeId {
  return typeof node === "string" ? node : node.id;
}

function isConnected(link: LinkLike, nodeId: NodeId) {
  return getNodeId(link.source) === nodeId || getNodeId(link.target) === nodeId;
}

export default function TheogonyGraph() {
  const fgRef = useRef<ForceGraphMethods>();
  const [data, setData] = useState<GraphData>(DEFAULT_DATA);
  const [highlightNodes, setHighlightNodes] = useState<Set<NodeId>>(new Set());
  const [highlightLinks, setHighlightLinks] = useState<Set<LinkLike>>(new Set());
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [query, setQuery] = useState("");
  const [showCharacter, setShowCharacter] = useState(true);
  const [showMyth, setShowMyth] = useState(true);
  const [enabledRelationships, setEnabledRelationships] = useState<Set<string>>(
    new Set()
  );

  const imageCache = useMemo(() => new Map<string, HTMLImageElement>(), []);
  const nodeIndex = useMemo(
    () => new Map(data.nodes.map((n) => [n.id, n] as const)),
    [data.nodes]
  );

  const relationshipOptions = useMemo(() => {
    const options = new Set<string>();
    data.links.forEach((link) => options.add(link.relationship));
    return Array.from(options).sort();
  }, [data.links]);

  // 关系类型配置（颜色、显示名称）
  const relationshipConfig: Record<string, { color: string; label: string; category: string }> = {
    BELONGS_TO: { color: "#94a3b8", label: "归属", category: "神话" },
    PROTOTYPE_IS: { color: "#8b5cf6", label: "原型", category: "神话" },
    GENDER_SWAP: { color: "#ec4899", label: "性转", category: "神话" },
    DERIVED_FROM: { color: "#a78bfa", label: "衍生", category: "神话" },
    COMPOSITE_OF: { color: "#c084fc", label: "复合", category: "神话" },
    
    PARENT_OF: { color: "#10b981", label: "父母", category: "家族" },
    CHILD_OF: { color: "#34d399", label: "子女", category: "家族" },
    SIBLING_OF: { color: "#6ee7b7", label: "兄弟姐妹", category: "家族" },
    SPOUSE_OF: { color: "#f472b6", label: "配偶", category: "家族" },
    LOVER_OF: { color: "#fb7185", label: "恋人", category: "家族" },
    
    MASTER_OF: { color: "#3b82f6", label: "主人", category: "社会" },
    SERVANT_OF: { color: "#60a5fa", label: "从者", category: "社会" },
    ALLY_OF: { color: "#22c55e", label: "盟友", category: "社会" },
    ENEMY_OF: { color: "#ef4444", label: "敌对", category: "社会" },
    FOUGHT_WITH: { color: "#f97316", label: "战斗", category: "社会" },
    MENTOR_OF: { color: "#0ea5e9", label: "师傅", category: "社会" },
    STUDENT_OF: { color: "#06b6d4", label: "学生", category: "社会" },
  };

  // 按类别分组的关系选项
  const relationshipsByCategory = useMemo(() => {
    const categories: Record<string, string[]> = {};
    relationshipOptions.forEach((rel) => {
      const config = relationshipConfig[rel];
      const category = config?.category || "其他";
      if (!categories[category]) {
        categories[category] = [];
      }
      categories[category].push(rel);
    });
    return categories;
  }, [relationshipOptions]);

  useEffect(() => {
    if (enabledRelationships.size === 0 && relationshipOptions.length > 0) {
      setEnabledRelationships(new Set(relationshipOptions));
    }
  }, [relationshipOptions, enabledRelationships.size]);

  const filteredData = useMemo(() => {
    const allowedTypes = new Set<string>();
    if (showCharacter) allowedTypes.add("Character");
    if (showMyth) allowedTypes.add("Myth");

    const filteredLinks = data.links.filter((link) => {
      const relOk = enabledRelationships.has(link.relationship);
      const source = typeof link.source === "string" ? nodeIndex.get(link.source) : link.source;
      const target = typeof link.target === "string" ? nodeIndex.get(link.target) : link.target;
      const typeOk =
        (source ? allowedTypes.has(source.type) : true) &&
        (target ? allowedTypes.has(target.type) : true);
      return relOk && typeOk;
    });

    const keepIds = new Set<NodeId>();
    filteredLinks.forEach((link) => {
      keepIds.add(getNodeId(link.source));
      keepIds.add(getNodeId(link.target));
    });

    const filteredNodes = data.nodes.filter(
      (node) => allowedTypes.has(node.type) && (keepIds.size === 0 || keepIds.has(node.id))
    );

    return { nodes: filteredNodes, links: filteredLinks } as GraphData;
  }, [data, enabledRelationships, nodeIndex, showCharacter, showMyth]);

  const stats = useMemo(() => {
    const characters = filteredData.nodes.filter((n) => n.type === "Character").length;
    const myths = filteredData.nodes.filter((n) => n.type === "Myth").length;
    return { characters, myths, links: filteredData.links.length };
  }, [filteredData]);

  useEffect(() => {
    let cancelled = false;
    fetch("/graph_data.json")
      .then((res) => res.json())
      .then((json: GraphData) => {
        if (!cancelled) setData(json);
      })
      .catch(() => {
        if (!cancelled) setData(DEFAULT_DATA);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleNodeClick = (node: GraphNode) => {
    const nodeId = node.id;
    const nextNodes = new Set<NodeId>([nodeId]);
    const nextLinks = new Set<LinkLike>();

    filteredData.links.forEach((link) => {
      if (isConnected(link, nodeId)) {
        nextLinks.add(link);
        nextNodes.add(getNodeId(link.source));
        nextNodes.add(getNodeId(link.target));
      }
    });

    setHighlightNodes(nextNodes);
    setHighlightLinks(nextLinks);
    setSelectedNode(node);
  };

  const handleBackgroundClick = () => {
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());
    setSelectedNode(null);
  };

  const focusNode = (node: GraphNode) => {
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    fgRef.current?.centerAt(x, y, 800);
    fgRef.current?.zoom(4, 800);
  };

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const q = query.trim();
    if (!q) return;
    const match = filteredData.nodes.find(
      (n) => n.name.includes(q) || n.id.includes(q)
    );
    if (match) {
      handleNodeClick(match);
      focusNode(match);
    }
  };

  const toggleRelationship = (rel: string) => {
    setEnabledRelationships((prev) => {
      const next = new Set(prev);
      if (next.has(rel)) {
        next.delete(rel);
      } else {
        next.add(rel);
      }
      return next;
    });
    setHighlightNodes(new Set());
    setHighlightLinks(new Set());
  };

  const drawNode = (node: GraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const isMyth = node.type === "Myth";
    const isHighlighted = highlightNodes.size > 0 && highlightNodes.has(node.id);
    const isHovered = hoveredNode?.id === node.id;

    const baseRadius = isMyth ? 9 : 6;
    const radius = isHighlighted || isHovered ? baseRadius + 2 : baseRadius;
    const color = isMyth ? "#ef4444" : "#3b82f6";

    // 背景圆
    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2, false);
    ctx.fillStyle = color;
    ctx.fill();

    // 可选头像
    if (node.image_url) {
      let img = imageCache.get(node.image_url);
      if (!img) {
        img = new Image();
        img.src = node.image_url;
        imageCache.set(node.image_url, img);
      }

      if (img.complete) {
        ctx.save();
        ctx.beginPath();
        ctx.arc(node.x ?? 0, node.y ?? 0, radius - 1, 0, Math.PI * 2);
        ctx.clip();
        ctx.drawImage(img, (node.x ?? 0) - radius, (node.y ?? 0) - radius, radius * 2, radius * 2);
        ctx.restore();
      }
    }

    // 外圈高亮
    if (isHovered) {
      ctx.beginPath();
      ctx.arc(node.x ?? 0, node.y ?? 0, radius + 2, 0, Math.PI * 2, false);
      ctx.strokeStyle = "#f59e0b";
      ctx.lineWidth = 2;
      ctx.stroke();
    }

    // 标签（根据缩放控制）
    const label = node.name;
    const fontSize = 12 / globalScale;
    if (globalScale > 1.2) {
      ctx.font = `${fontSize}px sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.fillStyle = "#111827";
      ctx.fillText(label, node.x ?? 0, (node.y ?? 0) + radius + 2);
    }
  };

  return (
    <div className="relative h-screen w-screen">
      <div className="pointer-events-auto absolute left-4 top-4 z-10 w-[340px] rounded-xl border border-zinc-200 bg-white/90 p-4 shadow-lg backdrop-blur">
        <h1 className="text-lg font-semibold text-zinc-900">Theogony-Graph</h1>
        <p className="mt-1 text-xs text-zinc-500">
          角色与神话原型关系图谱（点击节点高亮）
        </p>

        <form onSubmit={handleSearch} className="mt-3 flex gap-2">
          <input
            className="w-full rounded-md border border-zinc-200 bg-white px-3 py-2 text-sm outline-none focus:border-blue-400"
            placeholder="搜索角色/神话（名称或ID）"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <button
            type="submit"
            className="rounded-md bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            定位
          </button>
        </form>

        <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs text-zinc-600">
          <div className="rounded-md bg-zinc-50 py-2">
            角色<br />
            <span className="text-sm font-semibold text-blue-600">{stats.characters}</span>
          </div>
          <div className="rounded-md bg-zinc-50 py-2">
            神话<br />
            <span className="text-sm font-semibold text-red-500">{stats.myths}</span>
          </div>
          <div className="rounded-md bg-zinc-50 py-2">
            连线<br />
            <span className="text-sm font-semibold text-amber-600">{stats.links}</span>
          </div>
        </div>

        <div className="mt-4 border-t border-zinc-200 pt-3">
          <div className="text-xs font-semibold text-zinc-500">类型筛选</div>
          <div className="mt-2 flex gap-3 text-xs">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showCharacter}
                onChange={(e) => setShowCharacter(e.target.checked)}
              />
              <span className="text-blue-600">Character</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={showMyth}
                onChange={(e) => setShowMyth(e.target.checked)}
              />
              <span className="text-red-500">Myth</span>
            </label>
          </div>

          <div className="mt-3 text-xs font-semibold text-zinc-500">关系筛选</div>
          <div className="mt-2 max-h-[200px] overflow-y-auto">
            {Object.entries(relationshipsByCategory).map(([category, rels]) => (
              <div key={category} className="mb-3">
                <div className="text-[10px] font-semibold uppercase text-zinc-400 mb-1">
                  {category}
                </div>
                <div className="grid grid-cols-2 gap-1.5 text-[11px] text-zinc-600">
                  {rels.map((rel) => {
                    const config = relationshipConfig[rel];
                    return (
                      <label key={rel} className="flex items-center gap-1.5 cursor-pointer hover:bg-zinc-50 p-1 rounded">
                        <input
                          type="checkbox"
                          checked={enabledRelationships.has(rel)}
                          onChange={() => toggleRelationship(rel)}
                          className="w-3 h-3"
                        />
                        <span
                          className="inline-block w-2 h-2 rounded-full"
                          style={{ backgroundColor: config?.color || "#94a3b8" }}
                        />
                        <span className="truncate">{config?.label || rel}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-4 border-t border-zinc-200 pt-3">
          <div className="text-xs font-semibold text-zinc-500">当前节点</div>
          {selectedNode ? (
            <div className="mt-2 text-sm text-zinc-800">
              <div className="font-medium">{selectedNode.name}</div>
              <div className="text-xs text-zinc-500">{selectedNode.type}</div>
              {selectedNode.description && (
                <div className="mt-2 text-xs text-zinc-600 line-clamp-4">
                  {selectedNode.description}
                </div>
              )}
              {selectedNode.metadata && (
                <div className="mt-2 text-xs text-zinc-500">
                  {Object.entries(selectedNode.metadata)
                    .slice(0, 4)
                    .map(([k, v]) => (
                      <div key={k}>
                        {k}: {String(v)}
                      </div>
                    ))}
                </div>
              )}
            </div>
          ) : (
            <div className="mt-2 text-xs text-zinc-400">点击任一节点查看详情</div>
          )}
        </div>

        {hoveredNode && (
          <div className="mt-4 border-t border-zinc-200 pt-3">
            <div className="text-xs font-semibold text-zinc-500">悬浮节点</div>
            <div className="mt-2 text-xs text-zinc-600">
              {hoveredNode.name} · {hoveredNode.type}
            </div>
          </div>
        )}
      </div>

      <ForceGraph2D
        ref={fgRef}
        graphData={filteredData}
        backgroundColor="#f8fafc"
        nodeCanvasObject={drawNode}
        nodePointerAreaPaint={(node, color, ctx) => {
          const isMyth = node.type === "Myth";
          const radius = isMyth ? 9 : 6;
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2, false);
          ctx.fill();
        }}
        linkColor={(link) => {
          if (highlightLinks.has(link)) return "#f59e0b";
          const config = relationshipConfig[link.relationship];
          return config?.color || "rgba(15, 23, 42, 0.25)";
        }}
        linkWidth={(link) => (highlightLinks.has(link) ? 2.4 : 1)}
        linkDirectionalParticles={(link) => {
          // 对特定关系显示方向箭头粒子
          const directionalRelations = [
            "PARENT_OF", "CHILD_OF", "MASTER_OF", "SERVANT_OF", 
            "MENTOR_OF", "STUDENT_OF", "DERIVED_FROM"
          ];
          return directionalRelations.includes(link.relationship) ? 2 : 0;
        }}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.003}
        linkLabel={(link) => {
          const config = relationshipConfig[link.relationship];
          return config?.label || link.relationship;
        }}
        onNodeClick={handleNodeClick}
        onNodeHover={(node) => setHoveredNode(node || null)}
        onBackgroundClick={handleBackgroundClick}
      />
    </div>
  );
}
