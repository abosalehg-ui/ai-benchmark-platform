"""مزود OpenRouter (يصل لمئات النماذج)."""
from __future__ import annotations

from backend.providers.openai_compatible import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    available_models = [
        "deepseek/deepseek-chat",
        "qwen/qwen-2.5-72b-instruct",
        "meta-llama/llama-3.3-70b-instruct",
    ]
    API_URL = "https://openrouter.ai/api/v1/chat/completions"
    DEFAULT_TIMEOUT = 180.0

    def _extra_headers(self) -> dict:
        return {
            "HTTP-Referer": "https://github.com/abosalehg-ui",
            "X-Title": "AI Benchmark Platform",
        }

    def _extract_cost(self, data, model, input_tokens, output_tokens):
        # OpenRouter يرجّع التكلفة الفعلية أحياناً ضمن usage.cost
        actual = data.get("usage", {}).get("cost")
        if actual is not None:
            return actual
        return self.estimate_cost(model, input_tokens, output_tokens)
