"""LLM クライアントの抽象化。

VOYAGER がレポート生成に使う唯一の LLM 呼出しポイント。プロバイダは以下の 2 種類：

- `"Google Gemini"`: 既存の HF Spaces / hosted モード用。`google-generativeai`
  パッケージ経由。`generate_content()` が system role を持たないので
  `【System Instructions】... 【User Request】...` 形式で 1 プロンプトに結合する。
- `"LM Studio"`: private モード用。任意の OpenAI 互換エンドポイント
  （LM Studio / Ollama / vLLM / llama.cpp-server 等）。`openai` SDK 経由で
  `/v1/chat/completions` を呼び出す。system role ネイティブ対応。
  マルチモーダル（PNG 入力）は OpenAI vision フォーマットで base64 URL
  埋め込み。

使用側（VOYAGER）は `LLMClient(provider, api_key, model_name, base_url)` と
インスタンス化して `generate_text(system, user, images=...)` を呼ぶ。
"""

from __future__ import annotations

import base64
import io
import re
import time

import streamlit as st

import apollo_config


def _load_genai():
    """`google.generativeai` を遅延 import する。hosted モード専用の optional 依存。

    private モードでは呼ばれないので deprecation warning も発生しない。
    """
    try:
        import google.generativeai as genai

        return genai
    except ImportError:
        return None


class LLMClient:
    """モード非依存の LLM クライアント。

    プロバイダ / モデル名 / ベース URL を渡して初期化する。`error_msg` が
    設定されるのは「初期化時点では壊れていると分かっている」状態で、
    `generate_text()` 呼出し時に `ValueError` として投げられる。
    """

    def __init__(
        self,
        provider: str,
        api_key: str | None,
        model_name: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.provider = provider
        self.api_key = api_key
        self.model_name = model_name
        self.base_url = base_url
        self.error_msg: str | None = None
        self._openai_client = None  # LM Studio 用の openai クライアント

        if self.provider == "Google Gemini":
            self._init_google_gemini()
        elif self.provider == "LM Studio":
            self._init_lm_studio()
        else:
            self.error_msg = f"未サポートのプロバイダ: {self.provider}"

    # ---------- 初期化サブルーチン ----------

    def _init_google_gemini(self) -> None:
        if not self.api_key:
            self.error_msg = "API Keyが設定されていません。"
            return
        genai = _load_genai()
        if genai is None:
            self.error_msg = (
                "google-generativeai ライブラリがインストールされていません。"
                "hosted モードでは `uv sync --extra hosted` を実行してください。"
            )
            return
        genai.configure(api_key=self.api_key)
        if not self.model_name:
            self.model_name = "gemini-1.5-pro"

    def _init_lm_studio(self) -> None:
        # LM Studio / Ollama / vLLM など OpenAI 互換エンドポイント用。
        # API キーは不要なことが多いので dummy を許容する。
        from openai import OpenAI  # 遅延 import: hosted モードでは未インストール

        self._openai_client = OpenAI(
            api_key=self.api_key or apollo_config.LM_STUDIO_API_KEY,
            base_url=self.base_url or apollo_config.LM_STUDIO_BASE_URL,
        )
        if not self.model_name:
            self.model_name = apollo_config.CHAT_MODEL

    # ---------- 生成 API ----------

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[bytes] | None = None,
    ) -> str:
        """テキスト（+ 任意の画像）をプロンプトに渡してテキストを生成する。

        `images` は PNG バイト列のリスト。`None` または空なら純粋にテキスト。
        戻り値は LLM の出力テキスト。エラー時は `RuntimeError` を投げる。
        """
        if self.error_msg:
            raise ValueError(self.error_msg)

        max_retries = 3
        last_error: Exception | None = None

        for attempt in range(max_retries):
            try:
                if self.provider == "Google Gemini":
                    return self._generate_gemini(system_prompt, user_prompt, images)
                if self.provider == "LM Studio":
                    return self._generate_lm_studio(system_prompt, user_prompt, images)
                raise RuntimeError(f"未サポートのプロバイダ: {self.provider}")
            except Exception as e:  # noqa: BLE001
                error_str = str(e)
                last_error = e

                # レート制限リトライ（主に Gemini 用）
                is_rate_limited = (
                    "429" in error_str
                    or "Quota exceeded" in error_str
                    or "Resource has been exhausted" in error_str
                )
                if is_rate_limited and attempt < max_retries - 1:
                    wait_time = 60.0
                    match = re.search(r"retry in (\d+(\.\d+)?)s", error_str)
                    if match:
                        wait_time = float(match.group(1)) + 10
                    st.toast(
                        f"⏳ レート制限に達しました。{int(wait_time)}秒後に再試行します... "
                        f"({attempt + 1}/{max_retries})",
                        icon="⚠️",
                    )
                    with st.empty():
                        for i in range(int(wait_time), 0, -1):
                            st.write(f"⚠️ API制限に達しました。再試行まであと {i} 秒待機中...")
                            time.sleep(1)
                    continue
                break

        raise RuntimeError(f"LLM Generation Failed: {last_error}")

    # ---------- プロバイダ別実装 ----------

    def _generate_gemini(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[bytes] | None,
    ) -> str:
        from PIL import Image  # 遅延 import

        genai = _load_genai()
        if genai is None:
            raise RuntimeError("google-generativeai が利用できません")
        model = genai.GenerativeModel(self.model_name)
        # Gemini 1.5 系は system role を持たないので 1 プロンプトに連結
        full_prompt = f"【System Instructions】\n{system_prompt}\n\n【User Request】\n{user_prompt}"

        if images:
            content_parts: list = [full_prompt]
            for img_bytes in images:
                if not img_bytes:
                    continue
                try:
                    pil_img = Image.open(io.BytesIO(img_bytes))
                    content_parts.append(pil_img)
                except Exception as e:  # noqa: BLE001
                    print(f"Image load error in LLMClient: {e}")
            response = model.generate_content(content_parts)
        else:
            response = model.generate_content(full_prompt)

        return response.text

    def _generate_lm_studio(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[bytes] | None,
    ) -> str:
        # OpenAI 互換 chat.completions。system role をネイティブ分離する。
        messages: list[dict] = [{"role": "system", "content": system_prompt}]

        if images:
            content_parts: list[dict] = [{"type": "text", "text": user_prompt}]
            for img_bytes in images:
                if not img_bytes:
                    continue
                b64 = base64.b64encode(img_bytes).decode("ascii")
                content_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
            messages.append({"role": "user", "content": content_parts})
        else:
            messages.append({"role": "user", "content": user_prompt})

        response = self._openai_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
        )
        return response.choices[0].message.content or ""


def default_provider() -> str:
    """モードに応じたデフォルトプロバイダ名を返す。"""
    return "LM Studio" if apollo_config.IS_PRIVATE else "Google Gemini"


def default_model() -> str:
    """モードに応じたデフォルトモデル名を返す。"""
    return apollo_config.CHAT_MODEL if apollo_config.IS_PRIVATE else "gemini-2.5-flash"
