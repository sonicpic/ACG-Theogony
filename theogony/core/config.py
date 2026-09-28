"""全局配置（pydantic-settings，读取仓库根目录 .env）。"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 数据
    data_dir: Path = REPO_ROOT / "data"
    db_path: Path = REPO_ROOT / "data" / "theogony.db"

    # DeepSeek
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # gpt-luna-5.6（联网检索模型）
    luna_api_key: str = ""
    luna_api_base: str = ""
    luna_model: str = "gpt-luna-5.6"
    luna_extra_body: str = "{}"  # JSON 字符串

    # 嵌入向量（语义检索，可选）
    embeddings_api_key: str = ""
    embeddings_api_base: str = ""
    embeddings_model: str = ""

    # 服务
    review_token: str = ""
    cors_origins: str = "http://localhost:3000"

    @property
    def luna_extra(self) -> dict:
        try:
            value = json.loads(self.luna_extra_body or "{}")
            return value if isinstance(value, dict) else {}
        except json.JSONDecodeError:
            return {}

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "cache").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "exports").mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
