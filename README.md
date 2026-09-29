# ACG-Theogony · 神谱图谱 v2

ACG 角色 × 神话原型 关系知识图谱：**异步数据管道 + FastAPI + Next.js 16 WebGL 图可视化 + GraphRAG 问答**。

以 Fate/Grand Order 全英灵为初始数据源，支持关系路径探索、神话地理/时间轴/聚类视图、家谱树、LLM 关系挖掘审核流、每日猜角色等。

## 架构

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

## 快速开始

要求：**Python 3.13+、Node 20.9+（Next 16 要求）、uv**。

```bash
# 0) 配置环境变量（至少一个 LLM 提供方；不配也能跑，AI 功能自动降级）
cp .env.example .env

# 1) Python 依赖 + 数据入库
uv sync --group dev
npm run db:build

# 2) 前后端类型同步（OpenAPI → TS）
npm install
npm run gen

# 3) 启动
npm run api        # FastAPI  → http://127.0.0.1:8000/docs
npm run dev        # Next.js  → http://localhost:3000
```

Windows 下若系统 Node 低于 20.9，本项目可用便携 Node：`.tools/node/node.exe`（见 `scripts/use-node.sh`）。

## 数据管道

| 命令 | 说明 |
|---|---|
| `npm run scrape` | 异步爬取 Mooncell 英灵图鉴 + 详情页（region 全量修复） |
| `npm run db:build` | raw JSON → SQLite（别名/神话推断/关系归一化 + FTS） |
| `npm run enrich` | LLM 结构化增强全部角色（并发 8，断点续传，`--limit 5` 试跑） |
| `npm run mine` | 按神话体系分批挖掘角色关系 → 审核队列（`--limit-batches 2` 试跑） |
| `npm run research` | gpt-luna-5.6 联网研究（`--character 阿蒂拉` 或 `--ask "..."`） |

推荐顺序：`scrape → db:build → enrich → mine → 审核(/review)`。

## API 一览（完整文档见 /docs）

- `GET /api/graph` — 子图（mythologies/types/classes/gender/onlyRelated/egoCenter/maxWikiId…）
- `GET /api/graph/clusters` — Louvain 社区检测
- `GET /api/paths?from=c1&to=c496` — 关系路径（六度分隔）
- `GET /api/search?q=` — FTS5+拼音(+可选语义) 混合检索
- `GET /api/characters/{id}` / `GET /api/characters/{id}/family` — 详情 / 家谱
- `GET /api/stats` — 数据质量看板
- `POST /api/relationships` — 众包提交（进审核队列）
- `GET|POST /api/review/*` — 审核工作流（`X-Review-Token` 鉴权，可选）
- `GET /api/games/daily` — 每日猜角色（按日期确定性选题）
- `POST /api/ai/ask` — GraphRAG 问答（图检索 + LLM；无 Key 时纯图回答）
- `POST /api/ai/nlq` — 自然语言查图（规则+LLM 双引擎）
- `POST /api/ai/whatif` — 角色对决推演
- `GET /api/ai/suggest` — 图谱补全建议
- `GET /api/export/graphml|csv` — 导出
- `GET /api/img?url=` — 图片代理（解决 wiki 热链跨域）

## gpt-luna-5.6 / RAG 集成

系统对自然语言的处理分三层，逐级降级、功能不缺失：

1. **语义向量检索**（可选）：`.env` 配置任意 OpenAI 兼容 `EMBEDDINGS_*` 端点后，
   `/api/search` 与 GraphRAG 召回自动升级为"词法+语义"混合；
2. **gpt-luna-5.6 联网研究**：配置 `LUNA_API_KEY/LUNA_API_BASE` 后，
   `npm run research` 用其 web_search/fetch_url 工具循环查证 wiki 资料再结构化入库；
3. **纯图检索回退**：无任何 Key 时，问答/查图仍可用（FTS5 + BFS 图检索 + 模板化回答）。

## 开发

```bash
npm run test:py     # pytest（图算法/搜索/NLQ/游戏/API 冒烟）
npm run lint        # eslint（web）
uv run ruff check . # python lint
```

Docker（单容器全栈，host 网络对外仅一个端口）：`docker compose up -d --build` → `http://localhost:58115`（FastAPI 与 Next 同容器，API 仅绑内部回环）。

## 数据与版权

角色资料来自 [Mooncell（fgo.wiki）](https://fgo.wiki)，遵循其 CC BY-NC-SA 协议，本项目为
非商业资料聚合与可视化；LLM 生成内容均带 confidence/evidence，经人工审核（/review）后
才进入默认图谱视图。
