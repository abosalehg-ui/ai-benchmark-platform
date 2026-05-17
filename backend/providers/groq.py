"""مزود Groq - استنتاج سريع للنماذج المفتوحة."""
from __future__ import annotations

import httpx

from backend.providers._http import post_with_retry
from backend.providers.base import BaseProvider, ModelResponse, measure_latency


class GroqProvider(BaseProvider):
    name = "groq"
    available_models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
        "deepseek-r1-distill-llama-70b",
    ]
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

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
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        with measure_latency() as t:
            try:
                r = await post_with_retry(self.API_URL, headers=headers, json=body, timeout=120.0)
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
        except (KeyError, IndexError) as e:
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
            cost_usd=self.estimate_cost(model, in_tok, out_tok),
            model_id=model,
            raw=data,
        )
