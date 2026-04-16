"""LM Studio `/v1/models` のモデル一覧取得とセッション選択解決。

サイドバーの埋め込み / 推論モデル selectbox から使う。ユーザが毎回モデル名を
タイプしなくて済むよう、`/v1/models` エンドポイントを叩いて実際にロード中の
モデルだけを選択肢にする。

- `fetch_models()` — LM Studio に接続してモデル一覧を取得 (10 秒メモリキャッシュ)
- `split_embed_chat()` — モデル ID から埋め込み / チャットを推定して振り分け
- `current_embed_model()` / `current_chat_model()` — session_state override →
  env 既定値 → LM Studio 先頭モデル の順で解決する統一エントリ

private モード以外でも呼び出しは許容する (VOYAGER 側の通信切替で使う可能性が
あるため)。ただし実通信は private モード時のみ行い、hosted では即 env 値を返す。
"""

from __future__ import annotations

import time
from typing import Tuple

import apollo_config

# ------------------------------------------------------------------
# 10 秒程度の単純なメモリキャッシュ
# Streamlit は rerun 毎に import 済みモジュールは維持されるので、
# モジュールレベル変数でキャッシュするだけで十分。
# ------------------------------------------------------------------
_CACHE_TTL = 10.0  # seconds
_cache_at: float = 0.0
_cache_payload: list[dict] = []
_cache_error: str | None = None


def _fetch_from_api(timeout: float) -> list[dict]:
    """LM Studio の /v1/models を叩いて生のリストを返す。

    返り値は `[{"id": ..., "object": "model", ...}, ...]`。
    例外は呼び出し元に伝搬させる。
    """
    from openai import OpenAI  # 遅延 import

    client = OpenAI(
        api_key=apollo_config.LM_STUDIO_API_KEY,
        base_url=apollo_config.LM_STUDIO_BASE_URL,
        timeout=timeout,
    )
    resp = client.models.list()
    out: list[dict] = []
    for m in resp.data:
        out.append({"id": getattr(m, "id", ""), "object": getattr(m, "object", "model")})
    return out


def fetch_models(timeout: float = 3.0, force_refresh: bool = False) -> list[dict]:
    """LM Studio からモデル一覧を取得する。失敗時は env 既定値 1〜2 件を返す。

    - 10 秒の簡易メモリキャッシュを挟むため、Streamlit rerun で叩きすぎない
    - private モード以外では env 既定値だけを返す (実通信なし)
    - LM Studio が落ちている場合も env 既定値フォールバック (UI は動く)
    """
    global _cache_at, _cache_payload, _cache_error

    if not apollo_config.IS_PRIVATE:
        return _fallback_models()

    now = time.time()
    if not force_refresh and _cache_payload and (now - _cache_at) < _CACHE_TTL:
        return _cache_payload

    try:
        payload = _fetch_from_api(timeout=timeout)
        if not payload:
            payload = _fallback_models()
            _cache_error = "LM Studio returned empty model list"
        else:
            _cache_error = None
        _cache_payload = payload
        _cache_at = now
        return payload
    except Exception as e:  # noqa: BLE001
        _cache_error = f"{type(e).__name__}: {e}"
        _cache_payload = _fallback_models()
        _cache_at = now
        return _cache_payload


def last_fetch_error() -> str | None:
    """直近の fetch 時エラー文字列 (UI の注意書き用)。"""
    return _cache_error


def _fallback_models() -> list[dict]:
    """env 既定値を 1〜2 件のモデルリストとして返す。"""
    out: list[dict] = []
    if apollo_config.EMBEDDING_MODEL:
        out.append({"id": apollo_config.EMBEDDING_MODEL, "object": "model"})
    if apollo_config.CHAT_MODEL and apollo_config.CHAT_MODEL != apollo_config.EMBEDDING_MODEL:
        out.append({"id": apollo_config.CHAT_MODEL, "object": "model"})
    return out


# ------------------------------------------------------------------
# 分類ロジック
# ------------------------------------------------------------------

_EMBED_HINTS = ("embed", "embedding")


def _is_embedding_model(model_id: str) -> bool:
    low = model_id.lower()
    return any(hint in low for hint in _EMBED_HINTS)


def split_embed_chat(models: list[dict]) -> Tuple[list[str], list[str]]:
    """model id リストを embedding 系 / chat 系に振り分ける。

    LM Studio のモデル ID には通常 "embed" / "embedding" が含まれる
    (例: `text-embedding-qwen3-embedding-4b`)。それ以外は chat 扱い。
    """
    embed_ids: list[str] = []
    chat_ids: list[str] = []
    for m in models:
        mid = m.get("id") or ""
        if not mid:
            continue
        if _is_embedding_model(mid):
            embed_ids.append(mid)
        else:
            chat_ids.append(mid)
    return embed_ids, chat_ids


# ------------------------------------------------------------------
# 現在選択中のモデル解決
# ------------------------------------------------------------------


def _session_override(key: str) -> str | None:
    """st.session_state からオーバーライド値を読む。Streamlit 外では None。"""
    try:
        import streamlit as st  # 遅延 import

        val = st.session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val
    except Exception:  # noqa: BLE001
        pass
    return None


def current_embed_model() -> str:
    """埋め込みモデル ID を解決する。

    優先順位: session_state["apollo_embed_model_select"]
              → apollo_config.EMBEDDING_MODEL (env)
              → LM Studio で最初に見つかった embedding 系モデル
    """
    override = _session_override("apollo_embed_model_select")
    if override:
        return override
    if apollo_config.EMBEDDING_MODEL:
        return apollo_config.EMBEDDING_MODEL
    # 最終手段: LM Studio から取る
    embed_ids, _ = split_embed_chat(fetch_models())
    if embed_ids:
        return embed_ids[0]
    return "text-embedding-qwen3-embedding-4b"


def current_chat_model() -> str:
    """推論モデル ID を解決する。VOYAGER レポート生成で使う。"""
    override = _session_override("apollo_chat_model_select")
    if override:
        return override
    if apollo_config.CHAT_MODEL:
        return apollo_config.CHAT_MODEL
    _, chat_ids = split_embed_chat(fetch_models())
    if chat_ids:
        return chat_ids[0]
    return "qwen/qwen3-30b-a3b-2507"
