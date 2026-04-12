"""永続化層: disk cache とジョブ管理のためのファイルパス解決。

private モードでマウントされたボリューム (`/var/lib/apollo` 配下) に対して
以下のような構造でデータを配置する::

    /var/lib/apollo/
    ├── cache/
    │   └── embeddings/
    │       └── {cache_key}.npy              埋め込み行列のキャッシュ
    ├── jobs/
    │   └── {job_id}/
    │       └── status.json                  非同期ジョブのステータス
    ├── uploads/                              (Phase 4 以降で使用)
    ├── sessions/                             (Phase 4 以降で使用)
    └── users/
        └── users.yml                         (Phase 4 認証用)

hosted モードでは `apollo_config.IS_PRIVATE` が False なので、これらの
関数を呼び出しても基本的にディスク I/O は発生しない（None / 空リストを返す）。
"""

from __future__ import annotations

import time
from pathlib import Path

import apollo_config


def embedding_cache_path(cache_key: str) -> Path:
    """埋め込み npy ファイルのパスを返す。"""
    return apollo_config.CACHE_DIR / f"{cache_key}.npy"


def job_dir(job_id: str) -> Path:
    """ジョブディレクトリのパスを返す。"""
    return apollo_config.JOBS_DIR / job_id


def job_status_file(job_id: str) -> Path:
    """ジョブのステータス JSON ファイルのパスを返す。"""
    return job_dir(job_id) / "status.json"


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


def purge_stale_jobs(stale_threshold_sec: int = 3600) -> int:
    """長時間 `running` のまま放置されたジョブを error 扱いにマークする。

    サーバ再起動でワーカースレッドが消失した場合の復旧用。戻り値はマーク
    したジョブ数。
    """
    if not apollo_config.IS_PRIVATE or not apollo_config.JOBS_DIR.exists():
        return 0
    import json

    now = time.time()
    marked = 0
    for jd in apollo_config.JOBS_DIR.iterdir():
        sf = jd / "status.json"
        if not sf.exists():
            continue
        try:
            data = json.loads(sf.read_text())
        except Exception:  # noqa: BLE001
            continue
        if data.get("state") == "running":
            updated_at = data.get("updated_at", 0)
            if now - updated_at > stale_threshold_sec:
                data["state"] = "error"
                data["error"] = (
                    f"ジョブが {int(stale_threshold_sec / 60)} 分以上更新されていません "
                    f"(サーバ再起動の可能性)"
                )
                sf.write_text(json.dumps(data, ensure_ascii=False, indent=2))
                marked += 1
    return marked
