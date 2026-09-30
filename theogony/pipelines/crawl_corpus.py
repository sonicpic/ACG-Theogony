"""型月维基语料收割：全站 wikitext → 清洗分句 → 含实体句子库（传统 NLP 管线的语料层）。

产物：
  data/corpus/pages.jsonl      每页 {title, sections:[{heading, text}]}（章节过滤后）
  data/corpus/sentences.jsonl  含 ≥2 已知实体的句子 {text, entities:[{id,name}], title}

用法：
  python -u -m theogony.pipelines.crawl_corpus --limit 60   # 试跑
  python -u -m theogony.pipelines.crawl_corpus              # 全站
  python -u -m theogony.pipelines.crawl_corpus --from-pages   # 页面已缓存，只重跑清洗
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time

from sqlalchemy import select

from theogony.core.config import get_settings
from theogony.core.db import get_session
from theogony.core.names import normalize_name
from theogony.core.orm import Alias, Character
from theogony.providers.fandom import FandomProvider

CORPUS_DIR = get_settings().data_dir / "corpus"

# ──────────────────────────────────────────────
# wikitext 清洗
# ──────────────────────────────────────────────

_SKIP_SECTIONS = re.compile(
    r"references?|external links?|navigation|gallery|categor|see also|"
    r"引用|参考|外部链接|导航|分类|注释",
    re.IGNORECASE,
)


def strip_wikitext(text: str) -> str:
    """wiki 标记 → 纯文本（保留显示文本，去掉模板/引用/表格标记）。"""
    text = re.sub(r"<ref[^>]*/>", "", text)                       # 自闭引用
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)       # 注释
    text = re.sub(r"\{\{[Ii]nfobox[^{}]*\}\}", "", text)          # 单层 infobox
    for _ in range(3):                                            # 模板（嵌套≤3层，保守）
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)  # 链接取显示文本
    text = re.sub(r"'''?", "", text)                               # 粗斜体
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)                 # 残留 html
    text = re.sub(r"\[\d+\]", "", text)                           # 引用编号
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def split_sections(wikitext: str) -> list[dict]:
    """按 wiki 标题切段，过滤参考/导航类章节。"""
    parts = re.split(r"\n(={2,5})\s*([^=\n]+?)\s*\1\n", wikitext)
    sections, current = [], {"heading": "", "text": parts[0] if parts else ""}
    for i in range(1, len(parts) - 1, 2):
        heading = parts[i + 1].strip()
        if current["text"].strip():
            sections.append(current)
        current = {"heading": heading, "text": parts[i + 2] if i + 2 < len(parts) else ""}
    if current["text"].strip():
        sections.append(current)
    return [
        {"heading": s["heading"], "text": strip_wikitext(s["text"])}
        for s in sections
        if s["text"].strip() and not _SKIP_SECTIONS.search(s["heading"])
    ]


_SENT_SPLIT = re.compile(r"[。！？!?\.]+[\s\n]|[\n]+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if 12 <= len(s.strip()) <= 400]


# ──────────────────────────────────────────────
# 闭域词典 NER
# ──────────────────────────────────────────────

# 职阶名不作为人名匹配（实测坑：'Saber' 是阿尔托莉雅的别名，全页 "(Saber)" 误命中）
_CLASS_NAMES = {
    "saber", "archer", "lancer", "caster", "rider", "assassin", "berserker",
    "ruler", "avenger", "alterego", "mooncancer", "foreigner", "pretender",
    "beast", "shielder", "saber脸",
}


def build_dictionary() -> dict[str, tuple[str, str]]:
    """归一化名称 → (实体id, 规范名)。含英文别名（Wikidata qid 匹配的实体用其英文名）。"""
    session = get_session()
    try:
        chars = session.execute(select(Character)).scalars().all()
        aliases = session.execute(select(Alias)).scalars().all()
    finally:
        session.close()
    dic: dict[str, tuple[str, str]] = {}
    for c in chars:
        if c.class_name == "原型":
            continue  # 原型名与角色名常重合，句子层先只匹配角色
        for n in [c.name, *(a.alias for a in aliases if a.character_id == c.id)]:
            key = normalize_name(n or "")
            # 更长名称优先（后写覆盖短名时保留长名）
            if len(key) >= 2 and key not in _CLASS_NAMES and (
                    key not in dic or len(key) > len(dic[key][1])):
                dic[key] = (c.id, c.name)
        # 英文名兜底：wikidata 实体的 label 常为英文
        if c.wikidata_qid and c.source != "fgo":
            key = normalize_name(c.name)
            if len(key) >= 3 and key not in _CLASS_NAMES:
                dic.setdefault(key, (c.id, c.name))
    return dic


def find_entities(sentence: str, dic: dict[str, tuple[str, str]]) -> list[tuple[int, str, str]]:
    """词典最长匹配。返回 [(pos, entity_id, matched_name)]。"""
    hits: list[tuple[int, str, str]] = []
    toks = re.split(r"([\u4e00-\u9fff·A-Za-z0-9'’\-〔〕（）()]+)", sentence)
    pos = 0
    for tok in toks:
        if not tok or not re.search(r"[\u4e00-\u9fffA-Za-z0-9]", tok):
            pos += len(tok)
            continue
        # 贪心：从整段开始逐字缩短
        s = tok.lower()
        for size in range(len(s), 1, -1):
            key = normalize_name(s[:size])
            if key in dic:
                hits.append((pos, dic[key][0], tok[:size]))
                break
        pos += len(tok)
    # 去嵌套（相同起点保留最长）
    seen: dict[str, tuple[int, str, str]] = {}
    for h in hits:
        if h[1] not in seen:
            seen[h[1]] = h
    return sorted(seen.values())


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

async def crawl(fandom: FandomProvider, limit: int | None) -> dict[str, str]:
    titles = await fandom.all_page_titles()
    if limit:
        titles = titles[:limit]
    print(f"[fandom] 全站 {len(titles)} 页，批量抓取（50页/请求）…")
    pages: dict[str, str] = {}
    t0 = time.time()
    for i in range(0, len(titles), 250):
        batch = await fandom.fetch_pages_batch(titles[i:i + 250])
        pages.update(batch)
        print(f"  {min(i+250, len(titles))}/{len(titles)} 页（{time.time()-t0:.0f}s）")
    return pages


def process(pages: dict[str, str], dic: dict[str, tuple[str, str]]) -> dict:
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    pages_f = CORPUS_DIR / "pages.jsonl"
    sents_f = CORPUS_DIR / "sentences.jsonl"
    n_sent, n_hit, seen_sent = 0, 0, set()
    with pages_f.open("w", encoding="utf-8") as fp, sents_f.open("w", encoding="utf-8") as fs:
        for title, wikitext in pages.items():
            sections = split_sections(wikitext)
            if sections:
                fp.write(json.dumps({"title": title, "sections": sections}, ensure_ascii=False) + "\n")
            for sec in sections:
                for sent in split_sentences(sec["text"]):
                    n_sent += 1
                    ents = find_entities(sent, dic)
                    if len(ents) >= 2:
                        ids = tuple(sorted(e[1] for e in ents))
                        key = (normalize_name(sent), ids)
                        if key in seen_sent:
                            continue
                        seen_sent.add(key)
                        fs.write(json.dumps({
                            "text": sent, "title": title, "heading": sec["heading"],
                            "entities": [{"id": e[1], "match": e[2]} for e in ents],
                        }, ensure_ascii=False) + "\n")
                        n_hit += 1
    return {"pages": len(pages), "sections_pages": sum(1 for _ in pages), "sentences": n_sent, "hit_sentences": n_hit}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--from-pages", action="store_true", help="用已缓存页面重跑清洗")
    args = parser.parse_args()

    fandom = FandomProvider()
    if args.from_pages:
        pages = {}
        pf = CORPUS_DIR / "pages_raw.jsonl"
        if pf.exists():
            for line in pf.open(encoding="utf-8"):
                pages.update(json.loads(line))
        print(f"[cache] 载入 {len(pages)} 页")
    else:
        pages = await crawl(fandom, args.limit)
    dic = build_dictionary()
    print(f"[dict] 实体词典 {len(dic)} 个名称变体")
    stats = process(pages, dic)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    await fandom.aclose()


if __name__ == "__main__":
    asyncio.run(main())
