"""Mooncell (fgo.wiki) 英灵爬虫 — 异步版。

修复旧版两个问题：
1. 详情页抓取只限前 50 个 → 现在 --max-details 默认全量（并发 6 + 限速）
2. region 解析只认 wikitable → 兼容 infobox 与更多表头（出典/出身/地域）

用法：
    uv run python -m theogony.pipelines.scrape_mooncell [--max-details N] [--skip-details]
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import random
import re

import httpx
from bs4 import BeautifulSoup

from theogony.core.config import get_settings

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BASE_URL = "https://fgo.wiki"
INDEX_URL = f"{BASE_URL}/w/英灵图鉴"
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3


def _headers() -> dict:
    return {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": BASE_URL,
    }


def guess_prototype(name: str) -> str:
    cleaned = re.sub(r"[（(][^）)]*[）)]", "", name)
    cleaned = re.sub(
        r"\s*·\s*(Saber|Archer|Lancer|Rider|Caster|Assassin|Berserker|Ruler|Avenger|"
        r"MoonCancer|Foreigner|Pretender|Alter\s*Ego|Shielder|Beast)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    return cleaned.strip()


async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(url, headers=_headers(), timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            print(f"  [!] 第 {attempt} 次请求失败: {url} -> {e}")
            await asyncio.sleep(1.5 * attempt)
    return None


def scrape_servant_table(soup: BeautifulSoup) -> list[dict]:
    """从索引页表格提取（沿用旧版逻辑，已验证可用）。"""
    characters: list[dict] = []
    seen_ids: set[str] = set()

    def _norm(text: str) -> str:
        return re.sub(r"\s+", "", text).strip()

    tables = soup.select("table.wikitable, table.sortable, table")
    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_row = next((r for r in rows if r.find_all("th")), None)
        headers = [_norm(th.get_text(strip=True)) for th in header_row.find_all("th")] if header_row else []
        mapping: dict[str, int] = {}
        patterns = {
            "id": r"(编号|No\.?|ID|序号)",
            "name": r"(真名|名称|英灵|从者|角色)",
            "class": r"(职阶|Class)",
            "region": r"(地域|出处|出典|原典|神话)",
        }
        for i, h in enumerate(headers):
            for key, pat in patterns.items():
                if key not in mapping and re.search(pat, h, re.IGNORECASE):
                    mapping[key] = i

        for row in rows[1:]:
            cells = row.find_all("td")
            if len(cells) < 2:
                continue
            if "id" in mapping and mapping["id"] < len(cells):
                raw_id = cells[mapping["id"]].get_text(strip=True)
            else:
                raw_id = cells[0].get_text(strip=True)
            id_match = re.search(r"(\d+)", raw_id)
            if not id_match:
                continue
            servant_id = id_match.group(1)
            if servant_id in seen_ids:
                continue
            seen_ids.add(servant_id)

            name, detail_path = "", ""
            for cell in cells:
                link = cell.find("a")
                if link and link.get_text(strip=True):
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        detail_path = href
                    break
            if not name and len(cells) > 1:
                name = cells[1].get_text(strip=True)
            if not name:
                continue

            servant_class = ""
            if "class" in mapping and mapping["class"] < len(cells):
                servant_class = cells[mapping["class"]].get_text(strip=True)
            region = ""
            if "region" in mapping and mapping["region"] < len(cells):
                region = cells[mapping["region"]].get_text(strip=True)

            image_url = ""
            for cell in cells:
                img = cell.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    image_url = src if src.startswith("http") else BASE_URL + src
                    break

            characters.append(
                {
                    "id": servant_id,
                    "name": name,
                    "class": servant_class,
                    "prototype": guess_prototype(name),
                    "detail_url": f"{BASE_URL}{detail_path}" if detail_path else "",
                    "region": region,
                    "description": "",
                    "image_url": image_url,
                }
            )
    return characters


def parse_embedded_csv(html: str) -> list[dict]:
    def _extract_js_string(key: str) -> str:
        pattern = re.compile(rf'{key}\s*=\s*"(.*?)";', re.DOTALL)
        match = pattern.search(html)
        if not match:
            return ""
        raw = match.group(1)
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")

    raw_str = _extract_js_string("raw_str")
    if not raw_str:
        return []
    override_map: dict[str, dict] = {}
    override_str = _extract_js_string("override_data")
    if override_str:
        current_id = None
        for line in override_str.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key, val = key.strip(), val.strip()
            if key == "id":
                current_id = val
                override_map.setdefault(current_id, {})
            elif current_id:
                override_map[current_id][key] = val

    characters = []
    for row in csv.DictReader(io.StringIO(raw_str)):
        servant_id = (row.get("id") or "").strip()
        if not servant_id:
            continue
        extra = override_map.get(servant_id, {})
        name = extra.get("name_cn") or extra.get("name_en") or extra.get("name_link") or servant_id
        avatar = row.get("avatar", "")
        characters.append(
            {
                "id": servant_id,
                "name": name,
                "class": (row.get("class_link") or "").strip(),
                "prototype": guess_prototype(name),
                "detail_url": f"{BASE_URL}/w/{extra['name_link']}" if extra.get("name_link") else "",
                "region": "",
                "description": "",
                "image_url": avatar if avatar.startswith("http") else ("https:" + avatar if avatar else ""),
            }
        )
    return characters


def parse_detail(html: str) -> dict:
    """详情页解析：region（地域/出典/出处/出身/原典）+ 简介。"""
    soup = BeautifulSoup(html, "lxml")
    info: dict = {}
    region_keys = ("地域", "出典", "出处", "出身", "原典", "神话")
    for table in soup.select("table.wikitable, table.infobox, table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue
            header = cells[0].get_text(strip=True)
            value = cells[1].get_text(strip=True)
            if any(k in header for k in region_keys) and value:
                info.setdefault("region", value)
            if "属性" in header and "阵营" not in header and value:
                info.setdefault("attribute", value)
    first_p = soup.select_one("#mw-content-text > .mw-parser-output > p")
    if first_p:
        desc = first_p.get_text(strip=True)
        if len(desc) > 10:
            info["description"] = desc[:300]
    return info


async def main() -> None:
    parser = argparse.ArgumentParser(description="Mooncell 英灵爬虫（异步）")
    parser.add_argument("--max-details", type=int, default=0, help="详情页抓取上限（0=全量）")
    parser.add_argument("--skip-details", action="store_true")
    parser.add_argument("--concurrency", type=int, default=6)
    args = parser.parse_args()

    settings = get_settings()
    out_file = settings.data_dir / "raw" / "raw_characters.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Theogony · Mooncell 异步爬虫")
    print("=" * 60)

    async with httpx.AsyncClient(follow_redirects=True) as client:
        print("[1/3] 获取英灵图鉴页 ...")
        characters: list[dict] = []
        html = None
        for url in [INDEX_URL, f"{INDEX_URL}?action=render", f"{INDEX_URL}?printable=yes"]:
            html = await fetch_page(client, url)
            if html:
                characters = scrape_servant_table(BeautifulSoup(html, "lxml"))
                if characters:
                    print(f"  ✓ 表格解析 {len(characters)} 条")
                    break
        if not characters and html:
            characters = parse_embedded_csv(html)
            print(f"  ✓ CSV 内嵌解析 {len(characters)} 条")
        if not characters:
            print("[✗] 未提取到数据（页面结构可能变更），保留现有数据不变。")
            return

        if not args.skip_details:
            limit = args.max_details or len(characters)
            targets = [c for c in characters if c.get("detail_url")][:limit]
            print(f"[2/3] 抓取详情页（{len(targets)} 个，并发 {args.concurrency}）...")
            sem = asyncio.Semaphore(args.concurrency)
            done = 0

            async def worker(c: dict) -> None:
                nonlocal done
                async with sem:
                    await asyncio.sleep(random.uniform(0.2, 0.6))  # 限速礼貌抓取
                    page = await fetch_page(client, c["detail_url"])
                    if page:
                        info = parse_detail(page)
                        if info.get("region"):
                            c["region"] = info["region"]
                        if info.get("description"):
                            c["description"] = info["description"]
                        if info.get("attribute"):
                            c.setdefault("metadata", {})["attribute"] = info["attribute"]
                done += 1
                if done % 50 == 0:
                    print(f"  … {done}/{len(targets)}")

            await asyncio.gather(*(worker(c) for c in targets))
            got_region = sum(1 for c in characters if c.get("region"))
            print(f"  ✓ region 覆盖 {got_region}/{len(characters)}")
        else:
            print("[2/3] 跳过详情页")

    # 与现有数据合并（新爬到的覆盖，保留旧的非空字段）
    merged: dict[str, dict] = {}
    if out_file.exists():
        for old in json.loads(out_file.read_text(encoding="utf-8")):
            merged[old["id"]] = old
    for c in characters:
        prev = merged.get(c["id"], {})
        for key in ("region", "description", "detail_url", "image_url"):
            if not c.get(key) and prev.get(key):
                c[key] = prev[key]
        merged[c["id"]] = {**prev, **{k: v for k, v in c.items() if v}}
    result = sorted(merged.values(), key=lambda x: int(x["id"]))

    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3/3] 已保存 {len(result)} 条 → {out_file}")
    print("    下一步: npm run db:build")


if __name__ == "__main__":
    asyncio.run(main())
