"""种子数据入库：raw JSON → SQLite（含神话推断、别名生成、关系归一化）。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from theogony.core.config import get_settings
from theogony.core.db import rebuild_fts, session_scope
from theogony.core.enums import (
    INVERSE_RELATIONS,
    RELATION_META,
    Mythology,
    RelationOrigin,
    ReviewStatus,
)
from theogony.core.orm import Alias, Character, Relationship

# ──────────────────────────────────────────────
# 神话体系推断（确定性回退，LLM 增强会覆盖）
# ──────────────────────────────────────────────

_REGION_MAP = {
    "希腊": "希腊神话", "罗马": "罗马神话", "北欧": "北欧神话", "凯尔特": "凯尔特神话",
    "不列颠": "不列颠神话", "亚瑟王": "不列颠神话", "埃及": "埃及神话",
    "美索不达米亚": "美索不达米亚神话", "苏美尔": "美索不达米亚神话", "巴比伦": "美索不达米亚神话",
    "波斯": "波斯神话", "印度": "印度神话", "中国": "中国神话", "日本": "日本神话",
    "阿兹特克": "阿兹特克神话", "玛雅": "玛雅神话", "非洲": "非洲神话",
    "斯拉夫": "斯拉夫神话", "芬兰": "芬兰神话", "基督": "基督教",
}

_PROTO_HINTS: dict[str, str] = {
    # 希腊
    "赫拉克勒斯": "希腊神话", "阿喀琉斯": "希腊神话", "美狄亚": "希腊神话",
    "阿塔兰忒": "希腊神话", "俄里翁": "希腊神话", "珀尔修斯": "希腊神话",
    "阿斯忒里翁": "希腊神话", "欧律阿勒": "希腊神话", "忒修斯": "希腊神话",
    "奥德修斯": "希腊神话", "赫克托尔": "希腊神话", "帕里斯": "希腊神话",
    "彭忒西勒亚": "希腊神话", "喀戎": "希腊神话", "阿斯克勒庇俄斯": "希腊神话",
    "俄耳甫斯": "希腊神话", "埃阿斯": "希腊神话", "狄俄斯库里": "希腊神话",
    "卡吕冬": "希腊神话", "阿耳忒弥斯": "希腊神话", "波塞冬": "希腊神话",
    "宙斯": "希腊神话", "哈迪斯": "希腊神话", "德墨忒尔": "希腊神话",
    "珀耳塞福涅": "希腊神话", "赫拉": "希腊神话", "阿佛洛狄忒": "希腊神话",
    "雅典娜": "希腊神话", "阿瑞斯": "希腊神话", "赫菲斯托斯": "希腊神话",
    "赫尔墨斯": "希腊神话", "美杜莎": "希腊神话", "戈耳工": "希腊神话",
    "喀耳刻": "希腊神话", "卡珊德拉": "希腊神话", "伊阿宋": "希腊神话",
    "阿伽门农": "希腊神话", "克吕泰涅斯特拉": "希腊神话", "希波吕忒": "希腊神话",
    "塔罗斯": "希腊神话", "斯芬克斯": "希腊神话", "厄律曼托斯": "希腊神话",
    "涅墨西斯": "希腊神话", "提亚马特": "美索不达米亚神话",
    # 北欧
    "布伦希尔德": "北欧神话", "西格尔德": "北欧神话", "斯卡蒂": "北欧神话",
    "瓦尔基里": "北欧神话", "奥丁": "北欧神话", "索尔": "北欧神话",
    "洛基": "北欧神话", "芙蕾雅": "北欧神话", "海姆达尔": "北欧神话",
    "芬里尔": "北欧神话", "耶梦加得": "北欧神话", "尼德霍格": "北欧神话",
    "史尔特": "北欧神话", "齐格鲁德": "北欧神话", "雷金": "北欧神话",
    "法夫纳": "北欧神话", "格里戈里": "北欧神话", "希格德莉法": "北欧神话",
    "奥菲莉亚": "北欧神话", "布拉奇": "北欧神话", "纳普": "北欧神话",
    # 不列颠
    "阿尔托莉雅": "不列颠神话", "兰斯洛特": "不列颠神话", "高文": "不列颠神话",
    "特里斯坦": "不列颠神话", "莫德雷德": "不列颠神话", "梅林": "不列颠神话",
    "加拉哈德": "不列颠神话", "珀西瓦尔": "不列颠神话", "贝德维尔": "不列颠神话",
    "崔斯坦": "不列颠神话", "阿格规文": "不列颠神话", "加雷斯": "不列颠神话",
    "摩根": "不列颠神话", "薇薇安": "不列颠神话", "尼托克丽丝": "埃及神话",
    "圆桌": "不列颠神话", "亚瑟": "不列颠神话",
    # 美索不达米亚
    "吉尔伽美什": "美索不达米亚神话", "恩奇都": "美索不达米亚神话",
    "伊什塔尔": "美索不达米亚神话", "埃列什基伽勒": "美索不达米亚神话",
    "金古": "美索不达米亚神话", "宁松": "美索不达米亚神话",
    "阿萨基姆": "美索不达米亚神话", "魁扎尔": "阿兹特克神话",
    # 印度
    "迦尔纳": "印度神话", "阿周那": "印度神话", "罗摩": "印度神话",
    "帕尔瓦蒂": "印度神话", "迦梨": "印度神话", "阿斯瓦塔玛": "印度神话",
    "怖军": "印度神话", "坚战": "印度神话", "黑天": "印度神话",
    "释迦": "印度神话", "佛陀": "印度神话", "难敌": "印度神话",
    # 日本
    "酒吞童子": "日本神话", "源赖光": "日本神话", "牛若丸": "日本神话",
    "武藏": "日本神话", "玉藻前": "日本神话", "清姬": "日本神话",
    "卑弥呼": "日本神话", "坂田金时": "日本神话", "茨木童子": "日本神话",
    "镰鼬": "日本神话", "静谧": "日本神话", "望月千代女": "日本神话",
    "宫本武藏": "日本神话", "佐佐木小次郎": "日本神话", "冲田总司": "史实人物",
    "织田信长": "史实人物", "德川家康": "史实人物", "森长可": "史实人物",
    "柳生但马守": "史实人物", "宝藏院胤舜": "史实人物",
    "葛饰北斋": "史实人物", "托马斯·爱迪生": "史实人物", "特斯拉": "史实人物",
    "拿破仑": "史实人物", "始皇帝": "中国神话", "项羽": "中国神话",
    "虞美人": "中国神话", "哪吒": "中国神话", "杨贵妃": "中国神话",
    "武则天": "史实人物", "司马懿": "史实人物", "诸葛亮": "史实人物",
    "吕布": "史实人物", "赤兔马": "中国神话", "貂蝉": "中国神话",
    "燕青": "史实人物", "陈宫": "史实人物", "华佗": "史实人物",
    "秦良玉": "史实人物", "曼荼罗": "印度神话",
    # 凯尔特
    "库·丘林": "凯尔特神话", "斯卡哈": "凯尔特神话", "弗格斯": "凯尔特神话",
    "迪尔姆德": "凯尔特神话", "梅芙": "凯尔特神话", "芬恩": "凯尔特神话",
    "奥Jack": "凯尔特神话", "贝林": "凯尔特神话", "努阿达": "凯尔特神话",
    "梅尔顿": "凯尔特神话", "康奇厄布王": "凯尔特神话", "格罗娅": "凯尔特神话",
    # 埃及
    "尼托克丽": "埃及神话", "克利奥帕特拉": "史实人物", "拉美西斯": "埃及神话",
    "阿努比斯": "埃及神话", "荷鲁斯": "埃及神话", "伊西斯": "埃及神话",
    "奥西里斯": "埃及神话", "塞特": "埃及神话",
    "图坦卡蒙": "埃及神话", "娜芙蒂蒂": "埃及神话",
    # 现代
    "玛修": "现代创作", "藤丸立香": "现代创作", "所长": "现代创作",
    "达·芬奇": "史实人物", "所罗门": "基督教", "大卫": "基督教",
    "圣乔治": "基督教", "玛尔达": "基督教", "贞德": "史实人物",
    "天草四郎": "史实人物", "岩窟王": "史实人物", "克里斯托弗": "史实人物",
    # 斯拉夫/其他
    "阿纳斯塔西娅": "史实人物", "伊凡雷帝": "史实人物", "沙皇": "史实人物",
    "比利小子": "史实人物", "杰罗尼莫": "史实人物",
}

_CLASSES = (
    "Saber", "Archer", "Lancer", "Rider", "Caster", "Assassin", "Berserker",
    "Ruler", "Avenger", "MoonCancer", "Foreigner", "Pretender", "AlterEgo",
    "Shielder", "Beast",
)


def normalize_region(raw: str) -> str:
    text = (raw or "").strip()
    if not text or text in {"-", "—", "？", "?", "不明", "无", "N/A"}:
        return ""
    for short, full in _REGION_MAP.items():
        if text == short or short in text:
            return full
    return text


def infer_mythology(prototype: str, name: str = "", region: str = "") -> str:
    """确定性神话体系推断：region 规范化 > 原型关键词 > 名称关键词。"""
    region_norm = normalize_region(region)
    if region_norm in Mythology._value2member_map_:
        return region_norm
    for text in (prototype, name):
        if not text:
            continue
        for keyword, myth in _PROTO_HINTS.items():
            if keyword in text:
                return myth
        for short, full in _REGION_MAP.items():
            if short in text:
                return full
    return ""


def strip_parentheses(name: str) -> str:
    return re.sub(r"[（(][^）)]*[）)]", "", name).strip()


def build_aliases(name: str, prototype: str, extra: list[str] | None = None) -> list[str]:
    """从名称/原型生成别名（保证关系挖掘时的名称召回）。"""
    result: list[str] = []
    for candidate in [name, strip_parentheses(name), prototype, *(extra or [])]:
        candidate = (candidate or "").strip()
        if candidate and candidate not in result:
            result.append(candidate)
    return result


# ──────────────────────────────────────────────
# 种子入库
# ──────────────────────────────────────────────

def _load_json(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_relationship(source_id: str, target_id: str, rel_type: str) -> tuple[str, str, str] | None:
    """归一化关系三元组：逆关系翻转到规范方向；未知类型返回 None。"""
    rel_type = rel_type.strip()
    flipped = False
    if rel_type in INVERSE_RELATIONS:
        rel_type = INVERSE_RELATIONS[rel_type]
        flipped = True
    if rel_type not in RELATION_META and rel_type != "BELONGS_TO":
        return None
    if flipped:
        return target_id, source_id, rel_type
    return source_id, target_id, rel_type


def seed_from_raw(session, *, preserve_reviews: bool = True) -> dict:
    """从 data/raw/*.json 全量重建角色与关系。返回统计。"""
    settings = get_settings()
    raw_dir = settings.data_dir / "raw"

    raw_chars = _load_json(raw_dir / "raw_characters.json", [])
    enriched = {c["id"]: c for c in _load_json(raw_dir / "enriched_characters.json", [])}
    rel_data = _load_json(raw_dir / "character_relationships.json", {})
    rel_list = rel_data.get("relationships", []) if isinstance(rel_data, dict) else []

    # 保留已有审核结论，重建后按三元组回填
    review_memory: dict[tuple[str, str, str], str] = {}
    if preserve_reviews:
        from theogony.core.orm import Relationship as Rel

        for rel in session.execute(select(Rel)).scalars():
            review_memory[(rel.source_id, rel.target_id, rel.type)] = rel.status

    for table in (Alias, Relationship, Character):
        session.query(table).delete()
    session.flush()

    stats = {"characters": 0, "enriched_merged": 0, "relations_added": 0, "relations_skipped": 0}

    # 角色
    for raw in raw_chars:
        wiki_id = int(re.search(r"\d+", str(raw.get("id", "0"))).group(0)) if str(raw.get("id", "")).strip() else 0
        if not wiki_id:
            continue
        cid = f"c{wiki_id}"
        name = (raw.get("name") or "").strip()
        if not name:
            continue
        merge = enriched.get(str(raw.get("id")) or str(wiki_id), {})
        region = merge.get("region") or raw.get("region") or ""
        mythology = infer_mythology(raw.get("prototype", ""), name, region)
        myth_source = "rule"
        if merge.get("region"):
            mythology = normalize_region(merge["region"]) or mythology
            myth_source = "llm"
        metadata = merge.get("metadata", {}) or {}
        aliases = build_aliases(name, raw.get("prototype", ""), merge.get("aliases"))

        char = Character(
            id=cid,
            wiki_id=wiki_id,
            name=name,
            class_name=(raw.get("class") or "").strip(),
            prototype=(raw.get("prototype") or "").strip(),
            mythology=mythology or None,
            description=(merge.get("description") or raw.get("description") or "").strip(),
            mythology_background=(merge.get("mythology_background") or "").strip(),
            alignment=(metadata.get("alignment") or "").strip(),
            gender=(metadata.get("gender") or "").strip(),
            image_url=(raw.get("image_url") or "").strip(),
            detail_url=(raw.get("detail_url") or "").strip(),
            extra=merge.get("extra", {}) or {},
            myth_source=myth_source,
            enriched_at=datetime.now(UTC) if merge else None,
            enrich_model="deepseek-chat" if merge else "",
        )
        session.add(char)
        for alias in aliases:
            session.add(Alias(character_id=cid, alias=alias))
        stats["characters"] += 1
        if merge:
            stats["enriched_merged"] += 1

    session.flush()

    # 名称 → id 映射（含别名）；同名冲突时优先编号最小的原版角色
    name_to_id: dict[str, str] = {}
    for cid, name in session.execute(
        select(Character.id, Character.name).order_by(Character.wiki_id)
    ):
        name_to_id.setdefault(name, cid)
    for alias, cid in session.execute(
        select(Alias.alias, Alias.character_id)
        .join(Character, Alias.character_id == Character.id)
        .order_by(Character.wiki_id)
    ):
        name_to_id.setdefault(alias, cid)

    # 关系
    seen_triples: set[tuple[str, str, str]] = set()
    for rel in rel_list:
        src = name_to_id.get((rel.get("source_name") or "").strip())
        dst = name_to_id.get((rel.get("target_name") or "").strip())
        if not src or not dst:
            stats["relations_skipped"] += 1
            continue
        normalized = normalize_relationship(src, dst, rel.get("relationship", ""))
        if not normalized or normalized[0] == normalized[1]:
            stats["relations_skipped"] += 1
            continue
        s, t, rtype = normalized
        triple = (s, t, rtype)
        rtrip = (t, s, rtype)
        if triple in seen_triples or rtrip in seen_triples:
            continue
        seen_triples.add(triple)

        has_confidence = "confidence" in rel
        origin = RelationOrigin.LLM if has_confidence else RelationOrigin.MANUAL
        status = (
            review_memory.get(triple, ReviewStatus.PENDING.value)
            if has_confidence
            else ReviewStatus.APPROVED.value
        )
        session.add(
            Relationship(
                source_id=s,
                target_id=t,
                type=rtype,
                directed=RELATION_META.get(rtype, {}).get("directed", True),
                confidence=rel.get("confidence", "verified" if not has_confidence else "medium"),
                evidence=(rel.get("evidence") or "").strip(),
                origin=origin.value,
                status=status,
            )
        )
        stats["relations_added"] += 1

    fts_count = rebuild_fts(session)
    stats["fts_indexed"] = fts_count
    return stats


def build_db() -> dict:
    """CLI 入口：初始化并全量种子。"""
    from theogony.core.db import init_db

    init_db()
    with session_scope() as session:
        stats = seed_from_raw(session)
    return stats


if __name__ == "__main__":
    print(json.dumps(build_db(), ensure_ascii=False, indent=2))
