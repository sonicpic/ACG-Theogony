/** 展示元数据（与 theogony/core/enums.py 的 RELATION_META / MYTHOLOGY_COLORS 保持一致） */

export interface RelationMeta {
  label: string;
  category: "myth" | "family" | "social";
  color: string;
  directed: boolean;
}

export const RELATION_META: Record<string, RelationMeta> = {
  BELONGS_TO: { label: "归属", category: "myth", color: "#94a3b8", directed: true },
  PROTOTYPE_IS: { label: "同一原型", category: "myth", color: "#8b5cf6", directed: false },
  GENDER_SWAP: { label: "性转", category: "myth", color: "#ec4899", directed: false },
  DERIVED_FROM: { label: "衍生", category: "myth", color: "#a78bfa", directed: true },
  COMPOSITE_OF: { label: "复合", category: "myth", color: "#c084fc", directed: true },
  PARENT_OF: { label: "父母", category: "family", color: "#10b981", directed: true },
  SIBLING_OF: { label: "兄弟姐妹", category: "family", color: "#6ee7b7", directed: false },
  SPOUSE_OF: { label: "配偶", category: "family", color: "#f472b6", directed: false },
  LOVER_OF: { label: "恋人", category: "family", color: "#fb7185", directed: false },
  MASTER_OF: { label: "主人", category: "social", color: "#3b82f6", directed: true },
  ALLY_OF: { label: "盟友", category: "social", color: "#22c55e", directed: false },
  ENEMY_OF: { label: "敌对", category: "social", color: "#ef4444", directed: false },
  FOUGHT_WITH: { label: "交手", category: "social", color: "#f97316", directed: false },
  MENTOR_OF: { label: "师傅", category: "social", color: "#0ea5e9", directed: true },
};

export const CATEGORY_LABEL: Record<string, string> = {
  myth: "神话",
  family: "家族",
  social: "社会",
};

export const MYTHOLOGY_COLORS: Record<string, string> = {
  希腊神话: "#38bdf8",
  罗马神话: "#60a5fa",
  北欧神话: "#a5b4fc",
  凯尔特神话: "#34d399",
  不列颠神话: "#4ade80",
  埃及神话: "#fbbf24",
  美索不达米亚神话: "#f97316",
  波斯神话: "#fb923c",
  印度神话: "#c084fc",
  中国神话: "#f87171",
  日本神话: "#f472b6",
  阿兹特克神话: "#2dd4bf",
  玛雅神话: "#22d3ee",
  非洲神话: "#a3e635",
  斯拉夫神话: "#818cf8",
  芬兰神话: "#7dd3fc",
  基督教: "#e879f9",
  现代创作: "#94a3b8",
  史实人物: "#cbd5e1",
  其他: "#64748b",
};

export const CLUSTER_PALETTE = [
  "#f87171", "#fb923c", "#fbbf24", "#a3e635", "#34d399",
  "#2dd4bf", "#22d3ee", "#60a5fa", "#818cf8", "#a78bfa",
  "#c084fc", "#e879f9", "#f472b6", "#fb7185", "#facc15",
];

export function mythColor(m?: string | null): string {
  return MYTHOLOGY_COLORS[m || ""] || "#64748b";
}

export function relColor(type: string): string {
  return RELATION_META[type]?.color || "#71717a";
}

export function relLabel(type: string): string {
  return RELATION_META[type]?.label || type;
}

export const MYTH_NODE_COLOR = "#e4e4e7";
