"""图片代理：解决 wiki 图片热链跨域/防盗链（带白名单与本地缓存）。"""

from __future__ import annotations

import hashlib
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from theogony.core.config import get_settings
from theogony.pipelines.scrape_mooncell import UA

router = APIRouter(tags=["proxy"])

ALLOWED_HOSTS = {
    "fgo.wiki",
    "media.fgo.wiki",
    "static.wikia.nocookie.net",
    "upload.wikimedia.org",
}
ALLOWED_PREFIXES = tuple(ALLOWED_HOSTS)


@router.get("/img")
async def img_proxy(url: str = Query(...), size: str | None = None):
    from urllib.parse import urlparse

    host = urlparse(url).netloc.lower()
    if not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise HTTPException(403, f"不在白名单内的图片域: {host}")

    settings = get_settings()
    cache_dir: Path = settings.data_dir / "cache" / "img"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(url.encode()).hexdigest()
    ext = ".jpg"
    if ".png" in url.lower():
        ext = ".png"
    elif ".webp" in url.lower():
        ext = ".webp"
    elif ".gif" in url.lower():
        ext = ".gif"
    cached = cache_dir / (key + ext)
    if cached.exists() and cached.stat().st_size > 0:
        return FileResponse(cached, headers={"Cache-Control": "public, max-age=86400"})

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(url, headers={"User-Agent": UA, "Referer": "https://fgo.wiki/"})
            resp.raise_for_status()
            data = resp.content
    except Exception as e:
        raise HTTPException(502, f"图片获取失败: {e}") from e

    cached.write_bytes(data)
    media_type = resp.headers.get("content-type", "image/jpeg")
    return FileResponse(cached, media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})
