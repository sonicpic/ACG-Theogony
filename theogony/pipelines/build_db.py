"""全量入库管道：raw JSON → SQLite（幂等，保留审核结论）。

用法：uv run python -m theogony.pipelines.build_db
"""

from __future__ import annotations

import json

from theogony.core.db import init_db
from theogony.core.graph import GraphService
from theogony.core.seeding import build_db as seed


def main() -> None:
    print("=" * 60)
    print("Theogony · 数据入库")
    print("=" * 60)
    init_db()
    stats = seed()
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    # 预热图缓存并输出摘要
    gs = GraphService.instance()
    view = gs.build_view()
    print(
        f"[✓] 图服务就绪：{len(view['nodes'])} 节点 / {len(view['links'])} 连线 / "
        f"{sum(1 for n in view['nodes'] if n['degree'] > 0)} 个角色有角色间关系"
    )


if __name__ == "__main__":
    main()
