"""
Mooncell (FGO 中文 Wiki) 英灵数据爬虫

目标页面: https://fgo.wiki/w/英灵图鉴
输出文件: backend/data/raw_characters.json

使用方法:
    python -m backend.scraper_mooncell          # 从项目根目录运行
    python scraper_mooncell.py                  # 从 backend/ 目录运行
"""

from __future__ import annotations

import json
import os
import random
import re
import time
import csv
import io
import argparse
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup, Tag
from fake_useragent import UserAgent

# ──────────────────────────────────────────────
# 常量
# ──────────────────────────────────────────────

BASE_URL = "https://fgo.wiki"
INDEX_URL = f"{BASE_URL}/w/英灵图鉴"
INDEX_URLS = [
    INDEX_URL,
    f"{INDEX_URL}?action=render",
    f"{INDEX_URL}?printable=yes",
    f"{BASE_URL}/w/%E8%8B%B1%E7%81%B5%E5%9B%BE%E9%89%B4",
    f"{BASE_URL}/w/%E8%8B%B1%E7%81%B5%E5%9B%BE%E9%89%B4?printable=yes",
]
OUTPUT_DIR = Path(__file__).resolve().parent / "data"
OUTPUT_FILE = OUTPUT_DIR / "raw_characters.json"
DEBUG_HTML_FILE = OUTPUT_DIR / "index_debug.html"

# 请求配置
REQUEST_TIMEOUT = 30  # 秒
MIN_DELAY = 1.5       # 最短请求间隔（秒）
MAX_DELAY = 3.5       # 最长请求间隔（秒）
MAX_RETRIES = 3       # 单页最大重试次数

ua = UserAgent(fallback="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")


# ──────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────

def _random_headers() -> dict:
    """每次请求使用随机 User-Agent。"""
    return {
        "User-Agent": ua.random,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Referer": BASE_URL,
    }


def _polite_sleep() -> None:
    """请求间随机等待，防止触发反爬。"""
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def fetch_page(url: str) -> Optional[BeautifulSoup]:
    """
    获取页面并返回解析后的 BeautifulSoup 对象。
    自动重试 MAX_RETRIES 次。
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=_random_headers(),
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            return BeautifulSoup(resp.text, "lxml")
        except requests.RequestException as e:
            print(f"  [!] 第 {attempt} 次请求失败: {url} -> {e}")
            if attempt < MAX_RETRIES:
                _polite_sleep()
    return None


def guess_prototype(name: str) -> str:
    """
    从角色名推断神话原型核心名。

    规则:
      - 去除括号及括号内的内容（全角/半角）
      - 去除职阶后缀（如 "·Saber"）
      - 保留剩余文字作为原型名
    示例:
      "阿尔托莉雅·潘德拉贡(Lancer)" -> "阿尔托莉雅·潘德拉贡"
      "吉尔伽美什（Caster）"         -> "吉尔伽美什"
    """
    # 去除全角/半角括号及内容
    cleaned = re.sub(r"[（(][^）)]*[）)]", "", name)
    # 去除尾部的 ·Class 后缀（常见的日服名格式）
    cleaned = re.sub(r"\s*·\s*(Saber|Archer|Lancer|Rider|Caster|Assassin|Berserker|Ruler|Avenger|"
                     r"MoonCancer|Foreigner|Pretender|Alter\s*Ego|Shielder|Beast)\s*$",
                     "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


# ──────────────────────────────────────────────
# 详情页抓取
# ──────────────────────────────────────────────

def scrape_detail_page(detail_url: str) -> dict:
    """
    进入英灵详情页，提取补充信息（地域/出处等）。
    返回一个字典，可能包含 region、description 等字段。
    """
    info: dict = {}
    _polite_sleep()
    soup = fetch_page(detail_url)
    if soup is None:
        return info

    # Mooncell 详情页通常用 wikitable 展示基础信息
    # 查找包含"地域"或"出处"的行
    for table in soup.select("table.wikitable"):
        for row in table.find_all("tr"):
            cells = row.find_all(["th", "td"])
            if len(cells) >= 2:
                header_text = cells[0].get_text(strip=True)
                value_text = cells[1].get_text(strip=True)
                if "地域" in header_text or "出典" in header_text or "出处" in header_text:
                    info["region"] = value_text
                if "属性" in header_text:
                    info["attribute"] = value_text

    # 尝试提取简介段落（首个 <p> 标签）
    first_p = soup.select_one("#mw-content-text > .mw-parser-output > p")
    if first_p:
        desc = first_p.get_text(strip=True)
        if len(desc) > 10:  # 过滤太短的无效段落
            info["description"] = desc[:200]  # 截断到 200 字符

    return info


# ──────────────────────────────────────────────
# 主抓取流程
# ──────────────────────────────────────────────

def scrape_servant_table(soup: BeautifulSoup) -> list[dict]:
    """
    从英灵图鉴页面的表格中提取英灵列表。
    Mooncell 的英灵图鉴页面包含按职阶或按编号排列的大表格。
    """
    characters: list[dict] = []
    seen_ids: set[str] = set()

    def _norm(text: str) -> str:
        return re.sub(r"\s+", "", text).strip()

    def _extract_headers(table: Tag) -> list[str]:
        header_row = None
        for row in table.find_all("tr"):
            if row.find_all("th"):
                header_row = row
                break
        if not header_row:
            return []
        return [_norm(th.get_text(strip=True)) for th in header_row.find_all("th")]

    def _map_headers(headers: list[str]) -> dict[str, int]:
        patterns = {
            "id": r"(编号|No\.?|ID|序号)",
            "name": r"(真名|名称|英灵|从者|角色)",
            "class": r"(职阶|Class)",
            "region": r"(地域|出处|出典|原典|神话)",
        }
        mapping: dict[str, int] = {}
        for i, h in enumerate(headers):
            for key, pat in patterns.items():
                if key not in mapping and re.search(pat, h, re.IGNORECASE):
                    mapping[key] = i
        return mapping

    def _guess_class_from_cells(cells: list[Tag]) -> str:
        class_keywords = {
            "Saber", "Archer", "Lancer", "Rider", "Caster",
            "Assassin", "Berserker", "Ruler", "Avenger",
            "MoonCancer", "Foreigner", "Pretender", "Alter Ego",
            "Shielder", "Beast",
        }
        for cell in cells:
            text = cell.get_text(strip=True)
            for kw in class_keywords:
                if kw.lower() in text.lower():
                    return kw
            img = cell.find("img")
            if img:
                alt = (img.get("alt", "") + img.get("title", "")).strip()
                for kw in class_keywords:
                    if kw.lower() in alt.lower():
                        return kw
        return ""

    # 查找所有候选表格
    tables = soup.select("table.wikitable, table.sortable, table")
    tables = [t for t in tables if t.find_all("tr")]

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        headers = _extract_headers(table)
        header_map = _map_headers(headers) if headers else {}

        for row in rows[1:]:  # 跳过表头
            cells = row.find_all("td")
            if len(cells) < 2:
                continue

            # 编号
            servant_id = ""
            if "id" in header_map and header_map["id"] < len(cells):
                raw_id = cells[header_map["id"]].get_text(strip=True)
            else:
                raw_id = cells[0].get_text(strip=True)
            id_match = re.search(r"(\d+)", raw_id)
            if id_match:
                servant_id = id_match.group(1)
            if not servant_id:
                continue

            if servant_id in seen_ids:
                continue
            seen_ids.add(servant_id)

            # 名称 + 详情链接
            name = ""
            detail_path = ""
            name_cell_index = header_map.get("name", 1)
            name_cells = [cells[name_cell_index]] if name_cell_index < len(cells) else cells
            for cell in name_cells:
                link: Optional[Tag] = cell.find("a")
                if link:
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        detail_path = href
                    break
            if not name:
                # 回退：找任意链接文本
                link = row.find("a")
                if link:
                    name = link.get_text(strip=True)
                    href = link.get("href", "")
                    if href and not href.startswith("http"):
                        detail_path = href
            if not name:
                # 最后回退：第二列文本
                if len(cells) > 1:
                    name = cells[1].get_text(strip=True)
            if not name:
                continue

            # 职阶
            servant_class = ""
            if "class" in header_map and header_map["class"] < len(cells):
                servant_class = cells[header_map["class"]].get_text(strip=True)
            if not servant_class:
                servant_class = _guess_class_from_cells(cells)

            # 地域/出处（可能在表格中）
            region = ""
            if "region" in header_map and header_map["region"] < len(cells):
                region = cells[header_map["region"]].get_text(strip=True)

            # 构建记录
            prototype = guess_prototype(name)
            character = {
                "id": servant_id,
                "name": name,
                "class": servant_class,
                "prototype": prototype,
                "detail_url": f"{BASE_URL}{detail_path}" if detail_path else "",
                "region": region,
                "description": "",
                "image_url": "",
            }

            # 尝试提取图片 URL
            for cell in cells:
                img = cell.find("img")
                if img and img.get("src"):
                    src = img["src"]
                    if not src.startswith("http"):
                        src = BASE_URL + src
                    character["image_url"] = src
                    break

            characters.append(character)

    return characters


def parse_embedded_csv(html: str) -> list[dict]:
    """
    Mooncell 的英灵图鉴页在脚本中内嵌 CSV 数据与 override_data。
    尝试从 HTML 中提取并解析这些内容。
    """
    def _extract_js_string(key: str) -> str:
        pattern = re.compile(rf"{key}\s*=\s*\"(.*?)\";", re.DOTALL)
        match = pattern.search(html)
        if not match:
            return ""
        raw = match.group(1)
        # 处理常见转义
        raw = raw.replace("\\n", "\n").replace("\\\"", "\"").replace("\\\\", "\\")
        return raw

    raw_str = _extract_js_string("raw_str")
    if not raw_str:
        return []

    override_str = _extract_js_string("override_data")

    # 解析 override_data: id -> name_cn/name_link
    override_map: dict[str, dict] = {}
    if override_str:
        current_id: Optional[str] = None
        for line in override_str.splitlines():
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key == "id":
                current_id = val
                override_map.setdefault(current_id, {})
                continue
            if current_id is None:
                continue
            override_map[current_id][key] = val

    # 解析 CSV
    f = io.StringIO(raw_str)
    reader = csv.DictReader(f)
    characters: list[dict] = []
    for row in reader:
        servant_id = row.get("id", "").strip()
        if not servant_id:
            continue

        extra = override_map.get(servant_id, {})
        name = extra.get("name_cn") or extra.get("name_en") or extra.get("name_link") or servant_id
        name_link = extra.get("name_link", "")
        avatar = row.get("avatar", "")

        image_url = ""
        if avatar:
            image_url = avatar if avatar.startswith("http") else "https:" + avatar

        detail_url = ""
        if name_link:
            detail_url = f"{BASE_URL}/w/{name_link}"

        character = {
            "id": servant_id,
            "name": name,
            "class": row.get("class_link", "").strip(),
            "prototype": guess_prototype(name),
            "detail_url": detail_url,
            "region": "",
            "description": "",
            "image_url": image_url,
        }
        characters.append(character)

    return characters


def enrich_with_details(characters: list[dict], max_details: int = 50) -> None:
    """
    为前 max_details 个角色补充详情页信息。
    数量限制是为了控制请求量，避免给 wiki 带来过大压力。
    """
    for i, char in enumerate(characters[:max_details]):
        if not char.get("detail_url"):
            continue
        print(f"  [{i + 1}/{min(len(characters), max_details)}] "
              f"抓取详情: {char['name']} ...")
        details = scrape_detail_page(char["detail_url"])
        if details.get("region"):
            char["region"] = details["region"]
        if details.get("description"):
            char["description"] = details["description"]
        if details.get("attribute"):
            char.setdefault("metadata", {})["attribute"] = details["attribute"]


# ──────────────────────────────────────────────
# 入口
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Mooncell 英灵图鉴爬虫")
    parser.add_argument("--max-details", type=int, default=50, help="详情页抓取数量上限")
    parser.add_argument("--skip-details", action="store_true", help="跳过详情页抓取")
    args = parser.parse_args()

    print("=" * 60)
    print("Theogony-Graph · Mooncell 英灵爬虫")
    print("=" * 60)

    # 1. 抓取索引页
    print("\n[1/3] 正在获取英灵图鉴页面...")
    soup = None
    last_html = ""
    for url in INDEX_URLS:
        print(f"  → 尝试: {url}")
        soup = fetch_page(url)
        if soup is None:
            continue
        last_html = str(soup)
        # 先试解析，能提取到就使用该页面
        characters = scrape_servant_table(soup)
        if characters:
            print(f"  ✓ 当前入口可用，提取 {len(characters)} 条")
            break
    else:
        characters = []

    if soup is None:
        print("[✗] 无法访问英灵图鉴页面，请检查网络或 URL。")
        return

    # 2. 解析表格
    print("[2/3] 正在解析英灵表格 ...")
    print(f"  → 共提取到 {len(characters)} 个英灵")

    if not characters and last_html:
        print("  → 尝试解析页面内嵌 CSV 数据...")
        characters = parse_embedded_csv(last_html)
        print(f"  → CSV 解析得到 {len(characters)} 个英灵")

    if not characters:
        print("[✗] 未提取到任何数据，页面结构可能已变更。")
        print("    请手动检查页面并更新解析逻辑。")
        if last_html:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            DEBUG_HTML_FILE.write_text(last_html, encoding="utf-8")
            print(f"    已保存调试HTML: {DEBUG_HTML_FILE}")
        return

    # 3. 补充详情（限制请求数）
    if args.skip_details or args.max_details <= 0:
        print("[3/3] 跳过详情页抓取")
    else:
        print(f"[3/3] 正在补充详情页信息（限前{args.max_details}个）...")
        enrich_with_details(characters, max_details=args.max_details)

    # 4. 保存
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(characters, f, ensure_ascii=False, indent=2)

    print(f"\n[✓] 数据已保存到: {OUTPUT_FILE}")
    print(f"    共 {len(characters)} 条记录")


if __name__ == "__main__":
    main()
