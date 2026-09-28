# 使用 DeepSeek API 增强数据

## 功能

使用 DeepSeek 大语言模型自动：
1. **补充缺失信息**：地域、描述、属性等
2. **提取角色关系**：基于神话知识自动推断关系
3. **数据清洗标准化**：统一格式和命名
4. **获取深度信息**：爬虫无法获取的背景知识

## 准备工作

### 1. 获取 API Key

访问 [DeepSeek 开放平台](https://platform.deepseek.com/api_keys) 注册并获取 API Key。

### 2. 安装依赖

```bash
pip install openai
# 或在项目根目录运行
pip install -r backend/requirements.txt
```

### 3. 设置环境变量

**Windows (PowerShell):**
```powershell
$env:DEEPSEEK_API_KEY="your_api_key_here"
```

**Linux/macOS (bash):**
```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

**持久化设置（推荐）：**
- 创建 `.env` 文件（已在 `.gitignore` 中，不会被提交）：
  ```
  DEEPSEEK_API_KEY=your_api_key_here
  ```
- 或在系统环境变量中设置

## 使用方法

### 基础用法

```bash
# 在项目根目录执行
python -m backend.enrich_with_llm
```

### 命令行参数

```bash
# 测试模式：只处理前 10 个角色
python -m backend.enrich_with_llm --limit 10

# 预览模式：查看效果但不保存文件
python -m backend.enrich_with_llm --limit 5 --dry-run

# 只补充信息，不提取关系
python -m backend.enrich_with_llm --enrich-only

# 只提取关系，不补充信息
python -m backend.enrich_with_llm --relations-only

# 组合使用
python -m backend.enrich_with_llm --limit 20 --enrich-only
```

## 处理流程

### 1. 信息补充阶段

对每个角色，LLM 会：
- 分析角色名、职阶、原型
- 补充缺失的神话地域（如"希腊神话"）
- 生成 100-150 字的角色简介
- 推断属性（阵营、性别等）

**输入示例：**
```json
{
  "name": "阿尔托莉雅·潘德拉贡",
  "class": "Saber",
  "prototype": "亚瑟王",
  "region": "",
  "description": ""
}
```

**输出示例：**
```json
{
  "name": "阿尔托莉雅·潘德拉贡",
  "class": "Saber",
  "prototype": "亚瑟王",
  "region": "不列颠神话",
  "description": "不列颠传说中的传奇君主，圆桌骑士的领袖。在FGO中以性转形象登场...",
  "mythology_background": "亚瑟王是中世纪不列颠最著名的传奇国王，拔出石中剑继承王位...",
  "metadata": {
    "alignment": "秩序·善",
    "gender": "女"
  }
}
```

### 2. 关系提取阶段

对每个有原型的角色，LLM 会：
- 基于神话知识推断与其他角色的关系
- 评估关系的置信度（high/medium/low）
- 提供关系依据说明

**提取逻辑：**
1. 读取所有已知角色列表
2. 让 LLM 判断目标角色与哪些角色有关系
3. 只保留高/中置信度的关系
4. 自动去重并合并到 `character_relationships.json`

**关系示例：**
```json
{
  "source_name": "阿尔托莉雅·潘德拉贡",
  "target_name": "莫德雷德",
  "relationship": "PARENT_OF",
  "bidirectional": false,
  "confidence": "high",
  "evidence": "亚瑟王与莫德雷德为父子关系"
}
```

## 输出文件

| 文件 | 说明 |
|------|------|
| `backend/data/enriched_characters.json` | 增强后的角色数据 |
| `backend/data/character_relationships.json` | 更新后的关系数据（自动合并） |

## 成本估算

DeepSeek 价格（2024 年）：
- 输入：¥1 / 1M tokens
- 输出：¥2 / 1M tokens

**预估消耗：**
- 单个角色信息补充：~500 tokens（输入） + ~300 tokens（输出）
- 单个角色关系提取：~2000 tokens（输入） + ~200 tokens（输出）

**465 个角色完整处理：**
- 信息补充：约 ¥0.8
- 关系提取：约 ¥1.2
- **总计：约 ¥2.0**

## 质量控制

### 置信度筛选

脚本会自动过滤低置信度关系，只保留：
- `high`: 确定的神话关系（如亚瑟王-莫德雷德）
- `medium`: 可能的关系（如剧情中的盟友）
- ~~`low`: 推测性关系~~（自动丢弃）

### 手动审核建议

1. **检查生成的描述**：确保无明显错误
2. **验证关系依据**：查看 `evidence` 字段
3. **去除重复关系**：脚本会自动去重，但建议人工复核

## 故障排除

### API Key 错误
```
[✗] 请设置环境变量 DEEPSEEK_API_KEY
```
→ 检查环境变量是否正确设置

### 限流错误
```
[!] API 调用失败: Rate limit exceeded
```
→ 调大 `REQUEST_DELAY`（默认 0.5 秒）

### JSON 解析失败
```
[!] 无法解析 JSON: ...
```
→ LLM 响应格式不标准，脚本会自动重试提取，如果持续失败则保留原数据

## 高级用法

### 自定义 Prompt

修改 [enrich_with_llm.py](enrich_with_llm.py) 中的 `ENRICH_CHARACTER_PROMPT` 和 `EXTRACT_RELATIONSHIPS_PROMPT`。

### 调整模型参数

```python
# 在 enrich_with_llm.py 中修改
DEEPSEEK_MODEL = "deepseek-chat"  # 模型版本
DEFAULT_TEMPERATURE = 0.3         # 温度（0-1，越低越确定）
REQUEST_DELAY = 0.5               # 请求间隔（秒）
```

## 完整工作流

```bash
# 1. 运行爬虫获取原始数据
python -m backend.scraper_mooncell

# 2. 使用 LLM 增强数据（先测试少量）
python -m backend.enrich_with_llm --limit 10 --dry-run

# 3. 正式处理全部数据
python -m backend.enrich_with_llm

# 4. 构建图谱
python -m backend.build_graph

# 5. 查看前端效果
cd frontend && npm run dev
```

## 注意事项

1. **首次运行建议使用 `--limit 10 --dry-run` 测试**
2. **处理全部 465 个角色约需 5-10 分钟**（取决于网络和 API 响应速度）
3. **生成的数据需要人工抽查质量**
4. **关系提取可能产生误判**，建议审核后再用于生产环境
5. **API Key 不要提交到 Git**，已在 `.gitignore` 中排除 `.env` 文件
