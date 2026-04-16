"""サーバ内 (named volume 内) ファイル管理。

private モードで「ブラウザでアップロードしたファイルが named volume に永続化され、
次回からはサーバ側ファイル一覧から選べる」フローを実現する。

ディレクトリ構造::

    /var/lib/apollo/inputs/
    ├── patent/
    │   ├── sample-patents.csv
    │   └── q4-data.xlsx
    ├── academic/
    ├── news/
    ├── policy/
    └── market/

各 label ごとにサブディレクトリを切る。Mission Control の各タブはここから一覧を
取得し、選んだファイルを既存の `pd.read_csv` 互換の `BytesIO` として返す。

hosted モードでは全関数が空リスト / None を返すので副作用ゼロ。
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import apollo_config

VALID_LABELS = ("patent", "academic", "news", "policy", "market")
VALID_EXTENSIONS = (".csv", ".xlsx", ".xls")


def _label_dir(label: str) -> Path:
    if label not in VALID_LABELS:
        raise ValueError(f"unknown label: {label}")
    return apollo_config.INPUTS_DIR / label


def _ensure_label_dir(label: str) -> Path:
    d = _label_dir(label)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    """ファイル名からパス区切り・隠しファイル prefix を除去する。"""
    base = Path(name).name
    base = re.sub(r"^\.+", "", base)
    return base or "unnamed"


def list_files(label: str) -> list[Path]:
    """label 配下の対応拡張子ファイル一覧 (mtime 降順)。

    private モード以外、またはディレクトリが無ければ空リスト。
    """
    if not apollo_config.IS_PRIVATE:
        return []
    d = _label_dir(label)
    if not d.exists():
        return []
    files = [p for p in d.iterdir() if p.is_file() and p.suffix.lower() in VALID_EXTENSIONS]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


def save_bytes(label: str, filename: str, data: bytes) -> Path:
    """アップロードされたファイルを named volume に保存する (上書き)。

    private モード以外では何もせず、ダミーパスを返す。
    """
    if not apollo_config.IS_PRIVATE:
        return Path(filename)
    d = _ensure_label_dir(label)
    out = d / _safe_filename(filename)
    out.write_bytes(data)
    return out


def load_as_bytesio(label: str, filename: str) -> io.BytesIO | None:
    """label 配下のファイルを `st.file_uploader` の戻り値互換の BytesIO で返す。

    `pd.read_csv` / `pd.read_excel` がそのまま受け取れる。`.name` 属性を
    付与しているので、既存の `uploaded_file.name.lower().endswith('.csv')`
    といったコードもそのまま動く。
    """
    if not apollo_config.IS_PRIVATE:
        return None
    path = _label_dir(label) / _safe_filename(filename)
    if not path.exists():
        return None
    bio = io.BytesIO(path.read_bytes())
    bio.name = path.name  # type: ignore[attr-defined]
    return bio


def delete_file(label: str, filename: str) -> bool:
    """label 配下のファイルを削除する。成功なら True。"""
    if not apollo_config.IS_PRIVATE:
        return False
    path = _label_dir(label) / _safe_filename(filename)
    if not path.exists():
        return False
    path.unlink()
    return True
