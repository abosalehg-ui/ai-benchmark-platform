"""أسعار النماذج (لكل مليون توكن بالدولار).

الأسعار تتغيّر باستمرار، والمنصّة تستخدمها في تقدير التكلفة وحدّ الميزانية —
فالرقم الخاطئ هنا ينفق مال المستخدم. لذلك:

- كل مزوّد له تاريخ تحقّق في ``PRICING_LAST_VERIFIED``، تعرضه الواجهة.
- النموذج الذي لا نملك له سعراً موثوقاً **لا يُضاف** بسعر مخمَّن؛ يظهر في
  الواجهة بعلامة «بدون تسعير معروف» بدل رقم يبدو دقيقاً وهو ليس كذلك.
"""
from __future__ import annotations

#: تاريخ آخر تحقّق من أسعار كل مزوّد مقابل مصدره الرسمي (ISO 8601)
PRICING_LAST_VERIFIED: dict[str, str] = {
    "anthropic": "2026-07-28",
    "openai": "2026-07-28",
    "gemini": "2026-07-28",
    "groq": "2026-07-28",
    "xai": "2026-07-28",
    "cohere": "2026-07-28",
    "mistral": "2026-01-15",     # لم يُعَد التحقّق — لا جدول أسعار موحّد منشور
    "openrouter": "2026-01-15",  # OpenRouter يرجّع التكلفة الفعلية في الاستجابة
    "ollama": "—",               # تشغيل محلي: التكلفة صفر دائماً
}

PRICING: dict[str, dict[str, dict[str, float]]] = {
    "anthropic": {
        "claude-fable-5": {"input": 10.0, "output": 50.0},
        "claude-opus-5": {"input": 5.0, "output": 25.0},
        "claude-opus-4-8": {"input": 5.0, "output": 25.0},
        "claude-opus-4-7": {"input": 5.0, "output": 25.0},
        "claude-sonnet-5": {"input": 3.0, "output": 15.0},
        "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
        "claude-haiku-4-5": {"input": 1.0, "output": 5.0},
    },
    "openai": {
        "gpt-5.6-sol": {"input": 5.0, "output": 30.0},
        "gpt-5.6-terra": {"input": 2.50, "output": 15.0},
        "gpt-5.6-luna": {"input": 1.0, "output": 6.0},
        "gpt-5.4": {"input": 2.50, "output": 15.0},
        "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
        "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
        "gpt-5": {"input": 1.25, "output": 10.0},
        "gpt-5-mini": {"input": 0.25, "output": 2.0},
        "o3": {"input": 2.0, "output": 8.0},
    },
    "gemini": {
        "gemini-3.6-flash": {"input": 1.50, "output": 7.50},
        "gemini-3.5-flash": {"input": 1.50, "output": 9.0},
        "gemini-3.5-flash-lite": {"input": 0.30, "output": 2.50},
        "gemini-3.1-flash-lite": {"input": 0.25, "output": 1.50},
        # Pro يسعّر على شريحتين حسب طول الـ prompt؛ نستخدم شريحة ≤200k
        "gemini-3.1-pro-preview": {"input": 2.0, "output": 12.0},
        "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
        "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    },
    "ollama": {
        # تشغيل محلي: التكلفة صفر
    },
    "openrouter": {
        # OpenRouter يحسب أسعاره ديناميكياً ويرجّع التكلفة الفعلية في
        # usage.cost، فهذه الأرقام تقديرية للعرض قبل التشغيل فقط
        "deepseek/deepseek-chat": {"input": 0.14, "output": 0.28},
        "qwen/qwen-2.5-72b-instruct": {"input": 0.35, "output": 0.40},
        "meta-llama/llama-3.3-70b-instruct": {"input": 0.13, "output": 0.40},
    },
    "groq": {
        "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
        "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
        "openai/gpt-oss-120b": {"input": 0.15, "output": 0.60},
        "openai/gpt-oss-20b": {"input": 0.075, "output": 0.30},
    },
    "mistral": {
        # أسعار غير مُتحقَّق منها حديثاً — الواجهة تعرض تاريخ التحقّق
        "mistral-large-latest": {"input": 2.0, "output": 6.0},
        "mistral-small-latest": {"input": 0.20, "output": 0.60},
        "codestral-latest": {"input": 0.30, "output": 0.90},
        "ministral-8b-latest": {"input": 0.10, "output": 0.10},
    },
    "cohere": {
        # نماذج command-a-* بلا سعر منشور في صفحة النماذج الرسمية، فنتركها
        # بلا تسعير بدل تخمين رقم يُبنى عليه حدّ الميزانية
        "command-r-plus-08-2024": {"input": 2.50, "output": 10.0},
        "command-r-08-2024": {"input": 0.15, "output": 0.60},
        "command-r7b-12-2024": {"input": 0.0375, "output": 0.15},
    },
    "xai": {
        # xAI يسعّر على شريحتين حسب طول الـ prompt؛ نستخدم شريحة <200k
        "grok-4.5": {"input": 2.0, "output": 6.0},
        "grok-4.3": {"input": 1.25, "output": 2.50},
    },
}


def get_price(provider: str, model: str) -> dict[str, float] | None:
    """ارجع سعر النموذج إذا كان معروفاً."""
    provider_prices = PRICING.get(provider, {})
    return provider_prices.get(model)
