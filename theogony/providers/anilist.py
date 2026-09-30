"""AniList GraphQL Provider：国际侧作品/角色入口，GraphQL 单请求可批量取数。

文档：https://docs.anilist.co
限流：30 req/min（降级态）——批量查询设计下，同步一次全量仅需个位数请求。
"""

from __future__ import annotations

from theogony.providers.base import HttpProviderBase

_URL = "https://graphql.anilist.co"

_POPULAR_MEDIA_CHARACTERS = """
query ($page: Int, $perPage: Int, $charPerPage: Int) {
  Page(page: $page, perPage: $perPage) {
    media(sort: POPULARITY_DESC, type: ANIME) {
      id
      title { romaji english native }
      genres
      characters(page: 1, perPage: $charPerPage, sort: RELEVANCE) {
        nodes {
          id
          name { full native alternative }
          description(asHtml: false)
        }
      }
    }
  }
}
"""


class AniListProvider(HttpProviderBase):
    name = "anilist"
    prefer_proxy = False
    min_interval = 1.2  # 降级态 30/min → 2s/req，取 1.2s 批量足够
    timeout = 30.0

    async def popular_media_characters(self, page: int, per_page: int = 25, char_per_page: int = 8) -> list[dict]:
        """按人气倒序取动画及其主要角色。返回扁平记录：media 信息 + 单角色。"""
        d = await self._post(_URL, json_body={
            "query": _POPULAR_MEDIA_CHARACTERS,
            "variables": {"page": page, "perPage": per_page, "charPerPage": char_per_page},
        }, ttl=86400 * 7)
        rows: list[dict] = []
        for media in d.get("data", {}).get("Page", {}).get("media", []):
            for ch in media.get("characters", {}).get("nodes", []):
                rows.append({
                    "media_id": media["id"],
                    "media_title": media.get("title", {}).get("native") or media.get("title", {}).get("romaji"),
                    "media_genres": media.get("genres", []),
                    "char_id": ch["id"],
                    "char_name": ch.get("name", {}).get("full"),
                    "char_native": ch.get("name", {}).get("native"),
                    "char_alt": ch.get("name", {}).get("alternative", []),
                    "description": (ch.get("description") or "")[:300],
                })
        return rows

    async def raw_query(self, query: str, variables: dict | None = None, ttl: float | None = None) -> dict:
        return await self._post(_URL, json_body={"query": query, "variables": variables or {}}, ttl=ttl)
