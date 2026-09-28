# Copilot Instructions — Theogony-Graph

## 项目结构与数据流
- 后端抓取与清洗在 [backend/](backend/)：先运行爬虫生成原始列表，再构建图谱 JSON。
- 前端可视化在 [frontend/](frontend/)：读取 [frontend/public/graph_data.json](frontend/public/graph_data.json) 渲染图谱。
- 统一数据结构：后端 [backend/schema.py](backend/schema.py) 与前端 [frontend/src/types.ts](frontend/src/types.ts) 必须同步更新。
- 角色关系数据在 [backend/data/character_relationships.json](backend/data/character_relationships.json)，手动维护已知关系。

## 核心脚本与职责
- [backend/scraper_mooncell.py](backend/scraper_mooncell.py)：爬取 Mooncell 英灵图鉴，输出原始数据到 [backend/data/raw_characters.json](backend/data/raw_characters.json)。
- [backend/enrich_with_llm.py](backend/enrich_with_llm.py)：使用 DeepSeek API 补充信息和提取关系，输出到 [backend/data/enriched_characters.json](backend/data/enriched_characters.json)。
- [backend/build_graph.py](backend/build_graph.py)：将原始列表 + 关系数据转换为图谱结构，输出到 [frontend/public/graph_data.json](frontend/public/graph_data.json)。

## 数据结构约定（必须遵守）
- `Node`：`id`, `name`, `type`, `source`, `description`（可选 `image_url`, `metadata`）。
- `Link`：`source`, `target`, `relationship`, `label`。
- `type` 仅允许 `Character` 或 `Myth`。
- `relationship` 类型分三类：
  - 神话关系：`BELONGS_TO`, `PROTOTYPE_IS`, `GENDER_SWAP`, `DERIVED_FROM`, `COMPOSITE_OF`
  - 家族关系：`PARENT_OF`, `CHILD_OF`, `SIBLING_OF`, `SPOUSE_OF`, `LOVER_OF`
  - 社会关系：`MASTER_OF`, `SERVANT_OF`, `ALLY_OF`, `ENEMY_OF`, `FOUGHT_WITH`, `MENTOR_OF`, `STUDENT_OF`
- 角色节点 `id` 形如 `char_<编号>`；神话节点 `id` 形如 `myth_<slug>`。

## 角色关系可视化
- 关系数据在 [backend/data/character_relationships.json](backend/data/character_relationships.json)，格式：
  ```json
  {
    "source_name": "角色名（需匹配 name 或 prototype）",
    "target_name": "目标角色名",
    "relationship": "关系类型（RelationshipType 枚举值）",
    "bidirectional": "是否双向关系（如 SIBLING_OF, ALLY_OF）"
  }
  ```
- 构建脚本会自动匹配角色名并创建连线，跳过未找到的关系。
- 前端通过不同颜色和方向箭头显示不同关系类型，支持按类别筛选。

## 前端可视化关键点
- 图谱组件在 [frontend/src/components/TheogonyGraph.tsx](frontend/src/components/TheogonyGraph.tsx)，使用 `react-force-graph-2d`。
- 页面入口在 [frontend/src/app/page.tsx](frontend/src/app/page.tsx)，通过 `next/dynamic` 禁用 SSR。
- 关系类型配置在 `relationshipConfig`，包含颜色、显示名称和类别分组。
- 方向性关系（父子、师徒等）显示方向箭头粒子。
- 交互逻辑：点击节点高亮其相邻节点与连线，支持按关系类型筛选（见 `onNodeClick` 实现）。

## 运行与工作流
- Python 依赖见 [backend/requirements.txt](backend/requirements.txt)。
- 典型流程：
  1) 运行爬虫生成原始数据：`python -m backend.scraper_mooncell`
  2) 【可选】使用 LLM 增强数据：`python -m backend.enrich_with_llm --limit 10`（需设置 `DEEPSEEK_API_KEY`）
  3) 编辑 [backend/data/character_relationships.json](backend/data/character_relationships.json) 手动添加/审核关系
  4) 构建图谱：`python -m backend.build_graph`
  5) 前端开发：在 [frontend/](frontend/) 执行 `npm run dev`

## 项目约定
- 不要直接改动 [frontend/public/graph_data.json](frontend/public/graph_data.json)，应通过构建脚本生成。
- 增加字段时必须同时更新 `backend/schema.py` 与 `frontend/src/types.ts`。
- 新增关系类型必须同时在后端 `RelationshipType` 枚举和前端 `relationshipConfig` 中定义。
- 爬虫访问 Mooncell 时需保留随机 `User-Agent` 与延时策略（见 `scraper_mooncell.py`）。
- 关系数据手动维护，确保 `source_name` 和 `target_name` 与原始数据中的 `name` 或 `prototype` 字段匹配。
