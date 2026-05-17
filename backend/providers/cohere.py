"""مزود Cohere (Chat API v2)."""
from __future__ import annotations

import httpx

from backend.providers._http import post_with_retry
from backend.providers.base import BaseProvider, ModelResponse, measure_latency


class CohereProvider(BaseProvider):
    name = "cohere"
    available_models = [
        "command-r-plus-08-2024",
        "command-r-08-2024",
        "command-r7b-12-2024",
        "command-light",
    ]
    API_URL = "https://api.cohere.com/v2/chat"

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
            # Cohere v2: message.content is a list of content blocks
            content_blocks = data.get("message", {}).get("content", [])
            text = "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")
        except (KeyError, IndexError, AttributeError) as e:
            return ModelResponse(
                text="", model_id=model, error=f"Parse error: {e}", raw=data
            )

        usage = data.get("usage", {}).get("billed_units", {})
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
