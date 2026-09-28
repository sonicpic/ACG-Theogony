"""导出 OpenAPI schema 到 data/openapi.json（供 openapi-typescript 生成前端类型）。"""

from __future__ import annotations

import json
from pathlib import Path

from theogony.core.config import get_settings


def main() -> None:
    from theogony.api.main import create_app

    app = create_app()
    settings = get_settings()
    out: Path = settings.data_dir / "openapi.json"
    out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[✓] OpenAPI 已导出: {out}")


if __name__ == "__main__":
    main()
