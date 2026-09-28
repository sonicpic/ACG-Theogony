"""
Theogony-Graph 统一数据结构定义

此模块定义了整个项目共享的数据模型。
前端 TypeScript 类型定义位于 frontend/src/types.ts，需保持同步。
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import json


# ──────────────────────────────────────────────
# 枚举
# ──────────────────────────────────────────────

class NodeType(str, Enum):
    """节点类型"""
    CHARACTER = "Character"  # ACG 角色（如 FGO 英灵）
    MYTH = "Myth"            # 神话原型 / 神话体系（如"希腊神话"）


class RelationshipType(str, Enum):
    """连线关系类型"""
    # ── 角色 ↔ 神话体系 ──
    PROTOTYPE_IS = "PROTOTYPE_IS"    # 角色 → 神话原型（同一人物）
    GENDER_SWAP = "GENDER_SWAP"      # 角色是原型的性转版本
    BELONGS_TO = "BELONGS_TO"        # 角色归属某一神话体系
    DERIVED_FROM = "DERIVED_FROM"    # 角色设定衍生自某原型
    COMPOSITE_OF = "COMPOSITE_OF"    # 角色是多个原型的复合体
    
    # ── 角色 ↔ 角色（家族/血缘）──
    PARENT_OF = "PARENT_OF"          # 父母关系
    CHILD_OF = "CHILD_OF"            # 子女关系
    SIBLING_OF = "SIBLING_OF"        # 兄弟姐妹
    SPOUSE_OF = "SPOUSE_OF"          # 配偶关系
    LOVER_OF = "LOVER_OF"            # 恋人关系
    
    # ── 角色 ↔ 角色（社会关系）──
    MASTER_OF = "MASTER_OF"          # 主仆关系（主人）
    SERVANT_OF = "SERVANT_OF"        # 主仆关系（从者）
    ALLY_OF = "ALLY_OF"              # 盟友/同伴
    ENEMY_OF = "ENEMY_OF"            # 敌对关系
    FOUGHT_WITH = "FOUGHT_WITH"      # 战斗过
    MENTOR_OF = "MENTOR_OF"          # 师徒关系（师傅）
    STUDENT_OF = "STUDENT_OF"        # 师徒关系（学生）


# ──────────────────────────────────────────────
# 数据类
# ──────────────────────────────────────────────

@dataclass
class Node:
    """
    图谱节点，可以是角色或神话原型。

    Attributes:
        id:          唯一标识符，角色使用 "char_<编号>"，神话使用 "myth_<slug>"
        name:        显示名称
        type:        节点类型 (Character / Myth)
        source:      出处，如 "Fate/Grand Order"、"希腊神话"
        description: 简短描述
        image_url:   可选的头像 URL
        metadata:    额外属性（职阶、地域等），便于扩展
    """
    id: str
    name: str
    type: NodeType
    source: str = ""
    description: str = ""
    image_url: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value
        return d


@dataclass
class Link:
    """
    图谱连线，表示两个节点之间的关系。

    Attributes:
        source:       起始节点 ID
        target:       目标节点 ID
        relationship: 关系类型
        label:        可选的显示标签（默认取 relationship 值）
    """
    source: str
    target: str
    relationship: RelationshipType
    label: str = ""

    def __post_init__(self):
        if not self.label:
            self.label = self.relationship.value

    def to_dict(self) -> dict:
        d = asdict(self)
        d["relationship"] = self.relationship.value
        return d


@dataclass
class GraphData:
    """完整的图谱数据，可直接序列化为 react-force-graph 所需的 JSON。"""
    nodes: list[Node] = field(default_factory=list)
    links: list[Link] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "links": [l.to_dict() for l in self.links],
        }

    def save_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load_json(cls, path: str) -> "GraphData":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        nodes = [
            Node(
                id=n["id"],
                name=n["name"],
                type=NodeType(n["type"]),
                source=n.get("source", ""),
                description=n.get("description", ""),
                image_url=n.get("image_url"),
                metadata=n.get("metadata", {}),
            )
            for n in data.get("nodes", [])
        ]
        links = [
            Link(
                source=l["source"],
                target=l["target"],
                relationship=RelationshipType(l["relationship"]),
                label=l.get("label", ""),
            )
            for l in data.get("links", [])
        ]
        return cls(nodes=nodes, links=links)
