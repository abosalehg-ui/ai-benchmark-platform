"""مزود Google Gemini."""
from __future__ import annotations

import httpx

from backend.providers._http import post_with_retry
from backend.providers.base import (
    BaseProvider,
    ModelResponse,
    format_exception,
    format_http_error,
    measure_latency,
)


class GeminiProvider(BaseProvider):
    name = "gemini"
    available_models = [
        "gemini-3.6-flash",
        "gemini-3.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.1-pro-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
    ]
    BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"

    async def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> ModelResponse:
        # المفتاح في ترويسة لا في query string: العنوان يظهر في سجلّات أي
        # proxy وفي نصوص استثناءات httpx، وكل المزوّدين الآخرين يستخدمون ترويسة
        url = f"{self.BASE_URL}/{model}:generateContent"
        headers = {
            "x-goog-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
            },
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}

        with measure_latency() as t:
            try:
                r = await post_with_retry(url, headers=headers, json=body, timeout=120.0)
                data = r.json()
            except httpx.HTTPStatusError as e:
                return ModelResponse(
                    text="",
                    model_id=model,
                    error=format_http_error(self.name, model, e),
                )
            except Exception as e:
                return ModelResponse(
                    text="", model_id=model, error=format_exception(self.name, model, e)
                )

        try:
            candidates = data.get("candidates", [])
            if not candidates:
                return ModelResponse(
                    text="", model_id=model, error="No candidates returned", raw=data
                )
            parts = candidates[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError) as e:
            return ModelResponse(
                text="", model_id=model, error=f"Parse error: {e}", raw=data
            )

        usage = data.get("usageMetadata", {})
        in_tok = usage.get("promptTokenCount", 0)
        out_tok = usage.get("candidatesTokenCount", 0)

        return ModelResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=t.elapsed_ms,
            cost_usd=self.estimate_cost(model, in_tok, out_tok),
            model_id=model,
            raw=data,
        )
