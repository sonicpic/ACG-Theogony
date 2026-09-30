"""Fandom 型月维基 Provider（MediaWiki API，英文站为主力）。

全宇宙世界观语料来源：typemoon.fandom.com（6532+ 篇，覆盖 Fate 全系列 +
月姬/空境共享宇宙）。内容 CC BY-SA。
"""

from __future__ import annotations

from theogony.providers.base import HttpProviderBase

_API = "https://typemoon.fandom.com/api.php"


class FandomProvider(HttpProviderBase):
    name = "fandom"
    prefer_proxy = True  # fandom.com 在部分网络不可直连
    min_interval = 0.35  # 礼貌限速；批量接口下全站只需 ~150 请求
    timeout = 40.0

    async def all_page_titles(self) -> list[str]:
        """主命名空间全部页面标题（apcontinue 翻页）。"""
        out: list[str] = []
        cont: dict | None = None
        while True:
            params = {"action": "query", "list": "allpages", "aplimit": "500",
                      "apnamespace": 0, "format": "json"}
            if cont:
                params.update(cont)
            d = await self._get(_API, params=params, ttl=86400 * 7)
            batch = d.get("query", {}).get("allpages", [])
            out.extend(p["title"] for p in batch)
            cont = d.get("continue")
            if not cont or not batch:
                break
        return out

    async def fetch_pages_batch(self, titles: list[str]) -> dict[str, str]:
        """批量取 wikitext（每请求 ≤50 页，revisions+slots）。返回 {title: wikitext}。"""
        out: dict[str, str] = {}
        for i in range(0, len(titles), 50):
            chunk = titles[i:i + 50]
            d = await self._get(_API, params={
                "action": "query", "titles": "|".join(chunk),
                "prop": "revisions", "rvprop": "content",
                "rvslots": "main", "format": "json",
            }, ttl=86400 * 30)
            for page in d.get("query", {}).get("pages", {}).values():
                try:
                    content = page["revisions"][0]["slots"]["main"]["*"]
                except (KeyError, IndexError, TypeError):
                    continue
                out[page["title"]] = content or ""
        return out
