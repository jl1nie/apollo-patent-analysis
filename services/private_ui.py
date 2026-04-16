"""APOLLO Private 専用 UI コンポーネント。

Home.py の編集量を最小化するため、private モード固有の重い UI ブロックを
ここに集約する。Home.py からは `if apollo_config.IS_PRIVATE: ...` ガードで
1 行関数呼び出しするだけで済む。また `apollo_bootstrap.init()` が
`utils.render_sidebar` をモンキーパッチしてサイドバー下部に
`render_sidebar_extras()` を自動で流し込むため、v7 本体のサイドバー
コードには一切手を入れずに「モデル選択 / キャッシュサマリ / 外部接続バッジ」
を追加できる。

すべての関数は private モード以外では即座に return するので、ガードを忘れても
副作用ゼロ (= hosted モードへの影響なし)。
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

import apollo_config


def render_patent_picker_section() -> None:
    """特許タブの最上部に表示するプロジェクトダッシュボード + サーバファイル picker。

    v7.0-private.2 からは以下を 1 つの expander にまとめる:
    - プロジェクトサマリ (名前・埋め込みモデル・Mission Objective・作成日)
    - タブ別詳細 (Files / Snapshots / CAPCOM Data / Reports)
    - サーバ保存ファイルからのロード UI (従来機能を維持)
    """
    if not apollo_config.IS_PRIVATE:
        return

    _render_project_dashboard()

    from services import server_files as srv
    from services import analysis_state as st_state

    server_files = srv.list_files("patent")
    with st.expander(
        f"📁 サーバ保存ファイルから読み込む ({len(server_files)} 件)",
        expanded=bool(server_files),
    ):
        # 読み込み成功時の flash メッセージ (rerun を跨いで 1 回だけ表示)
        _flash = st.session_state.pop("_picker_flash", None)
        if _flash:
            getattr(st, _flash[0])(_flash[1])

        # 直近で読み込んだ DataFrame のプレビュー (server picker 経由で読んだ場合)
        if (
            st.session_state.get("filename")
            and st.session_state.get("df_main") is not None
            and st.session_state.get("_loaded_via") == "server_picker"
        ):
            _df = st.session_state["df_main"]
            _badge = "前処理復元済" if st.session_state.get("preprocess_done") else "未前処理"
            st.caption(
                f"📋 現在ロード中: **{st.session_state['filename']}** "
                f"({len(_df)} 行 / {_badge})"
            )
            st.dataframe(_df.head(), use_container_width=True)

        if not server_files:
            st.caption(
                "まだサーバに保存されたファイルはありません。下のアップローダから D&D してください。"
                "アップロードしたファイルは自動的にここに保存されます。"
            )
            return

        labels = {}
        for p in server_files:
            badge = "✅ 前処理済 " if st_state.has_state("patent", p.name) else ""
            labels[p.name] = f"{badge}{p.name}"

        picked = st.selectbox(
            "ファイル",
            options=[p.name for p in server_files],
            format_func=lambda n: labels[n],
            key="server_patent_picker",
        )
        has_state = st_state.has_state("patent", picked)

        if has_state:
            st.caption(
                "✅ このファイルには前処理結果 (埋め込み + TF-IDF) が保存されています。"
                "どちらの読み込み方を選びますか？"
            )
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "✅ 前処理結果を復元",
                    key="server_patent_load_state",
                    type="primary",
                    help="保存された埋め込み・TF-IDF をそのまま読み込み、各分析モジュールに即座に進めます。",
                ):
                    _do_load(picked, srv, st_state, restore_state=True)
            with c2:
                if st.button(
                    "📄 CSV のみ読み込み (再前処理)",
                    key="server_patent_load_csv",
                    help="CSV だけを読み込みます。前処理結果は無視され、「分析エンジン起動」で再計算します。",
                ):
                    _do_load(picked, srv, st_state, restore_state=False)
        else:
            if st.button("📂 読み込み", key="server_patent_load", type="primary"):
                _do_load(picked, srv, st_state, restore_state=False)

        st.markdown("---")
        d1, d2 = st.columns(2)
        with d1:
            if has_state and st.button(
                "♻️ 前処理結果のみ削除",
                key="server_patent_delete_state",
                help="CSV ファイル本体は残し、保存された埋め込み・TF-IDF だけを削除します。",
            ):
                st_state.delete_state("patent", picked)
                st.success("前処理結果を削除しました。")
                st.rerun()
        with d2:
            if st.button(
                "🗑️ ファイル削除 (前処理結果も含む)",
                key="server_patent_delete",
            ):
                srv.delete_file("patent", picked)
                st_state.delete_state("patent", picked)
                st.success(f"'{picked}' を削除しました。")
                st.rerun()


def _do_load(picked: str, srv, st_state, restore_state: bool) -> None:
    """selectbox から選ばれたファイルを session_state に展開する内部処理。

    `restore_state=True` なら CSV に加えて pickle 化された前処理結果 (埋め込み /
    TF-IDF / col_map / delimiters) も session_state に復元する。`False` なら CSV
    のみ読み込み、ユーザは改めて「分析エンジン起動」で再前処理を行う。
    """
    bio = srv.load_as_bytesio("patent", picked)
    if bio is None:
        st.error("ファイルが見つかりません。")
        return

    try:
        if picked.lower().endswith(".csv"):
            try:
                df = pd.read_csv(bio, dtype=str)
            except UnicodeDecodeError:
                bio.seek(0)
                df = pd.read_csv(bio, dtype=str, encoding="shift_jis")
        else:
            df = pd.read_excel(bio, dtype=str)

        st.session_state.df_main = df
        st.session_state["shared_df"] = df
        st.session_state["filename"] = picked
        st.session_state.preprocess_done = False
        st.session_state["_loaded_via"] = "server_picker"

        if restore_state:
            saved = st_state.load_state("patent", picked)
            if not saved:
                st.session_state["_picker_flash"] = (
                    "warning",
                    "前処理結果ファイルが見つかりません。CSV のみ読み込みました。",
                )
            else:
                for k, v in saved.items():
                    if v is not None:
                        st.session_state[k] = v
                st.session_state["shared_df"] = st.session_state.get("df_main", df)
                st.session_state.preprocess_done = True
                st.session_state["_picker_flash"] = (
                    "success",
                    f"'{picked}' を読み込み、前処理結果を復元しました "
                    f"({len(st.session_state.df_main)}行)。各分析モジュールにそのまま進めます。",
                )
        else:
            st.session_state["_picker_flash"] = (
                "success",
                f"サーバ内ファイル '{picked}' を読み込みました ({len(df)}行)。"
                "「前処理実行」タブで分析エンジンを起動してください。",
            )

        st.rerun()
    except Exception as e:  # noqa: BLE001
        st.error(f"読み込みエラー: {e}")


def persist_uploaded_file(uploaded_file) -> None:
    """ブラウザからアップロードされたファイルを named volume に保存する。

    private モード以外では何もしない。Streamlit rerun 毎に呼ばれても
    上書きで idempotent なので副作用は無視できる。
    """
    if not apollo_config.IS_PRIVATE or uploaded_file is None:
        return
    from services import server_files as srv

    try:
        srv.save_bytes("patent", uploaded_file.name, uploaded_file.getvalue())
    except Exception as e:  # noqa: BLE001
        st.warning(f"サーバ保存に失敗: {e}")


def persist_analysis_state(
    df, sbert_embeddings, tfidf_matrix, feature_names, col_map, delimiters
) -> None:
    """前処理完了時に session_state の重要部分を pickle 保存する。

    private モード以外では何もしない。失敗しても処理を止めない (warning のみ)。
    NPL データ (`df_npl`, `df_npl_accumulated`) は呼び出し元からは渡されないが、
    session_state から直接拾って保存対象に含める (NEBULA 復元のため)。
    """
    if not apollo_config.IS_PRIVATE:
        return
    from services import analysis_state as st_state

    try:
        st_state.save_state(
            "patent",
            st.session_state.get("filename", "unnamed"),
            {
                "df_main": df,
                "df_npl": st.session_state.get("df_npl"),
                "df_npl_accumulated": st.session_state.get("df_npl_accumulated"),
                "sbert_embeddings": sbert_embeddings,
                "tfidf_matrix": tfidf_matrix,
                "feature_names": feature_names,
                "col_map": col_map,
                "delimiters": delimiters,
            },
        )
    except Exception as e:  # noqa: BLE001
        st.warning(f"前処理結果の保存に失敗 (機能には影響なし): {e}")


# ==================================================================
# content_key ベースの cache index テーブル
# ==================================================================


def _render_project_dashboard() -> None:
    """アクティブプロジェクトの全体サマリ + タブ別詳細を描画する。"""
    from services import projects

    active = projects.get_active()
    cfg = projects.get_config(active)
    if not cfg:
        # default が未作成 (起動直後など) なら skip — migration が次回で埋める
        return

    name = cfg.get("name", active)
    embed_model = cfg.get("embedding_model", "?")
    mission = cfg.get("mission_objective", "")
    created_at = cfg.get("created_at", "")[:10]
    updated_at = cfg.get("updated_at", "")

    header = f"📂 プロジェクト: {name}  |  埋め込み: `{embed_model}`"
    with st.expander(header, expanded=True):
        c1, c2, c3 = st.columns([2, 2, 3])
        c1.caption(f"作成: {created_at}")
        c2.caption(f"最終更新: {_relative_time(_parse_iso(updated_at))}")
        c3.caption(f"📁 ファイル: {cfg.get('file_count', '-')} / 🧪 state: {cfg.get('state_count', '-')}")

        new_mission = st.text_area(
            "Mission Objective",
            value=mission,
            key=f"proj_mission_{active}",
            height=70,
            help="プロジェクトの目的。VOYAGER レポート生成時の Mission Objective の既定値になります。",
        )
        if new_mission != mission and st.button(
            "💾 Mission Objective を保存",
            key=f"save_mission_{active}",
            use_container_width=False,
        ):
            projects.update_config(active, mission_objective=new_mission)
            st.success("保存しました")
            st.rerun()

        tab_files, tab_snaps, tab_data, tab_reports = st.tabs(
            ["📁 ファイル", "📸 Snapshots", "📊 CAPCOM Data", "📝 Reports"]
        )

        with tab_files:
            _render_project_files_tab(active)
        with tab_snaps:
            _render_project_snapshots_tab(active)
        with tab_data:
            _render_project_data_tab(active)
        with tab_reports:
            _render_project_reports_tab(active)


def _parse_iso(iso: str) -> float:
    """ISO フォーマット文字列を epoch 秒に変換 (失敗時は 0)。"""
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return 0.0


def _render_project_files_tab(active: str) -> None:
    """プロジェクト配下の全種別ファイル一覧をバッジ付きで表示する。"""
    from services import analysis_state as st_state
    from services import projects

    st.caption("プロジェクトの files/ 配下の全ファイル。特許以外はアップロード UI が Home.py NPL タブにあります。")

    # 種別ごとに一覧
    for kind, label in [
        ("patents", "特許"),
        ("academic", "学術論文"),
        ("news", "ニュース"),
        ("market", "マーケット"),
        ("policy", "政策"),
    ]:
        d = projects.project_files_dir(kind, active)
        if not d.exists():
            continue
        files = sorted([p for p in d.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
        if not files:
            continue
        with st.container():
            st.markdown(f"**{label} ({len(files)} 件)**")
            for p in files:
                mtime = p.stat().st_mtime
                size_kb = p.stat().st_size / 1024
                badge = ""
                # 特許のみ前処理済判定
                if kind == "patents" and st_state.has_state("patent", p.name):
                    badge = " ✅ 前処理済"
                cols = st.columns([5, 1, 1, 1])
                cols[0].caption(f"📄 {p.name}{badge}")
                cols[1].caption(f"{size_kb:.0f} KB")
                cols[2].caption(_relative_time(mtime))
                with cols[3]:
                    if st.button("削除", key=f"del_file_{active}_{kind}_{p.name}"):
                        try:
                            p.unlink()
                            if kind == "patents":
                                st_state.delete_state("patent", p.name)
                            st.success(f"'{p.name}' を削除しました")
                            st.rerun()
                        except OSError as e:
                            st.error(f"削除失敗: {e}")
    # 前処理キャッシュ (従来の matrix 表示)
    st.markdown("---")
    _render_cache_index_table()


def _render_project_snapshots_tab(active: str) -> None:
    """store/snapshots/*.png の一覧をサムネイル付きで表示する。"""
    from services import projects

    d = projects.project_store_dir(active) / "snapshots"
    if not d.exists():
        st.caption("まだスナップショットはありません。各分析モジュールで 📸 ボタンを押すと自動保存されます。")
        return
    pngs = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not pngs:
        st.caption("まだスナップショットはありません。")
        return
    st.caption(f"{len(pngs)} 件のスナップショットを保存済み")
    # 3 列グリッドで表示 (最初の 12 件まで)
    for i in range(0, min(len(pngs), 12), 3):
        cols = st.columns(3)
        for j, p in enumerate(pngs[i : i + 3]):
            with cols[j]:
                st.image(str(p), caption=p.stem, use_container_width=True)
    if len(pngs) > 12:
        st.caption(f"... 他 {len(pngs) - 12} 件")


def _render_project_data_tab(active: str) -> None:
    """store/data/*.json の一覧を表示する。"""
    from services import projects

    d = projects.project_store_dir(active) / "data"
    if not d.exists():
        st.caption("まだ CAPCOM データはありません。各分析モジュールを実行すると自動保存されます。")
        return
    files = sorted([p for p in d.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        st.caption("まだ CAPCOM データはありません。")
        return
    st.caption(f"{len(files)} 件の分析結果データを保存済み")
    for p in files:
        mtime = p.stat().st_mtime
        size_kb = p.stat().st_size / 1024
        cols = st.columns([5, 1, 1])
        cols[0].caption(f"📊 {p.name}")
        cols[1].caption(f"{size_kb:.1f} KB")
        cols[2].caption(_relative_time(mtime))


def _render_project_reports_tab(active: str) -> None:
    """reports/ 配下の生成済みレポートを一覧表示する。"""
    from services import projects

    d = projects.project_reports_dir(active)
    if not d.exists():
        st.caption("まだレポートはありません。VOYAGER / CAPCOM で生成するとここに保存されます。")
        return
    files = sorted([p for p in d.iterdir() if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        st.caption("まだレポートはありません。")
        return
    st.caption(f"{len(files)} 件のレポートを保存済み")
    for p in files:
        mtime = p.stat().st_mtime
        size_kb = p.stat().st_size / 1024
        cols = st.columns([5, 1, 1, 1])
        cols[0].caption(f"📝 {p.name}")
        cols[1].caption(f"{size_kb:.1f} KB")
        cols[2].caption(_relative_time(mtime))
        with cols[3]:
            try:
                st.download_button(
                    "↓",
                    data=p.read_bytes(),
                    file_name=p.name,
                    key=f"dl_report_{active}_{p.name}",
                    use_container_width=True,
                )
            except OSError:
                pass


def _render_cache_index_table() -> None:
    """前処理済みキャッシュを {ファイル × モデル} のテーブルで表示する。

    同じ CSV を異なる埋め込みモデルで前処理すると別行になる。各行に「復元」
    「削除」ボタン。削除時は pickle に加えて対応する npy キャッシュも掃除する。

    v7.0-private.2 からはダッシュボード expander 内から呼ばれるため、自身は expander を
    使わず見出し + 内容のみで描画する (nested expander エラー回避)。
    """
    from services import analysis_state as st_state

    items = st_state.list_sessions(label="patent")
    st.markdown(f"**🗃️ 前処理済みキャッシュ ({len(items)} 件)**")
    if not items:
        st.caption(
            "まだ前処理済みキャッシュはありません。CSV をアップロードして"
            "「前処理実行」タブで分析エンジンを起動すると、モデル別に自動保存されます。"
        )
        return

    st.caption(
        "💡 同じ CSV を異なる埋め込みモデルで前処理すると、モデル別に別行として"
        "保存されます。サイドバーからモデルを切り替えて再前処理すると増えていきます。"
    )

    # 列見出し
    h1, h2, h3, h4, h5, h6 = st.columns([3, 3, 1, 1, 1, 2])
    h1.markdown("**ファイル**")
    h2.markdown("**埋め込みモデル**")
    h3.markdown("**行数**")
    h4.markdown("**サイズ**")
    h5.markdown("**更新**")
    h6.markdown("**操作**")

    for it in items:
        ck = it["content_key"]
        fname = it.get("filename", "?")
        mid = it.get("model_id", "?")
        rows = it.get("rows", 0)
        size_mb = it.get("size_mb") or 0
        mtime = it.get("mtime") or 0

        c1, c2, c3, c4, c5, c6 = st.columns([3, 3, 1, 1, 1, 2])
        c1.caption(fname)
        c2.caption(mid)
        c3.caption(f"{rows:,}" if rows else "-")
        c4.caption(f"{size_mb:.1f} MB" if size_mb else "-")
        c5.caption(_relative_time(mtime))

        with c6:
            b1, b2 = st.columns(2)
            with b1:
                if st.button("復元", key=f"cache_restore_{ck}", use_container_width=True):
                    _restore_from_cache(ck, fname)
            with b2:
                if st.button("削除", key=f"cache_delete_{ck}", use_container_width=True):
                    _delete_cache_entry(ck)
                    st.rerun()


def _relative_time(ts: float) -> str:
    """1h ago / 2d ago のような短い相対時刻。"""
    if not ts:
        return "-"
    try:
        delta = datetime.now().timestamp() - ts
        if delta < 60:
            return "just now"
        if delta < 3600:
            return f"{int(delta / 60)}m ago"
        if delta < 86400:
            return f"{int(delta / 3600)}h ago"
        return f"{int(delta / 86400)}d ago"
    except Exception:  # noqa: BLE001
        return "-"


def _restore_from_cache(content_key: str, filename: str) -> None:
    """content_key を指定して pkl を session_state に展開する。

    `_do_load` の state 復元パスを流用する。CSV 本体は server_files から再読込、
    無ければ pkl に保存された df_main を使う。
    """
    from services import analysis_state as st_state
    from services import server_files as srv

    saved = st_state.load_state_by_key("patent", content_key)
    if not saved:
        st.error("キャッシュが見つかりません。削除されている可能性があります。")
        return

    df_pkl = saved.get("df_main")

    # CSV 本体をサーバから読む (UI 上の「現在ロード中」ファイルプレビュー用)
    bio = srv.load_as_bytesio("patent", filename) if filename else None
    if bio is not None:
        try:
            if filename.lower().endswith(".csv"):
                try:
                    df_raw = pd.read_csv(bio, dtype=str)
                except UnicodeDecodeError:
                    bio.seek(0)
                    df_raw = pd.read_csv(bio, dtype=str, encoding="shift_jis")
            else:
                df_raw = pd.read_excel(bio, dtype=str)
            st.session_state["_raw_df"] = df_raw
        except Exception:  # noqa: BLE001
            pass

    # 前処理済みの df_main を優先して session_state に展開
    display_df = df_pkl if df_pkl is not None else st.session_state.get("_raw_df")
    if display_df is None:
        st.error("復元対象の DataFrame が見つかりません。")
        return

    for k, v in saved.items():
        if v is not None:
            st.session_state[k] = v

    st.session_state["shared_df"] = st.session_state.get("df_main", display_df)
    st.session_state["filename"] = filename or "cached"
    st.session_state["_loaded_via"] = "cache_index"
    st.session_state["_patent_content_key"] = content_key
    st.session_state.preprocess_done = True
    st.session_state["_picker_flash"] = (
        "success",
        f"'{filename}' の前処理結果を復元しました "
        f"({len(st.session_state.get('df_main', display_df))}行)。",
    )
    st.rerun()


def _delete_cache_entry(content_key: str) -> None:
    """pkl + 対応する npy キャッシュを削除する。

    npy キャッシュは複数のテキスト列組み合わせで 2 件以上作られうるので、
    ファイル名に含まれる content_key ヒットだけでは特定できない。厳密な
    削除ができないため、現状は pkl + index.json エントリのみ削除する。
    npy 側は `sidebar extras` の「🗑️ npy キャッシュを一括削除」で掃除できる。
    """
    from services import analysis_state as st_state

    st_state.delete_state_by_key("patent", content_key)


# ==================================================================
# サイドバー extras (model selector + cache summary + external badge)
# ==================================================================


def render_sidebar_extras() -> None:
    """サイドバー下部に常駐させる private 機能の一式。

    `apollo_bootstrap.init()` が `utils.render_sidebar` をモンキーパッチして
    呼び出す。hosted モードでは即座に return するので副作用ゼロ。
    """
    if not apollo_config.IS_PRIVATE:
        return

    with st.sidebar:
        st.markdown("---")
        st.markdown("##### 🔒 Private Edition")
        _render_project_selector()
        _render_model_selector()
        _render_cache_summary()
        from services import airgap

        airgap.render_external_access_badge()
        _render_session_diagnostic()


def _render_project_selector() -> None:
    """プロジェクト切替 selectbox + 新規作成 form。

    - 現在のアクティブプロジェクトを selectbox でデフォルト表示
    - 切替時は analysis 系 session_state をクリアして rerun
    - 「➕ 新規作成」で expander 内のフォームから create_project を呼ぶ
    """
    from services import projects, lm_studio_models

    all_projects = projects.list_projects()
    active = projects.get_active()

    if not all_projects:
        # 起動直後で default が未作成の場合
        st.caption("プロジェクトが初期化中です…")
        return

    # active が list に含まれるよう保証
    ids = [p["project_id"] for p in all_projects]
    labels = {p["project_id"]: p["name"] for p in all_projects}
    if active not in ids:
        # 整合性取れない場合は先頭に fallback
        active = ids[0]
        projects.set_active(active)

    picked = st.selectbox(
        "📂 プロジェクト",
        options=ids,
        index=ids.index(active),
        format_func=lambda pid: labels.get(pid, pid),
        key="apollo_project_selector",
    )
    if picked != active:
        _switch_project(picked)

    # 新規作成 / 削除
    c1, c2 = st.columns(2)
    with c1:
        if st.button("➕ 新規", key="proj_new_btn", use_container_width=True):
            st.session_state["_show_proj_create"] = True
    with c2:
        if st.button("🗑️ 削除", key="proj_del_btn", use_container_width=True, disabled=(active == apollo_config.DEFAULT_PROJECT_ID)):
            st.session_state["_show_proj_delete"] = True

    if st.session_state.get("_show_proj_create"):
        _render_project_create_form()
    if st.session_state.get("_show_proj_delete") and active != apollo_config.DEFAULT_PROJECT_ID:
        _render_project_delete_confirm(active)


def _render_project_create_form() -> None:
    """新規プロジェクト作成フォーム (expander 内にインライン表示)。"""
    from services import projects, lm_studio_models

    with st.expander("➕ 新規プロジェクト作成", expanded=True):
        name = st.text_input("プロジェクト名", key="proj_create_name", placeholder="例: CNF 特許分析")

        models = lm_studio_models.fetch_models()
        embed_ids, chat_ids = lm_studio_models.split_embed_chat(models)

        embed_default = embed_ids[0] if embed_ids else apollo_config.EMBEDDING_MODEL
        chat_default = chat_ids[0] if chat_ids else apollo_config.CHAT_MODEL

        embed_choice = st.selectbox(
            "埋め込みモデル (作成後は変更不可)",
            embed_ids or [embed_default],
            key="proj_create_embed",
            help="プロジェクトのベクトル空間を決める固定モデル。同じ CSV でも別モデルで分析したい場合は別プロジェクトを作成してください。",
        )
        chat_choice = st.selectbox(
            "推論モデル (VOYAGER 既定値、後から変更可)",
            chat_ids or [chat_default],
            key="proj_create_chat",
        )
        description = st.text_input("説明 (任意)", key="proj_create_desc")
        mission = st.text_area(
            "Mission Objective (任意)",
            key="proj_create_mission",
            height=70,
            placeholder="このプロジェクトで達成したい分析目的",
        )

        c1, c2 = st.columns(2)
        with c1:
            if st.button("作成", key="proj_create_submit", type="primary", use_container_width=True, disabled=not name.strip()):
                try:
                    pid = projects.create_project(
                        name=name.strip(),
                        embedding_model=embed_choice,
                        chat_model=chat_choice,
                        description=description,
                        mission_objective=mission,
                    )
                    st.success(f"プロジェクト '{pid}' を作成しました")
                    st.session_state.pop("_show_proj_create", None)
                    _switch_project(pid)
                except Exception as e:  # noqa: BLE001
                    st.error(f"作成失敗: {e}")
        with c2:
            if st.button("キャンセル", key="proj_create_cancel", use_container_width=True):
                st.session_state.pop("_show_proj_create", None)
                st.rerun()


def _render_project_delete_confirm(project_id: str) -> None:
    """削除確認 UI (誤操作防止のため名前の再入力を要求)。"""
    from services import projects

    cfg = projects.get_config(project_id)
    name = cfg.get("name", project_id)
    with st.expander(f"🗑️ プロジェクト '{name}' を削除", expanded=True):
        st.warning(
            f"このプロジェクト配下の **全データ** (files/ state/ store/ reports/) が削除されます。"
            f"\n\n**取り消しはできません。** 埋め込み npy キャッシュは共有なので残ります。"
        )
        confirm = st.text_input(
            f"確認のため、プロジェクト名 `{name}` を入力してください",
            key=f"proj_del_confirm_{project_id}",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button(
                "削除を実行",
                key=f"proj_del_submit_{project_id}",
                type="primary",
                use_container_width=True,
                disabled=confirm.strip() != name,
            ):
                projects.delete_project(project_id)
                st.session_state.pop("_show_proj_delete", None)
                _switch_project(apollo_config.DEFAULT_PROJECT_ID)
        with c2:
            if st.button("キャンセル", key=f"proj_del_cancel_{project_id}", use_container_width=True):
                st.session_state.pop("_show_proj_delete", None)
                st.rerun()


def _switch_project(new_project_id: str) -> None:
    """プロジェクトを切り替え、analysis 系 session_state をクリアして rerun。

    認証・UI 状態など保持したいキーを除いて、分析関連の重い state は全て消す。
    capcom_store もクリアして、新プロジェクトの store が空から始まるようにする。
    """
    from services import projects

    projects.set_active(new_project_id)

    # 保持するキー prefix / 完全一致 (認証 + サイドバー selectbox)
    preserve_prefix = ("_auth", "authentication_status", "username", "name", "apollo_")
    preserve_exact = {"apollo_active_project"}

    for key in list(st.session_state.keys()):
        if key in preserve_exact:
            continue
        if any(str(key).startswith(p) for p in preserve_prefix):
            continue
        del st.session_state[key]

    st.session_state["apollo_active_project"] = new_project_id
    st.rerun()


def _render_session_diagnostic() -> None:
    """現在の session_state の主要キーを一覧表示する診断パネル。

    NPL データ欠落などのバグ調査用。行数とフラグをコンパクトに表示する。
    """
    try:
        df_main = st.session_state.get("df_main")
        df_npl = st.session_state.get("df_npl")
        df_npl_acc = st.session_state.get("df_npl_accumulated")
        preprocess_done = st.session_state.get("preprocess_done", False)
        sbert = st.session_state.get("sbert_embeddings")
        nebula_emb = st.session_state.get("nebula_academic_embeddings")

        def _fmt(label: str, value) -> str:
            if value is None:
                return f"- **{label}**: ❌ None"
            try:
                n = len(value)
            except Exception:  # noqa: BLE001
                return f"- **{label}**: ⚠️ (型不明)"
            if n == 0:
                return f"- **{label}**: ⚠️ 0 件"
            return f"- **{label}**: ✅ {n:,} 件"

        with st.expander("🔬 診断 (session_state)", expanded=False):
            st.markdown(_fmt("df_main (特許)", df_main))
            st.markdown(_fmt("df_npl (処理後 NPL)", df_npl))
            st.markdown(_fmt("df_npl_accumulated (生 NPL)", df_npl_acc))
            st.markdown(f"- **preprocess_done**: {'✅' if preprocess_done else '❌'}")
            st.markdown(_fmt("sbert_embeddings", sbert))
            st.markdown(_fmt("nebula_academic_embeddings", nebula_emb))

            # df_npl の data_sub_type 内訳
            if df_npl is not None and hasattr(df_npl, "columns") and "data_sub_type" in df_npl.columns:
                counts = df_npl["data_sub_type"].value_counts().to_dict()
                st.caption(f"df_npl data_sub_type: {counts}")
                if "year" in df_npl.columns:
                    valid_years = df_npl["year"].dropna()
                    if len(valid_years) > 0:
                        st.caption(
                            f"df_npl year: {int(valid_years.min())}-{int(valid_years.max())} "
                            f"({len(valid_years)}/{len(df_npl)} 件が有効)"
                        )
                    else:
                        st.caption("⚠️ df_npl の year が全て NaN (日付パース失敗)")
            elif df_npl_acc is not None and hasattr(df_npl_acc, "columns") and "data_sub_type" in df_npl_acc.columns and len(df_npl_acc) > 0:
                counts = df_npl_acc["data_sub_type"].value_counts().to_dict()
                st.caption(f"df_npl_accumulated data_sub_type: {counts}")
                st.caption("⚠️ df_npl が未生成 — 「分析エンジン起動」を実行してください")
    except Exception as e:  # noqa: BLE001
        st.caption(f"診断パネルエラー: {e}")


def _render_model_selector() -> None:
    """LM Studio のモデル一覧から埋め込み / 推論モデルを selectbox で選ぶ。

    v7.0-private.2: 埋め込みモデルはプロジェクト作成時に固定されるため read-only 表記。
    推論モデルは従来通り selectbox で変更可能 (レポート生成ごとに試したい要求に対応)。
    """
    from services import lm_studio_models

    models = lm_studio_models.fetch_models()
    embed_ids, chat_ids = lm_studio_models.split_embed_chat(models)

    err = lm_studio_models.last_fetch_error()
    if err:
        st.caption(f"⚠️ LM Studio 接続失敗: `{err[:60]}`")

    # 埋め込みモデル: 現在のアクティブプロジェクトで固定 (read-only)
    current_embed = lm_studio_models.current_embed_model()
    st.caption(f"🔒 埋め込みモデル: `{current_embed}` (プロジェクト固定)")
    st.caption("変更するには「➕ 新規」で別プロジェクトを作成してください。")

    # 推論モデル (VOYAGER 用)
    if chat_ids:
        default_chat = lm_studio_models.current_chat_model()
        try:
            default_idx_c = chat_ids.index(default_chat)
        except ValueError:
            default_idx_c = 0
        st.selectbox(
            "推論モデル (VOYAGER)",
            chat_ids,
            index=default_idx_c,
            key="apollo_chat_model_select",
            help="VOYAGER のレポート生成で使う LLM。",
        )
    else:
        st.caption("推論モデルが見つかりません")

    if st.button("🔄 モデル一覧を再取得", key="apollo_model_refresh", use_container_width=True):
        lm_studio_models.fetch_models(force_refresh=True)
        st.rerun()


def _render_cache_summary() -> None:
    """npy 埋め込みキャッシュの件数 + 合計サイズを小さく表示。"""
    from services import storage

    datasets = storage.list_cached_datasets()
    if not datasets:
        st.caption("📦 埋め込みキャッシュ: 0 件")
        return
    total_mb = sum(d.get("size_mb", 0) for d in datasets)
    st.caption(f"📦 埋め込みキャッシュ: {len(datasets)} 件 / {total_mb:.1f} MB")
    if st.button(
        "🗑️ 埋め込みキャッシュを一括削除",
        key="apollo_cache_purge",
        use_container_width=True,
        help="cache/embeddings/*.npy を全削除します。session pkl は残ります。",
    ):
        _purge_embedding_cache()
        st.rerun()


def _purge_embedding_cache() -> None:
    """cache/embeddings/*.npy を全削除する。"""
    try:
        cache_dir = apollo_config.CACHE_DIR
        if not cache_dir.exists():
            return
        count = 0
        for p in cache_dir.glob("*.npy"):
            try:
                p.unlink()
                count += 1
            except Exception:  # noqa: BLE001
                pass
        st.success(f"{count} 件の npy キャッシュを削除しました")
    except Exception as e:  # noqa: BLE001
        st.error(f"キャッシュ削除失敗: {e}")
