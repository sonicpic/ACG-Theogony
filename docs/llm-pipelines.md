# LLM 数据管道

系统通过 LLM 完成数据增强、关系挖掘与联网研究。所有 LLM 调用统一走
`theogony/core/llm.py` 的提供方抽象（任意 OpenAI 兼容端点，JSON mode +
Pydantic 校验 + 指数退避 + 并发钳制）。

## 配置

复制 `.env.example` 为 `.env` 后按需填写：

| 变量 | 用途 |
|---|---|
| `DEEPSEEK_API_KEY` / `DEEPSEEK_API_BASE` | DeepSeek 提供方（可选） |
| `LUNA_API_KEY` / `LUNA_API_BASE` / `LUNA_MODEL` | 支持联网检索的提供方（`npm run research` 用） |
| `LUNA_EXTRA_BODY` | 透传的额外请求体（如思考强度） |
| `EMBEDDINGS_API_KEY` / `EMBEDDINGS_API_BASE` / `EMBEDDINGS_MODEL` | 语义向量检索（可选，配置后搜索升级为词法+语义混合） |

不配置任何 Key 时系统完全可用：AI 功能自动降级为纯图检索（FTS5 + BFS + 模板化回答）。

## 管道命令

| 命令 | 说明 |
|---|---|
| `npm run enrich` | LLM 结构化增强全部角色（逐条落库、断点续传，`--limit 5` 试跑） |
| `npm run mine` | 按神话体系分批挖掘角色关系 → 审核队列（`--limit-batches 2` 试跑） |
| `npm run research` | 联网研究（`--character 阿蒂拉` 深挖单角色，或 `--ask "..."` 问答） |

推荐顺序：`scrape → db:build → enrich → mine → 审核(/review)`。

## 约定

- 批量任务用 `python -u` 运行并逐批增量落库，中断可续跑；
- 写库后需要 `rebuild_fts` 与 `GraphService.refresh()`（管道已内置）；
- 联网类提供方通常有严格风控：并发默认钳制为 2，批处理思考强度用 medium，
  深挖单批才用 `--effort max`；
- LLM 产出的关系一律 `status=pending` 且携带 `confidence`/`evidence`，
  经人工审核后才进入默认图谱（ADR-0003）。
