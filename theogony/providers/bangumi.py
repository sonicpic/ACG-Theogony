"""Bangumi（bgm.tv）v0 API Provider：ACG 作品/角色/人物的中文侧入口。

文档：https://github.com/bangumi/api
"""

from __future__ import annotations

from theogony.providers.base import HttpProviderBase


class BangumiProvider(HttpProviderBase):
    name = "bangumi"
    prefer_proxy = True  # 直连在部分网络环境超时，优先代理（失败自动回退）
    min_interval = 0.5   # 官方建议 ≤ 5 req/s，取保守间隔

    async def search_characters(self, keyword: str, limit: int = 20) -> list[dict]:
        d = await self._post("https://api.bgm.tv/v0/search/characters",
                             json_body={"keyword": keyword, "limit": limit}, ttl=86400 * 7)
        return d.get("data", [])

    async def search_subjects(self, keyword: str, subject_type: int = 2, limit: int = 5) -> list[dict]:
        """subject_type: 1=书 2=动画 4=游戏 6=三次元。"""
        d = await self._post("https://api.bgm.tv/v0/search/subjects",
                             json_body={"keyword": keyword, "filter": {"type": [subject_type]},
                                        "limit": limit},
                             ttl=86400 * 7)
        return d.get("data", [])

    async def subject_characters(self, subject_id: int) -> list[dict]:
        d = await self._get(f"https://api.bgm.tv/v0/subjects/{subject_id}/characters",
                            params={"limit": 100}, ttl=86400 * 7)
        return d if isinstance(d, list) else []

    async def character_detail(self, character_id: int) -> dict:
        return await self._get(f"https://api.bgm.tv/v0/characters/{character_id}", ttl=86400 * 30)

    async def character_subjects(self, character_id: int) -> list[dict]:
        """角色出演的作品列表（subject 含 type：1=书 2=动画 4=游戏 6=三次元）。"""
        d = await self._get(f"https://api.bgm.tv/v0/characters/{character_id}/subjects",
                            ttl=86400 * 30)
        return d if isinstance(d, list) else []
