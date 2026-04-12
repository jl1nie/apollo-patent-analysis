"""埋め込みバックエンドの抽象化。

`get_embedding_backend()` が `APOLLO_MODE` に応じて以下を返す:

- hosted: `SBERTBackend` (ローカル sentence-transformers, paraphrase-multilingual-MiniLM-L12-v2, 384 次元)
- private: `LMStudioBackend` (OpenAI 互換エンドポイント経由の Qwen3-Embedding など、次元は設定依存)

Phase 1 では `SBERTBackend` のみ実装し、`LMStudioBackend` は Phase 2 で追加する。
hosted モードの挙動は Home.py の既存コードと完全互換であることを目標にする。
"""

from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np
from sklearn.preprocessing import normalize

import apollo_config


class EmbeddingBackend(Protocol):
    """埋め込みバックエンドのプロトコル。

    実装クラスは以下を満たす:
    - `encode_batch`: テキスト配列を L2 正規化済みの numpy 配列に変換
    - `compute_cache_key`: テキスト内容＋モデル ID＋ソース名から決定的なキーを生成
    - `load_from_cache` / `save_to_cache`: disk 永続化（private モードのみ実効）
    - `_encode_batch_raw`: 非同期ワーカー用、正規化前の生ベクトルを返す
    """

    model_id: str

    def encode_batch(self, texts: list[str], batch_size: int = 128) -> np.ndarray: ...

    def compute_cache_key(self, texts: list[str], source_name: str) -> str: ...

    def load_from_cache(self, key: str) -> np.ndarray | None: ...

    def save_to_cache(self, key: str, arr: np.ndarray) -> None: ...

    def _encode_batch_raw(self, batch: list[str]) -> np.ndarray: ...


def _hash_texts(texts: list[str], source_name: str, model_id: str) -> str:
    """テキスト配列・ソース名・モデル ID を SHA-256 でハッシュ化する。

    同じデータセットでもモデルが変わればキャッシュキーが変わる設計。
    """
    h = hashlib.sha256()
    h.update(source_name.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    h.update(model_id.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    for t in texts:
        h.update(t.encode("utf-8", errors="replace"))
        h.update(b"\x00")
    return h.hexdigest()


class SBERTBackend:
    """hosted モード用: ローカル sentence-transformers。

    既存 Home.py の `paraphrase-multilingual-MiniLM-L12-v2` (384 次元) と
    完全互換。Streamlit の `@st.cache_resource` を使わずにインスタンス側で
    モデルをキャッシュする。外部からは `get_embedding_backend()` 経由で
    シングルトン的に取得される（Streamlit セッションスコープ）。
    """

    model_id: str = "sbert-paraphrase-multilingual-MiniLM-L12-v2"

    def __init__(self) -> None:
        # 遅延 import: private モードでは sentence-transformers が入っていない
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    def _encode_batch_raw(self, batch: list[str]) -> np.ndarray:
        return self._model.encode(batch, show_progress_bar=False)

    def encode_batch(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        embeddings_list: list[np.ndarray] = []
        total = len(texts)
        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            embeddings_list.append(self._encode_batch_raw(batch))
        arr = np.vstack(embeddings_list)
        return normalize(arr, norm="l2")

    def compute_cache_key(self, texts: list[str], source_name: str) -> str:
        return _hash_texts(texts, source_name, self.model_id)

    def load_from_cache(self, key: str) -> np.ndarray | None:
        # hosted モードでは永続化しない
        return None

    def save_to_cache(self, key: str, arr: np.ndarray) -> None:
        return None


class LMStudioBackend:
    """private モード用: OpenAI 互換エンドポイント経由の埋め込み。

    LM Studio, Ollama, vLLM, llama.cpp-server など `/v1/embeddings` を
    提供する任意の OpenAI 互換サーバで動作する。`APOLLO_EMBEDDING_MODEL` と
    `LM_STUDIO_BASE_URL` はそれぞれの環境に合わせて .env で設定する。

    返却ベクトルの次元はロードされているモデル依存（Qwen3-Embedding-4B なら
    2560 次元、MiniLM なら 384 次元など）。L2 正規化は呼び出し側の
    `encode_batch()` が一括で実行する。
    """

    def __init__(self) -> None:
        # 遅延 import: hosted モードでは openai パッケージが入っていない
        from openai import OpenAI

        self.model_id = apollo_config.EMBEDDING_MODEL
        self._client = OpenAI(
            api_key=apollo_config.LM_STUDIO_API_KEY,
            base_url=apollo_config.LM_STUDIO_BASE_URL,
        )

    def _encode_batch_raw(self, batch: list[str]) -> np.ndarray:
        # OpenAI 互換: POST /v1/embeddings
        # LM Studio / Ollama は `input` に配列を受け付けてバッチ返却
        response = self._client.embeddings.create(model=self.model_id, input=batch)
        vectors = [d.embedding for d in response.data]
        return np.asarray(vectors, dtype=np.float32)

    def encode_batch(self, texts: list[str], batch_size: int = 128) -> np.ndarray:
        embeddings_list: list[np.ndarray] = []
        total = len(texts)
        for i in range(0, total, batch_size):
            batch = texts[i : i + batch_size]
            embeddings_list.append(self._encode_batch_raw(batch))
        arr = np.vstack(embeddings_list)
        return normalize(arr, norm="l2")

    def compute_cache_key(self, texts: list[str], source_name: str) -> str:
        return _hash_texts(texts, source_name, self.model_id)

    def load_from_cache(self, key: str) -> np.ndarray | None:
        path = apollo_config.CACHE_DIR / f"{key}.npy"
        return np.load(path) if path.exists() else None

    def save_to_cache(self, key: str, arr: np.ndarray) -> None:
        path = apollo_config.CACHE_DIR / f"{key}.npy"
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, arr)


_backend_singleton: EmbeddingBackend | None = None


def get_embedding_backend() -> EmbeddingBackend:
    """モードに応じた埋め込みバックエンドを返す（プロセス内シングルトン）。

    Streamlit の rerun ごとに `SentenceTransformer` を再ロードしないよう、
    モジュールレベルのシングルトンで保持する。`@st.cache_resource` は
    services 層に Streamlit 依存を持ち込まないために使わない。
    """
    global _backend_singleton
    if _backend_singleton is not None:
        return _backend_singleton
    _backend_singleton = LMStudioBackend() if apollo_config.IS_PRIVATE else SBERTBackend()
    return _backend_singleton
