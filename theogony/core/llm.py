"""LLM 提供方抽象：DeepSeek（知识增强）+ gpt-luna-5.6（联网检索研究）。

统一走 OpenAI 兼容协议；结构化输出用 JSON mode + Pydantic 校验自动重试；
Luna 提供方额外支持 web_search / fetch_url 工具调用循环（联网研究用）。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel

from theogony.core.config import get_settings

T = TypeVar("T", bound=BaseModel)

# 中转站风控限制：Luna 并发硬上限
LUNA_MAX_CONCURRENCY = 2

RESEARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "联网搜索，返回搜索结果摘要列表。用于查询公开资料（wiki、百科等）。",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "搜索关键词"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "抓取指定 URL 的正文文本（自动去除 HTML 标签）。",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "要抓取的 URL"}},
                "required": ["url"],
            },
        },
    },
]


@dataclass
class Provider:
    name: str  # deepseek | luna
    client: AsyncOpenAI
    model: str
    extra_body: dict


def get_provider(prefer: str | None = None) -> Provider | None:
    """解析可用的 LLM 提供方。prefer=luna 时优先 Luna，否则 DeepSeek 优先。"""
    s = get_settings()
    candidates: list[Provider] = []
    if s.deepseek_api_key:
        candidates.append(
            Provider(
                name="deepseek",
                client=AsyncOpenAI(api_key=s.deepseek_api_key, base_url=s.deepseek_api_base),
                model=s.deepseek_model,
                extra_body={},
            )
        )
    if s.luna_api_key and s.luna_api_base:
        candidates.append(
            Provider(
                name="luna",
                client=AsyncOpenAI(api_key=s.luna_api_key, base_url=s.luna_api_base),
                model=s.luna_model,
                extra_body=s.luna_extra,
            )
        )
    if not candidates:
        return None
    if prefer:
        for p in candidates:
            if p.name == prefer:
                return p
    return candidates[0]


async def preflight(provider: Provider) -> None:
    """连通性预检：认证失败/网络不通时立即给出明确错误（而非逐条静默失败）。"""
    try:
        await provider.client.chat.completions.create(
            model=provider.model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=4,
            extra_body=provider.extra_body or None,
        )
    except Exception as e:
        msg = str(e)
        if "auth" in msg.lower() or "401" in msg or "invalid_api_key" in msg:
            raise RuntimeError(
                f"[{provider.name}] API Key 认证失败（{provider.client.base_url}）。"
                "请检查 .env 中对应 *_API_KEY 是否有效。"
            ) from e
        raise RuntimeError(
            f"[{provider.name}] API 连接失败: {msg[:200]}（检查网络或 *_API_BASE 配置）"
        ) from e


async def chat_text(provider: Provider, prompt: str, *, system: str = "", temperature: float = 0.4, max_tokens: int = 2000) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    resp = await provider.client.chat.completions.create(
        model=provider.model,
        messages=messages,  # type: ignore[arg-type]
        temperature=temperature,
        max_tokens=max_tokens,
        extra_body=provider.extra_body or None,
    )
    return resp.choices[0].message.content or ""


async def chat_json(
    provider: Provider,
    schema: type[T],
    prompt: str,
    *,
    system: str = "",
    temperature: float = 0.2,
    max_tokens: int = 1800,
    retries: int = 2,
) -> T | None:
    """JSON 结构化输出：response_format=json_object + Pydantic 校验 + 重试。"""
    messages: list[dict] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    last_error = ""
    for attempt in range(retries + 1):
        retry_note = f"\n\n上一次输出未通过校验：{last_error}。请严格输出符合此 JSON Schema 的单个 JSON 对象：{schema_hint}" if last_error else f"\n\n只返回一个符合此 JSON Schema 的 JSON 对象（无其他文字）：{schema_hint}"
        try:
            resp = await provider.client.chat.completions.create(
                model=provider.model,
                messages=messages + [{"role": "user", "content": retry_note}],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
                extra_body=provider.extra_body or None,
            )
            raw = (resp.choices[0].message.content or "").strip()
            raw = _strip_code_fence(raw)
            parsed = json.loads(raw)
            if schema.__name__ and hasattr(schema, "model_validate"):
                return schema.model_validate(parsed)
            return parsed  # type: ignore[return-value]
        except json.JSONDecodeError as e:
            last_error = f"JSON 解析失败: {e}；原文前120字: {raw[:120]}"
        except Exception as e:  # 网络/限流错误等
            last_error = f"调用失败: {type(e).__name__}: {e}"
        # 重试指数退避（对风控/限流友好）
        if attempt < retries:
            await asyncio.sleep(3 * (attempt + 1))
    print(f"  [!] chat_json 最终失败 [{provider.model}]: {last_error[:300]}")
    return None


def _strip_code_fence(text: str) -> str:
    # 去掉推理模型可能内联的思考块
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "<think>" in text:  # 未闭合的思考块：截取其后内容
        text = text.split("<think>", 1)[1].split("</think>", 1)[-1]
    if text.startswith("```"):
        lines = text.strip("`").splitlines()
        if lines and lines[0].startswith(("json", "JSON")):
            lines = lines[1:]
        text = "\n".join(lines)
    return text.strip()


async def luna_research(provider: Provider, question: str, *, max_rounds: int = 4) -> str:
    """gpt-luna-5.6 联网研究：工具调用循环（web_search / fetch_url）。

    服务端若原生执行工具，直接返回文本；若返回 tool_calls，
    则由本地执行 httpx 请求后回填，最多 max_rounds 轮。
    """


    messages: list[dict] = [
        {"role": "system", "content": "你是神话与 ACG 资料研究员。可调用工具联网查证，回答需附来源。"},
        {"role": "user", "content": question},
    ]
    transcript: list[str] = []

    for _ in range(max_rounds):
        resp = await provider.client.chat.completions.create(
            model=provider.model,
            messages=messages,  # type: ignore[arg-type]
            tools=RESEARCH_TOOLS,  # type: ignore[arg-type]
            temperature=0.3,
            extra_body=provider.extra_body or None,
        )
        msg = resp.choices[0].message
        if msg.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in msg.tool_calls
                    ],
                }
            )
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments or "{}")
                if tc.function.name == "web_search":
                    result = await _tool_web_search(args.get("query", ""))
                elif tc.function.name == "fetch_url":
                    result = await _tool_fetch_url(args.get("url", ""))
                else:
                    result = "unknown tool"
                transcript.append(f"[tool {tc.function.name}] {args} -> {result[:200]}")
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": result[:6000]})
            continue
        # 无工具调用：返回最终文本
        answer = msg.content or ""
        if transcript:
            answer += "\n\n--- 研究过程 ---\n" + "\n".join(transcript)
        return answer
    return "研究轮次耗尽，未能得到结论。\n" + "\n".join(transcript)


async def _tool_web_search(query: str) -> str:
    """本地执行的 web_search 工具：用 Bing/DuckDuckGo HTML 结果兜底。"""
    UA_LOCAL = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    try:
        import httpx

        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": UA_LOCAL},
            )
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "lxml")
            results = []
            for item in soup.select(".result")[:8]:
                title = item.select_one(".result__title")
                snippet = item.select_one(".result__snippet")
                if title:
                    results.append(f"{title.get_text(strip=True)}: {snippet.get_text(strip=True) if snippet else ''}")
            return "\n".join(results) or "（无搜索结果）"
    except Exception as e:
        return f"搜索失败: {e}"


async def _tool_fetch_url(url: str) -> str:
    import httpx

    UA_LOCAL = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": UA_LOCAL})
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(resp.text, "lxml")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
            return text[:8000]
    except Exception as e:
        return f"抓取失败: {e}"
