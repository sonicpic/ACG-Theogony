/** 前端领域类型（与 theogony/core/models.py 的 DTO 字段一一对应）。 */

export interface GraphNode {
  id: string;
  name: string;
  kind: "character" | "myth";
  mythology: string | null;
  className: string;
  imageUrl: string;
  degree: number;
  wikiId: number;
}

export interface GraphLink {
  source: string;
  target: string;
  type: string;
  directed: boolean;
  confidence: string;
}

export interface Cluster {
  index: number;
  size: number;
  topMythology: string;
  members: string[];
}

export interface GraphDTO {
  nodes: GraphNode[];
  links: GraphLink[];
  meta: {
    nodeCount: number;
    linkCount: number;
    clusters: Cluster[];
    geo: Record<string, [number, number]>;
  };
}

export interface CharacterDTO {
  id: string;
  wikiId: number;
  name: string;
  aliases: string[];
  className: string;
  prototype: string;
  mythology: string | null;
  description: string;
  mythologyBackground: string;
  alignment: string;
  gender: string;
  imageUrl: string;
  detailUrl: string;
  source: string;
  extra: Record<string, unknown>;
  degree: number;
}

export interface RelationshipDTO {
  id: number;
  sourceId: string;
  targetId: string;
  type: string;
  directed: boolean;
  confidence: string;
  evidence: string;
  origin: string;
  status: string;
  sourceName: string;
  targetName: string;
}

export interface PathDTO {
  found: boolean;
  distance: number;
  nodes: GraphNode[];
  steps: { source: string; target: string; type: string; label: string }[];
}

export interface SearchHit {
  character: {
    id: string;
    name: string;
    className: string;
    mythology: string | null;
    imageUrl: string;
    degree: number;
    hasRelation: boolean;
  };
  score: number;
  matchedOn: string;
}

export interface AskResponse {
  answer: string;
  citations: { id: string; name: string; relation: string }[];
  subgraph: GraphDTO | null;
  engine: string;
}

export interface NlqFilters {
  mythologies?: string[] | null;
  types?: string[] | null;
  classes?: string[] | null;
  search?: string | null;
  gender?: string | null;
  onlyRelated?: boolean | null;
  explanation: string;
}

export interface StatsDTO {
  characters: number;
  relationships: number;
  approved: number;
  pending: number;
  enriched: number;
  missingMythology: number;
  missingDescription: number;
  orphanNodes: number;
  relationDist: Record<string, number>;
  confidenceDist: Record<string, number>;
  mythologyDist: Record<string, number>;
  classDist: Record<string, number>;
  originDist: Record<string, number>;
}

export interface SuggestionDTO {
  sourceId: string;
  targetId: string;
  commonNeighbors: string[];
  sameMythology: boolean;
  score: number;
}

export function imgProxy(url: string): string {
  if (!url) return "";
  return `/api/img?url=${encodeURIComponent(url)}`;
}

/** 同源角色雷达（/api/prototypes） */

export interface PrototypeFgoIncarnation {
  id: string;
  name: string;
  className: string;
  imageUrl: string;
}

export interface PrototypeOtherIncarnation {
  id: string;
  name: string;
  media: string;
  description: string;
}

export interface PrototypeWork {
  id: string;
  name: string;
  kind: string;
}

export interface PrototypeItem {
  id: string;
  name: string;
  mythology: string;
  qid: string;
  fgo: PrototypeFgoIncarnation[];
  others: PrototypeOtherIncarnation[];
  works: PrototypeWork[];
  incarnationCount: number;
  worksCount: number;
}
