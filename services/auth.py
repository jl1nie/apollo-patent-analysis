"""認証レイヤー（private モード専用）。

`streamlit-authenticator` をラップしてシンプルな API を提供する。
hosted モードでは一切使われない（`apollo_config.IS_PRIVATE` が False
のときは `require_login()` も呼ばれない）。

## ユーザーストア

`apollo_config.USERS_FILE` (`/var/lib/apollo/users/users.yml`) に以下の
スキーマで配置する。パスワードは **bcrypt ハッシュ済みの値**を入れる::

    credentials:
      usernames:
        admin:
          name: 管理者
          email: admin@example.com
          password: $2b$12$...(bcrypt hash)
        analyst1:
          name: 田中 太郎
          email: tanaka@example.com
          password: $2b$12$...
    cookie:
      name: apollo_private_auth
      key: <openssl rand -hex 32 で生成したランダム値>
      expiry_days: 7

ハッシュ生成は `just hash-password` で対話的に作れる。
`auto_hash=False` にしているので、平文パスワードは受け付けない。

## API

- `require_login() -> bool` — ログイン済みなら True、未ログインなら
  ログインフォームを描画して False
- `get_current_user() -> str | None` — 表示名（YAML の `name` フィールド）
- `get_current_username() -> str | None` — ユーザー ID（YAML キー）
- `logout_button(location)` — ログアウトボタンを描画（主にサイドバー用）
"""

from __future__ import annotations

import streamlit as st

import apollo_config

_authenticator = None  # プロセス内シングルトン


def _load_authenticator():
    """YAML を読み込んで streamlit-authenticator インスタンスを返す。

    ファイル欠落・YAML 破損・スキーマ違反は全て例外で呼び出し側に伝える。
    """
    global _authenticator
    if _authenticator is not None:
        return _authenticator

    import streamlit_authenticator as stauth
    import yaml

    users_path = apollo_config.USERS_FILE
    if not users_path.exists():
        raise FileNotFoundError(
            f"ユーザー設定ファイルが見つかりません: {users_path}\n"
            f"deploy/private/users.example.yml を参考に作成してください。"
        )

    with open(users_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    if not config or "credentials" not in config or "cookie" not in config:
        raise ValueError(
            "users.yml のスキーマが不正です。credentials / cookie セクションが必要です。"
        )

    cookie_cfg = config["cookie"]
    _authenticator = stauth.Authenticate(
        credentials=config["credentials"],
        cookie_name=cookie_cfg.get("name", "apollo_private_auth"),
        cookie_key=cookie_cfg["key"],  # 必須: .env の APOLLO_COOKIE_SECRET から展開されることを想定
        cookie_expiry_days=float(cookie_cfg.get("expiry_days", 7)),
        auto_hash=False,  # YAML には bcrypt 済みハッシュしか入れない
    )
    return _authenticator


def require_login() -> bool:
    """未ログインなら login form を表示して False を返す。

    認証済みなら True を返すので、呼び出し側はそのまま処理を続行してよい。
    """
    try:
        auth = _load_authenticator()
    except FileNotFoundError as e:
        st.error(str(e))
        st.info(
            "初期セットアップ手順:\n"
            "1. `just hash-password` で管理者パスワードの bcrypt ハッシュを生成\n"
            "2. `deploy/private/users.example.yml` をコピーしてハッシュを貼り付け\n"
            f"3. `{apollo_config.USERS_FILE}` に配置"
        )
        return False
    except Exception as e:  # noqa: BLE001
        st.error(f"認証モジュール初期化失敗: {e}")
        return False

    # login() は認証結果を session_state に書き込む
    # (name / authentication_status / username キー)
    auth.login(location="main")

    status = st.session_state.get("authentication_status")
    if status is True:
        return True
    if status is False:
        st.error("ユーザー名またはパスワードが違います")
        return False
    # status is None: 未入力 / キャンセル
    st.info("🔒 APOLLO Private — 続行するにはログインしてください")
    return False


def get_current_user() -> str | None:
    """認証済みユーザーの表示名（YAML の name フィールド）を返す。"""
    if st.session_state.get("authentication_status") is True:
        return st.session_state.get("name")
    return None


def get_current_username() -> str | None:
    """認証済みユーザーの ID（YAML の credentials.usernames キー）を返す。"""
    if st.session_state.get("authentication_status") is True:
        return st.session_state.get("username")
    return None


def logout_button(location: str = "sidebar") -> None:
    """ログアウトボタンを描画する（主にサイドバー用）。

    ログインしていない状態では何も表示しない。
    """
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
