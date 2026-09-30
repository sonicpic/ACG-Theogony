# ADR-0001：Monorepo + 单一 schema 源

日期：2026-09-28 · 状态：已接受

## 背景

系统横跨 Python（数据管道 + API）与 TypeScript（前端），数据模型同时被两端消费。
早期版本两端各自维护类型与词表，改动频繁出现两端漂移。

## 决策

- 采用 monorepo：`theogony/`（Python）、`apps/web/`（Next.js）、`packages/shared/`（TS 类型）。
- **单一 schema 源**：后端 `theogony/core/models.py` 与 `enums.py` 是唯一权威定义；
  前端类型由 OpenAPI 经 `openapi-typescript` 生成（`npm run gen`），生成物禁止手改。
- 受控词表（关系类型、神话配色）在 `theogony/core/enums.py` 与
  `apps/web/src/lib/constants.ts` 两处保持一致，新增条目两端同步修改。
- CI 校验 schema 漂移：路由/模型改动后未重新生成并提交，流水线失败。

## 后果

- 正面：类型漂移在 CI 阶段被拦截，前后端契约始终一致。
- 代价：改后端必须记得 `npm run gen` 并提交生成物，流程多一步（由 CI 强制）。
