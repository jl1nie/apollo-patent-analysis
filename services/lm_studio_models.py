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
# モデル一覧キャッシュ
# Streamlit は rerun 毎に import 済みモジュールは維持されるので、
# モジュールレベル変数でキャッシュするだけで十分。
#
# 成功時は 10 秒、失敗時 (LM Studio 不達) は 60 秒キャッシュする。
# 失敗時に毎 rerun ごとに 3 秒待つと UX が非常に悪いため。
# ------------------------------------------------------------------
_CACHE_TTL_OK = 10.0      # seconds (成功時)
_CACHE_TTL_ERR = 60.0     # seconds (失敗時)
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


def fetch_models(timeout: float = 1.5, force_refresh: bool = False) -> list[dict]:
    """LM Studio からモデル一覧を取得する。失敗時は env 既定値 1〜2 件を返す。

    - 成功時 10 秒 / 失敗時 60 秒のメモリキャッシュ (LM Studio 不達で毎 rerun
      ごとに秒単位の遅延が入るのを防ぐ)
    - private モード以外では env 既定値だけを返す (実通信なし)
    - LM Studio が落ちている場合も env 既定値フォールバック (UI は動く)
    """
    global _cache_at, _cache_payload, _cache_error

    if not apollo_config.IS_PRIVATE:
        return _fallback_models()

    now = time.time()
    # 成功時と失敗時で TTL を切り替える
    ttl = _CACHE_TTL_ERR if _cache_error else _CACHE_TTL_OK
    if not force_refresh and _cache_payload and (now - _cache_at) < ttl:
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


def _project_config_model(field: str) -> str | None:
    """アクティブプロジェクトの config.json から model を取得する。

    private モード以外 or projects import 失敗時は None を返す。
    """
    if not apollo_config.IS_PRIVATE:
        return None
    try:
        from services import projects

        cfg = projects.get_config()
        val = cfg.get(field) if isinstance(cfg, dict) else None
        if isinstance(val, str) and val.strip():
            return val
    except Exception:  # noqa: BLE001
        pass
    return None


def current_embed_model() -> str:
    """埋め込みモデル ID を解決する (v7.0-private.2: プロジェクト固定モデル優先)。

    優先順位:
      1. アクティブプロジェクトの `config.embedding_model` (最優先、v7.0-private.2)
      2. session_state["apollo_embed_model_select"]
      3. apollo_config.EMBEDDING_MODEL (env)
      4. LM Studio で最初に見つかった embedding 系モデル

    v7.0-private.2 の意図: プロジェクトは「固定ベクトル空間」であるため、session_state
    オーバーライドより config が強い。UI 側で session_state を書き換えようとしても
    現在のプロジェクトには影響しない (プロジェクト作成時に固定する)。
    """
    pmodel = _project_config_model("embedding_model")
    if pmodel:
        return pmodel
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
    """推論モデル ID を解決する。VOYAGER レポート生成で使う。

    推論モデルはプロジェクト単位で「既定値」を持つが、サイドバーの selectbox
    で変更可能 (レポート生成のたびに別モデルを試したいのは自然な要求)。
    したがって session_state override はプロジェクト config より**強い**
    (埋め込みモデルとは逆の優先順位)。

    優先順位:
      1. session_state["apollo_chat_model_select"]
      2. アクティブプロジェクトの config.chat_model
      3. apollo_config.CHAT_MODEL (env)
      4. LM Studio で最初に見つかった chat 系モデル
    """
    override = _session_override("apollo_chat_model_select")
    if override:
        return override
    pmodel = _project_config_model("chat_model")
    if pmodel:
        return pmodel
    if apollo_config.CHAT_MODEL:
        return apollo_config.CHAT_MODEL
    _, chat_ids = split_embed_chat(fetch_models())
    if chat_ids:
        return chat_ids[0]
    return "qwen/qwen3-30b-a3b-2507"
