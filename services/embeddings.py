"""LM Studio (OpenAI 互換) 経由の埋め込みバックエンド。

`patiroha.SBERTEmbedder` の API シグネチャ互換シムとして実装し、
`apollo_bootstrap.init()` がモジュール属性を差し替える形で v7 ソースに触らずに
private モード時のみ有効化される。

v7 が呼び出すインタフェース::

    embedder = patiroha.SBERTEmbedder()
    vectors = embedder.encode(
        df,
        text_columns=[...],
        batch_size=128,
        normalize_embeddings=True,
        progress_callback=lambda frac: ...,
        column_weights={'col': 2},   # NEBULA でのみ使用
    )

戻り値は `(n_docs, embedding_dim)` の numpy 配列。L2 正規化済み。
"""

from __future__ import annotations

from typing import Callable, Sequence

import numpy as np
import pandas as pd
from sklearn.preprocessing import normalize

import apollo_config
from services import storage


def _build_text_column(
    df: pd.DataFrame,
    text_columns: Sequence[str],
    column_weights: dict | None,
) -> list[str]:
    """patiroha と互換のテキスト結合ロジック。

    `column_weights` で指定された列は重み回数だけ繰り返してから結合する
    （NEBULA の `column_weights={'unified_title': 2}` を再現）。
    """
    weights = column_weights or {}
    parts_per_row: list[list[str]] = []
    for col in text_columns:
        if col not in df.columns:
            continue
        repeat = max(1, int(weights.get(col, 1)))
        col_str = df[col].fillna("").astype(str)
        if repeat > 1:
            col_str = col_str.apply(lambda s: " ".join([s] * repeat))
        parts_per_row.append(col_str.tolist())

    if not parts_per_row:
        return [""] * len(df)
    return [" ".join(parts).strip() for parts in zip(*parts_per_row)]


class LMStudioEmbedderShim:
    """`patiroha.SBERTEmbedder` 互換の OpenAI 互換埋め込みクライアント。

    `apollo_bootstrap.init()` で `patiroha.SBERTEmbedder` の差し替え先として
    モジュール属性に登録される。Streamlit `@st.cache_resource` でラップされても
    モデル変更に追従できるよう、`encode()` の冒頭で毎回 `model_id` を
    session_state から再解決する。
    """

    model_id: str

    def __init__(self) -> None:
        from openai import OpenAI  # 遅延 import: hosted では openai 不要
        from services import lm_studio_models

        self.model_id = lm_studio_models.current_embed_model()
        self._client = OpenAI(
            api_key=apollo_config.LM_STUDIO_API_KEY,
            base_url=apollo_config.LM_STUDIO_BASE_URL,
        )

    def _refresh_model_id(self) -> None:
        """session_state / env の最新モデル ID に同期する。"""
        from services import lm_studio_models

        new_id = lm_studio_models.current_embed_model()
        if new_id and new_id != self.model_id:
            self.model_id = new_id

    def _encode_batch_raw(self, batch: list[str]) -> np.ndarray:
        # 空文字は埋め込みエンドポイントが拒否することがあるので最低 1 文字を保証
        safe_batch = [t if t else " " for t in batch]
        response = self._client.embeddings.create(
            model=self.model_id, input=safe_batch
        )
        vectors = [d.embedding for d in response.data]
        return np.asarray(vectors, dtype=np.float32)

    def encode(
        self,
        df: pd.DataFrame,
        text_columns: Sequence[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        progress_callback: Callable[[float], None] | None = None,
        column_weights: dict | None = None,
        **_: object,
    ) -> np.ndarray:
        """patiroha.SBERTEmbedder.encode() 互換 API。

        - 冒頭で session_state から `model_id` を再取得 (サイドバー selectbox の
          最新値に追従)
        - `df` から `text_columns` を結合してテキスト配列を生成
        - SHA-256 でキャッシュキーを計算し、`$DATA_ROOT/cache/embeddings/*.npy` に
          ヒットすればそれを返す (モデルを変えるとキーも変わるので別キャッシュになる)
        - キャッシュミス時のみ LM Studio に POST し、結果をキャッシュ保存
        - `progress_callback(frac)` をバッチごとに呼ぶ（v7 標準の進捗 UI を流用）
        - 終了時に `analysis_state.auto_register_encode_result` を呼び、NEBULA の
          学術論文埋め込みを現在ロード中の patent pkl に後追い保存する
        """
        self._refresh_model_id()

        texts = _build_text_column(df, text_columns, column_weights)
        total = len(texts)

        cache_key = storage.hash_texts(
            texts,
            source_name=",".join(text_columns),
            model_id=self.model_id,
        )
        cache_path = storage.embedding_cache_path(cache_key)

        if cache_path.exists():
            arr = np.load(cache_path)
            if progress_callback is not None:
                progress_callback(1.0)
            final = normalize(arr, norm="l2") if normalize_embeddings else arr
            _auto_register(df, text_columns, final, self.model_id)
            return final

        embeddings_list: list[np.ndarray] = []
        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            embeddings_list.append(self._encode_batch_raw(batch))
            if progress_callback is not None:
                progress_callback(min(1.0, (i + len(batch)) / max(1, total)))

        arr = (
            np.vstack(embeddings_list)
            if embeddings_list
            else np.zeros((0, 1), dtype=np.float32)
        )

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(cache_path, arr)

        final = normalize(arr, norm="l2") if normalize_embeddings else arr
        _auto_register(df, text_columns, final, self.model_id)
        return final


def _auto_register(
    df: pd.DataFrame,
    text_columns: Sequence[str],
    arr: np.ndarray,
    model_id: str,
) -> None:
    """encode() 完了後に session pkl へ追記する (失敗は analysis をブロックしない)。"""
    try:
        from services import analysis_state

        analysis_state.auto_register_encode_result(
            df=df, text_columns=text_columns, arr=arr, model_id=model_id
        )
    except Exception:  # noqa: BLE001
        pass
