# 架构

当前系统的组成、数据流与关键约束。

## 总览

```
pipelines（异步）                          apps/web（Next.js 16 + React 19）
┌────────────────────────────┐            ┌─────────────────────────────────┐
│ scrape_mooncell  异步爬虫   │            │ Sigma.js WebGL 全局图            │
│ enrich_llm       LLM 增强   │  ──API──▶  │ React Flow 星系图 / 家谱树       │
│ mine_relations   关系挖掘   │            │ GraphRAG 问答 / NLQ / 猜角色     │
│ luna_research    联网研究   │            └─────────────────────────────────┘
└─────────────┬──────────────┘                        ▲
              ▼                                       │ openapi-typescript
   SQLite(WAL) + FTS5 (+可选向量)                      │ 自动生成 TS 类型
              ▲                                       │
              └──────── apps/api（FastAPI）────────────┘
```

## Monorepo 布局

| 目录 | 职责 |
|---|---|
| `theogony/core/` | 领域核心：受控词表（`enums.py`）、ORM、种子入库、FTS5 检索、图算法、LLM 提供方抽象、NLQ 规则解析 |
| `theogony/pipelines/` | 数据管道：异步爬虫、LLM 增强、关系挖掘、联网研究、数据导出 |
| `theogony/api/` | FastAPI 应用与路由（`main.py` 装配，`routers/` 分模块） |
| `apps/web/` | Next.js 16 + React 19 前端（Sigma.js WebGL 图谱、React Flow 星系图/家谱树） |
| `packages/shared/` | OpenAPI 自动生成的前端类型（`npm run gen`，禁止手改） |
| `data/raw/` | git 跟踪的源数据；`data/*.db` 为生成产物（已 ignore） |

## 数据流

1. **采集**：`scrape_mooncell` 抓取 Mooncell 英灵图鉴与详情页 → `data/raw/*.json`
2. **入库**：`db:build` 将 raw JSON 灌入 SQLite（别名归并、神话归属推断、关系方向归一化、FTS5 索引）
3. **增强**：`enrich` 用 LLM 补齐结构化字段（逐条落库、断点续传）
4. **挖掘**：`mine` 按神话体系分批产出候选关系，一律 `status=pending`
5. **审核**：人工在 `/review` 批准后关系进入默认图谱视图
6. **消费**：FastAPI 读库提供图/搜索/路径/AI 端点；Next.js 全量拉取图数据做零延迟交互

## 关键约束（详见 docs/adr/）

- **单一 schema 源**：后端改 `models.py`/`enums.py` 后必须 `npm run gen` 重新生成 TS 类型，CI 校验漂移（ADR-0001）
- **图谱渲染在主线程跑活布局**：不使用 FA2 worker supervisor（ADR-0002）
- **关系入库必须过审核**：LLM/众包来源一律 pending，批准后才可见（ADR-0003）

## LLM 集成分层

对自然语言的处理分三层，逐级降级、功能不缺失：

1. **语义向量检索**（可选）：配置任意 OpenAI 兼容 `EMBEDDINGS_*` 端点后，
   `/api/search` 与 GraphRAG 召回升级为"词法+语义"混合
2. **联网研究**（可选）：配置 `LUNA_API_KEY/LUNA_API_BASE` 后，
   `npm run research` 用 web_search/fetch_url 工具循环查证 wiki 资料再结构化入库
3. **纯图检索回退**：无任何 Key 时，问答/查图仍可用（FTS5 + BFS 图检索 + 模板化回答）

## 部署形态

单容器全栈（`Dockerfile.web`）：Python(uv) 基底 + Node 22 二进制，
`docker/entrypoint.py` 以 python 守护 uvicorn（容器回环）与 next start（对外端口）。
host 网络对外仅暴露一个 HTTP 端口，API 不独立成服务。
