"""APOLLO のモード分岐と環境設定を集約するモジュール。

`APOLLO_MODE` 環境変数で hosted / private を切り替える。hosted は HF Spaces
向けの既存挙動（session_state のみ、永続化なし、Gemini API）。private は
オンプレ Docker 配布版（LM Studio 経由のローカル推論、disk cache、認証あり）。

このモジュールは v7 ソースを **編集せずに** import される設計。`apollo_bootstrap.init()`
を Home.py の最上部から呼び出すことで private モードのフックがアクティブになる。
"""

from __future__ import annotations

import os
from pathlib import Path

MODE: str = os.environ.get("APOLLO_MODE", "hosted").lower()
IS_PRIVATE: bool = MODE == "private"
IS_HOSTED: bool = not IS_PRIVATE

DATA_ROOT: Path = Path(os.environ.get("APOLLO_DATA_ROOT", "/var/lib/apollo"))
CACHE_DIR: Path = DATA_ROOT / "cache" / "embeddings"
UPLOADS_DIR: Path = DATA_ROOT / "uploads"
SESSION_DIR: Path = DATA_ROOT / "sessions"
INPUTS_DIR: Path = DATA_ROOT / "inputs"
# v7.0-private.2: プロジェクト階層のルート
PROJECTS_ROOT: Path = DATA_ROOT / "projects"
DEFAULT_PROJECT_ID: str = "default"

LM_STUDIO_BASE_URL: str = os.environ.get(
    "LM_STUDIO_BASE_URL", "http://host.docker.internal:1234/v1"
)
LM_STUDIO_API_KEY: str = os.environ.get("LM_STUDIO_API_KEY", "lm-studio")
# 長文生成用のタイムアウト (秒)。30B クラスのモデルで VOYAGER Phase 3 (Strategist)
# は max_tokens=65536 まで埋まりうるため、20-40 tok/s のスループットで 30-60 分級。
# OpenAI SDK の既定 600s や旧既定 1800s では 1 呼び出し分すら足りないことがある。
# `0` (または負値) を指定すると `None` に解釈され、SDK 側の timeout が無制限化される
# (Streaming 進捗 UI で目視監視する前提)。
LM_STUDIO_TIMEOUT: float = float(os.environ.get("LM_STUDIO_TIMEOUT", "7200"))


def resolve_lm_studio_timeout() -> float | None:
    """OpenAI SDK の `timeout=` にそのまま渡せる値を返す (0 以下は None)。"""
    return LM_STUDIO_TIMEOUT if LM_STUDIO_TIMEOUT and LM_STUDIO_TIMEOUT > 0 else None
# chat.completions.create の max_tokens 既定値。
# VOYAGER 戦略レポート (Phase 3 strategist) は 20K+ トークンに達することがあり、
# 上流 v7 の Gemini 呼び出しは max_output_tokens=65536 を使っている。同等に合わせる。
# 0 以下で送信省略 (モデル側の既定値に委ねる)。
LM_STUDIO_MAX_TOKENS: int = int(os.environ.get("LM_STUDIO_MAX_TOKENS", "65536"))

EMBEDDING_MODEL: str = os.environ.get(
    "APOLLO_EMBEDDING_MODEL", "text-embedding-qwen3-embedding-4b"
)
CHAT_MODEL: str = os.environ.get("APOLLO_CHAT_MODEL", "qwen/qwen3-30b-a3b-2507")

# Track M (VL 分業アーキテクチャ):
# VOYAGER を「Phase 0.5 = VL-8B が snapshot を構造化 JSON 記述 → Phase 1/2/3 は
# text-only reasoning」の 2 段パイプラインに切り替える。従来の multimodal 単段
# (VL が推論まで担当) では VL のモデル規模が推論品質を律速していたが、視覚と
# 推論を分業することで 80B 級の text モデルの推論力を活用できる。
USE_VISION_DESCRIPTOR: bool = os.environ.get(
    "APOLLO_USE_VISION_DESCRIPTOR", "true" if IS_PRIVATE else "false"
).lower() in ("1", "true", "yes", "on")

# 視覚記述 (Phase 0.5) 専用モデル。未指定なら lm_studio_models.current_vision_model()
# による自動検出にフォールバック (VL / Gemma-3/4 を id マッチで拾う)。
VISION_DESCRIPTOR_MODEL: str = os.environ.get(
    "APOLLO_VISION_DESCRIPTOR_MODEL", ""
)

# Reasoning (Phase 1/2/3) 専用モデル。未指定なら CHAT_MODEL と同じ扱い。
# 80B のような text-only 強モデルをここで指定し、chat_model を軽量モデル
# (VL 代替の fallback) に分離したい場合に使う。
REASONING_MODEL: str = os.environ.get("APOLLO_REASONING_MODEL", "")


def _embedder_label() -> str:
    """UI 表示用の埋め込みモデル略称。

    - hosted: "SBERT" 固定
    - private: サイドバー selectbox の現在値 (session_state override) を最優先し、
      なければ env 既定値 `APOLLO_EMBEDDING_MODEL` から派生
    """
    if not IS_PRIVATE:
        return "SBERT"

    # サイドバーの selectbox が選択されていればそれを使う。Streamlit コンテキスト外
    # でも失敗しないように遅延 import + try。
    model_id: str = EMBEDDING_MODEL
    try:
        from services import lm_studio_models

        model_id = lm_studio_models.current_embed_model() or EMBEDDING_MODEL
    except Exception:  # noqa: BLE001
        pass

    name = model_id.replace("text-embedding-", "")
    return name.split("/")[-1]


def __getattr__(name: str):  # noqa: N807 (PEP 562 module __getattr__)
    """`apollo_config.EMBEDDER_LABEL` を動的属性にする (PEP 562)。

    Home.py / pages/*.py から `apollo_config.EMBEDDER_LABEL` と参照される
    たびに `_embedder_label()` が呼ばれ、サイドバーの selectbox で切り替えた
    モデル名が即座に表示に反映される。

    V7 本体の記述 (`f"...{apollo_config.EMBEDDER_LABEL}..."`) は変えずに
    動的化するための仕組み。
    """
    if name == "EMBEDDER_LABEL":
        return _embedder_label()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

# 認証 (private モード専用) — env のみで完結。users.yml 等の外部ファイル不要。
# private モードでは埋め込みキャッシュ・アップロードファイルがディスクに残るため
# 本来認証は必須だが、APOLLO_ADMIN_PASSWORD 未設定でも起動はする (警告のみ)。
# 共有環境では必ず設定すること。
ADMIN_USER: str = os.environ.get("APOLLO_ADMIN_USER", "admin")
ADMIN_PASSWORD: str = os.environ.get("APOLLO_ADMIN_PASSWORD", "")
AUTH_ENABLED: bool = bool(ADMIN_PASSWORD)

# COOKIE_SECRET が未設定ならプロセス起動毎にランダム生成 (= 再起動でセッション失効)。
# 本番運用では .env で固定推奨。
def _resolve_cookie_secret() -> str:
    val = os.environ.get("APOLLO_COOKIE_SECRET", "").strip()
    if val:
        return val
    import secrets

    return secrets.token_hex(32)


COOKIE_SECRET: str = _resolve_cookie_secret()
COOKIE_NAME: str = os.environ.get("APOLLO_COOKIE_NAME", "apollo_auth")
COOKIE_EXPIRY_DAYS: int = int(os.environ.get("APOLLO_COOKIE_EXPIRY_DAYS", "7"))


def ensure_directories() -> None:
    """private モード時にマウント済みボリューム配下のディレクトリ構造を保証する。

    hosted モードでは何もしない（ホストに書き込まない原則を守る）。
    """
    if not IS_PRIVATE:
        return
    for d in [CACHE_DIR, UPLOADS_DIR, SESSION_DIR, INPUTS_DIR, PROJECTS_ROOT]:
        d.mkdir(parents=True, exist_ok=True)


def mode_label() -> str:
    """サイドバー表示用のモードラベル"""
    return "🔒 Private Edition" if IS_PRIVATE else "☁️ Hosted Edition"
