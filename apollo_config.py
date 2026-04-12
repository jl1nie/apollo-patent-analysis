"""APOLLO のモード分岐と環境設定を集約するモジュール。

`APOLLO_MODE` 環境変数で hosted / private を切り替える。hosted は HF Spaces
向けの既存挙動（session_state のみ、永続化なし、Gemini API）。private は
オンプレ Docker 配布版（LM Studio 経由のローカル推論、disk cache、認証あり）。
"""

from __future__ import annotations

import os
from pathlib import Path

MODE: str = os.environ.get("APOLLO_MODE", "hosted").lower()
IS_PRIVATE: bool = MODE == "private"
IS_HOSTED: bool = MODE == "hosted"

# 永続化ルート。private モードでのみ使用される。hosted モードでは参照しない
# （ディレクトリが存在しなくても ensure_directories がスキップする）
DATA_ROOT: Path = Path(os.environ.get("APOLLO_DATA_ROOT", "/var/lib/apollo"))
CACHE_DIR: Path = DATA_ROOT / "cache" / "embeddings"
UPLOADS_DIR: Path = DATA_ROOT / "uploads"
SESSION_DIR: Path = DATA_ROOT / "sessions"
JOBS_DIR: Path = DATA_ROOT / "jobs"
USERS_FILE: Path = DATA_ROOT / "users" / "users.yml"

# LM Studio (OpenAI 互換) エンドポイント。private モード専用。
# Docker compose では host.docker.internal、ローカル直接起動では localhost 相当を想定。
LM_STUDIO_BASE_URL: str = os.environ.get(
    "LM_STUDIO_BASE_URL", "http://host.docker.internal:1234/v1"
)
LM_STUDIO_API_KEY: str = os.environ.get("LM_STUDIO_API_KEY", "dummy")

EMBEDDING_MODEL: str = os.environ.get(
    "APOLLO_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-4b"
)
CHAT_MODEL: str = os.environ.get("APOLLO_CHAT_MODEL", "google/gemma-4-26b-a4b")


def ensure_directories() -> None:
    """private モード時にマウント済みボリューム配下のディレクトリ構造を保証する。

    hosted モードでは何もしない（ホストに書き込まない原則を守る）。
    """
    if not IS_PRIVATE:
        return
    for d in [CACHE_DIR, UPLOADS_DIR, SESSION_DIR, JOBS_DIR, USERS_FILE.parent]:
        d.mkdir(parents=True, exist_ok=True)


def mode_label() -> str:
    """サイドバー表示用のモードラベル"""
    return "🔒 Private Edition" if IS_PRIVATE else "☁️ Hosted Edition"
