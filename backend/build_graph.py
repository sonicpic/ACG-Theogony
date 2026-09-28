"""
数据清洗 & 图谱 JSON 生成

读取  : backend/data/raw_characters.json (爬虫产出)
输出  : frontend/public/graph_data.json   (react-force-graph 可直接消费)

使用方法:
    python -m backend.build_graph       # 从项目根目录运行
    python build_graph.py               # 从 backend/ 目录运行
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ──────────────────────────────────────────────
# 导入（兼容模块/脚本运行）
# ──────────────────────────────────────────────

try:
    # 作为模块运行: python -m backend.build_graph
    from backend.schema import (
        GraphData,
        Link,
        Node,
        NodeType,
        RelationshipType,
    )
except ModuleNotFoundError:
    # 作为脚本运行: python build_graph.py
    from schema import (  # type: ignore[assignment]
        GraphData,
        Link,
        Node,
        NodeType,
        RelationshipType,
    )

# ──────────────────────────────────────────────
# 路径
# ──────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
RAW_FILE = _HERE / "data" / "raw_characters.json"
RELATIONSHIPS_FILE = _HERE / "data" / "character_relationships.json"
OUTPUT_FILE = _HERE.parent / "frontend" / "public" / "graph_data.json"
REPORT_FILE = _HERE / "data" / "build_report.json"


# ──────────────────────────────────────────────
# 清洗工具
# ──────────────────────────────────────────────

def _normalize_region(raw: str) -> str:
    """
    标准化地域/出处字段。
    - 去除多余空格
    - 合并常见别名（如 "北欧" → "北欧神话"）
    """
    text = raw.strip()
    if not text or text in ("-", "—", "？", "?", "不明", "无", "N/A"):
        return ""

    # 如果只写了地区名没加"神话"后缀，自动补全
    region_map = {
        "希腊": "希腊神话",
        "北欧": "北欧神话",
        "凯尔特": "凯尔特神话",
        "印度": "印度神话",
        "日本": "日本神话",
        "中国": "中国神话",
        "埃及": "埃及神话",
        "美索不达米亚": "美索不达米亚神话",
        "苏美尔": "美索不达米亚神话",
        "不列颠": "不列颠神话",
    }
    for short, full in region_map.items():
        if text == short:
            return full

    return text


def _make_slug(text: str) -> str:
    """将中文/英文文本转为可用作 ID 的 slug。"""
    # 保留中文字符、英文字母和数字
    slug = re.sub(r"[^\w\u4e00-\u9fff]", "_", text)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug.lower()


# ──────────────────────────────────────────────
# 核心逻辑
# ──────────────────────────────────────────────

def build_graph(raw_characters: list[dict], relationships_data: list[dict] = None) -> GraphData:
    """
    将平面角色列表转换为节点 + 连线的图谱数据。

    生成规则:
      1. 每个角色 → 一个 Character 节点
      2. 每个不重复的地域/出处 → 一个 Myth 节点
      3. 角色 → 对应 Myth 节点建立 BELONGS_TO 连线
      4. 根据关系数据添加角色间连线
    """
    graph = GraphData()
    myth_nodes: dict[str, Node] = {}  # region_name → Node
    char_name_to_id: dict[str, str] = {}  # 角色名 → char_id（用于关系匹配）

    for char in raw_characters:
        char_id = f"char_{char['id']}"
        name = char.get("name", "").strip()
        if not name:
            continue

        # 记录名字映射（同时记录 name 和 prototype）
        char_name_to_id[name] = char_id
        prototype = char.get("prototype", "").strip()
        if prototype:
            char_name_to_id[prototype] = char_id

        # ── 角色节点 ──
        char_node = Node(
            id=char_id,
            name=name,
            type=NodeType.CHARACTER,
            source="Fate/Grand Order",
            description=char.get("description", ""),
            image_url=char.get("image_url") or None,
            metadata={
                k: v
                for k, v in {
                    "class": char.get("class", ""),
                    "prototype": char.get("prototype", ""),
                    "region": char.get("region", ""),
                }.items()
                if v
            },
        )
        graph.nodes.append(char_node)

        # ── 神话/地域节点（去重） ──
        region = _normalize_region(char.get("region", ""))
        if not region:
            # 尝试用 prototype 推断（如名字明显属于某体系）
            region = _infer_region_from_prototype(char.get("prototype", ""))

        if region:
            if region not in myth_nodes:
                myth_id = f"myth_{_make_slug(region)}"
                myth_node = Node(
                    id=myth_id,
                    name=region,
                    type=NodeType.MYTH,
                    source=region,
                    description=f"{region}相关的神话体系与传说",
                )
                myth_nodes[region] = myth_node
                graph.nodes.append(myth_node)

            # ── 角色 → 神话体系连线 ──
            link = Link(
                source=char_id,
                target=myth_nodes[region].id,
                relationship=RelationshipType.BELONGS_TO,
            )
            graph.links.append(link)

    # ── 添加角色间关系连线 ──
    if relationships_data:
        added_relationships = 0
        skipped_relationships = 0
        
        for rel in relationships_data:
            source_name = rel.get("source_name", "").strip()
            target_name = rel.get("target_name", "").strip()
            rel_type = rel.get("relationship", "")
            bidirectional = rel.get("bidirectional", False)
            
            # 查找对应的角色ID
            source_id = char_name_to_id.get(source_name)
            target_id = char_name_to_id.get(target_name)
            
            if not source_id or not target_id:
                skipped_relationships += 1
                continue
            
            # 验证关系类型
            try:
                relationship = RelationshipType(rel_type)
            except ValueError:
                print(f"  [!] 未知关系类型: {rel_type}, 跳过")
                skipped_relationships += 1
                continue
            
            # 添加连线
            link = Link(
                source=source_id,
                target=target_id,
                relationship=relationship,
            )
            graph.links.append(link)
            added_relationships += 1
            
            # 如果是双向关系且不是对称关系类型，添加反向连线
            if bidirectional:
                reverse_link = Link(
                    source=target_id,
                    target=source_id,
                    relationship=relationship,
                )
                graph.links.append(reverse_link)
        
        print(f"  [*] 角色关系: 已添加 {added_relationships} 条, 跳过 {skipped_relationships} 条")

    return graph


def build_report(raw_characters: list[dict], graph: GraphData) -> dict:
    """构建数据质量报告，便于后续调参与修复。"""
    missing_region = [c for c in raw_characters if not _normalize_region(c.get("region", ""))]
    missing_class = [c for c in raw_characters if not c.get("class")]
    missing_desc = [c for c in raw_characters if not c.get("description")]

    linked_ids = {link.source for link in graph.links} | {link.target for link in graph.links}
    orphan_nodes = [n for n in graph.nodes if n.id not in linked_ids]

    return {
        "raw_count": len(raw_characters),
        "node_count": len(graph.nodes),
        "link_count": len(graph.links),
        "missing_region_count": len(missing_region),
        "missing_class_count": len(missing_class),
        "missing_description_count": len(missing_desc),
        "orphan_node_count": len(orphan_nodes),
        "sample_missing_region": [c.get("name") for c in missing_region[:10]],
        "sample_missing_class": [c.get("name") for c in missing_class[:10]],
        "sample_missing_description": [c.get("name") for c in missing_desc[:10]],
        "sample_orphan_nodes": [n.name for n in orphan_nodes[:10]],
    }


def _infer_region_from_prototype(prototype: str) -> str:
    """
    根据原型名字启发式推断神话体系。
    这是一个简单的关键词匹配，可以持续扩充。
    """
    if not prototype:
        return ""

    hints: dict[str, str] = {
        # 希腊
        "赫拉克勒斯": "希腊神话", "阿喀琉斯": "希腊神话",
        "美狄亚": "希腊神话", "阿塔兰忒": "希腊神话",
        "俄里翁": "希腊神话", "珀尔修斯": "希腊神话",
        "阿斯忒里翁": "希腊神话", "欧律阿勒": "希腊神话",
        # 北欧
        "布伦希尔德": "北欧神话", "西格尔德": "北欧神话",
        "斯卡蒂": "北欧神话", "瓦尔基里": "北欧神话",
        # 不列颠 / 亚瑟王
        "阿尔托莉雅": "不列颠神话", "兰斯洛特": "不列颠神话",
        "高文": "不列颠神话", "特里斯坦": "不列颠神话",
        "莫德雷德": "不列颠神话", "梅林": "不列颠神话",
        # 美索不达米亚
        "吉尔伽美什": "美索不达米亚神话", "恩奇都": "美索不达米亚神话",
        "伊什塔尔": "美索不达米亚神话", "埃列什基伽勒": "美索不达米亚神话",
        # 印度
        "迦尔纳": "印度神话", "阿周那": "印度神话",
        "罗摩": "印度神话", "帕尔瓦蒂": "印度神话",
        # 日本
        "酒吞童子": "日本神话", "源赖光": "日本神话",
        "牛若丸": "日本神话", "武藏": "日本神话",
        "玉藻前": "日本神话", "清姬": "日本神话",
        # 中国
        "项羽": "中国神话", "始皇帝": "中国神话",
        "虞美人": "中国神话", "哪吒": "中国神话",
    }

    for keyword, region in hints.items():
        if keyword in prototype:
            return region

    return ""


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main() -> None:
    print("=" * 60)
    print("Theogony-Graph · 图谱数据构建")
    print("=" * 60)

    # 1. 读取原始数据
    if not RAW_FILE.exists():
        print(f"[✗] 找不到原始数据文件: {RAW_FILE}")
        print("    请先运行爬虫: python -m backend.scraper_mooncell")
        return

    with open(RAW_FILE, "r", encoding="utf-8") as f:
        raw_characters = json.load(f)
    print(f"[1/4] 已加载 {len(raw_characters)} 条原始角色数据")

    # 2. 读取关系数据
    relationships_data = None
    if RELATIONSHIPS_FILE.exists():
        with open(RELATIONSHIPS_FILE, "r", encoding="utf-8") as f:
            relationships_json = json.load(f)
            relationships_data = relationships_json.get("relationships", [])
        print(f"[2/4] 已加载 {len(relationships_data)} 条角色关系数据")
    else:
        print(f"[2/4] 未找到关系数据文件: {RELATIONSHIPS_FILE}")

    # 3. 构建图谱
    graph = build_graph(raw_characters, relationships_data)
    char_count = sum(1 for n in graph.nodes if n.type == NodeType.CHARACTER)
    myth_count = sum(1 for n in graph.nodes if n.type == NodeType.MYTH)
    
    # 统计关系类型分布
    relationship_counts = {}
    for link in graph.links:
        rel = link.relationship.value
        relationship_counts[rel] = relationship_counts.get(rel, 0) + 1
    
    print(f"[3/4] 图谱构建完成:")
    print(f"      角色节点 (Character) : {char_count}")
    print(f"      神话节点 (Myth)      : {myth_count}")
    print(f"      连线 (Links)         : {len(graph.links)}")
    print(f"      关系类型分布:")
    for rel_type, count in sorted(relationship_counts.items(), key=lambda x: -x[1]):
        print(f"        - {rel_type}: {count}")

    # 4. 输出
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    graph.save_json(str(OUTPUT_FILE))
    report = build_report(raw_characters, graph)
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"[4/4] 已保存到: {OUTPUT_FILE}")
    print(f"      质量报告: {REPORT_FILE}")
    print("\n[✓] 完成! 前端可通过 /graph_data.json 加载此文件。")


if __name__ == "__main__":
    main()
