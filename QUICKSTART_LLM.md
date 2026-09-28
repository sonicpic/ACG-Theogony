# DeepSeek API 增强数据 - 快速开始

## 1. 获取 API Key（免费额度足够测试）

访问：https://platform.deepseek.com/api_keys

## 2. 设置环境变量

**PowerShell（当前会话有效）：**
```powershell
$env:DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxx"
```

**持久化设置（推荐）：**
在项目根目录创建 `.env` 文件：
```
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
```

## 3. 测试运行（处理 5 个角色）

```powershell
# 预览模式，不保存文件
python -m backend.enrich_with_llm --limit 5 --dry-run
```

## 4. 正式运行

```powershell
# 处理全部角色（约 5-10 分钟，费用约 ¥2）
python -m backend.enrich_with_llm

# 或分阶段处理
python -m backend.enrich_with_llm --limit 50 --enrich-only  # 先补充 50 个
python -m backend.enrich_with_llm --limit 50 --relations-only  # 再提取关系
```

## 5. 重新构建图谱

```powershell
python -m backend.build_graph
```

## 预期效果

### 信息补充
- 自动填充缺失的 `region`（如"希腊神话"）
- 生成详细的 `description`（100-150 字）
- 推断属性（阵营、性别等）

### 关系提取
- 基于神话知识自动推断角色关系
- 只保留高/中置信度关系
- 自动合并到 `character_relationships.json`

## 示例输出

**补充前：**
```json
{
  "name": "赫拉克勒斯",
  "class": "Berserker",
  "region": "",
  "description": ""
}
```

**补充后：**
```json
{
  "name": "赫拉克勒斯",
  "class": "Berserker",
  "region": "希腊神话",
  "description": "希腊神话中最伟大的英雄，宙斯之子。完成十二项不可能的任务...",
  "mythology_background": "赫拉克勒斯是宙斯与凡人阿尔克墨涅之子...",
  "metadata": {
    "alignment": "混乱·狂",
    "gender": "男"
  }
}
```

**自动发现关系：**
```json
{
  "source_name": "赫拉克勒斯",
  "target_name": "美狄亚",
  "relationship": "ALLY_OF",
  "confidence": "high",
  "evidence": "伊阿宋远征时的同伴"
}
```

## 注意事项

1. 首次使用建议先 `--limit 5 --dry-run` 测试
2. API Key 不要提交到 Git（已在 `.gitignore` 排除）
3. 生成的关系建议人工审核后再用于生产
4. 处理全部数据约需 5-10 分钟

详细文档：[docs/LLM_ENRICHMENT.md](docs/LLM_ENRICHMENT.md)
