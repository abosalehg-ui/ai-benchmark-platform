"""مزوّد أساسي لكل الـ APIs المتوافقة مع OpenAI Chat Completions.

كثير من المزوّدين (OpenAI, Groq, Mistral, xAI, OpenRouter) يشتركون في نفس
شكل الطلب/الاستجابة (`/chat/completions`). هذا الصنف يجمّع المنطق المشترك،
وتخصّصه الأصناف الوارثة عبر نقاط ربط بسيطة:

- ``API_URL``            عنوان الـ endpoint
- ``DEFAULT_TIMEOUT``    مهلة الطلب
- ``_extra_headers()``   headers إضافية (مثل Referer في OpenRouter)
- ``_build_messages()``  بناء الرسائل (مثل دمج system في o1)
- ``_build_body()``      بناء جسم الطلب (مثل max_completion_tokens في o1)
- ``_extract_cost()``    استخراج التكلفة (مثل cost الفعلي من OpenRouter)
"""
from __future__ import annotations

import httpx

from backend.providers._http import post_with_retry
from backend.providers.base import BaseProvider, ModelResponse, measure_latency


class OpenAICompatibleProvider(BaseProvider):
    """أساس مشترك لمزوّدي Chat Completions المتوافقين مع OpenAI."""

    API_URL: str = ""
    DEFAULT_TIMEOUT: float = 120.0

    def _extra_headers(self) -> dict:
        """headers إضافية خاصة بالمزوّد (فارغة افتراضياً)."""
        return {}

    def _build_messages(
        self, prompt: str, system: str | None, model: str
    ) -> list[dict]:
        """بناء قائمة الرسائل. تُعاد كتابتها عند الحاجة (مثل o1)."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _build_body(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int,
        temperature: float,
    ) -> dict:
        """بناء جسم الطلب. تُعاد كتابته عند الحاجة (مثل o1)."""
        return {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

    def _extract_cost(
        self, data: dict, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        """حساب التكلفة. الافتراضي عبر جدول الأسعار المحلي."""
        return self.estimate_cost(model, input_tokens, output_tokens)

    async def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> ModelResponse:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self._extra_headers(),
        }
        messages = self._build_messages(prompt, system, model)
        body = self._build_body(model, messages, max_tokens, temperature)

        with measure_latency() as t:
            try:
                r = await post_with_retry(
                    self.API_URL, headers=headers, json=body, timeout=self.DEFAULT_TIMEOUT
                )
                data = r.json()
            except httpx.HTTPStatusError as e:
                return ModelResponse(
                    text="",
                    model_id=model,
                    error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                )
            except Exception as e:
                return ModelResponse(
                    text="", model_id=model, error=f"{type(e).__name__}: {e}"
                )

        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            return ModelResponse(
                text="", model_id=model, error=f"Parse error: {e}", raw=data
            )

        usage = data.get("usage", {})
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)

        return ModelResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=t.elapsed_ms,
            cost_usd=self._extract_cost(data, model, in_tok, out_tok),
            model_id=model,
            raw=data,
        )
