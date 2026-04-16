"""capcom のモンキーパッチによるレポート素材ミラー書き込み (v7.0-private.2 Track B)。

`apollo_bootstrap.init()` が private モード起動時に `install_all_hooks()` を
呼び、`capcom.save_*` 系の関数を wrap する。元の session_state 書き込みに加え、
アクティブプロジェクトの `projects/<active>/store/` 配下にもディスク書き込み
する (レポート素材の自動永続化)。

## 永続化レイアウト

::

    projects/<active>/store/
    ├── snapshots/
    │   ├── metadata.json                    # save_metadata が書く
    │   └── {snap_id}_{index}.png            # save_snapshot_image が書く
    ├── data/
    │   ├── atlas_statistics.json            # save_data (dict)
    │   ├── saturnv_clusters.json
    │   └── patents.csv                      # save_data(bytes) or save_patents_csv
    ├── prompts/
    │   └── *.md                             # save_prompt
    └── voyager/
        ├── mission.json                     # save_voyager_mission
        ├── context.json                     # save_voyager_context
        └── evidence/
            └── *.json                       # save_voyager_evidence

## 失敗の扱い
- ミラー書き込み失敗は分析をブロックしない (session_state への保存は成功する)
- アクティブプロジェクトが解決できない場合は default にフォールバック
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import apollo_config


_installed = False


def install_all_hooks() -> None:
    """capcom モンキーパッチを 1 度だけ適用する (冪等)。hosted では no-op。"""
    global _installed
    if _installed:
        return
    if not apollo_config.IS_PRIVATE:
        return
    try:
        _install_capcom_hooks()
    except Exception:  # noqa: BLE001
        # capcom import 失敗等は握り潰す (hosted fallback で VOYAGER は動く)
        return
    _installed = True


# ==================================================================
# パス解決 / ファイル書き込みヘルパ
# ==================================================================


def _store_dir(subdir: str) -> Path | None:
    """projects/<active>/store/<subdir>/ を返す。失敗時は None。"""
    try:
        from services import projects

        root = projects.project_store_dir() / subdir
        root.mkdir(parents=True, exist_ok=True)
        return root
    except Exception:  # noqa: BLE001
        return None


def _write_bytes(subdir: str, filename: str, data: bytes) -> None:
    d = _store_dir(subdir)
    if d is None:
        return
    try:
        (d / filename).write_bytes(data)
    except OSError:
        pass


def _write_json(subdir: str, filename: str, data: Any) -> None:
    d = _store_dir(subdir)
    if d is None:
        return
    try:
        with open(d / filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    except (OSError, TypeError, ValueError):
        pass


def _write_text(subdir: str, filename: str, text: str) -> None:
    d = _store_dir(subdir)
    if d is None:
        return
    try:
        (d / filename).write_text(text, encoding="utf-8")
    except OSError:
        pass


# ==================================================================
# capcom のモンキーパッチ
# ==================================================================


def _install_capcom_hooks() -> None:
    import capcom

    # --- save_snapshot_image ---
    _orig_save_snapshot_image = capcom.save_snapshot_image

    def save_snapshot_image(snap_id, image_bytes, index=None):
        result = _orig_save_snapshot_image(snap_id, image_bytes, index=index)
        if image_bytes:
            safe_id = capcom._sanitize_filename(snap_id)
            key = f"{safe_id}_{index}" if index is not None else safe_id
            _write_bytes("snapshots", f"{key}.png", image_bytes)
        return result

    capcom.save_snapshot_image = save_snapshot_image

    # --- save_metadata ---
    _orig_save_metadata = capcom.save_metadata

    def save_metadata(snapshots_list):
        _orig_save_metadata(snapshots_list)
        store = capcom._get_store()
        if store and "metadata" in store:
            _write_json("snapshots", "metadata.json", store["metadata"])

    capcom.save_metadata = save_metadata

    # --- save_prompt ---
    _orig_save_prompt = capcom.save_prompt

    def save_prompt(filename, prompt_text):
        _orig_save_prompt(filename, prompt_text)
        if not prompt_text:
            return
        if not filename.endswith(".md"):
            filename = filename + ".md"
        safe = capcom._sanitize_filename(filename)
        _write_text("prompts", safe, prompt_text)

    capcom.save_prompt = save_prompt

    # --- save_data ---
    _orig_save_data = capcom.save_data

    def save_data(filename, data):
        _orig_save_data(filename, data)
        if data is None:
            return
        # save_data の仕様: dict なら .json、ただし save_patents_csv 経由で
        # bytes が渡されるケースもある (patents.csv)
        if isinstance(data, (bytes, bytearray)):
            safe = capcom._sanitize_filename(filename)
            _write_bytes("data", safe, bytes(data))
        else:
            fn = filename if filename.endswith(".json") else filename + ".json"
            safe = capcom._sanitize_filename(fn)
            _write_json("data", safe, data)

    capcom.save_data = save_data

    # --- save_voyager_mission ---
    _orig_save_voyager_mission = capcom.save_voyager_mission

    def save_voyager_mission(mission_data):
        _orig_save_voyager_mission(mission_data)
        if mission_data is not None:
            _write_json("voyager", "mission.json", mission_data)

    capcom.save_voyager_mission = save_voyager_mission

    # --- save_voyager_context ---
    _orig_save_voyager_context = capcom.save_voyager_context

    def save_voyager_context(context_data):
        _orig_save_voyager_context(context_data)
        if context_data is not None:
            _write_json("voyager", "context.json", context_data)

    capcom.save_voyager_context = save_voyager_context

    # --- save_voyager_evidence ---
    _orig_save_voyager_evidence = capcom.save_voyager_evidence

    def save_voyager_evidence(filename, evidence_data):
        _orig_save_voyager_evidence(filename, evidence_data)
        if evidence_data is None:
            return
        fn = filename if filename.endswith(".json") else filename + ".json"
        safe = capcom._sanitize_filename(fn)
        # voyager/evidence/ サブディレクトリ
        d = _store_dir("voyager/evidence")
        if d is None:
            return
        try:
            with open(d / safe, "w", encoding="utf-8") as f:
                json.dump(evidence_data, f, ensure_ascii=False, indent=2, default=str)
        except (OSError, TypeError, ValueError):
            pass

    capcom.save_voyager_evidence = save_voyager_evidence

    # --- save_patents_csv ---
    # 直接 store['data']['patents.csv'] = csv_bytes を書くので、
    # original 完了後に session_state から csv_bytes を拾って書き出す。
    _orig_save_patents_csv = capcom.save_patents_csv

    def save_patents_csv():
        _orig_save_patents_csv()
        store = capcom._get_store()
        if store is None:
            return
        csv_bytes = store.get("data", {}).get("patents.csv")
        if isinstance(csv_bytes, (bytes, bytearray)):
            _write_bytes("data", "patents.csv", bytes(csv_bytes))

    capcom.save_patents_csv = save_patents_csv


# ==================================================================
# Track L: 再起動後のディスクからの session_state 再復元
# ==================================================================


def hydrate_from_disk() -> dict:
    """プロジェクト store/ 配下の永続データから session_state を再構築する。

    再起動や session_state.clear() で失われた snapshot / data / prompts /
    voyager を disk から読み戻す。`st.session_state['snapshots']` と
    `capcom_store` の両方を更新する。

    冪等: 既にデータが入っている session_state は上書きしない (metadata 側の
    size 比較で判断)。

    戻り値: 読み戻した件数のサマリ {"snapshots": N, "data": N, ...}
    """
    summary: dict = {"snapshots": 0, "data": 0, "prompts": 0, "voyager": 0}
    if not apollo_config.IS_PRIVATE:
        return summary
    try:
        import streamlit as st

        from services import projects
    except Exception:  # noqa: BLE001
        return summary

    try:
        store_dir = projects.project_store_dir()
    except Exception:  # noqa: BLE001
        return summary
    if not store_dir.exists():
        return summary

    # --- snapshots を session_state['snapshots'] として再構築 ---
    snap_dir = store_dir / "snapshots"
    if snap_dir.exists() and not st.session_state.get("snapshots"):
        summary["snapshots"] = _hydrate_snapshots(snap_dir, st)

    # --- capcom_store.data を再投入 ---
    data_dir = store_dir / "data"
    if data_dir.exists():
        summary["data"] = _hydrate_capcom_data(data_dir, st)

    # --- capcom_store.prompts ---
    prompts_dir = store_dir / "prompts"
    if prompts_dir.exists():
        summary["prompts"] = _hydrate_capcom_prompts(prompts_dir, st)

    # --- capcom_store.voyager (mission / context / evidence) ---
    voyager_dir = store_dir / "voyager"
    if voyager_dir.exists():
        summary["voyager"] = _hydrate_capcom_voyager(voyager_dir, st)

    return summary


def _hydrate_snapshots(snap_dir, st) -> int:
    """store/snapshots/ → session_state['snapshots'] を復元。"""
    import json as _json

    meta_path = snap_dir / "metadata.json"
    if not meta_path.exists():
        return 0
    try:
        meta = _json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    snaps_meta = meta.get("snapshots") if isinstance(meta, dict) else None
    if not snaps_meta:
        return 0

    restored = []
    for snap in snaps_meta:
        if not isinstance(snap, dict):
            continue
        sid = snap.get("id")
        if not sid:
            continue
        # snap_id_{index}.png を列挙
        pngs = sorted(snap_dir.glob(f"{sid}_*.png"))
        if not pngs:
            single = snap_dir / f"{sid}.png"
            if single.exists():
                pngs = [single]
        images = [p.read_bytes() for p in pngs]
        restored_snap = dict(snap)  # shallow copy of metadata
        restored_snap["images"] = images
        restored.append(restored_snap)

    if restored:
        st.session_state["snapshots"] = restored
    return len(restored)


def _hydrate_capcom_data(data_dir, st) -> int:
    """store/data/ → capcom_store['data'] を復元。"""
    import json as _json

    store = _session_capcom_store(st)
    if store is None:
        return 0
    count = 0
    for p in data_dir.iterdir():
        if not p.is_file():
            continue
        name = p.name
        if name in store["data"]:
            continue  # already present in memory
        try:
            if name.endswith(".json"):
                store["data"][name] = _json.loads(p.read_text(encoding="utf-8"))
            else:
                store["data"][name] = p.read_bytes()
            count += 1
        except (OSError, ValueError):
            continue
    return count


def _hydrate_capcom_prompts(prompts_dir, st) -> int:
    store = _session_capcom_store(st)
    if store is None:
        return 0
    count = 0
    for p in prompts_dir.iterdir():
        if not p.is_file() or not p.name.endswith(".md"):
            continue
        if p.name in store["prompts"]:
            continue
        try:
            store["prompts"][p.name] = p.read_text(encoding="utf-8")
            count += 1
        except OSError:
            continue
    return count


def _hydrate_capcom_voyager(voyager_dir, st) -> int:
    import json as _json

    store = _session_capcom_store(st)
    if store is None:
        return 0
    count = 0
    for name in ("mission.json", "context.json"):
        p = voyager_dir / name
        if p.exists():
            try:
                key = name.replace(".json", "")
                if store["voyager"].get(key) is None:
                    store["voyager"][key] = _json.loads(p.read_text(encoding="utf-8"))
                    count += 1
            except (OSError, ValueError):
                pass
    ev_dir = voyager_dir / "evidence"
    if ev_dir.exists():
        for p in ev_dir.iterdir():
            if not p.is_file() or not p.name.endswith(".json"):
                continue
            if p.name in store["voyager"]["evidence"]:
                continue
            try:
                store["voyager"]["evidence"][p.name] = _json.loads(p.read_text(encoding="utf-8"))
                count += 1
            except (OSError, ValueError):
                continue
    return count


def _session_capcom_store(st):
    """capcom_store を返す (無ければ None)。"""
    try:
        store = st.session_state.get("capcom_store")
        if isinstance(store, dict) and "data" in store:
            return store
    except Exception:  # noqa: BLE001
        pass
    return None
