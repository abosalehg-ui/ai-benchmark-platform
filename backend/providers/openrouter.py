"""مزود OpenRouter (يصل لمئات النماذج)."""
from __future__ import annotations

import httpx

from backend.providers.base import BaseProvider, ModelResponse, measure_latency


class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    available_models = [
        "deepseek/deepseek-chat",
        "mistralai/mistral-large",
        "qwen/qwen-2.5-72b-instruct",
        "meta-llama/llama-3.3-70b-instruct",
    ]
    API_URL = "https://openrouter.ai/api/v1/chat/completions"

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
            "HTTP-Referer": "https://github.com/abosalehg-ui",
            "X-Title": "AI Benchmark Platform",
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
                async with httpx.AsyncClient(timeout=180.0) as client:
                    r = await client.post(self.API_URL, headers=headers, json=body)
                    r.raise_for_status()
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
        # OpenRouter يرجّع التكلفة الفعلية أحياناً
        actual_cost = data.get("usage", {}).get("cost", None)
        cost = actual_cost if actual_cost is not None else self.estimate_cost(
            model, in_tok, out_tok
        )

        return ModelResponse(
            text=text,
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=t.elapsed_ms,
            cost_usd=cost,
            model_id=model,
            raw=data,
        )
