"""前処理結果 (df_main + 埋め込み + TF-IDF + col_map) の永続化。

private モードでブラウザログアウト/再ログインしても作業が継続できるよう、
preprocess 完了後の重い結果を named volume に pickle 保存する。

**v7.1 から** 保存キーを「ファイル名」から「CSV 内容ハッシュ + 埋め込みモデル ID」
ベース (`content_key`) に統一した。これにより:

- ファイル名を変えても同じ CSV は同じセッションにヒットする
- 同じ CSV でもモデルを変えれば別セッションとして共存できる
- UI は `services/storage.session_index_path()` の JSON を読んで
  {ファイル × モデル} のマトリクスで表示できる

ストレージ::

    /var/lib/apollo/sessions/
    ├── index.json                          {content_key: {filename, model_id, rows, label, mtime}}
    └── patent/
        └── {content_key}.pkl               pickle 本体

保存対象 (Home.py preprocess 完了時の session_state より):
- df_main: 前処理済み DataFrame
- sbert_embeddings: numpy ndarray (n_docs, dim) — 特許
- nebula_academic_embeddings: numpy ndarray (n_acad, dim) — NEBULA 学術論文 (後追い保存)
- tfidf_matrix: scipy sparse
- feature_names: array/list
- col_map: dict
- delimiters: dict

hosted モードでは全関数が None / no-op を返す。

**下位互換**: 既存の `save_state(label, filename, state)` / `load_state(label, filename)` /
`has_state(label, filename)` / `delete_state(label, filename)` はそのまま残す。
内部で content_key を逆引きし、新レイアウトの pkl を読み書きする。
"""

from __future__ import annotations

import pickle
import re
from pathlib import Path
from typing import Sequence

import apollo_config
from services import storage

STATE_KEYS = (
    "df_main",
    "df_npl",                       # 前処理後の NPL (Academic/Business/Policy/Market 統合) — NEBULA が参照
    "df_npl_accumulated",           # アップロード直後の NPL 生データ (再編集のため)
    "sbert_embeddings",
    "nebula_academic_embeddings",
    "tfidf_matrix",
    "feature_names",
    "col_map",
    "delimiters",
)

LABEL_DIRS = {
    "patent": "patent",
}


def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"^\.+", "", base)
    return base or "unnamed"


# ==================================================================
# 新 API: content_key ベース
# ==================================================================


def _state_path_by_key(label: str, content_key: str) -> Path:
    """projects/<active>/state/{content_key}.pkl (v7.1)

    v7.1 からベクトル空間はプロジェクト単位で分離されるため、label サブディレクトリ
    は廃止。下位互換のため引数の `label` は受け取るが使わない (将来 NEBULA 独立
    state 保存で再利用する余地を残す)。
    """
    from services import projects

    return projects.project_state_dir() / f"{content_key}.pkl"


def save_state_by_key(
    label: str,
    content_key: str,
    filename: str,
    model_id: str,
    state: dict,
) -> Path | None:
    """content_key ベースで preprocess 結果を pickle 保存 + index.json 登録。

    private モード以外では no-op。
    """
    if not apollo_config.IS_PRIVATE:
        return None
    path = _state_path_by_key(label, content_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: state.get(k) for k in STATE_KEYS}
    with open(path, "wb") as f:
        pickle.dump(payload, f, protocol=pickle.HIGHEST_PROTOCOL)

    df = state.get("df_main")
    rows = int(len(df)) if df is not None else 0
    size_mb = round(path.stat().st_size / 1_000_000, 2)
    storage.register_session(
        content_key=content_key,
        filename=filename,
        model_id=model_id,
        rows=rows,
        label=label,
        size_mb=size_mb,
    )
    return path


def load_state_by_key(label: str, content_key: str) -> dict | None:
    """content_key から state を読む。無ければ None。"""
    if not apollo_config.IS_PRIVATE:
        return None
    path = _state_path_by_key(label, content_key)
    if not path.exists():
        return None
    try:
        with open(path, "rb") as f:
            return pickle.load(f)
    except Exception:  # noqa: BLE001
        return None


def update_state(label: str, content_key: str, partial: dict) -> bool:
    """既存 pkl に partial をマージして書き戻す (in-place 更新)。

    NEBULA の学術論文埋め込みを後追いで保存する用途。pkl が存在しない場合は
    False を返して no-op。
    """
    if not apollo_config.IS_PRIVATE:
        return False
    path = _state_path_by_key(label, content_key)
    if not path.exists():
        return False
    try:
        with open(path, "rb") as f:
            existing = pickle.load(f)
    except Exception:  # noqa: BLE001
        return False

    if not isinstance(existing, dict):
        return False
    for k, v in partial.items():
        if k in STATE_KEYS and v is not None:
            existing[k] = v

    with open(path, "wb") as f:
        pickle.dump(existing, f, protocol=pickle.HIGHEST_PROTOCOL)

    # index.json の mtime と size を更新
    import time

    index = storage.load_session_index()
    if content_key in index:
        index[content_key]["mtime"] = time.time()
        index[content_key]["size_mb"] = round(path.stat().st_size / 1_000_000, 2)
        storage.save_session_index(index)
    return True


def delete_state_by_key(label: str, content_key: str) -> bool:
    """content_key に対応する pkl と index エントリを削除。"""
    if not apollo_config.IS_PRIVATE:
        return False
    path = _state_path_by_key(label, content_key)
    deleted = False
    if path.exists():
        path.unlink()
        deleted = True
    storage.unregister_session(content_key)
    return deleted


def list_sessions(label: str | None = None) -> list[dict]:
    """index.json から session 一覧を返す (UI 用)。

    各要素に `content_key` を追加して返す。label 指定時はそのラベルのみ。
    mtime 降順。
    """
    if not apollo_config.IS_PRIVATE:
        return []
    index = storage.load_session_index()
    items = []
    for key, meta in index.items():
        if label is not None and meta.get("label") != label:
            continue
        entry = {"content_key": key, **meta}
        items.append(entry)
    items.sort(key=lambda d: d.get("mtime", 0), reverse=True)
    return items


# ==================================================================
# auto_register_encode_result
#   LMStudioEmbedderShim.encode() の末尾から呼ばれる。現在ロード中の
#   patent CSV の content_key を特定し、その pkl に埋め込みを追記する。
# ==================================================================


def _text_columns_role(text_columns: Sequence[str]) -> str | None:
    """text_columns の組み合わせから用途を推定する。

    - 特許本体 (title/abstract/claim 系) → "sbert_embeddings"
    - NEBULA 学術論文 (unified_title/unified_content 系) → "nebula_academic_embeddings"
    - それ以外 → None (永続化対象外)
    """
    cols_lower = {c.lower() for c in text_columns}
    if {"unified_title", "unified_content"}.issubset(cols_lower):
        return "nebula_academic_embeddings"
    # 特許本体は title/abstract/claim の組み合わせだが、列名は col_map によって可変。
    # 安全サイド: unified_* ではなく 3 列以上の組み合わせなら特許扱い
    if len(text_columns) >= 2 and not any("unified_" in c for c in cols_lower):
        return "sbert_embeddings"
    return None


def auto_register_encode_result(
    df,
    text_columns: Sequence[str],
    arr,
    model_id: str,
) -> None:
    """encode() 完了後に呼ばれ、適切な session pkl を in-place 更新する。

    失敗しても呼び出し元の分析をブロックしない (呼び出し側で try/except する)。

    動作:
    - 特許本体の埋め込みならメインの save_state_by_key を呼ぶ (Home.py preprocess で
      persist_analysis_state 経由で別途呼ばれるので、ここは更新のみで十分)
    - NEBULA 学術論文の埋め込みなら、現在ロード中の patent の content_key を
      session_state / session_index から特定し、その pkl の
      `nebula_academic_embeddings` キーを update_state で追記する
    """
    if not apollo_config.IS_PRIVATE:
        return
    role = _text_columns_role(text_columns)
    if role != "nebula_academic_embeddings":
        return  # 特許本体側は persist_analysis_state 経由で別途保存される

    # 現在ロード中の patent content_key を決定する
    try:
        import streamlit as st  # 遅延 import
    except Exception:  # noqa: BLE001
        return

    content_key = st.session_state.get("_patent_content_key")
    if not content_key:
        # session_state に記録がなければ index から「最新の patent」を推定
        items = list_sessions(label="patent")
        if not items:
            return
        content_key = items[0]["content_key"]

    update_state("patent", content_key, {"nebula_academic_embeddings": arr})


# ==================================================================
# 下位互換 API (filename ベース)
# ------------------------------------------------------------------
# 既存の private_ui._do_load / Home.py の persist_analysis_state 呼び出しは
# この API 経由で動く。内部では content_key を計算して by_key API に委譲する。
# ==================================================================


def _resolve_content_key_for_filename(label: str, filename: str) -> str | None:
    """index.json から filename → content_key の逆引き。

    同名ファイルが複数モデルで保存されている場合は mtime 最新を返す。
    """
    items = list_sessions(label=label)
    safe = _safe_filename(filename)
    for it in items:
        if _safe_filename(it.get("filename", "")) == safe:
            return it["content_key"]
    return None


def save_state(label: str, filename: str, state: dict) -> Path | None:
    """preprocess 結果を pickle で保存する (private モード以外は no-op)。

    内部では `compute_content_key(df, text_columns, model_id)` で
    content_key を計算し、新レイアウトの pkl に保存する。
    """
    if not apollo_config.IS_PRIVATE:
        return None

    df = state.get("df_main")
    col_map = state.get("col_map") or {}
    if df is None:
        return None

    # 特許の主要テキスト列を content_key 計算の入力にする
    text_columns = [
        col_map.get("title") or "",
        col_map.get("abstract") or "",
        col_map.get("claim") or "",
    ]
    text_columns = [c for c in text_columns if c]

    # モデル ID を解決 (private_ui 経由で session_state に積まれていればそれを使う)
    try:
        from services import lm_studio_models

        model_id = lm_studio_models.current_embed_model()
    except Exception:  # noqa: BLE001
        model_id = apollo_config.EMBEDDING_MODEL

    content_key = storage.compute_content_key(df, text_columns, model_id)

    # session_state に記録しておく (NEBULA 学術論文が後追いで同じキーに書き込むため)
    try:
        import streamlit as st

        st.session_state["_patent_content_key"] = content_key
    except Exception:  # noqa: BLE001
        pass

    return save_state_by_key(
        label=label,
        content_key=content_key,
        filename=filename,
        model_id=model_id,
        state=state,
    )


def load_state(label: str, filename: str) -> dict | None:
    """保存された state を返す。無ければ None (filename ベース下位互換)。"""
    if not apollo_config.IS_PRIVATE:
        return None
    content_key = _resolve_content_key_for_filename(label, filename)
    if not content_key:
        return None

    # session_state に復元時の content_key を記録
    try:
        import streamlit as st

        st.session_state["_patent_content_key"] = content_key
    except Exception:  # noqa: BLE001
        pass

    return load_state_by_key(label, content_key)


def has_state(label: str, filename: str) -> bool:
    """state ファイルが存在するか (UI のバッジ表示用)。"""
    if not apollo_config.IS_PRIVATE:
        return False
    return _resolve_content_key_for_filename(label, filename) is not None


def delete_state(label: str, filename: str) -> bool:
    """filename ベース削除 (同名ファイルの content_key を全削除)。"""
    if not apollo_config.IS_PRIVATE:
        return False
    items = list_sessions(label=label)
    safe = _safe_filename(filename)
    targets = [it["content_key"] for it in items if _safe_filename(it.get("filename", "")) == safe]
    if not targets:
        return False
    for key in targets:
        delete_state_by_key(label, key)
    return True
