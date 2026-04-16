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
    """Google Gemini API クライアント (hosted モード用)。

    v7.0-private.2: `images` (list[bytes]) を受け取ると multimodal 呼び出しに切り替わる。
    """

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
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        images: list[bytes] | None = None,
    ) -> str:
        """テキスト / multimodal 生成。`images` が non-empty なら画像も一緒に送る。"""
        if images:
            return self._generate_multimodal(
                system_prompt, user_prompt, list(images), max_retries
            )
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

    def _generate_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[bytes],
        max_retries: int,
    ) -> str:
        """Gemini の multimodal 呼び出し (PNG 画像を parts に並べる)。"""
        for attempt in range(max_retries):
            try:
                parts: list = [f"{system_prompt}\n\n{user_prompt}"]
                for png in images:
                    parts.append({"mime_type": "image/png", "data": png})
                response = self.model.generate_content(
                    parts,
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

        # OpenAI SDK 既定の 600s では VOYAGER レポート生成 (30B モデルで 2K-3K 文字
        # 生成) でタイムアウトすることがある。apollo_config の LM_STUDIO_TIMEOUT
        # (env `LM_STUDIO_TIMEOUT`、既定 1800s) で上書きする。
        self._client = OpenAI(
            api_key=api_key or apollo_config.LM_STUDIO_API_KEY,
            base_url=apollo_config.LM_STUDIO_BASE_URL,
            timeout=apollo_config.LM_STUDIO_TIMEOUT,
        )
        # 引数が明示されていなければサイドバー selectbox の最新値を参照する
        self.model_name = model_name or lm_studio_models.current_chat_model()

    def _max_tokens_kwarg(self) -> dict:
        """chat.completions.create の max_tokens 引数を dict で返す (0 以下なら空)。"""
        n = apollo_config.LM_STUDIO_MAX_TOKENS
        return {"max_tokens": n} if n and n > 0 else {}

    # ------------------------------------------------------------------
    # Track K: streaming ヘルパ
    # ------------------------------------------------------------------
    def _consume_stream(self, stream) -> str:
        """ストリーミングレスポンスを順次受信し、全文を文字列で返す。

        streamlit コンテキスト内で呼ばれた場合は `st.empty()` プレースホルダを
        確保し、以下を 0.5 秒間隔で表示:
          - 累積文字数 / 経過時間 / 推定速度 (chars/s)
          - 出力の末尾 1500 文字 (末尾プレビュー)

        WebSocket を定期的な書き込みで活性化 (ブラウザ idle 切断を防ぐ)。
        streamlit 外でも動作する (単に placeholder が None になるだけ)。
        """
        placeholder = None
        try:
            import streamlit as st

            placeholder = st.empty()
            placeholder.caption(f"🤖 LM Studio ({self.model_name}) で生成開始...")
        except Exception:  # noqa: BLE001
            pass

        accumulated: list[str] = []
        start_ts = time.time()
        last_ui = 0.0
        chunk_count = 0

        for chunk in stream:
            chunk_count += 1
            try:
                delta = chunk.choices[0].delta.content
            except (AttributeError, IndexError, TypeError):
                continue
            if not delta:
                continue
            accumulated.append(delta)

            # UI 更新 (500ms ごと)
            if placeholder is not None:
                now = time.time()
                if now - last_ui > 0.5:
                    try:
                        full = "".join(accumulated)
                        elapsed = now - start_ts
                        chars_per_sec = len(full) / elapsed if elapsed > 0 else 0
                        tail = full[-1500:] if len(full) > 1500 else full
                        placeholder.markdown(
                            f"🤖 **生成中** · {len(full):,} 文字 · "
                            f"{elapsed:.0f}s 経過 · {chars_per_sec:.0f} 文字/秒 · "
                            f"{chunk_count:,} chunks\n\n"
                            f"_末尾プレビュー:_\n"
                            f"```\n{tail}\n```"
                        )
                    except Exception:  # noqa: BLE001
                        pass
                    last_ui = now

        # 生成完了: プレースホルダをクリア (次段の UI を邪魔しない)
        full_result = "".join(accumulated)
        if placeholder is not None:
            try:
                elapsed = time.time() - start_ts
                placeholder.caption(
                    f"✅ 生成完了 · {len(full_result):,} 文字 · "
                    f"{elapsed:.0f}s · {chunk_count:,} chunks"
                )
            except Exception:  # noqa: BLE001
                pass

        return full_result

    def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        images: list[bytes] | None = None,
    ) -> str:
        """テキスト / multimodal 生成。`images` が non-empty なら画像も一緒に送る。

        LM Studio 側のモデルが vision 非対応の場合は multimodal 呼び出しが失敗する
        可能性があるため、全リトライ失敗時はテキストのみで fallback を試みる。
        """
        if images:
            try:
                return self._generate_multimodal(
                    system_prompt, user_prompt, list(images), max_retries
                )
            except Exception as e:  # noqa: BLE001
                # vision 非対応モデル等で失敗した場合はテキストのみで再試行
                try:
                    import streamlit as st

                    st.warning(
                        f"⚠️ マルチモーダル呼び出し失敗 ({type(e).__name__}): "
                        "ロード中のモデルが vision 非対応の可能性があります。"
                        "テキストのみで再実行します。"
                    )
                except Exception:  # noqa: BLE001
                    pass
                # fallback: fall through to text-only

        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                stream = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.7,
                    stream=True,
                    **self._max_tokens_kwarg(),
                )
                return self._consume_stream(stream)
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

    def _generate_multimodal(
        self,
        system_prompt: str,
        user_prompt: str,
        images: list[bytes],
        max_retries: int,
    ) -> str:
        """LM Studio (OpenAI 互換) の multimodal 呼び出し。

        PNG 画像を base64 data URI として `image_url` content block に並べる。
        vision 対応モデル (例: Qwen2-VL, Gemma-Vision) が LM Studio にロード
        されている必要がある。

        v7.0-private.2 Track I: `current_vision_model()` が non-empty を返せば
        そのモデルに自動スイッチ (通常の chat_model は text-only かもしれない
        ため)。None の場合は chat_model の self.model_name にフォールバック。
        """
        import base64
        from services import lm_studio_models

        # Vision 専用モデルがあればそれを使う (Track I)
        vision_model = lm_studio_models.current_vision_model()
        effective_model = vision_model or self.model_name
        if vision_model and vision_model != self.model_name:
            try:
                import streamlit as st

                st.caption(f"🖼️ Vision モデルに切替: `{vision_model}` (chat: `{self.model_name}`)")
            except Exception:  # noqa: BLE001
                pass

        last_err: Exception | None = None
        for attempt in range(max_retries):
            try:
                content: list[dict] = [{"type": "text", "text": user_prompt}]
                for png in images:
                    b64 = base64.b64encode(png).decode("ascii")
                    content.append(
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        }
                    )
                stream = self._client.chat.completions.create(
                    model=effective_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": content},
                    ],
                    temperature=0.7,
                    stream=True,
                    **self._max_tokens_kwarg(),
                )
                return self._consume_stream(stream)
            except Exception as e:
                last_err = e
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise
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
