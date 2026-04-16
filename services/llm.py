"""VOYAGER 用 LLM クライアントのファクトリ。

`create_client()` がモード (`apollo_config.IS_PRIVATE`) に応じて以下を返す:

- hosted: `GeminiLLMClient` (google-generativeai を `__init__` 内で遅延 import)
- private: `LMStudioLLMClient` (openai SDK を `__init__` 内で遅延 import)

両クラスは VOYAGER 既存の `LLMClient` と同じインタフェース
(`generate_text(system_prompt, user_prompt, max_retries=3) -> str`) を持つ。

**遅延 import の意義**: private モードでは `google.generativeai` が一切 import
されないため、private イメージから google-generativeai を除外しても VOYAGER の
import は失敗しない。逆に hosted モードでは `openai` パッケージは触らない。
"""

from __future__ import annotations

import time

import apollo_config


class GeminiLLMClient:
    """Google Gemini API クライアント (hosted モード用)。"""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash") -> None:
        # private モードで万一 Gemini 経路に落ちた場合はエアギャップ警告を出す。
        # hosted モードではガード内で何も起きない (airgap は private 時のみ表示)。
        try:
            from services import airgap

            airgap.show_external_api_notice("gemini")
        except Exception:  # noqa: BLE001
            pass

        import google.generativeai as genai  # 遅延 import

        self._genai = genai
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name)
        self.model_name = model_name

    def generate_text(
        self, system_prompt: str, user_prompt: str, max_retries: int = 3
    ) -> str:
        for attempt in range(max_retries):
            try:
                response = self.model.generate_content(
                    f"{system_prompt}\n\n{user_prompt}",
                    generation_config=self._genai.GenerationConfig(
                        temperature=0.7,
                        max_output_tokens=65536,
                    ),
                )
                return response.text
            except Exception as e:
                if "429" in str(e) and attempt < max_retries - 1:
                    time.sleep(60)
                    continue
                raise


class LMStudioLLMClient:
    """LM Studio (OpenAI 互換) クライアント (private モード用)。

    `openai` SDK 経由で `/v1/chat/completions` を呼び出す。system role に
    ネイティブ対応。API キーは不要なことが多いので dummy を許容する。
    """

    def __init__(self, api_key: str | None = None, model_name: str | None = None) -> None:
        from openai import OpenAI  # 遅延 import
        from services import lm_studio_models

        self._client = OpenAI(
            api_key=api_key or apollo_config.LM_STUDIO_API_KEY,
            base_url=apollo_config.LM_STUDIO_BASE_URL,
        )
        # 引数が明示されていなければサイドバー selectbox の最新値を参照する
        self.model_name = model_name or lm_studio_models.current_chat_model()

    def generate_text(
        self, system_prompt: str, user_prompt: str, max_retries: int = 3
    ) -> str:
        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise
        # 到達しない経路だが型チェック対策
        if last_err:
            raise last_err
        return ""


def create_client(api_key: str | None = None, model_name: str | None = None):
    """モードに応じた LLM クライアントを返す。

    - hosted: `GeminiLLMClient`
    - private: `LMStudioLLMClient` (api_key は無視され、apollo_config の値を使う)
    """
    if apollo_config.IS_PRIVATE:
        return LMStudioLLMClient(api_key=api_key, model_name=model_name)
    return GeminiLLMClient(
        api_key=api_key or "", model_name=model_name or "gemini-2.5-flash"
    )
