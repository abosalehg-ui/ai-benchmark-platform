"""مزود OpenAI."""
from __future__ import annotations

import httpx

from backend.providers.base import BaseProvider, ModelResponse, measure_latency


class OpenAIProvider(BaseProvider):
    name = "openai"
    available_models = [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "o1-preview",
        "o1-mini",
    ]
    API_URL = "https://api.openai.com/v1/chat/completions"

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

        body: dict = {"model": model, "messages": messages}
        # موديلات o1 ما تقبل temperature ولها max_completion_tokens
        if model.startswith("o1"):
            body["max_completion_tokens"] = max_tokens
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature

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

        text = data["choices"][0]["message"]["content"] or ""
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
