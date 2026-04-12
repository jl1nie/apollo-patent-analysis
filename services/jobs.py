"""非同期埋め込みジョブ管理。

`start_embedding_job()` がバックグラウンドスレッドでバックエンドの埋め込み
処理を走らせ、状態を disk 上の `status.json` に書き込む。UI 側は
`read_status(job_id)` でポーリングし、進行状況を表示する。

## なぜスレッド+ファイル方式か

Streamlit は 1 リクエスト=1 スクリプト実行のモデルで、重い処理を同期的に
走らせるとブラウザがロックする。Qwen3-Embedding-4B で数千件の特許を埋め
込むと数分〜数十分かかるため、同期実行は実用にならない。

`threading.Thread(daemon=True)` で別スレッドを起動し、状態をプロセス内
オブジェクトではなく disk のファイル (atomic rename) に書き出すことで：

1. 複数の Streamlit セッション（複数ブラウザタブ）から同じジョブを観測できる
2. ブラウザを閉じて再接続してもジョブ状態を復元できる
3. `st.fragment(run_every=...)` で軽量ポーリングできる

## ステータス遷移

    pending → running → done
                     → error
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import asdict, dataclass

import numpy as np
from sklearn.preprocessing import normalize

import apollo_config
from services import storage


@dataclass
class JobStatus:
    job_id: str
    state: str  # "pending" | "running" | "done" | "error"
    progress: float  # 0.0 .. 1.0
    message: str
    started_at: float
    updated_at: float
    cache_key: str | None
    total: int
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _write_status(status: JobStatus) -> None:
    """status.json を atomic rename で書き出す。

    Streamlit の読み取りスレッドと worker スレッドの間で半端な JSON が
    読まれないようにするため、`tmp` ファイル → `rename` で差し替える。
    """
    status.updated_at = time.time()
    path = storage.job_status_file(status.job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status.to_dict(), ensure_ascii=False, indent=2))
    tmp.replace(path)


def read_status(job_id: str) -> JobStatus | None:
    """指定ジョブの現在ステータスを読み込む。存在しなければ None。"""
    path = storage.job_status_file(job_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return JobStatus(**data)
    except Exception:  # noqa: BLE001
        return None


def list_active_jobs() -> list[JobStatus]:
    """pending / running 状態のジョブを一覧する（サイドバー表示・復元用）。"""
    if not apollo_config.IS_PRIVATE or not apollo_config.JOBS_DIR.exists():
        return []
    active = []
    for jd in apollo_config.JOBS_DIR.iterdir():
        st = read_status(jd.name)
        if st and st.state in ("pending", "running"):
            active.append(st)
    return active


def start_embedding_job(
    texts: list[str],
    source_name: str,
    backend,  # EmbeddingBackend
    batch_size: int = 128,
) -> str:
    """埋め込み計算ジョブをバックグラウンドで起動する。

    返り値は `job_id`（12 桁 hex）。UI 側はこれを `session_state` に保持し、
    `read_status(job_id)` で進捗を観測する。

    キャッシュヒット時もジョブオブジェクトを作ってから即座に done にするので
    呼び出し側は常に「ジョブ経由」の単一フローで処理できる。
    """
    job_id = uuid.uuid4().hex[:12]
    cache_key = backend.compute_cache_key(texts, source_name)
    status = JobStatus(
        job_id=job_id,
        state="pending",
        progress=0.0,
        message="ジョブ起動中...",
        started_at=time.time(),
        updated_at=time.time(),
        cache_key=cache_key,
        total=len(texts),
    )
    _write_status(status)

    def worker() -> None:
        try:
            status.state = "running"
            status.message = "キャッシュ確認中..."
            _write_status(status)

            # キャッシュヒット確認
            cached = backend.load_from_cache(cache_key)
            if cached is not None:
                status.progress = 1.0
                status.message = f"キャッシュヒット ({cached.shape[0]} 件)"
                status.state = "done"
                _write_status(status)
                return

            # バッチ埋め込み（バッチ完了ごとに progress 更新）
            status.message = f"埋め込み計算中... (0/{len(texts)})"
            _write_status(status)

            embeddings_list: list[np.ndarray] = []
            total = len(texts)
            for i in range(0, total, batch_size):
                batch = texts[i : i + batch_size]
                embeddings_list.append(backend._encode_batch_raw(batch))
                done_count = min(i + batch_size, total)
                status.progress = done_count / total
                status.message = f"埋め込み計算中... ({done_count}/{total})"
                _write_status(status)

            arr = np.vstack(embeddings_list)
            arr = normalize(arr, norm="l2")
            backend.save_to_cache(cache_key, arr)

            status.state = "done"
            status.progress = 1.0
            status.message = f"完了 ({arr.shape[0]} 件)"
            _write_status(status)
        except Exception as e:  # noqa: BLE001
            status.state = "error"
            status.error = str(e)
            status.message = f"エラー: {str(e)[:120]}"
            _write_status(status)

    t = threading.Thread(target=worker, daemon=True, name=f"apollo-embed-{job_id}")
    t.start()
    return job_id
