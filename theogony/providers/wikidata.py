"""Wikidata Provider：神话/历史/通用知识侧的权威底座。

- 实体搜索（wbsearchentities）返回 QID + label + description，成本极低；
- 属性批量解析走 SPARQL（VALUES 批量），避免逐实体拉全量 claims；
- 关键属性：P31(instance of) / P144(based on) / P1074(fictional or mythical analog of)。
"""

from __future__ import annotations

import asyncio
import re

from theogony.providers.base import HttpProviderBase

_API = "https://www.wikidata.org/w/api.php"
_SPARQL = "https://query.wikidata.org/sparql"

# 强神话/君主/传说信号（描述命中即视为原型候选）
_STRONG_MYTHIC_RE = re.compile(
    r"神话|传说中|民间传说|神明|"
    r"皇帝|国王|女王|王后|法老|天皇|可汗|沙皇|苏丹|将军|武士|骑士|统治者|君主|海盗|探险家|大王|"
    r"神話|伝説|英雄|武将|女神|男神|"
    r"mytholog|legendary|folklore|deity|god of|goddess|"
    r"emperor|empress|pharaoh|shogun|samurai|knight|king of|queen of|tsar|warlord|conqueror|"
    r"monarch|sovereign|legend|figure in",
    re.IGNORECASE,
)
# 神话/传奇实体类（P31 值的 label 命中即视为神话侧实体：神话生物/神祇/传奇人物等，
# 这类实体常不带 Q5——吉尔伽美什王是 mythological king，玉藻前是 妖怪/九尾狐）
_MYTHIC_CLASS_RE = re.compile(
    r"神話|神话|傳說|传说|妖|神$|之神|deity|god$|god of|goddess|mytholog|legendary|"
    r"folklore|supernatural|saint|皇帝|国王|君主",
    re.IGNORECASE,
)

# 通用词义类（头衔/国家/词语/符号/人名等——同名巧合的主要来源）
_GENERIC_CLASS_RE = re.compile(
    r"title|country|sovereign state|word|symbol|given name|surname|album|film|television|"
    r"video game|manga|anime|novel|series|band|song|下位語|頭銜|國家|头衔|国家|姓氏|名",
    re.IGNORECASE,
)

# 虚构实体类（命中 → 这是"角色"实体，不是原型；Tier A 场景外一律排除）
_FICTIONAL_CLASS_RE = re.compile(
    r"fictional|虚构|虛構|架空|キャラクター|character|anime|manga|video game",
    re.IGNORECASE,
)

# 现代职业黑名单（无出生年佐证时排除，防原创角色撞名现代人）
_MODERN_OCC_RE = re.compile(
    r"歌手|演员|声优|政治人物|政治家|议员|说唱|音乐|偶像|漫画家|小说家|作家|记者|主持人|足球运动员|篮球|选手|艺术家|YouTuber|"
    r"歌手|俳優|声優|政治家|漫画家|小説家|作家|音楽家|アイドル|選手|タレント|"
    r"singer|rapper|musician|actor|actress|voice actor|politician|mangaka|novelist|writer|journalist|"
    r"footballer|basketball|artist|idol|member of|band|pornographic|adult",
    re.IGNORECASE,
)

# 虚构实体常见 P31 类（判定"这是角色实体"而非原型实体）
FICTIONAL_CLASSES = {
    "Q95074",    # fictional character（泛）
    "Q1114461",  # fictional human
    "Q11491122", # anime and manga character? （宽容集合，未命中也不影响）
}


class WikidataProvider(HttpProviderBase):
    name = "wikidata"
    prefer_proxy = True  # 大陆网络环境下 Wikidata 通常不可直连
    min_interval = 0.22  # wbsearchentities 持续高频会 429（实测），8 req/s 以下保守
    timeout = 30.0

    async def search_entities(self, name: str, language: str, limit: int = 10) -> list[dict]:
        # 不传 uselang：label/description 以搜索语言返回，供精确比对（zh 显示交给 labels_descriptions）
        d = await self._get(_API, params={
            "action": "wbsearchentities", "search": name, "language": language,
            "format": "json", "limit": limit,
        }, ttl=86400 * 7)
        return [{
            "qid": x["id"],
            "label": x.get("label", ""),
            "description": x.get("description", ""),
            "match": x.get("match", {}).get("type", ""),
        } for x in d.get("search", [])]

    async def resolve_claims(self, qids: list[str], batch_size: int = 100) -> dict[str, dict]:
        """批量取 P31/P144/P1074/P569。返回 {qid: {p31/p144/p1074: [...], birth_year: int|None}}。"""
        out: dict[str, dict] = {}
        for i in range(0, len(qids), batch_size):
            chunk = qids[i:i + batch_size]
            values = " ".join(f"wd:{q}" for q in chunk)
            query = (
                "SELECT ?q ?p31 ?p144 ?p1074 ?birth WHERE { VALUES ?q { " + values + " } "
                "OPTIONAL { ?q wdt:P31 ?p31 } OPTIONAL { ?q wdt:P144 ?p144 } "
                "OPTIONAL { ?q wdt:P1074 ?p1074 } OPTIONAL { ?q wdt:P569 ?birth } }"
            )
            d = await self._get(_SPARQL, params={"query": query, "format": "json"},
                                headers={"Accept": "application/sparql-results+json"}, ttl=None)
            for row in d.get("results", {}).get("bindings", []):
                q = row["q"]["value"].rsplit("/", 1)[-1]
                rec = out.setdefault(q, {"p31": [], "p144": [], "p1074": []})
                for prop in ("p31", "p144", "p1074"):
                    if prop in row:
                        rec[prop].append(row[prop]["value"].rsplit("/", 1)[-1])
            await asyncio.sleep(0)  # 让出事件循环
        return out

    async def labels_descriptions(self, qids: list[str], batch_size: int = 100) -> dict[str, dict]:
        """批量取实体 zh/en label 与 description。返回 {qid: {label, description}}。"""
        out: dict[str, dict] = {}
        for i in range(0, len(qids), batch_size):
            chunk = qids[i:i + batch_size]
            values = " ".join(f"wd:{q}" for q in chunk)
            query = (
                "SELECT ?q ?l ?d WHERE { VALUES ?q { " + values + " } "
                "OPTIONAL { ?q rdfs:label ?l FILTER(LANG(?l) IN (\"zh\", \"zh-hans\", \"en\")) } "
                "OPTIONAL { ?q schema:description ?d FILTER(LANG(?d) IN (\"zh\", \"en\")) } }"
            )
            d = await self._get(_SPARQL, params={"query": query, "format": "json"},
                                headers={"Accept": "application/sparql-results+json"}, ttl=None)
            for row in d.get("results", {}).get("bindings", []):
                q = row["q"]["value"].rsplit("/", 1)[-1]
                rec = out.setdefault(q, {"label": "", "description": ""})
                if "l" in row:
                    lang = row["l"].get("xml:lang", "")
                    val = row["l"]["value"]
                    if not rec["label"] or lang.startswith("zh"):
                        rec["label"] = val
                if "d" in row:
                    lang = row["d"].get("xml:lang", "")
                    val = row["d"]["value"]
                    if not rec["description"] or lang.startswith("zh"):
                        rec["description"] = val
            await asyncio.sleep(0)
        return out

    @staticmethod
    def is_historic_or_mythic(claims: dict, description: str,
                              p31_meta: dict[str, dict] | None = None) -> bool:
        """是否"历史/神话人物"（区别于虚构角色、现代人物与同名词义实体）。

        优先级（高→低）：
        ① P31 实体类为神话侧且无通用词义类（男神/神话生物/传奇国王——这类实体常不带 Q5；
           "神话+文学角色"双标的多聞天王由此放行）；
        ② 描述命中强神话/君主信号，且描述/类名无通用词义；
        ③ 1900 年前出生且描述无现代职业黑名单；
        其余（含虚构角色类、头衔/国家/symbol 等词义实体）一律拒绝。
        """
        desc = description or ""
        classes = claims.get("p31", [])
        metas = [(p31_meta or {}).get(c) for c in classes]
        metas = [m for m in metas if m]

        def _hit(re_: re.Pattern[str]) -> bool:
            return any(re_.search(f'{m.get("label", "")} {m.get("description", "")}') for m in metas)

        if _hit(_MYTHIC_CLASS_RE) and not _hit(_GENERIC_CLASS_RE):
            return True
        generic_hit = _hit(_GENERIC_CLASS_RE) or bool(_GENERIC_CLASS_RE.search(desc))
        if _STRONG_MYTHIC_RE.search(desc) and not generic_hit:
            return True
        birth = claims.get("birth_year")
        historical = birth is not None and birth < 1900
        modern = bool(_MODERN_OCC_RE.search(desc))
        return historical and not modern
