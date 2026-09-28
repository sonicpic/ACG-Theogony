# ACG-Theogony 现代化重构方案 v2

> 生成于 2026-09-28。基于对仓库现状的完整代码审查。

---

## 一、项目背景还原

### 1.1 项目定位

ACG-Theogony（神谱图谱）是一个 **"ACG 角色 × 神话原型" 关系知识图谱可视化项目**。以 Fate/Grand Order（FGO）全部 465 位英灵为初始数据源，将角色（Character）与其神话体系（Myth）通过力导向图展示，支持按关系类型筛选、搜索定位、点击高亮邻居。

### 1.2 当前架构（离线三段式管道 + 静态前端）

```
Mooncell Wiki (fgo.wiki)
      │  ① scraper_mooncell.py（requests + BS4，串行，随机 UA）
      ▼
backend/data/raw_characters.json        （465 条，region/description 100% 为空）
      │  ② enrich_with_llm.py（DeepSeek API，串行，手工 JSON 解析）
      ▼
backend/data/enriched_characters.json   （仅 7 条完成增强）
backend/data/character_relationships.json（15 条关系：手动 + LLM 生成）
      │  ③ build_graph.py（纯函数合并，硬编码启发式推断 region）
      ▼
frontend/public/graph_data.json         （472 节点 / 83 连线，构建时静态生成）
      │  fetch("/graph_data.json")
      ▼
Next.js 14 + react-force-graph-2d（单页 Canvas 2D 力导向图）
```

### 1.3 数据现状（来自 build_report.json 实测）

| 指标 | 数值 | 说明 |
|---|---|---|
| 原始角色 | 465 | 图片 URL 100% 有 |
| 缺失 region | 465（100%） | 爬虫详情页抓取实际未产出数据 |
| 缺失 description | 465（100%） | 同上 |
| LLM 已增强 | 仅 7 条 | 管道跑通但未全量执行 |
| 角色间关系 | 15 条 | 图谱几乎全是"角色→神话体系"的星型辐射 |
| 孤儿节点 | 397（85%） | 无任何角色间关系连线的节点 |

**结论：管道骨架完整，但数据层是"空转"状态——图能看，但知识密度极低。这是重构的第一优先级，比换任何框架都重要。**

### 1.4 技术栈清单

| 层 | 现状 | 问题 |
|---|---|---|
| 版本控制 | **无 git 仓库** | 最高优先级风险 |
| 后端 | Python 3.13 纯脚本，无框架/无 DB/无测试 | requirements.txt 无锁文件，test_api.py 只是连通性脚本 |
| LLM 调用 | openai SDK→DeepSeek，串行 + sleep，手工正则解析 JSON | 慢、脆、无结构化输出保障 |
| 数据存储 | 4 个 JSON 文件 | 无事务、无索引、并发写会互相覆盖 |
| 类型系统 | schema.py 与 types.ts 手工双维护 | 已经出现漂移风险 |
| 前端 | Next 14.2 + React 18 + Tailwind 4 + react-force-graph-2d | 425 行单组件；数据静态 fetch；搜索为线性 includes |
| 部署 | 无 CI/CD，无 Dockerfile | 完全本地项目 |

---

## 二、目标架构

```
┌─────────────────────────── 数据管道（异步任务） ───────────────────────────┐
│  scraper（httpx 异步 + Playwright 兜底）                                   │
│      → normalizer（Pydantic v2 校验/清洗/别名归一）                        │
│      → enricher（LLM 结构化输出，并发 + 限流 + 断点续传）                   │
│      → relation-miner（关系抽取，带 confidence/evidence）                   │
│      → reviewer（人工审核队列，可选 Web UI）                               │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   ▼
                     SQLite（WAL）+ FTS5 全文索引
                     （角色/别名/关系/来源/审核状态）
                     （规模破万后平迁 PostgreSQL，代码零改动）
                                   ▲
┌────────────────────────────── API 层 ──────────────────────────────────────┐
│  FastAPI：/characters  /characters/{id}  /relationships                    │
│           /graph（按筛选条件返回子图）  /search（FTS5 + 拼音）               │
│           /paths（两角色间关系路径）  /ai/ask（GraphRAG 问答，可选）          │
│  OpenAPI schema → openapi-typescript 自动生成前端类型（终结手工双维护）       │
└──────────────────────────────────┬────────────────────────────────────────┘
                                   ▼
┌────────────────────────────── 前端（Next.js 16） ─────────────────────────┐
│  全局图：Sigma.js（WebGL）+ graphology + ForceAtlas2/圆 packed 布局         │
│  局部图：React Flow（角色详情"关系星系图"）                                  │
│  状态：TanStack Query（服务端状态）+ Zustand（视图状态）                     │
│  UI：Tailwind 4 + shadcn/ui，暗色模式，移动端自适应                          │
└───────────────────────────────────────────────────────────────────────────┘
```

### 关键选型理由

| 决策点 | 选型 | 理由 |
|---|---|---|
| 包管理（Python） | **uv** | 2026 事实标准，锁文件 + 极快安装，替代 requirements.txt |
| 包管理（JS） | **pnpm workspace** | monorepo 管理 apps/web + packages/shared |
| 数据校验 | **Pydantic v2** | 单一 schema 源，`model_json_schema()` 可直接喂给 LLM 结构化输出 |
| LLM 结构化输出 | **openai SDK（DeepSeek JSON mode）+ Pydantic 校验**，或 instructor | 淘汰正则解析；JSON 不合法自动重试 |
| 数据库 | **SQLite + FTS5** | 万级节点绰绰有余；SQLAlchemy 2.0 写法保证平迁 PG 的可能 |
| 图数据库（可选） | KuzuDB | 若需要多跳 Cypher 查询再引入，嵌入式零运维；初期 BFS 内存计算即可 |
| API | **FastAPI** | 自动 OpenAPI → 前端类型生成，一举解决 schema 双维护 |
| 前端框架 | **Next.js 16 + React 19** | 当前最新大版本（15 已进维护期，2026-10 EOL） |
| 全局图渲染 | **Sigma.js（WebGL）+ graphology** | Canvas2D 在千级节点+图片纹理下必卡；Sigma 原生支持数万节点 |
| 局部图 | **React Flow** | 详情页 ego-network / 家谱树的最佳交互库 |
| 服务端状态 | TanStack Query v5 | 缓存/重取/分页全套 |
| 代码质量 | ruff + mypy（Py）、eslint + prettier（TS）、pytest + vitest + Playwright | 全部进 GitHub Actions |
| 部署 | 前端 Vercel；API + 管道 Fly.io / Railway；或单机 Docker Compose | 静态数据期间甚至可以只发 Vercel |

---

## 三、分阶段实施计划

### Phase 0 — 工程底座（0.5 天，立即做）

1. `git init` + 首次提交现状（**目前连版本控制都没有，这是最大的风险**）
2. 确认 `.env` 已在 `.gitignore`（已有）；**轮换一次 DeepSeek API Key**（.env 长期存在于未受控目录）
3. Monorepo 化：
   ```
   acg-theogony/
   ├── apps/
   │   ├── web/            # Next.js 16（由 frontend/ 迁移）
   │   └── api/            # FastAPI（新建）
   ├── packages/
   │   └── shared/         # openapi-typescript 生成的类型
   ├── pipelines/          # 原 backend/ 的爬虫与增强脚本（uv 管理）
   ├── data/               # 原 backend/data/（结构化数据，可考虑 git-lfs 或对象存储）
   ├── docker-compose.yml
   └── README.md
   ```
4. `uv init` + `pyproject.toml`（ruff、mypy、pytest 配置）；GitHub Actions：lint + test + build 三条流水线

### Phase 1 — 数据层重建（核心，2~3 天）

**原则：先让数据"活"，再谈功能。**

1. **Pydantic v2 数据模型**（替代 dataclass schema.py，作为唯一 schema 源）
   ```python
   class Character(BaseModel):
       id: str
       name: str
       aliases: list[str] = []          # 真名/简称/多语言名，解决"精确匹配断链"
       class_name: str = ""
       prototype: str = ""
       mythology: str | None = None     # 受控词表（Enum）
       description: str = ""
       image_url: HttpUrl | None = None
       source: Literal["fgo"] = "fgo"   # 为多作品扩展预留
       enrichment: EnrichmentMeta | None = None   # 记录 LLM 置信度/时间/模型

   class Relationship(BaseModel):
       source_id: str                   # 用 ID 而非 name 关联（淘汰 name 匹配）
       target_id: str
       type: RelationshipType
       directed: bool
       confidence: Literal["high", "medium", "low", "verified"] = "verified"
       evidence: str = ""
       origin: Literal["manual", "llm", "wiki"] = "manual"
   ```
2. **入 SQLite**：SQLAlchemy 2.0；角色表、别名表、关系表、审核队列表；FTS5 虚表做中文全文搜索（jieba 预分词 + 拼音列）
3. **爬虫现代化**：httpx.AsyncClient + 十并发 + tenacity 重试；详情页 region 抓取改为**一次性全量**（现有限 50 的策略导致 region 100% 缺失）；页面改版兜底用 Playwright
4. **LLM 增强现代化**：
   - DeepSeek `response_format={"type": "json_object"}` + Pydantic 校验失败自动重试
   - asyncio.Semaphore(8) 并发，465 角色从"5-10 分钟串行"降到 1 分钟内
   - 关系抽取改为**按神话体系分批**（同体系角色塞进同一上下文，召回率远高于现在的"前 100 个全局列表"）
   - 产物全部带 `confidence + evidence + origin`，进审核队列而非直接上线
5. **一次性数据回填**：全量跑通 ①→④，目标把孤儿节点从 85% 压到 30% 以下

### Phase 2 — API 层（1~2 天）

| 端点 | 说明 |
|---|---|
| `GET /api/characters` | 分页、筛选（mythology/class/has-relation）、排序 |
| `GET /api/characters/{id}` | 详情 + 一度关系展开 |
| `GET /api/search?q=` | FTS5 + 别名 + 拼音模糊 |
| `GET /api/graph?mythology=&types=&limit=` | **按需返回子图**（替代 465 节点全量下发） |
| `GET /api/paths?from=A&to=B` | BFS 最短关系路径（六度分隔） |
| `POST /api/relationships` | 众包提交（进审核队列，Phase 3 的 UGC 基础） |
| `GET /api/stats` | 数据质量看板（缺失率/置信度分布/关系类型分布） |

- CORS 白名单 + 速率限制（slowapi）
- **`openapi-typescript` 生成 `packages/shared/types.ts`**，前端 import，CI 校验 schema 漂移

### Phase 3 — 前端重构（3~5 天）

1. **Next.js 16 + React 19 + TS strict**；TanStack Query 管数据；Zustand 管视图状态
2. **双引擎图可视化**：
   - 全局探索：Sigma.js + graphology + ForceAtlas2，节点图片用 sprite atlas 或缩略图代理（直接热链 fgo.wiki 媒体域有跨域与防盗链风险，需要一个 `/api/img-proxy`）
   - 角色详情：React Flow ego-network（二度关系星系图）+ 家族关系族谱树视图
3. 拆分 425 行巨石组件：`<GraphCanvas />`、`<FilterPanel />`、`<CharacterDrawer />`、`<SearchBox />`、`<StatsBar />`
4. 交互升级：暗色模式、移动端底部抽屉、URL 同步筛选状态（可分享的视图链接）、hover 缩略卡片
5. 骨架屏 + 图数据分级加载（先节点后图片）

### Phase 4 — 部署与运维（1 天）

- `docker-compose.yml`（api + sqlite 卷 + 定时管道任务）
- GitHub Actions：PR 跑 lint/test/build；main 分支自动部署 Vercel（web）
- 管道定时任务（GitHub Actions cron 或 Fly machine）每周增量更新数据

**总计：约 7~11 个工作日的重构量，可按 Phase 独立交付，旧版前端在 Phase 3 之前保持可用。**

---

## 四、新功能头脑风暴

### 4.1 图谱体验（核心差异化）

| 功能 | 描述 | 价值 | 难度 |
|---|---|---|---|
| **关系路径探索** | 任意两角色最短路径 + 动画高亮（"吉尔伽美什和项羽隔着几层关系？"） | ★★★★★ | 低（BFS） |
| **Ego 星系图** | 点击角色展开二度关系星系，取代现在的侧栏文字详情 | ★★★★★ | 中 |
| **神话地理模式** | 图谱按神话地理投射世界地图（希腊圈/日本圈/北欧圈），看文化版图 | ★★★★ | 中 |
| **时间轴回放** | 按 FGO 实装版本回放图谱生长动画（"人理纪年回放"） | ★★★★ | 中 |
| **社区自动聚类** | Louvain/Leiden 自动发现"神话圈子"，集群折叠/展开 | ★★★ | 中 |
| **家谱树视图** | 家族关系单独抽出渲染族谱 | ★★★ | 中 |
| 3D 沉浸模式 | react-force-graph-3d 彩蛋 | ★★ | 低 |

### 4.2 AI 功能（数据飞轮引擎）

| 功能 | 描述 | 价值 | 难度 |
|---|---|---|---|
| **GraphRAG 问答** | "谁杀了赫克托尔？"→ 图检索 + LLM 生成带高亮路径的答案 | ★★★★★ | 中高 |
| **自然语言查图** | "显示希腊神话里所有父子关系" → LLM 转 API 过滤参数 | ★★★★ | 中 |
| **关系审核工作流** | LLM 生成的关系（confidence/evidence）进审核后台，人工确认升为 verified —— 数据质量的飞轮 | ★★★★★ | 中 |
| 图谱补全建议 | LLM 主动提示"这两位同体系角色可能存在未收录关系" | ★★★ | 中 |
| What-if 剧情推演 | "阿喀琉斯 vs 吉尔伽美什谁赢？"AI 生成趣味推演（引流向） | ★★★ | 低 |

### 4.3 内容扩展

| 功能 | 描述 | 价值 | 难度 |
|---|---|---|---|
| **多作品宇宙对照** | 同一神话原型在 FGO / 明日方舟 / 公主连结等作品的化身横向对比（schema 已预留 source 字段） | ★★★★★ | 高 |
| 真名/别名体系 | 多语言名、真名揭晓线（FGO 剧透预警） | ★★★★ | 低 |
| 宝具/技能/羁绊数据 | 挂接角色节点，丰富详情页 | ★★★ | 中 |
| 剧情出场索引 | 角色在哪些章节/活动出场，支撑时间轴回放 | ★★★ | 中 |

### 4.4 社区与传播

| 功能 | 描述 | 价值 | 难度 |
|---|---|---|---|
| **每日猜角色** | Wordle 式逐条线索猜英灵，答案直跳图谱页（病毒传播点） | ★★★★★ | 低 |
| 众包关系编辑 | Wiki 式提交 + 审核队列 + 贡献徽章 | ★★★★ | 中高 |
| 分享卡片 | 角色 ego 图生成 OG 分享图 / iframe 嵌入卡 | ★★★★ | 低 |
| 开放 API | 公开只读 API + 文档，让别人拿数据二创 | ★★★ | 低 |
| 导出 | PNG/SVG/GraphML(Gephi)/CSV | ★★★ | 低 |

### 4.5 推荐 MVP（重构完成后第一批做）

1. **关系路径探索** —— 实现成本低、最能体现"知识图谱"价值
2. **Ego 星系图 + 角色详情页** —— 把 85% 孤儿节点问题转化为体验升级
3. **审核工作流** —— 让 LLM 数据敢上线，质量随时间自增
4. **每日猜角色** —— 零后端成本的传播点
5. **GraphRAG 问答** —— 差异化护城河

---

## 五、里程碑

| 里程碑 | 内容 | 验收标准 |
|---|---|---|
| M0（本周） | git + monorepo + CI | PR 即跑 lint/test |
| M1 | 数据层 + 管道全量回填 | region/description 覆盖率 >95%，关系 ≥1500 条，孤儿 <30% |
| M2 | API + 类型自动生成 | 前端删掉手写 types.ts |
| M3 | 新前端上线 | Sigma 全局图 + 星系图 + 暗色 + 移动端 |
| M4 | MVP 新功能 | 路径探索 / 审核后台 / 猜角色 |
| M5 | AI 问答 + 多作品扩展立项 | GraphRAG demo |

---

## 六、风险与对策

| 风险 | 对策 |
|---|---|
| fgo.wiki 反爬/改版 | 详情页解析集中在 repository 层 + Playwright 兜底 + 调试 HTML 落盘（现有机制保留） |
| 图片热链跨域/防盗链 | 自建图片代理 + 本地缩略图缓存（管线期离线抓取为佳，注意版权只做缩略引用） |
| LLM 幻觉污染关系数据 | 所有 LLM 数据带 confidence/evidence，默认只在"审核后"全量展示 |
| 版权 | 项目定位为资料聚合与学术性可视化，引用 Mooncell 遵循其 CC BY-NC-SA 协议并标注来源；商用需重审 |
| Next 16 迁移成本 | 现有代码量小（1 页面 1 组件），重写比重构快，直接按新架构写 |
