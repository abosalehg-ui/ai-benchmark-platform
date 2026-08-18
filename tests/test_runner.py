"""اختبارات محرّك التشغيل: التزامن، الميزانية، الانقطاع، والحالات الحدّية."""
from __future__ import annotations

import asyncio

import pytest

import backend.runner as runner
from backend.providers.base import BaseProvider, ModelResponse
from backend.runner import ModelTarget, RunRequest, event_to_sse


def _make_fake_provider(delay=0.0, cost=0.0):
    """مزوّد وهمي يرجّع الإجابة المرجعية دائماً."""

    class _Fake(BaseProvider):
        name = "fake"
        available_models = ["fake-model"]
        active = 0
        max_active = 0

        async def complete(self, prompt, model, max_tokens=1024, temperature=0.0, system=None):
            type(self).active += 1
            type(self).max_active = max(type(self).max_active, type(self).active)
            if delay:
                await asyncio.sleep(delay)
            type(self).active -= 1
            # "أ" لأن الداتاست السعودي إجاباته حروف عربية
            return ModelResponse(text="الإجابة: أ", input_tokens=1, output_tokens=1, cost_usd=cost)

    return _Fake


def _drain(req, **kwargs):
    async def _go():
        return [ev async for ev in runner.run_benchmark(req, **kwargs)]

    return asyncio.run(_go())


@pytest.fixture
def fake_runner(monkeypatch, temp_db):
    def _install(delay=0.0, cost=0.0):
        Fake = _make_fake_provider(delay=delay, cost=cost)
        monkeypatch.setattr(runner, "make_provider", lambda *a, **k: Fake(api_key=""))
        return Fake

    return _install


def _req(**overrides):
    base = dict(
        benchmark="saudi_legal",
        targets=[ModelTarget(provider="fake", model="fake-model", api_key="")],
        n_problems=8,
        use_cache=False,
    )
    base.update(overrides)
    return RunRequest(**base)


def test_runs_problems_concurrently(monkeypatch, fake_runner):
    monkeypatch.setenv("RUN_CONCURRENCY", "4")
    Fake = fake_runner(delay=0.05)

    events = _drain(_req())
    kinds = [e.event for e in events]
    assert kinds[0] == "start"
    assert kinds[-1] == "done"
    assert kinds.count("progress") == 8
    assert Fake.max_active > 1, f"لم يحدث تزامن (max_active={Fake.max_active})"


def test_stops_on_client_disconnect(monkeypatch, fake_runner, temp_db):
    monkeypatch.setenv("RUN_CONCURRENCY", "2")
    fake_runner(delay=0.01)

    async def _always_disconnected():
        return True

    events = _drain(_req(n_problems=20), is_disconnected=_always_disconnected)
    assert sum(1 for e in events if e.event == "progress") < 20
    assert not any(e.event == "done" for e in events)
    assert temp_db.get_run(events[0].run_id)["status"] == "aborted_disconnect"


def test_budget_stops_the_run(monkeypatch, fake_runner, temp_db):
    monkeypatch.setenv("RUN_CONCURRENCY", "1")
    fake_runner(cost=0.10)

    events = _drain(_req(n_problems=10, budget_usd=0.25))
    assert any(e.event == "budget_exceeded" for e in events)
    assert temp_db.get_run(events[0].run_id)["status"] == "aborted_budget"
    # يتوقّف قرب الحدّ لا بعد إنفاق كل المسائل
    assert sum(1 for e in events if e.event == "progress") <= 4


def test_budget_spans_all_targets(monkeypatch, fake_runner, temp_db):
    """التكلفة التراكمية تُمرَّر بين النماذج، فلا يتضاعف الإنفاق مع كل نموذج."""
    monkeypatch.setenv("RUN_CONCURRENCY", "1")
    fake_runner(cost=0.10)

    req = _req(
        n_problems=5,
        budget_usd=0.25,
        targets=[
            ModelTarget(provider="fake", model="m1", api_key=""),
            ModelTarget(provider="fake", model="m2", api_key=""),
        ],
    )
    events = _drain(req)
    assert sum(1 for e in events if e.event == "progress") <= 4
    assert any(e.event == "budget_exceeded" for e in events)


def test_empty_filter_result_reports_an_error(fake_runner, temp_db):
    """كان يُنشَأ run فارغ ويظهر 0% بدل رسالة تشرح أن الفلتر لم يطابق شيئاً."""
    fake_runner()
    events = _drain(_req(categories=["تصنيف لا وجود له"]))
    kinds = [e.event for e in events]
    assert kinds == ["start", "error"]
    assert "لا توجد مسائل مطابقة" in events[-1].payload["error"]
    assert temp_db.get_run(events[0].run_id)["status"] == "failed"


def test_cache_hit_is_free_and_flagged(monkeypatch, fake_runner, temp_db):
    monkeypatch.setenv("RUN_CONCURRENCY", "1")
    fake_runner(cost=0.05)

    first = _drain(_req(n_problems=3, use_cache=True))
    assert all(not e.payload.get("cache_hit") for e in first if e.event == "progress")

    second = _drain(_req(n_problems=3, use_cache=True))
    hits = [e for e in second if e.event == "progress" and e.payload["cache_hit"]]
    assert len(hits) == 3
    assert all(h.payload["running_cost"] == 0.0 for h in hits)


def test_model_done_carries_final_stats(fake_runner, temp_db):
    fake_runner()
    events = _drain(_req(n_problems=4))
    done = next(e for e in events if e.event == "model_done")
    assert done.payload["n_total"] == 4
    assert 0.0 <= done.payload["accuracy"] <= 1.0


def test_start_event_reports_real_total_after_filtering(fake_runner, temp_db):
    """الواجهة تعتمد على هذا الرقم لشريط التقدّم بدل تقدير محلي خاطئ."""
    fake_runner()
    events = _drain(_req(n_problems=500, difficulties=["سهل"]))
    start = events[0]
    assert start.event == "start"
    assert 0 < start.payload["total_calls"] < 500
    assert start.payload["total_calls"] == start.payload["n_problems"]


def test_event_to_sse_format():
    from backend.runner import ProgressEvent

    sse = event_to_sse(ProgressEvent(event="progress", run_id="abc", payload={"i": 1, "ar": "نص"}))
    assert sse.startswith("event: progress\n")
    assert '"run_id": "abc"' in sse
    assert "نص" in sse  # ensure_ascii=False
    assert sse.endswith("\n\n")


# ============ التوازي بين النماذج ============

def test_targets_run_in_parallel(monkeypatch, fake_runner, temp_db):
    """زمن التشغيل صار أطول نموذج لا مجموع النماذج — وهو جوهر منصّة مقارنة."""
    monkeypatch.setenv("RUN_CONCURRENCY", "1")
    monkeypatch.delenv("RUN_TARGET_CONCURRENCY", raising=False)

    seen: list[str] = []

    class _Tracking(BaseProvider):
        name = "fake"
        available_models = ["m"]
        in_flight = 0
        max_in_flight = 0

        def __init__(self, api_key="", base_url=None, tag=""):
            super().__init__(api_key=api_key, base_url=base_url)
            self.tag = tag

        async def complete(self, prompt, model, max_tokens=1024, temperature=0.0, system=None):
            type(self).in_flight += 1
            type(self).max_in_flight = max(type(self).max_in_flight, type(self).in_flight)
            seen.append(model)
            await asyncio.sleep(0.05)
            type(self).in_flight -= 1
            return ModelResponse(text="الإجابة: أ", cost_usd=0.0)

    monkeypatch.setattr(runner, "make_provider", lambda *a, **k: _Tracking())
    req = _req(
        n_problems=3,
        targets=[
            ModelTarget(provider="fake", model="m1", api_key=""),
            ModelTarget(provider="fake", model="m2", api_key=""),
        ],
    )
    events = _drain(req)
    # نموذجان × 3 مسائل، والتزامن داخل النموذج 1 ⇒ أي تداخل يعني توازي النماذج
    assert _Tracking.max_in_flight >= 2
    assert sum(1 for e in events if e.event == "progress") == 6
    assert sum(1 for e in events if e.event == "model_done") == 2
    assert events[-1].event == "done"


def test_target_concurrency_env_can_serialize(monkeypatch, fake_runner, temp_db):
    """صمّام أمان لمن يضرب حدود المعدّل: RUN_TARGET_CONCURRENCY=1 يعيد التتابع."""
    monkeypatch.setenv("RUN_CONCURRENCY", "1")
    monkeypatch.setenv("RUN_TARGET_CONCURRENCY", "1")

    class _Serial(BaseProvider):
        name = "fake"
        available_models = ["m"]
        in_flight = 0
        max_in_flight = 0

        async def complete(self, prompt, model, max_tokens=1024, temperature=0.0, system=None):
            type(self).in_flight += 1
            type(self).max_in_flight = max(type(self).max_in_flight, type(self).in_flight)
            await asyncio.sleep(0.02)
            type(self).in_flight -= 1
            return ModelResponse(text="الإجابة: أ")

    monkeypatch.setattr(runner, "make_provider", lambda *a, **k: _Serial(api_key=""))
    _drain(_req(n_problems=2, targets=[
        ModelTarget(provider="fake", model="m1", api_key=""),
        ModelTarget(provider="fake", model="m2", api_key=""),
    ]))
    assert _Serial.max_in_flight == 1


def test_budget_exceeded_is_announced_once(monkeypatch, fake_runner, temp_db):
    """مع التوازي كان كل نموذج قد يُعلن التجاوز — الحدث يجب أن يصل مرّة واحدة."""
    monkeypatch.setenv("RUN_CONCURRENCY", "1")
    fake_runner(cost=0.10)

    events = _drain(_req(n_problems=5, budget_usd=0.25, targets=[
        ModelTarget(provider="fake", model="m1", api_key=""),
        ModelTarget(provider="fake", model="m2", api_key=""),
    ]))
    assert sum(1 for e in events if e.event == "budget_exceeded") == 1


# ============ تحذيرات ما قبل الإنفاق ============

def test_budget_with_unpriced_model_warns_before_spending(fake_runner, temp_db):
    """حدّ الميزانية لا يرى نموذجاً بلا سعر — التكلفة تُحسب صفراً فلا يُفعَّل أبداً."""
    fake_runner(cost=0.0)
    events = _drain(_req(n_problems=2, budget_usd=1.0))
    warn = [e for e in events if e.event == "budget_unreliable"]
    assert warn, "لم يصل تحذير الميزانية غير الموثوقة"
    assert "fake/fake-model" in warn[0].payload["models"]
    # التحذير يسبق أي استدعاء
    assert events.index(warn[0]) < next(
        i for i, e in enumerate(events) if e.event == "progress"
    )


def test_no_budget_means_no_unreliable_warning(fake_runner, temp_db):
    fake_runner()
    events = _drain(_req(n_problems=2))
    assert not [e for e in events if e.event == "budget_unreliable"]


def test_priced_model_does_not_warn(monkeypatch, fake_runner, temp_db):
    fake_runner()
    req = _req(n_problems=2, budget_usd=1.0, targets=[
        ModelTarget(provider="anthropic", model="claude-opus-5", api_key=""),
    ])
    assert not [e for e in _drain(req) if e.event == "budget_unreliable"]


def test_unpriced_targets_excludes_ollama():
    """Ollama تكلفته صفر فعلاً لا مجهولة — تحذيره سيكون ضجيجاً."""
    from backend.runner import unpriced_targets

    targets = [
        ModelTarget(provider="ollama", model="llama3", api_key=""),
        ModelTarget(provider="anthropic", model="claude-opus-5", api_key=""),
        ModelTarget(provider="cohere", model="command-a-03-2025", api_key=""),
    ]
    assert unpriced_targets(targets) == ["cohere/command-a-03-2025"]


def test_code_benchmark_warns_when_sandbox_is_not_isolated(monkeypatch, fake_runner, temp_db):
    """كود النماذج سيُنفَّذ على الجهاز — التحذير يصل قبل أول تنفيذ."""
    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    fake_runner()
    events = _drain(_req(benchmark="humaneval", n_problems=1))
    warn = [e for e in events if e.event == "sandbox_warning"]
    assert warn
    assert warn[0].payload["backend"] == "subprocess"
    assert events.index(warn[0]) < next(
        i for i, e in enumerate(events) if e.event == "progress"
    )


def test_non_code_benchmark_never_warns_about_sandbox(monkeypatch, fake_runner, temp_db):
    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    fake_runner()
    events = _drain(_req(benchmark="saudi_legal", n_problems=2))
    assert not [e for e in events if e.event == "sandbox_warning"]


# ============ enforce_safety يصل فعلاً ============

def test_enforce_safety_reaches_the_sandbox(monkeypatch, fake_runner, temp_db):
    """العلَم كان يتوقّف عند RunRequest ولا يُقرأ — الخانة في الواجهة كانت كاذبة."""
    import backend.benchmarks.humaneval as he

    captured = []

    def _spy(code, test_code="", timeout=5, enforce_safety=True):
        captured.append(enforce_safety)
        from backend.sandbox.base import SandboxResult
        return SandboxResult(passed=True, backend="subprocess")

    monkeypatch.setattr(he, "run_python_code", _spy)
    fake_runner()

    _drain(_req(benchmark="humaneval", n_problems=1, enforce_safety=False))
    _drain(_req(benchmark="humaneval", n_problems=1, enforce_safety=True))
    assert captured == [False, True]
