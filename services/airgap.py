"""エアギャップ環境での外部 API 注意喚起と接続ログ。

private モードでは外部 HTTP API への接続はエアギャップ原則の例外となるため、
ユーザに「外部に出る」ことを明示的に示す必要がある。機能を完全にブロックする
わけではなく、ユーザが意図的に使いたい場合は実行可能。

提供機能:
- `show_external_api_notice(api_key)` — dismiss 可能なインライン警告 (既存 API)
- `note_external_access(api_key)` — サイドバーのバッジ用に接続ログを session_state
  に蓄積 (UI 表示なし)
- `render_external_access_badge()` — サイドバー下部の常駐バッジ
  - ログ 0 件: 🔒 エアギャップ維持中 (緑)
  - ログ 1 件以上: 🌐 外部接続: N 件 (黄) + 展開時に接続先一覧

UI パターン::

    services.airgap.show_external_api_notice("openalex")  # ページ本文中
    # サイドバーの常駐バッジは apollo_bootstrap が自動で組み込む

dismiss は session_state レベル (タブを閉じれば再表示)。永続化したい場合は
`$DATA_ROOT/users/<username>/prefs.json` に保存する拡張余地を残してある。
"""

from __future__ import annotations

import time

import streamlit as st

import apollo_config

EXTERNAL_API_LABELS: dict[str, tuple[str, str]] = {
    "openalex": ("OpenALEX", "学術論文 API (https://api.openalex.org)"),
    "gemini": ("Gemini API", "Google AI (https://generativelanguage.googleapis.com)"),
    "huggingface": (
        "HuggingFace Hub",
        "モデル初回ダウンロード (https://huggingface.co)",
    ),
    # 将来 GoogleScholar / Crossref / 特許 DB 等を追加する場合もここに集約
}

_ACCESS_LOG_KEY = "_external_access_log"


def note_external_access(api_key: str) -> None:
    """外部接続ログに 1 件追記する (UI 表示なし)。

    private モード以外では no-op。`show_external_api_notice` が内部で呼ぶ
    ほか、将来 `requests` ラッパー経由でも呼べるよう分離してある。
    """
    if not apollo_config.IS_PRIVATE:
        return
    log = st.session_state.setdefault(_ACCESS_LOG_KEY, [])
    log.append({"api": api_key, "ts": time.time()})


def show_external_api_notice(api_key: str) -> None:
    """private モードで外部 API を使う前に注意喚起を出す (dismiss 可)。

    機能はブロックしない。エアギャップ環境を逸脱する旨をユーザに示し、
    接続ログに 1 件追記する。hosted モードでは何も表示しない。
    """
    if not apollo_config.IS_PRIVATE:
        return

    # ログ追記 (バッジ表示用)
    note_external_access(api_key)

    label, desc = EXTERNAL_API_LABELS.get(api_key, (api_key, "外部 API"))
    dismiss_key = f"airgap_dismiss_{api_key}"

    if st.session_state.get(dismiss_key, False):
        # dismiss 後も「外部接続あり」の最小ヒントは残す
        st.caption(f"🌐 {label} を使用すると外部 API に接続します (エアギャップ逸脱)")
        return

    with st.container(border=True):
        st.warning(
            f"🌐 **外部 API への接続注意**: {label} を使うと {desc} に接続します。"
            f"APOLLO Private はエアギャップ運用を前提としているため、本当に必要な"
            f"場合のみ使用してください。",
            icon="⚠️",
        )
        st.checkbox(
            "今後この警告を表示しない (このセッション中)",
            key=f"_dismiss_cb_{api_key}",
            on_change=lambda: st.session_state.update({dismiss_key: True}),
        )


def render_external_access_badge() -> None:
    """サイドバー下部の常駐バッジ。

    private モード以外では no-op。呼び出し側は `with st.sidebar:` の中で呼ぶ
    想定 (apollo_bootstrap のモンキーパッチ経由)。
    """
    if not apollo_config.IS_PRIVATE:
        return

    log: list[dict] = st.session_state.get(_ACCESS_LOG_KEY, [])
    count = len(log)

    if count == 0:
        st.markdown(
            """
            <div style="background:#e8f5e9;border:1px solid #66bb6a;border-radius:8px;
                        padding:8px 12px;margin:6px 0;font-size:12px;color:#1b5e20;">
                🔒 <b>エアギャップ維持中</b> (外部接続 0 件)
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # 集計: API 別カウント
    per_api: dict[str, int] = {}
    for e in log:
        per_api[e["api"]] = per_api.get(e["api"], 0) + 1

    st.markdown(
        f"""
        <div style="background:#fff8e1;border:1px solid #ffb300;border-radius:8px;
                    padding:8px 12px;margin:6px 0;font-size:12px;color:#e65100;">
            🌐 <b>外部接続: {count} 件</b>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("接続先の内訳", expanded=False):
        for api_key, cnt in sorted(per_api.items(), key=lambda kv: -kv[1]):
            label, desc = EXTERNAL_API_LABELS.get(api_key, (api_key, "外部 API"))
            st.caption(f"- **{label}** × {cnt}  — {desc}")
