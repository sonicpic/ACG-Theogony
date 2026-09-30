"""名称归一化（跨数据源实体匹配的共用底座）。

层次：NFKC 全半角 → 去分隔符/括号 → 小写 → 音译变体折叠 → 简繁折叠（OpenCC t2s）。
"""

from __future__ import annotations

import unicodedata

from opencc import OpenCC

_t2s = OpenCC("t2s")

# 中文音译常见变体折叠（同一人名的不同译法：恺撒/凯撒、阿蒂拉/阿提拉）
_TRANSLIT_FOLD = str.maketrans({
    "恺": "凯", "蒂": "提", "佛": "弗", "茨": "兹", "莎": "沙",
    "娅": "亚", "锹": "乔",
    "ō": "o", "ū": "u", "ā": "a", "ē": "e", "ī": "i",
    "ö": "o", "ü": "u", "é": "e", "á": "a",
})

_STRIP_CHARS = " \u3000·・.。'\"''\"·-‐–—_/／（）()〔〕[]"


def normalize_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    for ch in _STRIP_CHARS:
        s = s.replace(ch, "")
    return _t2s.convert(s.lower().translate(_TRANSLIT_FOLD))
