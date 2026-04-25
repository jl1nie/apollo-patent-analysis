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
import traceback
from datetime import datetime
from pathlib import Path

import apollo_config


def _llm_debug_log(event: str, **fields) -> None:
    """LM Studio 呼び出しの診断ログを `/var/lib/apollo/llm_debug.log` に追記する。

    タイムアウト等の実例を事後解析するため、OpenAI SDK / httpx レベルの例外
    クラスや経過時間を保存する。ファイルへの書き込み失敗は握り潰す。
    """
    if not apollo_config.IS_PRIVATE:
        return
    try:
        log_path = apollo_config.DATA_ROOT / "llm_debug.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().isoformat(timespec="milliseconds")
        parts = [f"[{ts}]", event]
        for k, v in fields.items():
            parts.append(f"{k}={v!r}")
        with log_path.open("a", encoding="utf-8") as f:
            f.write(" ".join(parts) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _describe_exception(exc: BaseException) -> str:
    """例外の型 + cause chain を 1 行で記述する (診断用)。"""
    chain: list[str] = []
    cur: BaseException | None = exc
    while cur is not None:
        chain.append(f"{type(cur).__module__}.{type(cur).__name__}: {cur}")
        cur = cur.__cause__ or cur.__context__
        if len(chain) >= 5:
            break
    return " | caused_by | ".join(chain)


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

        # OpenAI SDK 既定の 600s では VOYAGER Phase 3 (Strategist) 単発でも 30-60 分
        # 級になるため不足。apollo_config の LM_STUDIO_TIMEOUT (env、既定 7200s)
        # で上書きする。`0` / 負値なら無制限 (None)。
        self._client = OpenAI(
            api_key=api_key or apollo_config.LM_STUDIO_API_KEY,
            base_url=apollo_config.LM_STUDIO_BASE_URL,
            timeout=apollo_config.resolve_lm_studio_timeout(),
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
        finish_reason: str | None = None

        for chunk in stream:
            chunk_count += 1
            # finish_reason は最終チャンクでのみセットされる (stop / length / content_filter 等)
            try:
                fr = chunk.choices[0].finish_reason
                if fr:
                    finish_reason = fr
            except (AttributeError, IndexError, TypeError):
                pass
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
        truncated = finish_reason == "length"
        if placeholder is not None:
            try:
                elapsed = time.time() - start_ts
                if truncated:
                    # max_tokens 到達: 本文は残るが途中で切れているため、必ず気付かせる
                    placeholder.error(
                        f"⚠️ **出力が max_tokens で途中打ち切り** "
                        f"(finish_reason=length) · {len(full_result):,} 文字 · "
                        f"{elapsed:.0f}s · {chunk_count:,} chunks\n\n"
                        f"`LM_STUDIO_MAX_TOKENS` (現在 {apollo_config.LM_STUDIO_MAX_TOKENS:,}) "
                        f"を引き上げて再実行してください。生成物は保存されますが本文末尾が不完全です。"
                    )
                else:
                    placeholder.caption(
                        f"✅ 生成完了 · {len(full_result):,} 文字 · "
                        f"{elapsed:.0f}s · {chunk_count:,} chunks "
                        f"(finish_reason={finish_reason or 'unknown'})"
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

        _llm_debug_log(
            "generate_text.start",
            model=self.model_name,
            prompt_chars=len(system_prompt) + len(user_prompt),
            max_retries=max_retries,
            max_tokens=apollo_config.LM_STUDIO_MAX_TOKENS,
            timeout=apollo_config.LM_STUDIO_TIMEOUT,
        )
        last_err: Exception | None = None
        call_start = time.time()
        for attempt in range(max_retries):
            attempt_start = time.time()
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
                result = self._consume_stream(stream)
                _llm_debug_log(
                    "generate_text.success",
                    attempt=attempt,
                    elapsed=round(time.time() - call_start, 2),
                    result_chars=len(result),
                )
                return result
            except Exception as e:
                last_err = e
                _llm_debug_log(
                    "generate_text.exception",
                    attempt=attempt,
                    elapsed_attempt=round(time.time() - attempt_start, 2),
                    elapsed_total=round(time.time() - call_start, 2),
                    exc_chain=_describe_exception(e),
                    traceback_tail=traceback.format_exc(limit=20)[-2000:],
                )
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

        _llm_debug_log(
            "multimodal.start",
            model=effective_model,
            prompt_chars=len(system_prompt) + len(user_prompt),
            image_count=len(images),
            total_image_bytes=sum(len(i) for i in images),
        )
        last_err: Exception | None = None
        call_start = time.time()
        for attempt in range(max_retries):
            attempt_start = time.time()
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
                result = self._consume_stream(stream)
                _llm_debug_log(
                    "multimodal.success",
                    attempt=attempt,
                    elapsed=round(time.time() - call_start, 2),
                    result_chars=len(result),
                )
                return result
            except Exception as e:
                last_err = e
                _llm_debug_log(
                    "multimodal.exception",
                    attempt=attempt,
                    elapsed_attempt=round(time.time() - attempt_start, 2),
                    elapsed_total=round(time.time() - call_start, 2),
                    exc_chain=_describe_exception(e),
                    traceback_tail=traceback.format_exc(limit=20)[-2000:],
                )
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                raise
        if last_err:
            raise last_err
        return ""

    # ------------------------------------------------------------------
    # Track M: 構造化 JSON 生成 (VL 視覚記述の Phase 0.5 で使用)
    # ------------------------------------------------------------------
    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        images: list[bytes] | None = None,
        model: str | None = None,
        max_retries: int = 2,
        temperature: float = 0.3,
    ) -> dict:
        """JSON オブジェクトを生成する (response_format=json_object)。

        ストリーミングは使わない (途中で切れた JSON は parse 不能になるため)。
        画像を与えた場合は OpenAI 互換 multimodal content block を構築する。
        `model` を指定すれば per-call でモデルを差し替えられる (Phase 0.5 の
        VL 専用呼出で chat_model を一時上書きするため)。
        """
        import base64
        import json as _json

        effective_model = model or self.model_name

        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        if images:
            content: list[dict] = [{"type": "text", "text": user_prompt}]
            for png in images:
                b64 = base64.b64encode(png).decode("ascii")
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    }
                )
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})

        _llm_debug_log(
            "generate_json.start",
            model=effective_model,
            prompt_chars=len(system_prompt) + len(user_prompt),
            image_count=len(images) if images else 0,
        )
        last_err: Exception | None = None
        call_start = time.time()
        for attempt in range(max_retries):
            attempt_start = time.time()
            try:
                resp = self._client.chat.completions.create(
                    model=effective_model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                    stream=False,
                    **self._max_tokens_kwarg(),
                )
                text = resp.choices[0].message.content or ""
                data = _json.loads(text)
                _llm_debug_log(
                    "generate_json.success",
                    attempt=attempt,
                    elapsed=round(time.time() - call_start, 2),
                    result_chars=len(text),
                )
                return data
            except Exception as e:
                last_err = e
                _llm_debug_log(
                    "generate_json.exception",
                    attempt=attempt,
                    elapsed_attempt=round(time.time() - attempt_start, 2),
                    exc_chain=_describe_exception(e),
                )
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                raise
        if last_err:
            raise last_err
        return {}


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
