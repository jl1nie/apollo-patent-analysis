"""永続化層: 埋め込みキャッシュとユーザ設定のためのファイルパス解決。

private モードでマウントされたボリューム (`/var/lib/apollo` 配下) に対して
以下のような構造でデータを配置する::

    /var/lib/apollo/
    ├── cache/
    │   └── embeddings/
    │       └── {cache_key}.npy              埋め込み行列のキャッシュ
    ├── uploads/
    ├── sessions/
    │   ├── index.json                        content_key ベースのセッションインデックス
    │   └── patent/
    │       └── {content_key}.pkl             前処理結果 pickle
    └── users/
        └── users.yml                         認証ユーザ定義

hosted モードでは `apollo_config.IS_PRIVATE` が False なので、これらの
関数を呼び出してもディスク I/O は発生しない（None / 空リストを返す）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

import apollo_config


def hash_texts(texts: list[str], source_name: str, model_id: str) -> str:
    """テキスト配列・ソース名・モデル ID から決定的な SHA-256 キーを生成する。"""
    h = hashlib.sha256()
    h.update(source_name.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    h.update(model_id.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    for t in texts:
        h.update(t.encode("utf-8", errors="replace"))
        h.update(b"\x00")
    return h.hexdigest()


def embedding_cache_path(cache_key: str) -> Path:
    """埋め込み npy ファイルのパスを返す。"""
    return apollo_config.CACHE_DIR / f"{cache_key}.npy"


def list_cached_datasets() -> list[dict]:
    """キャッシュ済みの埋め込みデータセット一覧を返す（サイドバー表示用）。

    private モード以外では空リストを返す。
    """
    if not apollo_config.IS_PRIVATE or not apollo_config.CACHE_DIR.exists():
        return []
    datasets = []
    for p in apollo_config.CACHE_DIR.glob("*.npy"):
        st = p.stat()
        datasets.append(
            {
                "key": p.stem,
                "size_mb": round(st.st_size / 1_000_000, 2),
                "mtime": st.st_mtime,
            }
        )
    datasets.sort(key=lambda d: d["mtime"], reverse=True)
    return datasets


# ==================================================================
# content_key / session_index
# ------------------------------------------------------------------
# 前処理結果 pickle を「ファイル名」ではなく「CSV 内容 + モデル ID のハッシュ」
# でキー付けするための補助。`analysis_state.py` がこの関数群を使って
# sessions/{label}/{content_key}.pkl に保存し、index.json に
# {content_key: {filename, model_id, ...}} を書き込む。
#
# これにより:
# - ファイル名を変えても同じ CSV は同じキャッシュにヒットする
# - 同じ CSV でもモデルを変えれば別キャッシュとして共存できる
# - UI は {ファイル × モデル} のマトリクスで表示できる
# ==================================================================


def compute_content_key(
    df,  # pandas.DataFrame だが型を固定 import しない（hosted の import 軽量化）
    text_columns: Sequence[str],
    model_id: str,
) -> str:
    """DataFrame の該当列内容から決定的な content_key を返す。

    `hash_texts` と同じロジックで SHA-256 を計算し、先頭 16 文字を短縮キーと
    して返す。短縮しても衝突確率は十分低く (2^64)、UI 表示・ディレクトリ名
    として扱いやすい。
    """
    parts: list[str] = []
    for col in text_columns:
        if col in df.columns:
            parts.append(df[col].fillna("").astype(str).tolist())
        else:
            parts.append([""] * len(df))
    # 列順を保つために zip でフラット化
    texts = [" ".join(row) for row in zip(*parts)] if parts else [""] * len(df)
    return hash_texts(texts, source_name=",".join(text_columns), model_id=model_id)[:16]


def session_index_path() -> Path:
    """session index (content_key → metadata) のパス。

    v7.0-private.2 以降: アクティブプロジェクト内 `projects/<active>/state/.index.json`。
    プロジェクト単位でベクトル空間が分離されるので、index も project-scoped。

    hosted モード / private 初期化前でも path 計算は行う (実 I/O は callers の
    `IS_PRIVATE` ガード下で行われる)。
    """
    try:
        from services import projects

        return projects.project_state_dir() / ".index.json"
    except Exception:  # noqa: BLE001
        # projects import 失敗時は旧 v7.0 パスにフォールバック (保険)
        return apollo_config.SESSION_DIR / "index.json"


def load_session_index() -> dict:
    """session index (content_key → metadata) を読む。無ければ空 dict。

    private モード以外では空 dict を返す。
    """
    if not apollo_config.IS_PRIVATE:
        return {}
    path = session_index_path()
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return {}


def save_session_index(index: dict) -> None:
    """session index を書き戻す。private モード以外は no-op。"""
    if not apollo_config.IS_PRIVATE:
        return
    path = session_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def register_session(
    content_key: str,
    filename: str,
    model_id: str,
    rows: int,
    label: str,
    size_mb: float | None = None,
) -> None:
    """1 エントリを index.json に追加/更新する。private モード以外は no-op。"""
    if not apollo_config.IS_PRIVATE:
        return
    import time

    index = load_session_index()
    index[content_key] = {
        "filename": filename,
        "model_id": model_id,
        "rows": rows,
        "label": label,
        "size_mb": size_mb,
        "mtime": time.time(),
    }
    save_session_index(index)


def unregister_session(content_key: str) -> None:
    """index.json から 1 エントリを削除する。private モード以外は no-op。"""
    if not apollo_config.IS_PRIVATE:
        return
    index = load_session_index()
    if content_key in index:
        del index[content_key]
        save_session_index(index)
