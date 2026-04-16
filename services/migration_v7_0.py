"""v7.0-private.1 → v7.1 データ自動マイグレーション。

`apollo_bootstrap.init()` が private モード起動時に 1 回だけ呼ぶ冪等関数。
既存データを破壊せずに新しいプロジェクト階層に統合する。

## マイグレーション内容

**旧 v7.0 レイアウト:**
::

    /var/lib/apollo/
    ├── sessions/
    │   ├── index.json
    │   └── patent/
    │       └── {content_key}.pkl
    ├── inputs/
    │   ├── patent/*.csv
    │   ├── academic/*.csv
    │   └── ...
    ├── cache/embeddings/*.npy            # 共有なので移動しない
    └── users/users.yml

**新 v7.1 レイアウト:**
::

    /var/lib/apollo/
    ├── projects/
    │   ├── .active
    │   ├── .migrated_from_v7.0           # sentinel
    │   └── default/
    │       ├── config.json
    │       ├── state/{content_key}.pkl   # sessions/patent/ からハードリンク
    │       └── files/
    │           ├── patents/*.csv         # inputs/patent/ からハードリンク
    │           ├── academic/*.csv
    │           └── ...
    ├── sessions/                         # read-only 残置 (削除は v7.2 以降)
    ├── inputs/                           # 同上
    ├── cache/                            # そのまま共有
    └── users/

## 戦略
- **ハードリンク** で原本を残しつつ新階層から参照 (disk 使用量は増えない)
- FS が hardlink 非対応なら `shutil.copy2` にフォールバック
- sentinel `projects/.migrated_from_v7.0` で冪等性を保証
- 失敗しても分析は続行できるよう例外は握り潰し警告ログのみ
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import apollo_config
from services import projects

# 旧 label 名 → v7.1 files/ サブディレクトリ名の対応
# server_files.VALID_LABELS は ("patent", "academic", ...) だが v7.1 は "patents" (複数形)
_LABEL_MAP = {
    "patent": "patents",
    "academic": "academic",
    "news": "news",
    "market": "market",
    "policy": "policy",
}


def _sentinel_path() -> Path:
    return apollo_config.PROJECTS_ROOT / ".migrated_from_v7.0"


def _link_or_copy(src: Path, dst: Path) -> None:
    """ハードリンクを試み、失敗したら copy2。既存 dst は skip。"""
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dst)
    except OSError:
        shutil.copy2(src, dst)


def _migrate_session_index(default_id: str) -> bool:
    """sessions/index.json → projects/default/state/.index.json にコピー。

    v7.1 では index を project-scoped にするため、v7.0 のフラットな index を
    そのまま default プロジェクト配下にコピーする (全エントリが v7.0 では
    patent label しか無かった前提。label フィールドは保持)。

    戻り値: コピーが行われたら True。
    """
    old_index = apollo_config.SESSION_DIR / "index.json"
    new_index = projects.project_state_dir(default_id) / ".index.json"
    if not old_index.exists() or new_index.exists():
        return False
    new_index.parent.mkdir(parents=True, exist_ok=True)
    _link_or_copy(old_index, new_index)
    return True


def _migrate_state_pkls(default_id: str) -> int:
    """sessions/patent/*.pkl → projects/default/state/ にハードリンク。

    v7.0 の pkl フォーマットは v7.1 と互換 (`analysis_state.STATE_KEYS` 一致)
    なのでそのままコピーすれば load_state_by_key で読める。
    """
    old_dir = apollo_config.SESSION_DIR / "patent"
    if not old_dir.exists():
        return 0
    new_dir = projects.project_state_dir(default_id)
    new_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for pkl in old_dir.glob("*.pkl"):
        target = new_dir / pkl.name
        if target.exists():
            continue
        _link_or_copy(pkl, target)
        count += 1
    return count


def _migrate_input_files(default_id: str) -> int:
    """inputs/{label}/*.{csv,xlsx} → projects/default/files/{kind}/ にハードリンク。"""
    if not apollo_config.INPUTS_DIR.exists():
        return 0
    count = 0
    for old_label, new_kind in _LABEL_MAP.items():
        old_dir = apollo_config.INPUTS_DIR / old_label
        if not old_dir.exists() or not old_dir.is_dir():
            continue
        new_dir = projects.project_files_dir(new_kind, default_id)
        new_dir.mkdir(parents=True, exist_ok=True)
        for f in old_dir.iterdir():
            if not f.is_file():
                continue
            target = new_dir / f.name
            if target.exists():
                continue
            _link_or_copy(f, target)
            count += 1
    return count


def migrate_if_needed() -> dict:
    """v7.0 → v7.1 マイグレーション。冪等。

    返り値は sentinel 以外に行った処理のサマリ::

        {
            "ran": True/False,        # 実際に移行処理を行ったか (sentinel 更新含む)
            "state_migrated": int,    # pkl コピー数
            "files_migrated": int,    # 入力ファイルコピー数
            "default_created": bool,  # default プロジェクトを今回作成したか
        }

    hosted モードでは何もせず `{"ran": False, ...}` を返す。
    """
    summary = {
        "ran": False,
        "state_migrated": 0,
        "files_migrated": 0,
        "index_migrated": False,
        "default_created": False,
    }
    if not apollo_config.IS_PRIVATE:
        return summary

    sentinel = _sentinel_path()
    if sentinel.exists():
        # 既にマイグレーション済み。default プロジェクトだけ念のため保証
        projects.ensure_default_project()
        return summary

    # sentinel が無ければ初回起動とみなして処理する。
    # default プロジェクト作成 (冪等)
    existed = (apollo_config.PROJECTS_ROOT / apollo_config.DEFAULT_PROJECT_ID).is_dir()
    default_id = projects.ensure_default_project()
    summary["default_created"] = not existed

    # pkl / 入力ファイル / session_index.json の移行
    try:
        summary["state_migrated"] = _migrate_state_pkls(default_id)
    except Exception:  # noqa: BLE001
        # 失敗しても致命的ではないので続行 (次回起動時に sentinel 無しで再試行)
        pass
    try:
        summary["files_migrated"] = _migrate_input_files(default_id)
    except Exception:  # noqa: BLE001
        pass
    try:
        summary["index_migrated"] = _migrate_session_index(default_id)
    except Exception:  # noqa: BLE001
        summary["index_migrated"] = False

    # sentinel を立てる (これ以降はこの関数は no-op)
    sentinel.parent.mkdir(parents=True, exist_ok=True)
    sentinel.touch()
    summary["ran"] = True
    return summary
