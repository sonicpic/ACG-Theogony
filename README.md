# ACG-Theogony · 神谱图谱

ACG 角色 × 神话原型 关系知识图谱：异步数据管道 + FastAPI + Next.js 16 WebGL 图可视化 + GraphRAG 问答。

以 Fate/Grand Order 全英灵为初始数据源，支持关系路径探索、神话地理/时间轴/聚类视图、家谱树、LLM 关系挖掘审核流、每日猜角色等。

## 功能

- **全局图谱**（Sigma.js WebGL）：力导向 / 神话星系 / 3D 三种视图，节点选中高亮邻居、拖拽、悬停浮卡；点击或悬停关系线查看关系类型与两端角色
- **关系路径探索**：任意两角色的最短关系链（六度分隔）
- **筛选**：神话体系 / 关系类型 / 职阶 / 性别 / 实装时间轴 / 孤立点，一键清除
- **角色视图**：React Flow 星系图与家谱树；角色卡内点击关系标签跳转高亮
- **搜索**：FTS5 中文 2-gram + 拼音混合检索（可选升级语义向量）
- **GraphRAG 问答**：图检索 + LLM 生成回答；自然语言查图（NLQ）转筛选条件；角色对决推演
- **数据管道**：Mooncell 异步爬虫 → LLM 结构化增强 → 关系挖掘 → 人工审核工作流
- **每日猜角色**：按日期确定性选题，逐条线索揭示
- **导出**：PNG / SVG / GraphML(Gephi) / CSV
- 桌面与移动端自适应（底部 Dock + 抽屉），首访使用指引

## 快速开始

要求：Python 3.13+、Node ≥ 20.9、[uv](https://docs.astral.sh/uv/)。

```bash
# 0) 配置环境变量（可选；不配 LLM Key 也能跑，AI 功能自动降级）
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

## Docker 部署

单容器全栈（host 网络，对外仅一个端口）：

```bash
docker buildx build --allow network.host --network host \
  -f Dockerfile.web --build-arg API_ORIGIN=http://127.0.0.1:18000 \
  -t acg-theogony:web --load .
docker compose up -d   # → http://localhost:58115
```

`API_ORIGIN` 在构建期固化进 Next.js rewrites（运行时不可改）；网络不受限的环境可去掉
`--allow network.host --network host` 参数。

## 数据管道

| 命令 | 说明 |
|---|---|
| `npm run scrape` | 异步爬取 Mooncell 英灵图鉴 + 详情页 |
| `npm run db:build` | raw JSON → SQLite（别名/神话推断/关系归一化 + FTS） |
| `npm run enrich` | LLM 结构化增强全部角色（断点续传，`--limit 5` 试跑） |
| `npm run mine` | 按神话体系分批挖掘角色关系 → 审核队列（`--limit-batches 2` 试跑） |
| `npm run research` | 联网研究（`--character 阿蒂拉` 或 `--ask "..."`） |

推荐顺序：`scrape → db:build → enrich → mine → 审核(/review)`。LLM 配置见
[docs/llm-pipelines.md](docs/llm-pipelines.md)。

## API 一览（完整文档见启动后的 /docs）

- `GET /api/graph` — 子图（mythologies/types/classes/gender/onlyRelated/egoCenter/maxWikiId…）
- `GET /api/graph/clusters` — Louvain 社区检测
- `GET /api/paths?from=c1&to=c496` — 关系路径
- `GET /api/search?q=` — FTS5+拼音(+可选语义) 混合检索
- `GET /api/characters/{id}` / `GET /api/characters/{id}/family` — 详情 / 家谱
- `GET /api/stats` — 数据质量看板
- `POST /api/relationships` — 众包提交（进审核队列）
- `GET|POST /api/review/*` — 审核工作流（`X-Review-Token` 鉴权，可选）
- `GET /api/games/daily` — 每日猜角色
- `POST /api/ai/ask` / `nlq` / `whatif` — GraphRAG 问答 / 自然语言查图 / 对决推演
- `GET /api/ai/suggest` — 图谱补全建议
- `GET /api/export/graphml|csv` — 导出

## 开发

```bash
npm run test:py     # pytest（图算法/搜索/NLQ/游戏/API 冒烟）
npm run lint        # eslint（web）
uv run ruff check . # python lint
```

架构与目录说明见 [docs/architecture.md](docs/architecture.md)；
重要设计决策见 [docs/adr/](docs/adr/)；
关系数据模型见 [docs/relations.md](docs/relations.md)；
版本历史见 [CHANGELOG.md](CHANGELOG.md)。

## 故障排查

- **端口被占用**：配置的端口（默认 API 8000 / Web 3000 / 容器 58115）被占用时启动失败，
  换空闲端口或停掉冲突进程；容器内部 API 端口固定 18000，勿与宿主已占端口冲突。
- **Node 版本过低**：Next.js 16 要求 Node ≥ 20.9，升级后重试。
- **容器构建拉取 PyPI 超时**：Docker 桥接网络受限的环境（如透明代理）下，
  按"Docker 部署"用 host 网络构建；依赖层带 BuildKit 缓存卷，重复构建不再联网。
- **图谱为空**：先运行 `npm run db:build` 生成数据库；确认 `data/*.db` 存在。
- **AI 功能不可用**：正常降级行为；配置任一 LLM Key 后恢复
  （见 [docs/llm-pipelines.md](docs/llm-pipelines.md)）。

## 数据与版权

- 代码：[LICENSE](LICENSE)（MIT）
- 角色资料来自 [Mooncell（fgo.wiki）](https://fgo.wiki)，遵循其 CC BY-NC-SA 协议，
  本项目为非商业资料聚合与可视化，详见 [DATA_LICENSE.md](DATA_LICENSE.md)
- LLM 生成内容均带 confidence/evidence，经人工审核（/review）后才进入默认图谱视图
