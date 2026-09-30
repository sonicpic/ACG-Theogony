"""外部数据源 Provider 层：统一缓存/限流/重试/代理回退的 HTTP 适配器。

设计约定：
- 数据源实现只描述"接口形态"（URL、参数、解析），通用能力全部由 HttpProviderBase 承担；
- 响应按 cache-key 落盘于 data/cache/providers/<name>/，重启即缓存命中；
- 限流为最小请求间隔 + 可选并发信号量，礼貌抓取；
- 代理策略：provider 声明 prefer_proxy，连接层失败自动回退另一条通道并记住本次会话可用通道。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Any

import httpx

from theogony.core.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()
PROXY_URL = _settings.http_proxy or "http://127.0.0.1:7897"
CACHE_ROOT = _settings.data_dir / "cache" / "providers"

_DEFAULT_HEADERS = {
    "User-Agent": "acg-theogony/2.1 (https://github.com/sonicpic/ACG-Theogony)",
    "Accept": "application/json",
}


def _cache_key(url: str, params: Any, body: Any) -> str:
    raw = json.dumps([url, params, body], ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


class HttpProviderBase:
    """带文件缓存、最小间隔限流、重试与代理回退的异步 HTTP 基类。"""

    name: str = "base"
    prefer_proxy: bool = False
    min_interval: float = 0.25  # 相邻请求最小间隔（秒）
    timeout: float = 20.0

    def __init__(self) -> None:
        self._cache_dir = CACHE_ROOT / self.name
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._last_send = 0.0
        self._use_proxy: bool | None = None  # 会话内记住可用通道
        self._clients: dict[str, httpx.AsyncClient] = {}

    # ── 子类入口 ──────────────────────────────
    async def _get(self, url: str, *, params: dict | None = None, headers: dict | None = None,
                   ttl: float | None = None) -> Any:
        return await self._request("GET", url, params=params, headers=headers, ttl=ttl)

    async def _post(self, url: str, *, json_body: dict | None = None, params: dict | None = None,
                    headers: dict | None = None, ttl: float | None = None) -> Any:
        return await self._request("POST", url, params=params, headers=headers,
                                   json_body=json_body, ttl=ttl)

    # ── 通用实现 ──────────────────────────────
    async def _request(self, method: str, url: str, *, params: dict | None = None,
                       headers: dict | None = None, json_body: dict | None = None,
                       ttl: float | None = None) -> Any:
        key = _cache_key(url, params, json_body)
        cache_file = self._cache_dir / f"{key}.json"
        if cache_file.exists():
            blob = json.loads(cache_file.read_text(encoding="utf-8"))
            if ttl is None or time.time() - blob["t"] < ttl:
                return blob["d"]

        last_error: Exception | None = None
        for attempt in range(3):
            await self._pace()
            try:
                data = await self._send_once(method, url, params, headers, json_body)
            except (httpx.HTTPError, _UpstreamError) as e:
                last_error = e
                wait = 1.5 * (attempt + 1)
                logger.warning("%s %s 第%d次失败: %s，%.1fs 后重试", self.name, url, attempt + 1, e, wait)
                await asyncio.sleep(wait)
                self._use_proxy = None  # 通道可能劣化，重置回退探测
                continue
            cache_file.write_text(
                json.dumps({"t": time.time(), "d": data}, ensure_ascii=False), encoding="utf-8")
            return data
        raise RuntimeError(f"{self.name} 请求最终失败: {url} ({last_error})")

    async def _pace(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last_send + self.min_interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_send = time.monotonic()

    def _client(self, use_proxy: bool) -> httpx.AsyncClient:
        key = "proxy" if use_proxy else "direct"
        if key not in self._clients:
            self._clients[key] = httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=False,
                headers={**_DEFAULT_HEADERS, **getattr(self, "extra_headers", {})},
                proxy=PROXY_URL if use_proxy else None,
            )
        return self._clients[key]

    async def _send_once(self, method: str, url: str, params: dict | None,
                         headers: dict | None, json_body: dict | None) -> Any:
        order = [self.prefer_proxy, not self.prefer_proxy] if self._use_proxy is None else [self._use_proxy]
        last_err: Exception | None = None
        for use_proxy in order:
            client = self._client(use_proxy)
            try:
                resp = await client.request(
                    method, url, params=params, headers=headers, json=json_body if json_body else None)
            except httpx.HTTPError as e:
                # 本通道连接失败 → 落到下一通道（代理/直连互为备份）
                last_err = e
                self._use_proxy = None
                continue
            if resp.status_code in (200,):
                self._use_proxy = use_proxy
                return resp.json()
            if resp.status_code in (429, 500, 502, 503, 504):
                raise _UpstreamError(f"HTTP {resp.status_code}: {resp.text[:120]}")
            # 4xx（参数问题等）不重试、不换通道，直接抛
            raise _UpstreamError(f"HTTP {resp.status_code}: {resp.text[:120]}")
        raise _UpstreamError(f"no channel ({last_err})")

    async def aclose(self) -> None:
        for c in self._clients.values():
            await c.aclose()
        self._clients.clear()


class _UpstreamError(Exception):
    """上游可重试错误。"""
