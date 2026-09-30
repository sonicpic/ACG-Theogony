"""远程监督 bootstrap：用已审关系当种子，从语料学触发词，扫全库产关系候选。

设计（防噪声三原则）：
  1. 对称关系（盟友/敌对/恋人/兄弟/配偶/交手）→ 触发词自由扫描：
     种子 = 人工先验 + 远程监督学习（频次≥3、非停用词、非实体名）
  2. 方向敏感关系（父母/师父）→ 只走显式句式模板，不做自由扫描
  3. DERIVED_FROM 不参与 —— 原型链有结构化来源（Wikidata），文本不可靠

产出全部 status=pending 入审核队列，证据为原句。

用法：
  python -u -m theogony.pipelines.bootstrap_relations --dry-run
  python -u -m theogony.pipelines.bootstrap_relations
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from sqlalchemy import select

from theogony.core.config import get_settings
from theogony.core.db import get_session, rebuild_fts
from theogony.core.graph import GraphService
from theogony.core.orm import Character, Relationship

CORPUS: Path = get_settings().data_dir / "corpus" / "sentences.jsonl"

_CONNECTOR_RE = re.compile(r"[\u4e00-\u9fff]{2,6}|[a-zA-Z]{4,16}")

_STOP = {
    "and", "the", "of", "is", "was", "are", "were", "in", "on", "at", "to",
    "his", "her", "their", "with", "for", "who", "whom", "that", "which",
    "also", "both", "two", "one", "other", "another", "been", "have", "has",
    "had", "not", "but", "she", "they", "them", "him", "about", "after",
    "before", "from", "into", "when", "what", "then", "would", "could",
    "should", "will", "this", "these", "those", "there", "here", "over",
    "under", "out", "asks", "tells", "said", "says", "made", "make", "finds",
    "found", "able", "because", "while", "during", "where", "still", "just",
    "even", "same", "super", "used", "help", "orders", "sends", "meets",
    "reveals", "herself", "himself", "alter", "lily", "face",
    "之后", "以及", "并且", "同时", "一个", "这个", "那个", "自己", "他们",
    "她们", "其中", "因为", "但是", "然后", "所以", "还是", "已经", "正在",
}

# 对称关系（schema 中 undirected）——触发词自由扫描
_SYMMETRIC_SEEDS: dict[str, set[str]] = {
    "SPOUSE_OF": {"wife", "husband", "spouse", "married", "marriage", "妻子", "丈夫", "配偶", "结婚"},
    "LOVER_OF": {"lover", "lovers", "romance", "恋人", "情人", "相爱", "恋情"},
    "SIBLING_OF": {"brother", "sister", "sibling", "twin", "brothers", "sisters",
                   "兄弟", "姐妹", "双胞胎", "兄妹", "姐弟"},
    "ALLY_OF": {"ally", "allies", "friend", "friends", "companion", "comrade", "comrades",
                "served", "together", "alongside", "盟友", "同伴", "战友", "侍从", "部下", "追随"},
    "ENEMY_OF": {"enemy", "enemies", "rival", "rivals", "opponent", "killed", "slain",
                 "defeated", "murdered", "敌对", "宿敌", "对手", "杀死", "击败", "讨伐", "背叛"},
    "FOUGHT_WITH": {"fought", "fight", "battle", "battled", "clash", "clashed", "combat",
                    "duel", "交战", "战斗", "对决", "交手", "讨伐"},
}

# 方向敏感关系——双实体锚定句式（缺失锚定会误判同句第三方，实测踩坑）
# 每条模板必须同时含 {A} 与 {B}；语义：
#   P1: "{A}'s/{A}的 + 亲属词 … {B}" → B 是该亲属
#   P2/P3: "{A} … is/was/是 … 亲属词 of/的 … {B}" → A 是长辈
_PARENT_ROLES = r"(?:father|mother|父亲|母亲)"
_MENTOR_ROLES = r"(?:mentor|teacher|师父|师傅|老师)"
_CHILD_ROLES = r"(?:son|daughter|儿子|女儿)"


def _directional_templates() -> list[tuple[str, str, bool]]:
    """(regex, rtype, first_entity_is_subject)。"""
    t: list[tuple[str, str, bool]] = []
    for roles, rtype in ((_PARENT_ROLES, "PARENT_OF"), (_MENTOR_ROLES, "MENTOR_OF")):
        # A's father/mentor … B → B 是 A 的长辈（B 为关系主体）
        t.append((rf"{{A}}(?:'s|的)[^.!?]{{0,14}}{roles}[^.!?]{{0,30}}{{B}}", rtype, False))
        # A is/was [something of X and] the father/mentor of B → A 为关系主体
        # （{0,60} 覆盖 "the sister of X and mother of Y" 列表式）
        t.append((rf"{{A}}[^.!?]{{0,60}}(?:is|was)\s+the\s+(?:[^,.!?]{{1,40}}and\s+)?{roles}\s+of\s+{{B}}", rtype, True))
        # 中文语序一：A 是 B 的师父/父亲（角色词在 B 后）
        t.append((rf"{{A}}(?:是|作为)[^。！？]{{0,6}}{{B}}[^。！？]{{0,8}}的?[^。！？]{{0,4}}{roles}", rtype, True))
        # 中文语序二：A 是（伟大的）父亲/师父 … B
        t.append((rf"{{A}}[^。！？]{{0,12}}(?:是|作为)[^。！？]{{0,10}}{roles}[^。！？]{{0,4}}的?[^。！？]{{0,12}}{{B}}", rtype, True))
    # A's son … B → A 是 B 的父（A 为关系主体）
    t.append((rf"{{A}}(?:'s|的)[^.!?]{{0,14}}{_CHILD_ROLES}[^.!?]{{0,30}}{{B}}", "PARENT_OF", True))
    return t


_DIRECTIONAL: list[tuple[str, str, bool]] = []  # 运行时由 _directional_templates() 构造


def load_sentences() -> list[dict]:
    if not CORPUS.exists():
        raise SystemExit(f"句子库不存在：{CORPUS}（先跑 crawl_corpus）")
    return [json.loads(line) for line in CORPUS.open(encoding="utf-8")]


def connectors_between(sentence: str, match_a: str, match_b: str) -> list[str]:
    """两个实体匹配串之间的连接词。"""
    out: list[str] = []
    for x, y in ((match_a, match_b), (match_b, match_a)):
        i = sentence.find(x)
        while i != -1:
            j = sentence.find(y, i + len(x))
            if j != -1 and j - i - len(x) <= 60:
                mid = sentence[i + len(x):j]
                out.extend(w.lower() for w in _CONNECTOR_RE.findall(mid))
            i = sentence.find(x, i + 1)
    return out


def learn_triggers(sentences: list[dict], seed_pairs: dict[frozenset, str],
                   entity_names: set[str]) -> dict[str, set[str]]:
    """远程监督：种子对共现句 → 学习各关系类型的触发词。"""
    learned: dict[str, Counter] = {}
    for s in sentences:
        ids = frozenset(e["id"] for e in s["entities"])
        if len(ids) < 2:
            continue
        for pair, rtype in seed_pairs.items():
            if rtype not in _SYMMETRIC_SEEDS:
                continue
            if not pair <= ids:
                continue
            ents = {e["id"]: e["match"] for e in s["entities"]}
            a, b = tuple(pair)
            for w in connectors_between(s["text"], ents[a], ents[b]):
                if w in _STOP or w in entity_names or len(w) < 3:
                    continue
                learned.setdefault(rtype, Counter())[w] += 1
    triggers = {rt: set(tv) for rt, tv in _SYMMETRIC_SEEDS.items()}
    print("[triggers] 远程监督学习（频次≥3）：")
    for rt, counter in sorted(learned.items()):
        extra = {w for w, n in counter.items() if n >= 3}
        if extra:
            triggers.setdefault(rt, set()).update(extra)
            print(f"  {rt}: +{sorted(extra)[:12]}")
    return triggers


def directional_candidates(sentence: str, a: dict, b: dict) -> list[tuple[str, str, str]]:
    """双实体锚定模板 → (source_id, target_id, type)。"""
    out: list[tuple[str, str, str]] = []
    for pat, rtype, first_is_subject in _directional_templates():
        for left, right in ((a, b), (b, a)):
            rex = re.compile(
                pat.replace("{A}", re.escape(left["match"])).replace("{B}", re.escape(right["match"])),
                re.IGNORECASE)
            if rex.search(sentence):
                src = left if first_is_subject else right
                dst = right if first_is_subject else left
                out.append((src["id"], dst["id"], rtype))
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    sentences = load_sentences()
    print(f"[corpus] 句子库 {len(sentences)} 条")

    session = get_session()
    try:
        chars = {c.id: c for c in session.execute(select(Character)).scalars().all()}
        from theogony.core.orm import Alias
        entity_names = {c.name.lower() for c in chars.values() if c.name}
        entity_names.update(a.alias.lower() for a in session.execute(select(Alias)).scalars().all() if a.alias)
        seeds = session.execute(
            select(Relationship).where(
                Relationship.status == "approved",
                Relationship.origin.in_(["manual", "llm"]),
            )
        ).scalars().all()
        seed_pairs: dict[frozenset, str] = {}
        for r in seeds:
            if r.source_id in chars and r.target_id in chars \
                    and chars[r.source_id].class_name != "原型" \
                    and chars[r.target_id].class_name != "原型":
                seed_pairs[frozenset((r.source_id, r.target_id))] = r.type
        print(f"[seeds] 可用种子 {len(seed_pairs)} 对")

        triggers = learn_triggers(sentences, seed_pairs, entity_names)

        existing: set[tuple] = set()
        for r in session.execute(select(Relationship)).scalars().all():
            existing.add((r.source_id, r.target_id, r.type))
            existing.add((r.target_id, r.source_id, r.type))

        candidates: dict[tuple, dict] = {}

        def add(src: str, dst: str, rtype: str, evidence: str, trig: list[str], hits: int) -> None:
            key, rkey = (src, dst, rtype), (dst, src, rtype)
            if key in existing or rkey in existing or key in candidates or rkey in candidates:
                return
            candidates[key] = {"evidence": evidence, "triggers": trig, "hits": hits}

        for s in sentences:
            ents = s["entities"]
            ev = f"[{s['title']}] {s['text'][:180]}"
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    a, b = ents[i], ents[j]
                    if a["id"] == b["id"]:
                        continue
                    for src, dst, rt in directional_candidates(s["text"], a, b):
                        add(src, dst, rt, ev, ["template"], 2)
                    words = set(w.lower() for w in connectors_between(s["text"], a["match"], b["match"]))
                    if words:
                        best_type, best_hits = None, 0
                        for rt, tv in triggers.items():
                            hits = len(words & tv)
                            if hits > best_hits:
                                best_type, best_hits = rt, hits
                        if best_type and best_hits >= 1:
                            src, dst = sorted([a["id"], b["id"]])
                            add(src, dst, best_type, ev, sorted(words & triggers[best_type])[:4], best_hits)

        print(f"\n[candidates] 产出 {len(candidates)} 条候选（全部将进 pending 审核）")
        print("  类型分布:", dict(Counter(k[2] for k in candidates)))
        top = sorted(candidates.items(), key=lambda kv: (-kv[1]["hits"], kv[1]["evidence"]))[:14]
        for (src, dst, rt), info in top:
            print(f"  {chars[src].name} --{rt}--> {chars[dst].name}  {info['triggers']}")
            print(f"    {info['evidence'][:88]}")

        if not args.dry_run and candidates:
            for (src, dst, rt), info in candidates.items():
                session.add(Relationship(
                    source_id=src, target_id=dst, type=rt,
                    directed=rt not in ("SIBLING_OF", "LOVER_OF", "SPOUSE_OF", "ENEMY_OF", "FOUGHT_WITH", "ALLY_OF"),
                    confidence="medium", evidence=info["evidence"],
                    origin="bootstrap", status="pending"))
            session.commit()
            rebuild_fts(session)
            print(f"\n[db] 已写入 {len(candidates)} 条 pending 候选 → /review 审核")
    finally:
        session.close()
    GraphService.instance().refresh()


if __name__ == "__main__":
    main()
