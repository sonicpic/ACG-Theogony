"""数据导出：DB → data/raw/*.json（版本化持久化，防止 DB 丢失增强成果）。

导出内容与 build_db 的导入格式双向兼容（含 status 字段，重建时保留审核结论）。

用法：uv run python -m theogony.pipelines.export_data
"""

from __future__ import annotations

import json

from sqlalchemy import select

from theogony.core.config import get_settings
from theogony.core.db import get_session
from theogony.core.orm import Alias, Character, Relationship


def main() -> None:
    settings = get_settings()
    raw_dir = settings.data_dir / "raw"
    session = get_session()
    try:
        chars = session.execute(select(Character).order_by(Character.wiki_id)).scalars().all()
        alias_map: dict[str, list[str]] = {}
        for a in session.execute(select(Alias)).scalars():
            alias_map.setdefault(a.character_id, []).append(a.alias)
        rels = session.execute(select(Relationship).order_by(Relationship.id)).scalars().all()
        name_map = {c.id: c.name for c in chars}

        enriched = [
            {
                "id": str(c.wiki_id),
                "name": c.name,
                "class": c.class_name,
                "prototype": c.prototype,
                "detail_url": c.detail_url,
                "region": c.mythology or "",
                "description": c.description,
                "mythology_background": c.mythology_background,
                "image_url": c.image_url,
                "aliases": [a for a in alias_map.get(c.id, []) if a != c.name],
                "metadata": {"alignment": c.alignment, "gender": c.gender},
                "extra": c.extra or {},
                "enrich_model": c.enrich_model,
            }
            for c in chars
        ]
        (raw_dir / "enriched_characters.json").write_text(
            json.dumps(enriched, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        rel_payload = {
            "_comment": "角色关系数据库 - 手动维护 + LLM 生成（status: approved/pending/rejected）",
            "relationships": [
                {
                    "source_name": name_map.get(r.source_id, r.source_id),
                    "target_name": name_map.get(r.target_id, r.target_id),
                    "relationship": r.type,
                    "confidence": r.confidence,
                    "evidence": r.evidence,
                    "origin": r.origin,
                    "status": r.status,
                }
                for r in rels
            ],
        }
        (raw_dir / "character_relationships.json").write_text(
            json.dumps(rel_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"[✓] 已导出 {len(enriched)} 角色 → {raw_dir / 'enriched_characters.json'}")
        print(f"[✓] 已导出 {len(rels)} 关系 → {raw_dir / 'character_relationships.json'}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
