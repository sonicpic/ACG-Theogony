/** API 客户端（统一走 Next rewrite 的 /api/*）。 */

import type {
  AskResponse,
  CharacterDTO,
  GraphDTO,
  NlqFilters,
  PathDTO,
  PrototypeItem,
  RelationshipDTO,
  SearchHit,
  StatsDTO,
  SuggestionDTO,
} from "./types";

const BASE = "/api";

async function get<T>(path: string, params?: Record<string, string | number | boolean | string[] | undefined>): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) {
    if (v === undefined || v === "" || v === null) continue;
    if (Array.isArray(v)) v.forEach((item) => qs.append(k, String(item)));
    else qs.append(k, String(v));
  }
  const url = qs.toString() ? `${BASE}${path}?${qs}` : `${BASE}${path}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${text.slice(0, 120)}`);
  }
  return res.json() as Promise<T>;
}

async function post<T>(path: string, body: unknown, token?: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { "X-Review-Token": token } : {}),
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText} ${text.slice(0, 160)}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  prototypes(): Promise<{ items: PrototypeItem[] }> {
    return get("/prototypes");
  },
  graph(params?: {
    mythologies?: string[];
    types?: string[];
    classes?: string[];
    gender?: string;
    onlyRelated?: boolean;
    includeMythNodes?: boolean;
    maxWikiId?: number;
  }) {
    return get<GraphDTO>("/graph", params as never);
  },
  clusters() {
    return get<{ clusters: import("./types").Cluster[] }>("/graph/clusters");
  },
  options() {
    return get<{ classes: string[]; mythologies: string[]; sources: string[] }>("/characters/meta/options");
  },
  character(id: string) {
    return get<CharacterDTO>(`/characters/${id}`);
  },
  characterRelationships(id: string) {
    return get<RelationshipDTO[]>(`/characters/${id}/relationships`, { includePending: "false" });
  },
  family(id: string) {
    return get<{ center: string | null; nodes: import("./types").GraphNode[]; links: (import("./types").GraphLink & { label?: string })[] }>(
      `/characters/${id}/family`
    );
  },
  ego(id: string, hops = 2) {
    return get<GraphDTO>(`/characters/${id}/ego`, { hops });
  },
  paths(from: string, to: string) {
    return get<PathDTO>("/paths", { from_id: from, to_id: to });
  },
  search(q: string, limit = 10) {
    return get<{ query: string; semantic: boolean; hits: SearchHit[] }>("/search", { q, limit });
  },
  stats() {
    return get<StatsDTO>("/stats");
  },
  suggest(limit = 20) {
    return get<SuggestionDTO[]>("/ai/suggest", { limit });
  },
  ask(question: string) {
    return post<AskResponse>("/ai/ask", { question });
  },
  nlq(query: string) {
    return post<NlqFilters>("/ai/nlq", { query });
  },
  whatif(aId: string, bId: string) {
    return post<{ narrative: string; engine: string }>("/ai/whatif", { aId, bId });
  },
  daily() {
    return get<{ date: string; clues: string[]; allClues: string[]; totalCandidates: number; maxAttempts: number }>(
      "/games/daily"
    );
  },
  guess(name: string) {
    return post<{ correct: boolean; matchedId: string; answerId: string; answerName: string; hint: string }>(
      "/games/daily/guess",
      { guess: name }
    );
  },
  reveal() {
    return post<{ answerId: string; answerName: string; imageUrl: string }>("/games/daily/reveal", {});
  },
  relationshipsQuery(params: { status?: string; origin?: string; limit?: number }) {
    return get<{ total: number; items: RelationshipDTO[] }>("/relationships", params as never);
  },
  submitRelation(payload: { sourceId: string; targetId: string; type: string; evidence: string; contributor?: string }) {
    return post<RelationshipDTO>("/relationships", payload);
  },
  reviewPending(_token: string, origin?: string) {
    return get<{ total: number; items: RelationshipDTO[] }>("/review/pending", {
      limit: 200,
      origin: origin && origin !== "all" ? origin : undefined,
    });
  },
  reviewDecide(id: number, action: "approve" | "reject", token: string, note = "") {
    return post<RelationshipDTO>(`/review/${id}`, { action, note }, token);
  },
  reviewBatch(decisions: Record<string, string>, token: string) {
    return post<{ approved: number; rejected: number; skipped: number }>("/review/batch", decisions, token);
  },
  refreshGraph() {
    return post<{ ok: boolean }>("/graph/refresh", {});
  },
};
