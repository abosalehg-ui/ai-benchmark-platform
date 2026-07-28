"""مزود Anthropic Claude."""
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


class ClaudeProvider(BaseProvider):
    name = "anthropic"
    available_models = [
        "claude-opus-5",
        "claude-fable-5",
        "claude-sonnet-5",
        "claude-opus-4-8",
        "claude-haiku-4-5",
    ]
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"

    async def complete(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 1024,
        temperature: float = 0.0,
        system: str | None = None,
    ) -> ModelResponse:
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
        body: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system

        with measure_latency() as t:
            try:
                r = await post_with_retry(self.API_URL, headers=headers, json=body, timeout=120.0)
                data = r.json()
            except httpx.HTTPStatusError as e:
                return ModelResponse(
                    text="",
                    model_id=model,
                    error=format_http_error(self.name, model, e),
                    latency_ms=t.elapsed_ms if hasattr(t, "elapsed_ms") else 0,
                )
            except Exception as e:
                return ModelResponse(
                    text="", model_id=model, error=format_exception(self.name, model, e)
                )

        text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        usage = data.get("usage", {})
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)

        return ModelResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=t.elapsed_ms,
            cost_usd=self.estimate_cost(model, in_tok, out_tok),
            model_id=model,
            raw=data,
        )
