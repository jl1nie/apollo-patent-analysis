"""認証レイヤー（private モード専用 / 環境変数のみで完結）。

`streamlit-authenticator` をラップしてシンプルな API を提供する。hosted モード
および private モードで `APOLLO_ADMIN_PASSWORD` 未設定時は `require_login_if_private()`
が即座に True を返すので副作用ゼロ（= Docker Desktop で「とりあえず立ち上げる」運用）。

## 認証情報の供給

すべて環境変数から読み込み、users.yml 等のファイルは一切使わない。

| 環境変数 | 必須 | デフォルト | 説明 |
|---|---|---|---|
| `APOLLO_ADMIN_PASSWORD` | ◯ (auth 有効化条件) | (未設定なら認証無効) | 管理者ユーザの平文パスワード |
| `APOLLO_ADMIN_USER` | | `admin` | 管理者ユーザ名 |
| `APOLLO_COOKIE_SECRET` | | プロセス起動毎にランダム生成 | cookie 署名キー (本番では固定推奨) |
| `APOLLO_COOKIE_NAME` | | `apollo_auth` | cookie 名 |
| `APOLLO_COOKIE_EXPIRY_DAYS` | | `7` | セッション有効期限 |

平文パスワードは `streamlit_authenticator.Authenticate(auto_hash=True)` が
内部で bcrypt 化するため、ユーザはハッシュを生成する必要がない。
"""

from __future__ import annotations

import streamlit as st

import apollo_config

_authenticator = None


def _build_credentials() -> dict:
    """環境変数から streamlit-authenticator 用の credentials dict を生成する。"""
    return {
        "usernames": {
            apollo_config.ADMIN_USER: {
                "name": apollo_config.ADMIN_USER,
                "email": f"{apollo_config.ADMIN_USER}@apollo.local",
                "password": apollo_config.ADMIN_PASSWORD,  # 平文 → auto_hash=True で内部 bcrypt 化
                "roles": ["admin"],
                "failed_login_attempts": 0,
                "logged_in": False,
            }
        }
    }


def _load_authenticator():
    """env から streamlit-authenticator インスタンスを構築する (プロセス内シングルトン)。"""
    global _authenticator
    if _authenticator is not None:
        return _authenticator

    import streamlit_authenticator as stauth

    _authenticator = stauth.Authenticate(
        credentials=_build_credentials(),
        cookie_name=apollo_config.COOKIE_NAME,
        cookie_key=apollo_config.COOKIE_SECRET,
        cookie_expiry_days=apollo_config.COOKIE_EXPIRY_DAYS,
        auto_hash=True,
    )
    return _authenticator


def require_login_if_private() -> bool:
    """private モード + auth 有効時のみログインを要求する。

    - hosted モード: 何もせず True を返す
    - private モード + `APOLLO_ADMIN_PASSWORD` 未設定: 何もせず True を返す
      (=「とりあえず立ち上げ」運用、警告のみ表示)
    - private モード + auth 有効: 未ログインならログインフォームを描画し `st.stop()`

    `utils.render_sidebar()` の冒頭から呼ばれる想定。
    """
    if not apollo_config.IS_PRIVATE:
        return True

    if not apollo_config.AUTH_ENABLED:
        # 認証無効モードでも起動は許容するが、ディスクに埋め込みキャッシュや
        # アップロードファイルが残るため、共有環境では危険であることを明示する
        with st.sidebar:
            st.error(
                "🔓 **認証無効モード**\n\n"
                "`APOLLO_ADMIN_PASSWORD` が未設定です。"
                "ローカルキャッシュ (`/var/lib/apollo`) に埋め込み・アップロードが"
                "残るため、共有環境では `.env` で必ず設定してください。",
                icon="⚠️",
            )
        return True

    try:
        auth = _load_authenticator()
    except Exception as e:  # noqa: BLE001
        st.error(f"認証モジュール初期化失敗: {e}")
        st.stop()

    # streamlit-authenticator 0.4.x の cookie controller が要求するキーを補完
    # (Authenticate.__init__ では設定されないため、login() の直前に初期化する)
    for _k in ("authentication_status", "name", "username", "logout"):
        if _k not in st.session_state:
            st.session_state[_k] = None

    auth.login(location="main")

    status = st.session_state.get("authentication_status")
    if status is True:
        return True
    if status is False:
        st.error("ユーザー名またはパスワードが違います")
        st.stop()
    # status is None: 未入力
    st.info("🔒 APOLLO Private — 続行するにはログインしてください")
    st.stop()


def get_current_user() -> str | None:
    """認証済みユーザーの表示名を返す。auth 無効モードでは ADMIN_USER をそのまま返す。"""
    if not apollo_config.IS_PRIVATE or not apollo_config.AUTH_ENABLED:
        return None
    if st.session_state.get("authentication_status") is True:
        return st.session_state.get("name")
    return None


def get_current_username() -> str | None:
    """認証済みユーザーの ID を返す。"""
    if not apollo_config.IS_PRIVATE or not apollo_config.AUTH_ENABLED:
        return None
    if st.session_state.get("authentication_status") is True:
        return st.session_state.get("username")
    return None


def logout_button(location: str = "sidebar") -> None:
    """ログアウトボタンを描画する (auth 有効モードのみ)。"""
    if not apollo_config.IS_PRIVATE or not apollo_config.AUTH_ENABLED:
        return
    if st.session_state.get("authentication_status") is not True:
        return
    try:
        auth = _load_authenticator()
    except Exception:  # noqa: BLE001
        return
    auth.logout(
        button_name="🚪 ログアウト",
        location=location,
        key="apollo_logout",
    )
