# Copilot Instructions — ACG-Theogony v2

## 项目结构（monorepo）

- `theogony/core/`：领域核心（受控词表 `enums.py`、ORM、种子入库、FTS5 检索、图算法、LLM 提供方抽象、NLQ 规则解析）
- `theogony/pipelines/`：数据管道（异步爬虫、LLM 增强、关系挖掘、联网研究、数据导出）
- `theogony/api/`：FastAPI 应用与路由（`main.py` 装配，`routers/` 分模块）
- `apps/web/`：Next.js 16 + React 19 前端（Sigma.js WebGL 图谱、React Flow 星系图/家谱树）
- `packages/shared/`：由 OpenAPI 自动生成的前端类型（`npm run gen`，**禁止手改**）
- `data/raw/`：git 跟踪的源数据；`data/*.db` 为生成产物（已 ignore）

## 关键约定（必须遵守）

1. **单一 schema 源**：后端改 `theogony/core/models.py` / `enums.py` 后必须 `npm run gen` 重新生成 OpenAPI 与 TS 类型并提交，CI 会校验漂移
2. **关系存储**：只用规范方向（逆关系 `CHILD_OF/SERVANT_OF/STUDENT_OF` 入库时翻转归一化，见 `seeding.normalize_relationship`）；LLM/众包关系一律 `status=pending`，经 `/api/review/*` 批准后才进入图谱
3. **名称解析**：同名角色（如各版本阿尔托莉雅）优先编号最小的本家；实体链接需做变体归并（见 `api/routers/ai.py`）
4. **LLM 调用**：统一走 `core/llm.py`；Luna 提供方并发硬上限 2（中转站风控），思考强度 bulk 用 medium、`--effort max` 仅用于单批深挖
5. **管道输出**：批量任务必须 `python -u` 运行且逐批增量落库（中断可续跑）；写库后需 `rebuild_fts` 与 `GraphService.refresh()`
6. **词表同步**：`theogony/core/enums.py`（RELATION_META/MYTHOLOGY_COLORS）与 `apps/web/src/lib/constants.ts` 保持一致；新增关系类型两边都要改

## 常用命令

```bash
uv sync --group dev && npm install && npm run db:build   # 初始化
npm run api          # FastAPI :8000（/docs 有全部端点）
npm run dev          # Next.js :3000
uv run pytest        # 测试；uv run ruff check .  # lint
npm run enrich / mine / research / export-data    # 数据管道
```
