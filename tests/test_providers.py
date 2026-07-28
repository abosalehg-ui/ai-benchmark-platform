"""اختبارات طبقة المزوّدين عبر httpx.MockTransport.

كان مزوّد واحد فقط من تسعة مُختبَراً، ولم يكن أي اختبار يمسّ تحليل
استجابات الـ API — وهي أكثر نقطة عرضة للتباعد بين المزوّدين.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.providers import PROVIDERS, make_provider
from backend.providers.base import estimate_tokens_from_text, format_http_error


def _patch_transport(monkeypatch, handler):
    """يجعل كل مزوّد يستخدم MockTransport بدل الشبكة."""
    import backend.providers._http as http_mod

    orig = httpx.AsyncClient

    def _factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return orig(*args, **kwargs)

    monkeypatch.setattr(http_mod.httpx, "AsyncClient", _factory)
    monkeypatch.setattr(httpx, "AsyncClient", _factory)
    return _factory


def _run(coro):
    return asyncio.run(coro)


# ============ التسجيل والإنشاء ============

def test_all_providers_instantiate():
    expected = {
        "anthropic", "openai", "gemini", "ollama", "openrouter",
        "groq", "mistral", "cohere", "xai",
    }
    assert set(PROVIDERS) == expected
    for name in PROVIDERS:
        assert make_provider(name, api_key="dummy").name == name


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        make_provider("nope")


# نماذج نعرضها رغم غياب سعر منشور موثوق. الواجهة تُعلمها بـ has_price=false،
# وهذه القائمة تجعل الاستثناء قراراً مُراجَعاً لا سهواً.
UNPRICED_BY_DESIGN = {
    "mistral/mistral-medium-latest",
    "cohere/command-a-plus-05-2026",
    "cohere/command-a-03-2025",
}


def test_every_listed_model_has_a_price_or_is_declared_unpriced():
    """أي نموذج معروض في الواجهة إمّا له سعر أو مُعلَن كغير مُسعَّر."""
    from backend.pricing import get_price

    # ollama محلي (صفر) و openrouter يرجّع التكلفة الفعلية في الاستجابة
    dynamic = {"ollama", "openrouter"}
    missing = []
    for name, cls in PROVIDERS.items():
        if name in dynamic:
            continue
        for model in cls.available_models:
            key = f"{name}/{model}"
            if get_price(name, model) is None and key not in UNPRICED_BY_DESIGN:
                missing.append(key)
    assert not missing, f"نماذج معروضة بلا تسعير ولا استثناء معلَن: {missing}"


def test_unpriced_allowlist_has_no_stale_entries():
    """لو أُضيف سعر لاحقاً يجب إزالة الاستثناء بدل تركه يخفي أخطاء جديدة."""
    from backend.pricing import get_price

    stale = [
        key for key in UNPRICED_BY_DESIGN
        if get_price(*key.split("/", 1)) is not None
    ]
    assert not stale, f"استثناءات قديمة يجب حذفها: {stale}"


# ============ تحليل الاستجابات ============

RESPONSES = {
    "anthropic": {
        "content": [{"type": "text", "text": "مرحباً"}],
        "usage": {"input_tokens": 11, "output_tokens": 7},
    },
    "openai": {
        "choices": [{"message": {"content": "مرحباً"}}],
        "usage": {"prompt_tokens": 11, "completion_tokens": 7},
    },
    "gemini": {
        "candidates": [{"content": {"parts": [{"text": "مرحباً"}]}}],
        "usageMetadata": {"promptTokenCount": 11, "candidatesTokenCount": 7},
    },
    "cohere": {
        "message": {"content": [{"type": "text", "text": "مرحباً"}]},
        "usage": {"billed_units": {"input_tokens": 11, "output_tokens": 7}},
    },
}
# المزوّدون المتوافقون مع OpenAI يتشاركون نفس شكل الاستجابة
for _p in ("groq", "mistral", "xai", "openrouter"):
    RESPONSES[_p] = RESPONSES["openai"]


@pytest.mark.parametrize("provider_name", sorted(RESPONSES))
def test_provider_parses_successful_response(monkeypatch, provider_name):
    payload = RESPONSES[provider_name]
    _patch_transport(monkeypatch, lambda req: httpx.Response(200, json=payload))

    p = make_provider(provider_name, api_key="k")
    model = p.available_models[0]
    resp = _run(p.complete("سؤال", model=model))

    assert resp.error is None, resp.error
    assert resp.text == "مرحباً"
    assert resp.input_tokens == 11
    assert resp.output_tokens == 7
    assert resp.latency_ms >= 0
    assert resp.cost_usd >= 0


@pytest.mark.parametrize("provider_name", sorted(RESPONSES))
def test_provider_returns_redacted_error_on_401(monkeypatch, provider_name):
    """أجسام أخطاء المزوّدين كانت تُعاد للعميل حرفياً (200 حرف)."""
    leaky = {"error": {"message": "invalid api_key=sk-ant-SUPERSECRETVALUE123456"}}
    _patch_transport(monkeypatch, lambda req: httpx.Response(401, json=leaky))

    p = make_provider(provider_name, api_key="k")
    resp = _run(p.complete("سؤال", model=p.available_models[0]))

    assert resp.error is not None
    assert "HTTP 401" in resp.error
    assert "SUPERSECRET" not in resp.error
    assert "sk-ant-" not in resp.error


def test_provider_handles_malformed_response(monkeypatch):
    _patch_transport(monkeypatch, lambda req: httpx.Response(200, json={"unexpected": True}))
    p = make_provider("openai", api_key="k")
    resp = _run(p.complete("سؤال", model="gpt-5-mini"))
    assert resp.error is not None
    assert resp.text == ""


def test_retry_on_500_then_success(monkeypatch):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=RESPONSES["openai"])

    _patch_transport(monkeypatch, handler)
    monkeypatch.setattr("backend.providers._http.DEFAULT_BASE_DELAY", 0.0)

    p = make_provider("openai", api_key="k")
    resp = _run(p.complete("سؤال", model="gpt-5-mini"))
    assert calls["n"] == 2
    assert resp.error is None


# ============ خصوصيات OpenAI ============

def test_o_series_omits_system_and_temperature(monkeypatch):
    captured = {}

    def handler(request):
        import json
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=RESPONSES["openai"])

    _patch_transport(monkeypatch, handler)
    p = make_provider("openai", api_key="k")

    _run(p.complete("سؤال", model="o3", system="أنت خبير"))
    body = captured["body"]
    assert "system" not in [m["role"] for m in body["messages"]]
    assert "أنت خبير" in body["messages"][0]["content"]
    assert "temperature" not in body
    assert "max_completion_tokens" in body

    _run(p.complete("سؤال", model="gpt-5-mini", system="أنت خبير"))
    body2 = captured["body"]
    assert body2["messages"][0]["role"] == "system"
    assert "temperature" in body2
    assert "max_tokens" in body2


def test_openrouter_prefers_actual_cost(monkeypatch):
    payload = dict(RESPONSES["openai"])
    payload["usage"] = {**payload["usage"], "cost": 0.4242}
    _patch_transport(monkeypatch, lambda req: httpx.Response(200, json=payload))

    p = make_provider("openrouter", api_key="k")
    resp = _run(p.complete("سؤال", model="deepseek/deepseek-chat"))
    assert resp.cost_usd == 0.4242


# ============ Ollama ============

def test_ollama_lists_local_models(monkeypatch):
    _patch_transport(monkeypatch, lambda req: httpx.Response(
        200, json={"models": [{"name": "llama3"}, {"name": "qwen"}]}))
    p = make_provider("ollama")
    result = _run(p.list_local_models())
    assert result["models"] == ["llama3", "qwen"]
    assert result["error"] is None


def test_ollama_reports_connection_failure(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    _patch_transport(monkeypatch, handler)
    p = make_provider("ollama")
    result = _run(p.list_local_models())
    assert result["models"] == []
    assert "Ollama" in result["error"]


def test_ollama_costs_nothing(monkeypatch):
    _patch_transport(monkeypatch, lambda req: httpx.Response(200, json={
        "message": {"content": "مرحباً"}, "prompt_eval_count": 5, "eval_count": 3,
    }))
    p = make_provider("ollama")
    resp = _run(p.complete("سؤال", model="llama3"))
    assert resp.cost_usd == 0.0
    assert resp.text == "مرحباً"


# ============ أدوات ============

def test_estimate_tokens_from_text():
    assert estimate_tokens_from_text("") == 0
    assert estimate_tokens_from_text("a") >= 1
    assert estimate_tokens_from_text("هذا نص تجريبي يحتوي على عدّة كلمات.") >= 5


def test_format_http_error_redacts_and_hints():
    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(429, text="key sk-or-v1-ABCDEFGH12345678", request=request)
    exc = httpx.HTTPStatusError("boom", request=request, response=response)
    msg = format_http_error("openrouter", "m", exc)
    assert "429" in msg
    assert "rate limit" in msg
    assert "ABCDEFGH" not in msg
