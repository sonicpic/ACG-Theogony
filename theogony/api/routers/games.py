"""每日猜角色（Wordle 式）：按日期确定性选题，无状态服务端。"""

from __future__ import annotations

import re
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from theogony.core.db import get_session
from theogony.core.graph import GraphService
from theogony.core.orm import Alias, Character
from theogony.core.search import hybrid_search

router = APIRouter(tags=["games"])


def _daily_target(today: date) -> Character:
    session = get_session()
    try:
        gs = GraphService.instance()
        pool_ids = [cid for cid, c in gs.snapshot.characters.items() if c.description and c.mythology]
        if not pool_ids:
            pool_ids = list(gs.snapshot.characters)
        seed_text = f"theogony-daily-{today.isoformat()}"
        target_id = gs.deterministic_id(seed_text, sorted(pool_ids))
        return session.get(Character, target_id)  # type: ignore[return-value]
    finally:
        session.close()


def _build_clues(c: Character) -> list[str]:
    clues = []
    if c.class_name:
        clues.append(f"职阶：{c.class_name}")
    if c.mythology:
        clues.append(f"神话体系：{c.mythology}")
    if c.gender:
        clues.append(f"性别：{c.gender}")
    if c.alignment:
        clues.append(f"阵营：{c.alignment}")
    if c.prototype and c.prototype != c.name:
        clues.append(f"原型名字里含有「{c.prototype[:1]}」字")
    if c.description:
        snippet = c.description[:50]
        clues.append(f"简介片段：{snippet}…")
    return clues


class DailyGuess(BaseModel):
    guess: str = Field(min_length=1)  # 角色名称或 ID


@router.get("/games/daily")
def daily_game():
    today = date.today()
    target = _daily_target(today)
    if target is None:
        raise HTTPException(500, "题库为空")
    clues = _build_clues(target)
    # 只发前 2 条，其余按猜错次数在前端逐条揭示（题目数据仍可被穷举，娱乐向够用）
    session = get_session()
    try:
        total = len(
            [c for c in GraphService.instance().snapshot.characters.values() if c.description]
        )
    finally:
        session.close()
    return {
        "date": today.isoformat(),
        "clues": clues[:2],
        "allClues": clues,
        "totalCandidates": total,
        "maxAttempts": 6,
    }


_BRACKET_TRANS = str.maketrans("（）〔〕［］", "()()[]")


def _normalize(s: str) -> str:
    """全角→半角括号 + 去空白 + 小写：让 美狄亚(Lily) 也能命中 美狄亚〔Lily〕。"""
    return s.strip().translate(_BRACKET_TRANS).lower()


def _match_character(guess: str) -> str:
    """精确匹配名/别名（全表查询，不依赖搜索排名——FTS 排名可能把本尊挤出前三）。"""
    session = get_session()
    try:
        c = session.query(Character).filter(Character.name == guess).first()
        if c:
            return c.id
        a = session.query(Alias).filter(Alias.alias == guess).first()
        if a:
            return a.character_id
        # 归一化兜底：全角/半角括号与大小写（美狄亚(Lily) ↔ 美狄亚〔Lily〕）
        ng = _normalize(guess)
        core = re.split(r"[（）〔〕\[\]()]", guess.strip(), maxsplit=1)[0].strip()
        if core:
            for c2 in session.query(Character).filter(Character.name.like(f"%{core}%")).limit(80):
                if _normalize(c2.name) == ng:
                    return c2.id
        return ""
    finally:
        session.close()


@router.post("/games/daily/guess")
def daily_guess(payload: DailyGuess):
    today = date.today()
    target = _daily_target(today)
    if target is None:
        raise HTTPException(500, "题库为空")
    guess = payload.guess.strip()
    # 支持名称/别名/ID；名称与别名走全表精确匹配，搜索仅作最后兜底
    if guess.lower().startswith("c") and guess[1:].isdigit():
        matched_id = guess
    else:
        matched_id = _match_character(guess)
        if not matched_id:
            ranked, _ = hybrid_search(guess, limit=10)
            # 搜索候选里做归一化等值比较（大小写/全半角括号）
            session = get_session()
            try:
                ng = _normalize(guess)
                for cid, _score in ranked:
                    c = session.get(Character, cid)
                    if c and (_normalize(c.name) == ng or any(_normalize(a.alias) == ng for a in c.aliases)):
                        matched_id = cid
                        break
            finally:
                session.close()
    correct = matched_id == target.id
    return {
        "correct": correct,
        "matchedId": matched_id,
        "answerId": target.id if correct or not matched_id else "",
        "answerName": target.name if correct else "",
        "hint": "" if correct else ("没匹配到这个角色，换个名字试试" if not matched_id else "不是 TA，再想想"),
    }


@router.post("/games/daily/reveal")
def daily_reveal():
    target = _daily_target(date.today())
    if target is None:
        raise HTTPException(500, "题库为空")
    return {"answerId": target.id, "answerName": target.name, "imageUrl": target.image_url}
