"""API 领域模型（Pydantic v2）。OpenAPI 导出后经 openapi-typescript 同步到前端。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from theogony.core.enums import (
    Confidence,
    Mythology,
    RelationOrigin,
    RelationshipType,
    ReviewStatus,
)


class CharacterDTO(BaseModel):
    id: str
    wikiId: int
    name: str
    aliases: list[str] = []
    className: str = ""
    prototype: str = ""
    mythology: str | None = None
    description: str = ""
    mythologyBackground: str = ""
    alignment: str = ""
    gender: str = ""
    imageUrl: str = ""
    detailUrl: str = ""
    source: str = "fgo"
    extra: dict = {}
    degree: int = 0  # 一度关系数（由图服务填充）


class CharacterListItem(BaseModel):
    id: str
    name: str
    className: str = ""
    mythology: str | None = None
    imageUrl: str = ""
    degree: int = 0
    hasRelation: bool = False


class RelationshipDTO(BaseModel):
    id: int
    sourceId: str
    targetId: str
    type: RelationshipType
    directed: bool = True
    confidence: Confidence
    evidence: str = ""
    origin: RelationOrigin
    status: ReviewStatus = ReviewStatus.APPROVED
    sourceName: str = ""
    targetName: str = ""


class RelationshipSubmit(BaseModel):
    """众包关系提交（进入审核队列）。"""

    sourceId: str
    targetId: str
    type: RelationshipType
    evidence: str = Field(max_length=200)
    contributor: str = Field(default="匿名", max_length=32)


class ReviewDecision(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    note: str = ""


class GraphNodeDTO(BaseModel):
    id: str
    name: str
    kind: str = "character"  # character | myth
    mythology: str | None = None
    className: str = ""
    imageUrl: str = ""
    degree: int = 0
    wikiId: int = 0


class GraphLinkDTO(BaseModel):
    source: str
    target: str
    type: RelationshipType
    directed: bool = True
    confidence: str = "verified"


class GraphDTO(BaseModel):
    nodes: list[GraphNodeDTO]
    links: list[GraphLinkDTO]
    meta: dict = {}


class PathStepDTO(BaseModel):
    source: str
    target: str
    type: RelationshipType
    label: str = ""


class PathDTO(BaseModel):
    found: bool
    distance: int = 0
    nodes: list[GraphNodeDTO] = []
    steps: list[PathStepDTO] = []


class ClusterDTO(BaseModel):
    index: int
    size: int
    topMythology: str = ""
    members: list[str] = []


class SearchHitDTO(BaseModel):
    character: CharacterListItem
    score: float = 0.0
    matchedOn: str = ""


class SearchResponseDTO(BaseModel):
    query: str
    semantic: bool = False
    hits: list[SearchHitDTO] = []


class DailyGameDTO(BaseModel):
    date: str
    clues: list[str]
    totalCandidates: int = 0


class DailyGuessDTO(BaseModel):
    correct: bool
    answerId: str = ""
    answerName: str = ""
    reveal: bool = False


class AskRequest(BaseModel):
    question: str = Field(max_length=300)


class AskCitation(BaseModel):
    id: str
    name: str
    relation: str = ""


class AskResponse(BaseModel):
    answer: str
    citations: list[AskCitation] = []
    subgraph: GraphDTO | None = None
    engine: str = "graph"  # graph | llm | luna


class NlqRequest(BaseModel):
    query: str = Field(max_length=200)


class GraphFiltersDTO(BaseModel):
    """自然语言查图的输出：与 /api/graph 查询参数同构。"""

    mythologies: list[Mythology] | None = None
    types: list[RelationshipType] | None = None
    classes: list[str] | None = None
    search: str | None = None
    gender: str | None = None
    onlyRelated: bool | None = None
    explanation: str = ""


class WhatIfRequest(BaseModel):
    aId: str
    bId: str


class WhatIfResponse(BaseModel):
    narrative: str
    engine: str = "graph"


class SuggestionDTO(BaseModel):
    sourceId: str
    targetId: str
    commonNeighbors: list[str] = []
    sameMythology: bool = False
    score: float = 0.0


class StatsDTO(BaseModel):
    characters: int
    relationships: int
    approved: int
    pending: int
    enriched: int
    missingMythology: int
    missingDescription: int
    orphanNodes: int
    relationDist: dict[str, int] = {}
    confidenceDist: dict[str, int] = {}
    mythologyDist: dict[str, int] = {}
    classDist: dict[str, int] = {}
    originDist: dict[str, int] = {}


class EnrichResult(BaseModel):
    """LLM 角色增强的结构化输出契约。"""

    region: str = ""
    description: str = ""
    mythology_background: str = ""
    alignment: str = ""
    gender: str = ""
    noble_phantasms: list[str] = []
    aliases: list[str] = []


class RelCandidate(BaseModel):
    """LLM 关系挖掘的结构化输出契约。"""

    source_name: str
    target_name: str
    relationship: str
    confidence: str = "medium"
    evidence: str = ""
