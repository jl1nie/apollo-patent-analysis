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
    """特許タブの最上部に表示する「サーバ保存ファイル」picker。

    - 上段: 内容ハッシュ (`content_key`) ベースの前処理キャッシュ一覧テーブル
      ({ファイル × モデル} のマトリクス表示、復元 / 削除ボタン付き)
    - 下段: named volume 内の CSV ファイル単体 picker (新規 CSV を読み込む用途)
    """
    if not apollo_config.IS_PRIVATE:
        return

    _render_cache_index_table()

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


def _render_cache_index_table() -> None:
    """前処理済みキャッシュを {ファイル × モデル} のテーブルで表示する。

    同じ CSV を異なる埋め込みモデルで前処理すると別行になる。各行に「復元」
    「削除」ボタン。削除時は pickle に加えて対応する npy キャッシュも掃除する。
    """
    from services import analysis_state as st_state

    items = st_state.list_sessions(label="patent")
    header = f"🗃️ 前処理済みキャッシュ ({len(items)} 件)"
    with st.expander(header, expanded=bool(items)):
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
        _render_model_selector()
        _render_cache_summary()
        from services import airgap

        airgap.render_external_access_badge()
        _render_session_diagnostic()


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
    """LM Studio のモデル一覧から埋め込み / 推論モデルを selectbox で選ぶ。"""
    from services import lm_studio_models

    models = lm_studio_models.fetch_models()
    embed_ids, chat_ids = lm_studio_models.split_embed_chat(models)

    err = lm_studio_models.last_fetch_error()
    if err:
        st.caption(f"⚠️ LM Studio 接続失敗: `{err[:60]}`")

    # 埋め込みモデル
    if embed_ids:
        default_embed = lm_studio_models.current_embed_model()
        try:
            default_idx = embed_ids.index(default_embed)
        except ValueError:
            default_idx = 0
        st.selectbox(
            "埋め込みモデル",
            embed_ids,
            index=default_idx,
            key="apollo_embed_model_select",
            help="LM Studio の /v1/models から自動取得しています。モデルを変えると"
            "次回の前処理から別キャッシュに保存されます。",
        )
    else:
        st.caption("埋め込みモデルが見つかりません")

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
