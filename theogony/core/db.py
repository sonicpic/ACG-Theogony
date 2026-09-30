"""数据库引擎与会话管理（SQLite WAL + FTS5）。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from theogony.core.config import get_settings
from theogony.core.orm import FTS_DDL, Base


def _make_engine(path):
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()

    return engine


_engine = None
_session_factory = None


def get_engine():
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        settings.db_path.parent.mkdir(parents=True, exist_ok=True)
        _engine = _make_engine(settings.db_path)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def init_db() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text(FTS_DDL))
        _migrate(conn)


def _migrate(conn) -> None:
    """轻量列迁移：create_all 不改已有表，新列在此补齐（幂等）。"""
    cols = {row[1] for row in conn.execute(text("PRAGMA table_info(characters)"))}
    work_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(works)"))}
    if "anilist_id" not in work_cols:
        conn.execute(text("ALTER TABLE works ADD COLUMN anilist_id INTEGER"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_works_anilist_id ON works(anilist_id)"))
    if "wikidata_qid" not in cols:
        conn.execute(text("ALTER TABLE characters ADD COLUMN wikidata_qid VARCHAR(32)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_characters_wikidata_qid ON characters(wikidata_qid)"))


def get_session() -> Session:
    if _session_factory is None:
        get_engine()
    return _session_factory()


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def rebuild_fts(session: Session) -> int:
    """全量重建 FTS 索引（种子/增强后调用）。"""
    from theogony.core.search import pinyin_of

    session.execute(text("DELETE FROM fts_characters"))
    chars = session.execute(
        text(
            "SELECT id, name, prototype, description, mythology FROM characters"
        )
    ).fetchall()
    alias_rows = session.execute(text("SELECT character_id, alias FROM aliases")).fetchall()
    alias_map: dict[str, list[str]] = {}
    for cid, alias in alias_rows:
        alias_map.setdefault(cid, []).append(alias)

    count = 0
    for cid, name, prototype, description, mythology in chars:
        aliases = alias_map.get(cid, [])
        alias_text = " ".join(aliases)
        session.execute(
            text(
                "INSERT INTO fts_characters "
                "(character_id, name, aliases, prototype, description, mythology, name_py, aliases_py) "
                "VALUES (:cid, :name, :aliases, :prototype, :description, :mythology, :name_py, :aliases_py)"
            ),
            {
                "cid": cid,
                "name": name,
                "aliases": alias_text,
                "prototype": prototype or "",
                "description": (description or "")[:500],
                "mythology": mythology or "",
                "name_py": pinyin_of(name),
                "aliases_py": pinyin_of(alias_text),
            },
        )
        count += 1
    return count
