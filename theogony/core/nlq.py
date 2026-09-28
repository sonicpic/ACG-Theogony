"""自然语言查图（NLQ）：规则解析器（离线可用）+ LLM 增强（在线时）。"""

from __future__ import annotations

from theogony.core.enums import RELATION_META, Mythology

# 关键词 → 关系类型
_TYPE_KEYWORDS: list[tuple[str, str]] = [
    ("父母", ["PARENT_OF"]),
    ("父亲", ["PARENT_OF"]),
    ("母亲", ["PARENT_OF"]),
    ("父子", ["PARENT_OF"]),
    ("母女", ["PARENT_OF"]),
    ("家长", ["PARENT_OF"]),
    ("子女", ["PARENT_OF"]),
    ("孩子", ["PARENT_OF"]),
    ("儿子", ["PARENT_OF"]),
    ("女儿", ["PARENT_OF"]),
    ("兄弟", ["SIBLING_OF"]),
    ("姐妹", ["SIBLING_OF"]),
    ("配偶", ["SPOUSE_OF"]),
    ("夫妻", ["SPOUSE_OF"]),
    ("妻子", ["SPOUSE_OF"]),
    ("丈夫", ["SPOUSE_OF"]),
    ("恋人", ["LOVER_OF"]),
    ("情侣", ["LOVER_OF"]),
    ("情人", ["LOVER_OF"]),
    ("主仆", ["MASTER_OF"]),
    ("主人", ["MASTER_OF"]),
    ("从者", ["MASTER_OF"]),
    ("盟友", ["ALLY_OF"]),
    ("同伴", ["ALLY_OF"]),
    ("战友", ["ALLY_OF"]),
    ("敌对", ["ENEMY_OF"]),
    ("敌人", ["ENEMY_OF"]),
    ("仇敌", ["ENEMY_OF"]),
    ("宿敌", ["ENEMY_OF"]),
    ("战斗", ["FOUGHT_WITH"]),
    ("交手", ["FOUGHT_WITH"]),
    ("对决", ["FOUGHT_WITH"]),
    ("师傅", ["MENTOR_OF"]),
    ("师父", ["MENTOR_OF"]),
    ("师徒", ["MENTOR_OF"]),
    ("老师", ["MENTOR_OF"]),
    ("性转", ["GENDER_SWAP"]),
    ("原型", ["PROTOTYPE_IS", "DERIVED_FROM"]),
    ("家族", ["PARENT_OF", "SIBLING_OF", "SPOUSE_OF", "LOVER_OF"]),
    ("血缘", ["PARENT_OF", "SIBLING_OF", "SPOUSE_OF"]),
    ("亲情", ["PARENT_OF", "SIBLING_OF"]),
]

_CLASS_KEYWORDS = [
    "Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker",
    "Ruler", "Avenger", "MoonCancer", "Foreigner", "Pretender", "AlterEgo",
    "Shielder", "Beast",
    "剑阶", "弓阶", "枪阶", "骑阶", "术阶", "杀阶", "狂阶",
]
_CLASS_MAP = {
    "剑阶": "Saber", "弓阶": "Archer", "枪阶": "Lancer", "骑阶": "Rider",
    "术阶": "Caster", "杀阶": "Assassin", "狂阶": "Berserker",
}


def rule_parse(query: str) -> dict:
    """离线规则解析：返回与 /api/graph 查询参数同构的过滤条件。"""
    q = query.strip()
    filters: dict = {"explanation": ""}

    # 神话体系
    myths: list[str] = []
    for m in Mythology:
        core = m.value.replace("神话", "").replace("教", "")
        if m.value in q or (len(core) >= 2 and core in q):
            myths.append(m.value)
    if myths:
        filters["mythologies"] = myths

    # 关系类型
    types: list[str] = []
    for kw, rels in _TYPE_KEYWORDS:
        if kw in q:
            for r in rels:
                if r not in types:
                    types.append(r)
    if types:
        filters["types"] = types

    # 职阶
    classes: list[str] = []
    for ck in _CLASS_KEYWORDS:
        if ck.lower() in q.lower():
            classes.append(_CLASS_MAP.get(ck, ck))
    if classes:
        filters["classes"] = classes

    # 性别
    if "女性" in q or "女主" in q:
        filters["gender"] = "女"
    elif "男性" in q or "男主" in q:
        filters["gender"] = "男"

    # 孤立节点
    if "有关系" in q or "相关" in q:
        filters["onlyRelated"] = True

    parts = []
    if myths:
        parts.append("体系=" + "/".join(myths))
    if types:
        parts.append("关系=" + "/".join(RELATION_META.get(t, {}).get("label", t) for t in types))
    if classes:
        parts.append("职阶=" + "/".join(classes))
    if filters.get("gender"):
        parts.append("性别=" + filters["gender"])
    filters["explanation"] = "规则解析：" + ("；".join(parts) if parts else "未识别到过滤条件")
    return filters


NLQ_SYSTEM_PROMPT = """你是知识图谱查询解析器。把用户的自然语言转换为图过滤条件 JSON。
可用神话体系：{mythologies}
可用关系类型：{types}
可用职阶：{classes}
输出字段（全部可选）：mythologies[], types[], classes[], gender("男"/"女"), onlyRelated(bool), search(角色名等自由文本), explanation(一句话中文说明你提取了什么)。
不要编造词表以外的值；与图筛选无关的问题 explanation 里说明无法解析。"""


async def llm_parse(query: str) -> dict | None:
    """LLM 增强解析（需配置任一 LLM 提供方），失败返回 None 由规则兜底。"""
    from theogony.core.llm import Provider, chat_json, get_provider
    from theogony.core.models import GraphFiltersDTO

    provider: Provider | None = get_provider()
    if provider is None:
        return None

    class NlqOut(GraphFiltersDTO):
        pass

    result = await chat_json(
        provider,
        NlqOut,
        NLQ_SYSTEM_PROMPT.format(
            mythologies="、".join(m.value for m in Mythology),
            types="、".join(RELATION_META),
            classes="、".join(_CLASS_KEYWORDS[:14]),
        )
        + f"\n\n用户问题：{query}",
        temperature=0.0,
        max_tokens=400,
    )
    if result is None:
        return None
    data = result.model_dump(exclude_none=True)
    return data


def merge_filters(rule: dict, llm_out: dict | None) -> dict:
    """融合规则与 LLM 结果：LLM 优先，规则补充。"""
    if not llm_out:
        return rule
    merged = {k: v for k, v in llm_out.items() if v}
    for key in ("mythologies", "types", "classes"):
        if key not in merged and rule.get(key):
            merged[key] = rule[key]
    if not merged.get("explanation"):
        merged["explanation"] = rule.get("explanation", "")
    else:
        merged["explanation"] = merged["explanation"] + "（规则补充已合并）"
    return merged
