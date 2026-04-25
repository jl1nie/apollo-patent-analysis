"""プロジェクト CRUD (v7.0-private.2)。

APOLLO Private v7.0-private.2 で導入した「プロジェクト階層」の基盤。ユーザが
ドメイン単位 (CNF 特許・バッテリー特許…) で作業を区切り、各プロジェクト
毎に埋め込みモデルを固定することで UMAP / クラスタ比較が常に同じベクトル
空間上で行われることを保証する。

ディスクレイアウト::

    /var/lib/apollo/projects/
    ├── .active                      # 現在アクティブな project_id (テキスト 1 行)
    ├── default/
    │   ├── config.json
    │   ├── files/{patents,academic,news,market,policy}/
    │   ├── state/                   # {content_key}.pkl
    │   ├── store/                   # VOYAGER / CAPCOM レポート素材
    │   └── reports/
    └── cnf/                         # ユーザ作成プロジェクト

**重要な設計原則:**
- active の single source of truth は `projects/.active` ファイル。
  `st.session_state` は optimistic cache でしかなく、`session_state.clear()`
  やプロセス再起動で失われても active は維持される
- `embedding_model` はプロジェクト作成時に固定、以降変更不可。ベクトル
  空間の汚染を構造的に防ぐ (推論モデル `chat_model` は変更可)
- hosted モードでは全関数が "default" 相当のダミー値を返し、ディスク I/O
  は発生させない

config.json の構造::

    {
      "project_id": "cnf",
      "name": "CNF 特許分析",
      "embedding_model": "text-embedding-qwen3-embedding-4b",
      "chat_model": "qwen/qwen3-30b-a3b-2507",
      "created_at": "2026-04-20T10:30:00",
      "updated_at": "2026-04-20T14:15:00",
      "description": "CNF 関連特許の競争環境分析",
      "mission_objective": "CNF の量産技術で優位に立つ出願人を特定する"
    }
"""

from __future__ import annotations

import json
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import apollo_config


_SUBDIRS = ("files", "state", "store", "reports")
_FILE_KINDS = ("patents", "academic", "news", "market", "policy")


# ==================================================================
# パス解決
# ==================================================================


def project_root(project_id: str | None = None) -> Path:
    """project_id 省略時はアクティブプロジェクトのルートを返す。

    hosted モードでも path 計算は行う (callers が gating する前提)。
    実ディレクトリは private モードでしか作成されない。
    """
    pid = project_id or get_active()
    return apollo_config.PROJECTS_ROOT / pid


def project_config_path(project_id: str | None = None) -> Path:
    return project_root(project_id) / "config.json"


def project_files_dir(kind: str = "patents", project_id: str | None = None) -> Path:
    """projects/<id>/files/<kind>/"""
    if kind not in _FILE_KINDS:
        raise ValueError(f"unknown file kind: {kind!r} (expected one of {_FILE_KINDS})")
    return project_root(project_id) / "files" / kind


def project_state_dir(project_id: str | None = None) -> Path:
    return project_root(project_id) / "state"


def project_store_dir(project_id: str | None = None) -> Path:
    return project_root(project_id) / "store"


def project_reports_dir(project_id: str | None = None) -> Path:
    return project_root(project_id) / "reports"


# ==================================================================
# active project の取得/設定
# ==================================================================


def _active_file() -> Path:
    return apollo_config.PROJECTS_ROOT / ".active"


def get_active() -> str:
    """projects/.active から読む (primary source)。

    無ければ DEFAULT_PROJECT_ID ("default") を返す。session_state は touch
    しない (apollo_bootstrap.init() の順序問題を避けるため)。
    """
    path = _active_file()
    if path.exists():
        try:
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
        except OSError:
            pass
    return apollo_config.DEFAULT_PROJECT_ID


def set_active(project_id: str) -> None:
    """projects/.active を atomic に書き換える + session_state cache を更新。

    hosted モードでは no-op。
    """
    if not apollo_config.IS_PRIVATE:
        return
    if not _project_dir_exists(project_id):
        raise ValueError(f"project not found: {project_id!r}")
    path = _active_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(project_id, encoding="utf-8")
    tmp.replace(path)

    try:
        import streamlit as st

        st.session_state["apollo_active_project"] = project_id
    except Exception:  # noqa: BLE001
        pass


# ==================================================================
# プロジェクト作成 / 削除 / 一覧
# ==================================================================


def _sanitize_project_id(name: str) -> str:
    """日本語名などから安全な project_id を生成する。

    - 英数字とハイフン・アンダースコアのみ残す
    - 連続するアンダースコアは 1 つに圧縮
    - 小文字化、先頭末尾の _ と - を除去
    - 空になった場合は時刻ベースのフォールバック
    """
    base = re.sub(r"[^A-Za-z0-9_\-]+", "_", name.strip())
    base = re.sub(r"_+", "_", base).strip("_-").lower()
    if not base:
        base = f"project_{int(time.time())}"
    return base[:60]


def _project_dir_exists(project_id: str) -> bool:
    return (apollo_config.PROJECTS_ROOT / project_id).is_dir()


def _unique_project_id(base: str) -> str:
    """同名衝突時は末尾に連番を付ける。"""
    if not _project_dir_exists(base):
        return base
    for n in range(2, 1000):
        candidate = f"{base}_{n}"
        if not _project_dir_exists(candidate):
            return candidate
    raise RuntimeError("could not allocate unique project_id")


def create_project(
    name: str,
    embedding_model: str,
    chat_model: str,
    description: str = "",
    mission_objective: str = "",
    vision_model: str | None = None,
) -> str:
    """新規プロジェクトを作成し、project_id を返す。

    - `name` を sanitize して project_id を生成 (衝突時は連番)
    - `config.json` を書き込み
    - `files/{patents,academic,...}`, `state/`, `store/`, `reports/` を作成

    hosted モードでは何もせず `apollo_config.DEFAULT_PROJECT_ID` を返す。

    v7.0-private.2 Track I: `vision_model` (省略可) を追加。VOYAGER Phase 1 で
    画像を送る時のみ使用するモデル (例: qwen/qwen3-vl-8b)。None なら chat_model
    が fallback として使われる。update_config で後から変更可能。
    """
    if not apollo_config.IS_PRIVATE:
        return apollo_config.DEFAULT_PROJECT_ID

    apollo_config.PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    project_id = _unique_project_id(_sanitize_project_id(name))
    root = apollo_config.PROJECTS_ROOT / project_id

    # ディレクトリ構造を作成
    for sub in _SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    for kind in _FILE_KINDS:
        (root / "files" / kind).mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")
    config = {
        "project_id": project_id,
        "name": name.strip() or project_id,
        "embedding_model": embedding_model,
        "chat_model": chat_model,
        "vision_model": vision_model or "",
        "description": description,
        "mission_objective": mission_objective,
        "created_at": now,
        "updated_at": now,
    }
    _write_config(project_id, config)
    return project_id


def ensure_default_project() -> str:
    """default プロジェクトが無ければ作成する (env 既定値で)。

    apollo_bootstrap.init() から private モード時に 1 回呼ばれる想定。
    既に存在すれば何もせず id を返す。
    """
    if not apollo_config.IS_PRIVATE:
        return apollo_config.DEFAULT_PROJECT_ID

    default_id = apollo_config.DEFAULT_PROJECT_ID
    if _project_dir_exists(default_id):
        return default_id

    apollo_config.PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
    root = apollo_config.PROJECTS_ROOT / default_id
    for sub in _SUBDIRS:
        (root / sub).mkdir(parents=True, exist_ok=True)
    for kind in _FILE_KINDS:
        (root / "files" / kind).mkdir(parents=True, exist_ok=True)

    now = datetime.now().isoformat(timespec="seconds")
    config = {
        "project_id": default_id,
        "name": "default",
        "embedding_model": apollo_config.EMBEDDING_MODEL,
        "chat_model": apollo_config.CHAT_MODEL,
        "vision_model": "",
        "description": "v7.0 からの自動移行先 / 初期起動時の既定プロジェクト",
        "mission_objective": "",
        "created_at": now,
        "updated_at": now,
    }
    _write_config(default_id, config)
    return default_id


def list_projects() -> list[dict]:
    """[{project_id, name, embedding_model, chat_model, file_count, state_count,
        mtime, created_at, updated_at}, ...] を mtime 降順で返す。

    hosted モードでは空リスト。
    """
    if not apollo_config.IS_PRIVATE or not apollo_config.PROJECTS_ROOT.exists():
        return []

    items: list[dict] = []
    for path in apollo_config.PROJECTS_ROOT.iterdir():
        if not path.is_dir() or path.name.startswith("."):
            continue
        cfg = _read_config_safe(path.name)
        if not cfg:
            continue
        files_root = path / "files"
        file_count = 0
        if files_root.exists():
            file_count = sum(1 for _ in files_root.rglob("*") if _.is_file())
        state_root = path / "state"
        state_count = 0
        if state_root.exists():
            state_count = sum(1 for _ in state_root.glob("*.pkl"))
        items.append(
            {
                "project_id": cfg.get("project_id", path.name),
                "name": cfg.get("name", path.name),
                "embedding_model": cfg.get("embedding_model", ""),
                "chat_model": cfg.get("chat_model", ""),
                "file_count": file_count,
                "state_count": state_count,
                "mtime": path.stat().st_mtime,
                "created_at": cfg.get("created_at", ""),
                "updated_at": cfg.get("updated_at", ""),
                "description": cfg.get("description", ""),
            }
        )
    items.sort(key=lambda d: d.get("mtime", 0), reverse=True)
    return items


def delete_project(project_id: str, purge_cache: bool = False) -> None:
    """プロジェクト配下 `projects/<id>/` を削除する。

    `purge_cache=True` なら関連する埋め込み npy も削除する (モデル ID が
    project と連動しているので npy ファイル名だけでは特定できない。将来
    拡張用に引数だけ残す)。

    hosted モードでは no-op。active project を消した場合は default に戻す。
    """
    if not apollo_config.IS_PRIVATE:
        return
    if project_id == apollo_config.DEFAULT_PROJECT_ID:
        raise ValueError("default プロジェクトは削除できません")
    root = apollo_config.PROJECTS_ROOT / project_id
    if not root.exists():
        return
    shutil.rmtree(root)
    if get_active() == project_id:
        set_active(apollo_config.DEFAULT_PROJECT_ID)
    # purge_cache は将来実装 (npy は content_key = model_id 含むので他プロジェクトと
    # 衝突しない。現状は削除してもメリットが小さい)


# ==================================================================
# config.json 読み書き
# ==================================================================


_IMMUTABLE_FIELDS = frozenset({"project_id", "embedding_model", "created_at"})


def get_config(project_id: str | None = None) -> dict:
    """projects/<id>/config.json を読む。無ければ空 dict。"""
    pid = project_id or get_active()
    return _read_config_safe(pid) or {}


def update_config(project_id: str | None = None, **kwargs: Any) -> dict:
    """config.json の可変フィールドを更新する。

    `project_id` / `embedding_model` / `created_at` は immutable として拒否する。
    `updated_at` は自動更新。

    hosted モードでは no-op (空 dict を返す)。
    """
    if not apollo_config.IS_PRIVATE:
        return {}
    pid = project_id or get_active()
    cfg = _read_config_safe(pid)
    if not cfg:
        raise ValueError(f"project config not found: {pid!r}")

    for key in kwargs:
        if key in _IMMUTABLE_FIELDS:
            raise ValueError(f"{key!r} は変更できません (プロジェクト作成時に固定)")

    cfg.update(kwargs)
    cfg["updated_at"] = datetime.now().isoformat(timespec="seconds")
    _write_config(pid, cfg)
    return cfg


def _read_config_safe(project_id: str) -> dict | None:
    path = apollo_config.PROJECTS_ROOT / project_id / "config.json"
    if not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return None


def _write_config(project_id: str, config: dict) -> None:
    """atomic write (tmp + replace)。"""
    path = apollo_config.PROJECTS_ROOT / project_id / "config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
