"""受控词表：关系类型 / 神话体系 / 置信度 / 数据来源 / 审核状态。

前端展示所需的 label、颜色、是否有向也在此统一定义，
这是前后端共用的唯一词表源（经 OpenAPI 生成的类型同步到 TS）。
"""

from __future__ import annotations

from enum import Enum


class RelationshipType(str, Enum):
    """关系类型（存储层只用规范方向，逆关系在入库时归一化）。"""

    # 角色 ↔ 角色（家族/血缘）
    PARENT_OF = "PARENT_OF"        # source 是 target 的父母
    SIBLING_OF = "SIBLING_OF"      # 兄弟姐妹
    SPOUSE_OF = "SPOUSE_OF"        # 配偶
    LOVER_OF = "LOVER_OF"          # 恋人
    # 角色 ↔ 角色（社会）
    MASTER_OF = "MASTER_OF"        # source 是 target 的主人
    ALLY_OF = "ALLY_OF"            # 盟友
    ENEMY_OF = "ENEMY_OF"          # 敌对
    FOUGHT_WITH = "FOUGHT_WITH"    # 交手过
    MENTOR_OF = "MENTOR_OF"        # source 是 target 的师傅
    # 角色 ↔ 神话原型
    PROTOTYPE_IS = "PROTOTYPE_IS"      # 角色与另一角色互为同一原型
    GENDER_SWAP = "GENDER_SWAP"        # 性转版本
    DERIVED_FROM = "DERIVED_FROM"      # 设定衍生
    COMPOSITE_OF = "COMPOSITE_OF"      # 多原型复合
    # 角色 ↔ 神话体系（体系节点由服务端派生）
    BELONGS_TO = "BELONGS_TO"          # 归属神话体系


class Mythology(str, Enum):
    """神话体系受控词表。"""

    GREEK = "希腊神话"
    ROMAN = "罗马神话"
    NORSE = "北欧神话"
    CELTIC = "凯尔特神话"
    BRITAIN = "不列颠神话"
    EGYPT = "埃及神话"
    MESOPOTAMIA = "美索不达米亚神话"
    PERSIA = "波斯神话"
    INDIA = "印度神话"
    CHINA = "中国神话"
    JAPAN = "日本神话"
    AZTEC = "阿兹特克神话"
    MAYA = "玛雅神话"
    AFRICA = "非洲神话"
    SLAVIC = "斯拉夫神话"
    FINNISH = "芬兰神话"
    CHRISTIAN = "基督教"
    MODERN = "现代创作"
    HISTORICAL = "史实人物"
    OTHER = "其他"


class Confidence(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERIFIED = "verified"


class RelationOrigin(str, Enum):
    MANUAL = "manual"      # 人工维护
    LLM = "llm"            # LLM 挖掘
    USER = "user"          # 众包提交
    WIKI = "wiki"          # 结构化数据源


class ReviewStatus(str, Enum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


# ──────────────────────────────────────────────
# 展示元数据
# ──────────────────────────────────────────────

RELATION_META: dict[str, dict] = {
    # type: {label, category, color, directed}
    "BELONGS_TO": {"label": "归属", "category": "myth", "color": "#94a3b8", "directed": True},
    "PROTOTYPE_IS": {"label": "同一原型", "category": "myth", "color": "#8b5cf6", "directed": False},
    "GENDER_SWAP": {"label": "性转", "category": "myth", "color": "#ec4899", "directed": False},
    "DERIVED_FROM": {"label": "衍生", "category": "myth", "color": "#a78bfa", "directed": True},
    "COMPOSITE_OF": {"label": "复合", "category": "myth", "color": "#c084fc", "directed": True},
    "PARENT_OF": {"label": "父母", "category": "family", "color": "#10b981", "directed": True},
    "SIBLING_OF": {"label": "兄弟姐妹", "category": "family", "color": "#6ee7b7", "directed": False},
    "SPOUSE_OF": {"label": "配偶", "category": "family", "color": "#f472b6", "directed": False},
    "LOVER_OF": {"label": "恋人", "category": "family", "color": "#fb7185", "directed": False},
    "MASTER_OF": {"label": "主人", "category": "social", "color": "#3b82f6", "directed": True},
    "ALLY_OF": {"label": "盟友", "category": "social", "color": "#22c55e", "directed": False},
    "ENEMY_OF": {"label": "敌对", "category": "social", "color": "#ef4444", "directed": False},
    "FOUGHT_WITH": {"label": "交手", "category": "social", "color": "#f97316", "directed": False},
    "MENTOR_OF": {"label": "师傅", "category": "social", "color": "#0ea5e9", "directed": True},
}

# 逆关系归一化：入库时 CHILD_OF(A,B) 会转成 PARENT_OF(B,A)，只存规范方向
INVERSE_RELATIONS: dict[str, str] = {
    "CHILD_OF": "PARENT_OF",
    "SERVANT_OF": "MASTER_OF",
    "STUDENT_OF": "MENTOR_OF",
}

FAMILY_TYPES = {"PARENT_OF", "SIBLING_OF", "SPOUSE_OF", "LOVER_OF"}

MYTHOLOGY_COLORS: dict[str, str] = {
    "希腊神话": "#38bdf8",
    "罗马神话": "#60a5fa",
    "北欧神话": "#a5b4fc",
    "凯尔特神话": "#34d399",
    "不列颠神话": "#4ade80",
    "埃及神话": "#fbbf24",
    "美索不达米亚神话": "#f97316",
    "波斯神话": "#fb923c",
    "印度神话": "#c084fc",
    "中国神话": "#f87171",
    "日本神话": "#f472b6",
    "阿兹特克神话": "#2dd4bf",
    "玛雅神话": "#22d3ee",
    "非洲神话": "#a3e635",
    "斯拉夫神话": "#818cf8",
    "芬兰神话": "#7dd3fc",
    "基督教": "#e879f9",
    "现代创作": "#94a3b8",
    "史实人物": "#cbd5e1",
    "其他": "#64748b",
}

# 神话地理锚点（0~1 抽象坐标，用于"神话地理"布局模式，近似真实文化地理分布）
MYTHOLOGY_GEO: dict[str, tuple[float, float]] = {
    "希腊神话": (0.52, 0.42),
    "罗马神话": (0.50, 0.41),
    "北欧神话": (0.50, 0.26),
    "凯尔特神话": (0.44, 0.30),
    "不列颠神话": (0.435, 0.28),
    "埃及神话": (0.55, 0.47),
    "美索不达米亚神话": (0.59, 0.45),
    "波斯神话": (0.63, 0.45),
    "印度神话": (0.69, 0.48),
    "中国神话": (0.79, 0.42),
    "日本神话": (0.88, 0.38),
    "阿兹特克神话": (0.17, 0.52),
    "玛雅神话": (0.20, 0.58),
    "非洲神话": (0.47, 0.60),
    "斯拉夫神话": (0.56, 0.27),
    "芬兰神话": (0.53, 0.23),
    "基督教": (0.51, 0.44),
    "现代创作": (0.50, 0.85),
    "史实人物": (0.50, 0.78),
    "其他": (0.50, 0.93),
}


def relation_label(rel: str) -> str:
    return RELATION_META.get(rel, {}).get("label", rel)


def is_valid_relationship(value: str) -> bool:
    return value in RELATION_META or value in INVERSE_RELATIONS
