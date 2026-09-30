"""SQLAlchemy 2.0 ORM 模型（SQLite，WAL 模式）。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # c<wiki_id>
    wiki_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    class_name: Mapped[str] = mapped_column(String(32), default="")
    prototype: Mapped[str] = mapped_column(String(128), default="")
    mythology: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    mythology_background: Mapped[str] = mapped_column(Text, default="")
    alignment: Mapped[str] = mapped_column(String(32), default="")
    gender: Mapped[str] = mapped_column(String(16), default="")
    image_url: Mapped[str] = mapped_column(Text, default="")
    detail_url: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(32), default="fgo", index=True)
    wikidata_qid: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)  # 宝具/技能/出场等
    myth_source: Mapped[str] = mapped_column(String(16), default="rule")  # rule|llm|wiki
    enriched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enrich_model: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    aliases: Mapped[list[Alias]] = relationship(
        back_populates="character", cascade="all, delete-orphan"
    )


class Alias(Base):
    __tablename__ = "aliases"
    __table_args__ = (Index("ix_aliases_alias", "alias"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"))
    alias: Mapped[str] = mapped_column(String(128))
    lang: Mapped[str] = mapped_column(String(8), default="zh")

    character: Mapped[Character] = relationship(back_populates="aliases")


class Work(Base):
    """作品（动画/漫画/游戏/小说/影视），多源统一，Wikidata 为锚。"""

    __tablename__ = "works"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)  # ww:Q...
    name: Mapped[str] = mapped_column(String(256), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="other")  # anime|manga|game|novel|film|tv|comic|other
    wikidata_qid: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    prototype_qid: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)  # 基于的原型
    source: Mapped[str] = mapped_column(String(16), default="wikidata")
    anilist_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class WorkRelation(Base):
    """作品间关系（续作/前传/衍生/同人/替代版本等）。"""

    __tablename__ = "work_relations"
    __table_args__ = (UniqueConstraint("source_id", "target_id", "relation_type", name="uq_workrel"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)   # 作品 id（bgw:xxx / ww:xxx）
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    relation_type: Mapped[str] = mapped_column(String(24))  # SEQUEL|PREQUEL|SPIN_OFF|ALTERNATIVE|SIDE_STORY|PARENT|CHARACTER|OTHER
    source: Mapped[str] = mapped_column(String(16), default="anilist")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Appearance(Base):
    """角色 ↔ 作品 出演关系（多源统一）。"""

    __tablename__ = "appearances"
    __table_args__ = (UniqueConstraint("character_id", "work_id", name="uq_appearance"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    character_id: Mapped[str] = mapped_column(ForeignKey("characters.id", ondelete="CASCADE"), index=True)
    work_id: Mapped[str] = mapped_column(ForeignKey("works.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), default="")  # 主角/配角/客串
    source: Mapped[str] = mapped_column(String(16), default="bangumi")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Relationship(Base):
    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint("source_id", "target_id", "type", name="uq_rel_triple"),
        Index("ix_rel_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(32), index=True)
    target_id: Mapped[str] = mapped_column(String(32), index=True)
    type: Mapped[str] = mapped_column(String(32))
    directed: Mapped[bool] = mapped_column(default=True)
    confidence: Mapped[str] = mapped_column(String(16), default="verified")
    evidence: Mapped[str] = mapped_column(Text, default="")
    origin: Mapped[str] = mapped_column(String(16), default="manual")
    status: Mapped[str] = mapped_column(String(16), default="approved", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Embedding(Base):
    __tablename__ = "embeddings"

    character_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    model: Mapped[str] = mapped_column(String(64))
    dim: Mapped[int] = mapped_column(Integer)
    vector: Mapped[str] = mapped_column(Text)  # JSON 数组


class KV(Base):
    """元信息存储（聚类结果、构建统计等）。"""

    __tablename__ = "kv"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict | float | str] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# FTS5 虚表（非 ORM 管理，在 db.py 里创建/重建）
FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS fts_characters USING fts5(
    character_id UNINDEXED,
    name,
    aliases,
    prototype,
    description,
    mythology,
    name_py,
    aliases_py,
    tokenize='unicode61'
)
"""
