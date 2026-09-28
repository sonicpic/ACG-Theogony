"""
使用 DeepSeek API 增强角色数据

功能：
  1. 补充缺失的角色描述、地域、属性等信息
  2. 自动推断角色间的神话关系（基于神话知识）
  3. 清洗和标准化数据格式
  4. 获取爬虫无法抓取的深度信息

使用方法：
    # 需要先设置环境变量 DEEPSEEK_API_KEY
    export DEEPSEEK_API_KEY="your_api_key"
    
    python -m backend.enrich_with_llm                    # 处理所有角色
    python -m backend.enrich_with_llm --limit 10        # 只处理前10个
    python -m backend.enrich_with_llm --dry-run         # 预览不保存
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Optional

try:
    from openai import OpenAI
except ImportError:
    print("[!] 需要安装 openai 库: pip install openai")
    exit(1)

try:
    from backend.schema import RelationshipType
except ModuleNotFoundError:
    from schema import RelationshipType  # type: ignore

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

_HERE = Path(__file__).resolve().parent
RAW_FILE = _HERE / "data" / "raw_characters.json"
ENRICHED_FILE = _HERE / "data" / "enriched_characters.json"
RELATIONSHIPS_FILE = _HERE / "data" / "character_relationships.json"

# 加载 .env 文件
_ENV_FILE = _HERE.parent / ".env"
if _ENV_FILE.exists():
    with open(_ENV_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()

DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_TEMPERATURE = 0.3
REQUEST_DELAY = 0.5  # 秒，避免触发限流

# ──────────────────────────────────────────────
# Prompt 模板
# ──────────────────────────────────────────────

ENRICH_CHARACTER_PROMPT = """分析以下 Fate/Grand Order 角色，补充神话信息。只返回 JSON，无其他文字。

角色信息：
- 名称: {name}
- 职阶: {char_class}
- 原型: {prototype}

返回格式：
{{
  "region": "神话体系（必须从下列选择或留空）",
  "description": "80-100字简介",
  "mythology_background": "30-50字神话背景",
  "alignment": "阵营（如'秩序·善'）",
  "gender": "男/女/未知"
}}

标准神话体系列表：
希腊神话, 罗马神话, 北欧神话, 凯尔特神话, 不列颠神话, 埃及神话, 美索不达米亚神话, 波斯神话, 印度神话, 中国神话, 日本神话, 阿兹特克神话, 玛雅神话, 非洲神话, 斯拉夫神话, 基督教, 伊斯兰教, 现代创作, 史实人物

规则：
1. region 必须从列表精确匹配一个，多个体系选最主要的
2. 现代虚构角色（如玛修）用"现代创作"
3. 真实历史人物（如织田信长）用"史实人物"
4. description 包含：身份+主要事迹+FGO特点
5. 无法确定的字段返回空字符串
6. 严格遵守字数限制"""

EXTRACT_RELATIONSHIPS_PROMPT = """你是一位精通全球神话关系网的专家。请分析以下角色的神话原型，列出与其他已知角色的关系。

目标角色：
- 名称: {name}
- 原型: {prototype}
- 地域: {region}

已知角色列表（可能与目标角色有关系的）：
{known_characters}

请以 JSON 数组格式返回关系（只返回 JSON，不要其他文字）：
[
  {{
    "target_name": "目标角色的准确名称（必须与已知角色列表完全匹配）",
    "relationship": "关系类型（见下方列表）",
    "bidirectional": true/false,
    "confidence": "high/medium/low（推断置信度）",
    "evidence": "简短说明关系依据（20字内）"
  }}
]

可用关系类型：
- 家族关系: PARENT_OF, CHILD_OF, SIBLING_OF, SPOUSE_OF, LOVER_OF
- 社会关系: MASTER_OF, SERVANT_OF, ALLY_OF, ENEMY_OF, FOUGHT_WITH, MENTOR_OF, STUDENT_OF
- 神话关系: PROTOTYPE_IS, GENDER_SWAP, DERIVED_FROM

规则：
1. 只返回置信度 high 或 medium 的关系
2. target_name 必须严格匹配已知角色列表中的名称
3. 优先神话原型的真实关系，其次考虑FGO剧情关系
4. 如果没有明确关系，返回空数组 []
5. 避免推测性强的关系
"""

# ──────────────────────────────────────────────
# API 调用
# ──────────────────────────────────────────────

def get_client() -> OpenAI:
    """初始化 DeepSeek API 客户端"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError(
            "请设置环境变量 DEEPSEEK_API_KEY\n"
            "获取方式: https://platform.deepseek.com/api_keys"
        )
    
    return OpenAI(
        api_key=api_key,
        base_url=DEEPSEEK_API_BASE,
    )


def call_llm(client: OpenAI, prompt: str, temperature: float = DEFAULT_TEMPERATURE) -> Optional[str]:
    """调用 LLM 并返回响应文本"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=600,  # 增加到 600 以容纳更多字段
                timeout=30.0,  # 保持 30秒超时
            )
            return response.choices[0].message.content
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"  [!] API 调用失败 (尝试 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print(f"  [*] 等待 {REQUEST_DELAY * 2} 秒后重试...")
                time.sleep(REQUEST_DELAY * 2)
            else:
                return None


def parse_json_response(response: str) -> Optional[dict | list]:
    """从 LLM 响应中提取 JSON（容错处理）"""
    if not response:
        return None
    
    # 尝试直接解析
    try:
        return json.loads(response)
    except json.JSONDecodeError:
        pass
    
    # 尝试提取代码块中的 JSON
    import re
    json_match = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", response, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # 尝试查找第一个有效的 JSON 对象/数组
    for pattern in [r"\{.*\}", r"\[.*\]"]:
        json_match = re.search(pattern, response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                continue
    
    print(f"  [!] 无法解析 JSON: {response[:100]}...")
    return None


# ──────────────────────────────────────────────
# 数据增强
# ──────────────────────────────────────────────

def enrich_character(client: OpenAI, character: dict) -> dict:
    """使用 LLM 补充单个角色的信息"""
    name = character.get("name", "")
    print(f"  [*] 增强角色: {name}")
    
    prompt = ENRICH_CHARACTER_PROMPT.format(
        name=name,
        char_class=character.get("class", "未知"),
        prototype=character.get("prototype", "未知"),
        region=character.get("region", "未知"),
        description=character.get("description", "无"),
    )
    
    response = call_llm(client, prompt)
    enriched_data = parse_json_response(response)
    
    if not enriched_data:
        print(f"    [!] 增强失败，保留原数据")
        return character
    
    # 合并数据
    enriched_char = character.copy()
    if enriched_data.get("region"):
        enriched_char["region"] = enriched_data["region"]
    if enriched_data.get("description"):
        enriched_char["description"] = enriched_data["description"]
    if enriched_data.get("mythology_background"):
        enriched_char["mythology_background"] = enriched_data["mythology_background"]
    
    # 合并属性到 metadata
    if "metadata" not in enriched_char:
        enriched_char["metadata"] = {}
    if enriched_data.get("alignment"):
        enriched_char["metadata"]["alignment"] = enriched_data["alignment"]
    if enriched_data.get("gender"):
        enriched_char["metadata"]["gender"] = enriched_data["gender"]
    
    print(f"    [✓] 已补充: region={enriched_data.get('region', '无')}")
    return enriched_char


def extract_relationships(
    client: OpenAI,
    character: dict,
    known_characters: list[dict]
) -> list[dict]:
    """使用 LLM 推断角色关系"""
    name = character.get("name", "")
    prototype = character.get("prototype", "")
    
    if not prototype:
        return []
    
    print(f"  [*] 提取关系: {name}")
    
    # 构建已知角色列表（只包含有原型的）
    char_list = []
    for c in known_characters:
        if c.get("prototype") and c.get("name") != name:
            char_list.append(f"- {c['name']} (原型: {c['prototype']})")
    
    if len(char_list) > 100:
        # 限制列表长度，避免超过 token 限制
        char_list = char_list[:100]
    
    prompt = EXTRACT_RELATIONSHIPS_PROMPT.format(
        name=name,
        prototype=prototype,
        region=character.get("region", "未知"),
        known_characters="\n".join(char_list),
    )
    
    response = call_llm(client, prompt)
    relationships = parse_json_response(response)
    
    if not relationships or not isinstance(relationships, list):
        print(f"    [✓] 未发现关系")
        return []
    
    # 过滤低置信度关系
    valid_relationships = [
        rel for rel in relationships
        if rel.get("confidence") in ("high", "medium")
    ]
    
    print(f"    [✓] 发现 {len(valid_relationships)} 条关系")
    return valid_relationships


# ──────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="使用 DeepSeek API 增强角色数据")
    parser.add_argument("--limit", type=int, help="限制处理数量（用于测试）")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不保存文件")
    parser.add_argument("--enrich-only", action="store_true", help="只补充信息，不提取关系")
    parser.add_argument("--relations-only", action="store_true", help="只提取关系，不补充信息")
    parser.add_argument("--skip", type=int, default=0, help="跳过前N个角色（断点续传）")
    args = parser.parse_args()
    
    print("=" * 60)
    print("DeepSeek API 数据增强")
    print("=" * 60)
    
    # 1. 检查 API Key
    try:
        client = get_client()
        print("[✓] API 客户端已初始化")
    except ValueError as e:
        print(f"[✗] {e}")
        return
    
    # 2. 读取原始数据
    if not RAW_FILE.exists():
        print(f"[✗] 找不到原始数据: {RAW_FILE}")
        return
    
    with open(RAW_FILE, "r", encoding="utf-8") as f:
        raw_characters = json.load(f)
    
    # 3. 支持断点续传：读取已有的增强数据
    existing_enriched = {}
    if ENRICHED_FILE.exists() and not args.dry_run:
        with open(ENRICHED_FILE, "r", encoding="utf-8") as f:
            existing_data = json.load(f)
            existing_enriched = {c["id"]: c for c in existing_data}
        print(f"[*] 已加载 {len(existing_enriched)} 条现有增强数据")
    
    total = len(raw_characters)
    if args.skip > 0:
        raw_characters = raw_characters[args.skip:]
        print(f"[*] 跳过前 {args.skip} 个角色")
    
    if args.limit:
        raw_characters = raw_characters[:args.limit]
        print(f"[1/4] 已加载 {len(raw_characters)}/{total} 条数据（测试模式）")
    else:
        print(f"[1/4] 已加载 {len(raw_characters)} 条原始数据")
    
    # 3. 补充角色信息
    enriched_characters = []
    if not args.relations_only:
        print(f"\n[2/4] 开始补充角色信息...")
        for i, char in enumerate(raw_characters, 1):
            # 检查是否已处理过
            if char["id"] in existing_enriched:
                print(f"  [{i}/{len(raw_characters)}]   [*] 跳过已处理: {char.get('name')}")
                enriched_characters.append(existing_enriched[char["id"]])
                continue
            
            print(f"  [{i}/{len(raw_characters)}]", end=" ")
            try:
                enriched_char = enrich_character(client, char)
                enriched_characters.append(enriched_char)
                
                # 实时保存（防止中断丢失）
                if not args.dry_run and i % 5 == 0:
                    # 合并现有数据
                    all_enriched = list(existing_enriched.values()) + enriched_characters
                    ENRICHED_FILE.parent.mkdir(parents=True, exist_ok=True)
                    with open(ENRICHED_FILE, "w", encoding="utf-8") as f:
                        json.dump(all_enriched, f, ensure_ascii=False, indent=2)
                    print(f"    [*] 已保存进度 ({len(all_enriched)} 条)")
                
                time.sleep(REQUEST_DELAY)
            except KeyboardInterrupt:
                print(f"\n  [!] 用户中断，保存当前进度...")
                if not args.dry_run:
                    all_enriched = list(existing_enriched.values()) + enriched_characters
                    with open(ENRICHED_FILE, "w", encoding="utf-8") as f:
                        json.dump(all_enriched, f, ensure_ascii=False, indent=2)
                    print(f"  [✓] 已保存 {len(all_enriched)} 条数据")
                    print(f"  [*] 继续处理：--skip {args.skip + i}")
                raise
        
        if not args.dry_run:
            # 最终保存（合并所有数据）
            all_enriched = list(existing_enriched.values())
            # 去重：优先使用新处理的数据
            new_ids = {c["id"] for c in enriched_characters}
            all_enriched = [c for c in all_enriched if c["id"] not in new_ids]
            all_enriched.extend(enriched_characters)
            
            ENRICHED_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(ENRICHED_FILE, "w", encoding="utf-8") as f:
                json.dump(all_enriched, f, ensure_ascii=False, indent=2)
            print(f"\n  [✓] 已保存增强数据: {ENRICHED_FILE}")
            print(f"      总计: {len(all_enriched)} 条")
    else:
        enriched_characters = raw_characters
        print(f"\n[2/4] 跳过信息补充")
    
    # 4. 提取关系
    all_relationships = []
    if not args.enrich_only:
        print(f"\n[3/4] 开始提取角色关系...")
        for i, char in enumerate(enriched_characters, 1):
            if not char.get("prototype"):
                continue
            
            print(f"  [{i}/{len(enriched_characters)}]", end=" ")
            relationships = extract_relationships(client, char, enriched_characters)
            
            for rel in relationships:
                all_relationships.append({
                    "source_name": char["name"],
                    "target_name": rel["target_name"],
                    "relationship": rel["relationship"],
                    "bidirectional": rel.get("bidirectional", False),
                    "confidence": rel.get("confidence", "medium"),
                    "evidence": rel.get("evidence", ""),
                })
            
            time.sleep(REQUEST_DELAY)
        
        print(f"\n  [*] 总计发现 {len(all_relationships)} 条关系")
        
        # 合并到现有关系文件
        if not args.dry_run and all_relationships:
            existing_relationships = []
            if RELATIONSHIPS_FILE.exists():
                with open(RELATIONSHIPS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    existing_relationships = data.get("relationships", [])
            
            # 去重（基于 source + target + relationship）
            existing_keys = {
                (r["source_name"], r["target_name"], r["relationship"])
                for r in existing_relationships
            }
            
            new_relationships = [
                r for r in all_relationships
                if (r["source_name"], r["target_name"], r["relationship"]) not in existing_keys
            ]
            
            combined = existing_relationships + new_relationships
            
            output = {
                "_comment": "角色关系数据库 - 手动维护 + LLM 自动生成",
                "_format": {
                    "source_name": "源角色名",
                    "target_name": "目标角色名",
                    "relationship": "关系类型",
                    "bidirectional": "是否双向",
                    "confidence": "置信度（仅 LLM 生成的有此字段）",
                    "evidence": "关系依据（仅 LLM 生成的有此字段）"
                },
                "relationships": combined
            }
            
            with open(RELATIONSHIPS_FILE, "w", encoding="utf-8") as f:
                json.dump(output, f, ensure_ascii=False, indent=2)
            
            print(f"  [✓] 已更新关系文件: {RELATIONSHIPS_FILE}")
            print(f"      新增: {len(new_relationships)} 条")
            print(f"      总计: {len(combined)} 条")
    else:
        print(f"\n[3/4] 跳过关系提取")
    
    # 5. 总结
    print(f"\n[4/4] 完成!")
    if args.dry_run:
        print("  [*] 预览模式，未保存任何文件")
    else:
        print("  [✓] 数据已增强并保存")
        print(f"\n下一步: python -m backend.build_graph")


if __name__ == "__main__":
    main()
