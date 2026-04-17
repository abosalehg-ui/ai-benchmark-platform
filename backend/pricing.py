"""أسعار النماذج (لكل مليون توكن بالدولار).

ملاحظة: الأسعار قد تتغير. راجع الموقع الرسمي لكل مزود.
آخر تحديث: 2026.
"""
from __future__ import annotations

PRICING: dict[str, dict[str, dict[str, float]]] = {
    "anthropic": {
        "claude-opus-4-7": {"input": 15.0, "output": 75.0},
        "claude-opus-4-6": {"input": 15.0, "output": 75.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5-20251001": {"input": 0.80, "output": 4.0},
    },
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.0},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.0, "output": 30.0},
        "o1-preview": {"input": 15.0, "output": 60.0},
        "o1-mini": {"input": 3.0, "output": 12.0},
    },
    "gemini": {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.0},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-2.0-flash-exp": {"input": 0.0, "output": 0.0},
    },
    "ollama": {
        # تشغيل محلي: التكلفة صفر
    },
    "openrouter": {
        # OpenRouter يحسب أسعاره ديناميكياً عبر الـ API
        "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
        "mistralai/mistral-large": {"input": 2.0, "output": 6.0},
        "qwen/qwen-2.5-72b-instruct": {"input": 0.35, "output": 0.40},
        "meta-llama/llama-3.3-70b-instruct": {"input": 0.13, "output": 0.40},
    },
}


def get_price(provider: str, model: str) -> dict[str, float] | None:
    """ارجع سعر النموذج إذا كان معروفاً."""
    provider_prices = PRICING.get(provider, {})
    return provider_prices.get(model)


def list_models(provider: str) -> list[str]:
    """قائمة بالنماذج المتاحة للمزود."""
    return list(PRICING.get(provider, {}).keys())
