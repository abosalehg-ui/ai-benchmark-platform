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
