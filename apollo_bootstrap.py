"""APOLLO Private bootstrap。

`Home.py` の最上部から `init()` を呼び出すことで、private モード時に必要な
モンキーパッチを v7 ソースに触らずに適用する。

- `HF_HUB_OFFLINE=1` を設定 (HuggingFace Hub への初回ダウンロードを抑止)
- `patiroha.SBERTEmbedder` → `services.embeddings.LMStudioEmbedderShim` に差し替え
- `utils.render_sidebar` を wrap して `services.private_ui.render_sidebar_extras`
  を呼び出す (サイドバー下部にモデル選択・キャッシュサマリ・外部接続バッジを追加)
- データディレクトリ作成

hosted モードでは何もせずに即 return するため、HF Spaces 上の挙動は完全に v7 と同一。
"""

from __future__ import annotations

_initialized = False


def init() -> None:
    """private モードのモンキーパッチを 1 度だけ適用する。

    Streamlit の rerun でも 1 プロセス内で 1 回だけ実行されるよう冪等にする。
    """
    global _initialized
    if _initialized:
        return
    _initialized = True

    import os

    import apollo_config

    if not apollo_config.IS_PRIVATE:
        return

    # HuggingFace Hub への外部通信を防ぐ。patiroha は既に LM Studio シムへ
    # 差し替え済みなので実質呼ばれないが、他の依存ライブラリが内部的に
    # sentence-transformers を触るケースに備えた保険。
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    apollo_config.ensure_directories()

    # v7.0-private.2: v7.0 既存データを projects/default/ に移行 (冪等、sentinel 付き)
    try:
        from services import migration_v7_0

        migration_v7_0.migrate_if_needed()
    except Exception:  # noqa: BLE001
        # マイグレーション失敗は分析をブロックしない (次回起動で再試行)
        pass

    # v7.0-private.2: capcom.save_* のモンキーパッチを適用し、レポート素材を
    # アクティブプロジェクトの store/ 配下にミラーする (Track B)
    try:
        from services import project_hooks

        project_hooks.install_all_hooks()
    except Exception:  # noqa: BLE001
        pass

    # patiroha.SBERTEmbedder を LM Studio バックエンドのシムに差し替える。
    # Home.py / NEBULA など全ての呼び出し箇所はモジュール属性経由で参照しているので、
    # ここで属性を再バインドするだけで全箇所がシム経由になる。
    import patiroha

    from services.embeddings import LMStudioEmbedderShim

    patiroha.SBERTEmbedder = LMStudioEmbedderShim

    # utils.render_sidebar を wrap してサイドバー下部に private 拡張を自動追加する。
    # 各ページのサイドバーコードを触らずに全ページ一律で反映できる。
    try:
        import utils

        _orig_render_sidebar = utils.render_sidebar

        def _render_sidebar_with_extras(*args, **kwargs):
            _orig_render_sidebar(*args, **kwargs)
            try:
                from services.private_ui import render_sidebar_extras

                render_sidebar_extras()
            except Exception as e:  # noqa: BLE001
                try:
                    import streamlit as st

                    with st.sidebar:
                        st.caption(f"⚠️ private extras error: {type(e).__name__}: {e}")
                except Exception:  # noqa: BLE001
                    pass

        utils.render_sidebar = _render_sidebar_with_extras
    except Exception:  # noqa: BLE001
        # utils の import 失敗は致命的ではないので握り潰す (hosted fallback に任せる)
        pass

    # v7.0-private.2 Track H: AI サジェスト系 UI を LM Studio 直接呼び出し版に差替
    # エアギャップ環境で「ChatGPT コピペ」フローが意味を成さないため、private では
    # LM Studio 直送ボタン付き UI にモンキーパッチで置き換える。既存の外部 LLM
    # コピペ経路も新 UI に残しているので柔軟性は失われない。
    try:
        import utils as _utils_for_ai

        from services.private_ui import render_local_ai_label_assistant

        _utils_for_ai.render_ai_label_assistant = render_local_ai_label_assistant
    except Exception:  # noqa: BLE001
        pass

    try:
        import utils_ai as _utils_ai_mod

        from services.private_ui import render_local_ai_insight_button

        _utils_ai_mod.render_ai_insight_button = render_local_ai_insight_button
    except Exception:  # noqa: BLE001
        pass
