"""AI 端点：GraphRAG 问答 / 自然语言查图 / What-if 推演 / 图谱补全建议。

设计原则：图检索永远先做（确定性、可解释）；LLM 只负责语言生成；
无任何 LLM Key 时自动降级为"纯图回答"，功能不缺失。
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Query

from theogony.core.db import get_session
from theogony.core.enums import RELATION_META
from theogony.core.graph import GraphService
from theogony.core.llm import Provider, chat_text, get_provider, luna_research
from theogony.core.models import (
    AskCitation,
    AskRequest,
    AskResponse,
    NlqRequest,
    SuggestionDTO,
    WhatIfRequest,
    WhatIfResponse,
)
from theogony.core.nlq import llm_parse, merge_filters, rule_parse
from theogony.core.orm import Character
from theogony.core.search import hybrid_search

router = APIRouter(tags=["ai"])


_STOP_WORDS = ("是什么", "的关系", "关系", "怎么样", "如何", "介绍", "说说", "讲讲", "请问", "一下", "告诉", "谁是", "谁在", "吗", "呢", "吧", "了", "的", "和谁", "在哪")


def _clean_token(token: str) -> str:
    for w in _STOP_WORDS:
        token = token.replace(w, "")
    return token.strip("的?？!！。 ，,")


def _link_entities(question: str, top_n: int = 3) -> list[Character]:
    """实体链接：全名直接命中 + 连词分句检索召回；同名变体取编号最小的本家。"""
    gs = GraphService.instance()
    snap = gs.snapshot
    candidates: dict[str, int] = {}
    # 1) 名称/别名直接命中
    for name, cid in snap.name_index.items():
        if len(name) >= 2 and name in question:
            candidates[cid] = len(name) * 10
    # 2) 按标点与常见连词分句，检索召回补充（"A和B的关系" 类问题）
    tokens = re.split(r"[，。？！,.\s、]+|(?:和|与|跟|对|对阵|VS|vs)", question)
    if len(tokens) > 1 or not candidates:
        for token in tokens:
            token = _clean_token(token)
            if len(token) < 2:
                continue
            ranked, _ = hybrid_search(token, limit=3)
            for cid, score in ranked:
                candidates[cid] = candidates.get(cid, 0) + (2 if score > 0.3 else 1)
    # 同名/同前缀变体归并：保留编号最小（本家）版本
    by_name: dict[str, tuple[int, str]] = {}
    for cid, score in candidates.items():
        c = snap.characters.get(cid)
        if not c:
            continue
        base = c.name.split("〔")[0].split("(")[0].strip()
        prev = by_name.get(base)
        if prev is None or cid < prev[1]:
            by_name[base] = (score, cid)
    ranked = sorted(by_name.values(), key=lambda kv: -kv[0])[:top_n]
    session = get_session()
    try:
        result = []
        for _score, cid in ranked:
            c = session.get(Character, cid)
            if c:
                result.append(c)
        return result
    finally:
        session.close()


def _graph_context_answer(question: str, entities: list[Character]) -> tuple[str, list[AskCitation], dict]:
    """确定性图回答（无 LLM 时的回退，也是 LLM 的上下文）。"""
    gs = GraphService.instance()
    snap = gs.snapshot
    lines: list[str] = []
    citations: list[AskCitation] = []
    entity_ids = [e.id for e in entities]
    for e in entities:
        lines.append(f"◆ {e.name}（{e.mythology or '体系未知'}｜{e.class_name or '职阶未知'}）")
        if e.description:
            lines.append(f"  {e.description[:120]}")
        neighbors = snap.adjacency.get(e.id, [])
        if neighbors:
            shown = 0
            for nid, rtype, conf in neighbors:
                n = snap.characters.get(nid)
                if not n:
                    continue
                label = RELATION_META.get(rtype, {}).get("label", rtype)
                lines.append(f"  —{label}→ {n.name}（置信度 {conf}）")
                citations.append(AskCitation(id=nid, name=n.name, relation=rtype))
                shown += 1
                if shown >= 8:
                    lines.append("  …（更多关系见图谱）")
                    break
        else:
            lines.append("  （暂无已审核的角色间关系）")
    if not entities:
        lines.append("没有在问题中识别到已知角色。可以试试：'阿尔托莉雅和莫德雷德是什么关系？'")
    subgraph = gs.subgraph_around(entity_ids, hops=1, cap=60)
    return "\n".join(lines), citations, subgraph


ASK_SYSTEM = """你是神话关系图谱的问答助手。基于给定的图检索资料回答用户问题：
- 只使用资料中的事实，不要编造关系
- 回答末尾用【依据】列出引用的角色名
- 中文回答，简洁（≤200字）"""


def _interactive_provider() -> Provider | None:
    """交互式端点用 medium 思考强度（max 在中转站上太慢，问答场景不需要）。"""
    provider = get_provider()
    if provider is not None and provider.name == "luna":
        provider.extra_body = {**provider.extra_body, "reasoning_effort": "medium"}
    return provider


@router.post("/ai/ask", response_model=AskResponse)
async def ask(payload: AskRequest):
    entities = _link_entities(payload.question)
    graph_answer, citations, subgraph = _graph_context_answer(payload.question, entities)

    provider: Provider | None = _interactive_provider()
    if provider is None:
        return AskResponse(answer=graph_answer, citations=citations[:30], subgraph=subgraph, engine="graph")

    context = "图检索资料：\n" + graph_answer
    try:
        answer = await chat_text(
            provider,
            payload.question,
            system=ASK_SYSTEM + "\n\n" + context,
            temperature=0.3,
            max_tokens=600,
        )
        return AskResponse(answer=answer, citations=citations[:30], subgraph=subgraph, engine=provider.name)
    except Exception:
        return AskResponse(
            answer=f"（LLM 调用失败，降级为图检索回答）\n{graph_answer}",
            citations=citations[:30],
            subgraph=subgraph,
            engine="graph",
        )


@router.post("/ai/nlq")
async def nlq(payload: NlqRequest):
    rule = rule_parse(payload.query)
    llm_out = None
    try:
        llm_out = await llm_parse(payload.query)
    except Exception:
        llm_out = None
    merged = merge_filters(rule, llm_out)
    return merged


@router.post("/ai/whatif", response_model=WhatIfResponse)
async def whatif(payload: WhatIfRequest):
    session = get_session()
    try:
        a = session.get(Character, payload.aId)
        b = session.get(Character, payload.bId)
        if not a or not b:
            raise HTTPException(404, "角色不存在")
        gs = GraphService.instance()
        snap = gs.snapshot
        a_allies = [snap.characters[n].name for n, t, _ in snap.adjacency.get(a.id, []) if t in ("ALLY_OF", "MASTER_OF")][:4]
        b_allies = [snap.characters[n].name for n, t, _ in snap.adjacency.get(b.id, []) if t in ("ALLY_OF", "MASTER_OF")][:4]

        def profile(c: Character) -> str:
            return (
                f"{c.name}（{c.class_name}｜{c.mythology or '?'}｜阵营 {c.alignment or '?'}）"
                f"{'｜盟友:' + '、'.join(a_allies) if (c is a and a_allies) else ''}"
                f"{'｜盟友:' + '、'.join(b_allies) if (c is b and b_allies) else ''}"
                f"：{c.description[:100]}"
            )

        fallback = (
            f"⚔️ {a.name} VS {b.name}\n"
            f"{a.name}：{a.class_name}，{a.mythology or '体系未知'}，{a.description[:80]}\n"
            f"{b.name}：{b.class_name}，{b.mythology or '体系未知'}，{b.description[:80]}\n"
            "（配置 LLM 后可获得完整剧情推演）"
        )

        provider = _interactive_provider()
        if provider is None:
            return WhatIfResponse(narrative=fallback, engine="graph")
        prompt = (
            f"写一段 250 字以内、生动有趣的 FGO 风格对决短文：{a.name} 对阵 {b.name}。"
            f"结合双方设定、宝具与阵营，交代交手过程与结果（平局也可），最后一句给胜者或总结。\n\n"
            f"资料A：{profile(a)}\n资料B：{profile(b)}"
        )
        try:
            narrative = await chat_text(provider, prompt, temperature=0.8, max_tokens=600)
            return WhatIfResponse(narrative=narrative, engine=provider.name)
        except Exception:
            return WhatIfResponse(narrative=fallback, engine="graph")
    finally:
        session.close()


@router.get("/ai/suggest", response_model=list[SuggestionDTO])
def suggest(limit: int = Query(default=20, le=100)):
    return GraphService.instance().suggest_completions(limit=limit)


@router.post("/ai/research")
async def research(question: str):
    """gpt-luna-5.6 联网研究（需配置 LUNA_*）。"""
    provider = get_provider("luna")
    if provider is None:
        raise HTTPException(503, "未配置 LUNA_API_KEY / LUNA_API_BASE")
    answer = await luna_research(provider, question)
    return {"answer": answer, "engine": "luna"}
