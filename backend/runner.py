"""محرّك تشغيل البنشمارك مع تتبّع التقدّم."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import AsyncIterator, Awaitable, Callable

from backend import db
from backend.benchmarks import make_benchmark
from backend.providers import make_provider
from backend.providers.base import ModelResponse


def _get_concurrency() -> int:
    """مستوى التزامن لكل نموذج (عدد الاستدعاءات المتوازية). قابل للضبط عبر env."""
    try:
        val = int(os.getenv("RUN_CONCURRENCY", "5"))
    except ValueError:
        return 5
    return max(1, min(val, 32))


@dataclass
class ModelTarget:
    """نموذج مستهدف للاختبار."""
    provider: str
    model: str
    api_key: str
    base_url: str | None = None


@dataclass
class RunRequest:
    benchmark: str
    targets: list[ModelTarget]
    n_problems: int = 10
    judge: ModelTarget | None = None  # للـ llm_judge
    enforce_safety: bool = True
    use_cache: bool = True
    budget_usd: float | None = None  # لو تجاوزت التشغيل يتوقف
    categories: list[str] = field(default_factory=list)  # فلتر للبنشماركات المصنّفة
    difficulties: list[str] = field(default_factory=list)  # فلتر لمستوى الصعوبة


@dataclass
class ProgressEvent:
    event: str  # "start" | "progress" | "result" | "model_done" | "done" | "error" | "budget_exceeded"
    run_id: str
    payload: dict


def _filter_problems(problems, categories: list[str], difficulties: list[str]):
    out = problems
    if categories:
        wanted_c = set(categories)
        out = [p for p in out if p.metadata.get("category") in wanted_c]
    if difficulties:
        wanted_d = set(difficulties)
        out = [p for p in out if p.metadata.get("difficulty") in wanted_d]
    return out


async def _complete_with_cache(provider, target: ModelTarget, prompt: str, system: str | None,
                               use_cache: bool) -> tuple[ModelResponse, bool]:
    """يستخدم cache إذا كان مفعّلاً. يرجع (response, cache_hit)."""
    if not use_cache:
        resp = await provider.complete(prompt=prompt, model=target.model,
                                       max_tokens=2048, temperature=0.0, system=system)
        return resp, False

    key = db.make_cache_key(target.provider, target.model, prompt, system, 0.0)
    cached = db.cache_get(key)
    if cached:
        return ModelResponse(
            text=cached["response_text"],
            input_tokens=cached["input_tokens"],
            output_tokens=cached["output_tokens"],
            latency_ms=0.0,  # cache hit = صفر
            cost_usd=0.0,    # cache hit = صفر دولار
            model_id=target.model,
        ), True

    resp = await provider.complete(prompt=prompt, model=target.model,
                                   max_tokens=2048, temperature=0.0, system=system)
    if not resp.is_error and resp.text:
        db.cache_put(key, target.provider, target.model,
                     text=resp.text, input_tokens=resp.input_tokens,
                     output_tokens=resp.output_tokens, cost_usd=resp.cost_usd,
                     latency_ms=resp.latency_ms)
    return resp, False


async def run_benchmark(
    req: RunRequest,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[ProgressEvent]:
    """يشغّل البنشمارك ويُنتج أحداث تقدّم لحظية (async generator).

    ``is_disconnected``: دالة اختيارية تُرجع True إذا أغلق العميل الاتصال،
    فنوقف التشغيل ونلغي الاستدعاءات المعلّقة بدل إنفاق تكلفة بلا فائدة.
    """
    benchmark = make_benchmark(req.benchmark)
    all_problems = benchmark.load()
    filtered = _filter_problems(all_problems, req.categories, req.difficulties)
    problems = filtered[: req.n_problems]
    n = len(problems)

    config = {
        "benchmark": req.benchmark,
        "n_problems": n,
        "models": [{"provider": t.provider, "model": t.model} for t in req.targets],
        "judge": (
            {"provider": req.judge.provider, "model": req.judge.model}
            if req.judge else None
        ),
        "use_cache": req.use_cache,
        "budget_usd": req.budget_usd,
        "categories": req.categories,
        "difficulties": req.difficulties,
    }
    run_id = db.create_run(req.benchmark, n, config)

    yield ProgressEvent(
        event="start",
        run_id=run_id,
        payload={
            "n_problems": n,
            "n_models": len(req.targets),
            "total_calls": n * len(req.targets),
            "use_cache": req.use_cache,
            "budget_usd": req.budget_usd,
        },
    )

    judge_provider = None
    if req.judge:
        judge_provider = make_provider(
            req.judge.provider, req.judge.api_key, req.judge.base_url
        )
        judge_provider.available_models = [req.judge.model]

    grand_total_cost = 0.0
    budget_exceeded = False
    disconnected = False
    concurrency = _get_concurrency()

    try:
        for target in req.targets:
            if budget_exceeded or disconnected:
                break
            provider = make_provider(target.provider, target.api_key, target.base_url)
            n_correct = 0
            completed = 0
            total_cost = 0.0
            total_latency = 0.0

            # ننفّذ مسائل النموذج بالتوازي بحدّ Semaphore لاحترام rate limits.
            sem = asyncio.Semaphore(concurrency)

            # نربط متغيّرات الحلقة كوسائط افتراضية لتفادي late-binding
            async def _process(problem, *, provider=provider, target=target, sem=sem):
                async with sem:
                    prompt = benchmark.build_prompt(problem)
                    response, cache_hit = await _complete_with_cache(
                        provider, target, prompt, benchmark.system_prompt, req.use_cache
                    )
                    score = await benchmark.evaluate(problem, response, judge_provider)
                    return problem, response, score, cache_hit

            tasks = [asyncio.create_task(_process(p)) for p in problems]
            try:
                for fut in asyncio.as_completed(tasks):
                    problem, response, score, cache_hit = await fut
                    completed += 1
                    # تكلفة المسألة = تكلفة النموذج + تكلفة الحَكَم (إن وُجد)
                    call_cost = response.cost_usd + score.judge_cost_usd

                    if score.correct:
                        n_correct += 1
                    total_cost += call_cost
                    total_latency += response.latency_ms
                    grand_total_cost += call_cost

                    db.insert_result(
                        run_id=run_id,
                        provider=target.provider,
                        model=target.model,
                        problem_id=problem.id,
                        correct=score.correct,
                        raw_score=score.raw_score,
                        latency_ms=response.latency_ms,
                        input_tokens=response.input_tokens,
                        output_tokens=response.output_tokens,
                        cost_usd=call_cost,
                        response_text=score.model_response,
                        judgment=score.judgment,
                        error=score.error or response.error,
                    )

                    yield ProgressEvent(
                        event="progress",
                        run_id=run_id,
                        payload={
                            "provider": target.provider,
                            "model": target.model,
                            "problem_id": problem.id,
                            "i": completed,
                            "n": n,
                            "correct": score.correct,
                            "running_accuracy": n_correct / completed,
                            "running_cost": round(total_cost, 6),
                            "grand_total_cost": round(grand_total_cost, 6),
                            "latency_ms": round(response.latency_ms, 1),
                            "cache_hit": cache_hit,
                            "error": score.error or response.error,
                        },
                    )

                    # فحص الميزانية بعد كل استدعاء (تقريبي: قد يتجاوز بمقدار
                    # الاستدعاءات المتوازية المتبقّية قيد التنفيذ)
                    if req.budget_usd is not None and grand_total_cost >= req.budget_usd:
                        budget_exceeded = True
                        yield ProgressEvent(
                            event="budget_exceeded",
                            run_id=run_id,
                            payload={
                                "budget_usd": req.budget_usd,
                                "spent_usd": round(grand_total_cost, 6),
                                "message": "تم تجاوز الميزانية المحدّدة. توقّف التشغيل.",
                            },
                        )
                        break

                    # لو أغلق العميل الاتصال نوقف ونلغي الباقي (لا نُنفق بلا فائدة)
                    if is_disconnected is not None and await is_disconnected():
                        disconnected = True
                        break
            finally:
                # إلغاء أي استدعاءات معلّقة وابتلاع استثناءات الإلغاء
                for tk in tasks:
                    if not tk.done():
                        tk.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)

            yield ProgressEvent(
                event="model_done",
                run_id=run_id,
                payload={
                    "provider": target.provider,
                    "model": target.model,
                    "accuracy": n_correct / max(completed, 1),
                    "n_correct": n_correct,
                    "n_total": completed,
                    "total_cost": round(total_cost, 6),
                    "avg_latency_ms": round(total_latency / max(completed, 1), 1),
                },
            )

        if disconnected:
            final_status = "aborted_disconnect"
        elif budget_exceeded:
            final_status = "aborted_budget"
        else:
            final_status = "completed"
        db.finish_run(run_id, final_status)
        if not disconnected:
            yield ProgressEvent(event="done", run_id=run_id, payload={"status": final_status})

    except asyncio.CancelledError:
        db.finish_run(run_id, "aborted_disconnect")
        raise
    except Exception as e:
        db.finish_run(run_id, "failed")
        yield ProgressEvent(
            event="error", run_id=run_id, payload={"error": f"{type(e).__name__}: {e}"}
        )


def event_to_sse(ev: ProgressEvent) -> str:
    """تحويل ProgressEvent إلى تنسيق Server-Sent Events."""
    return f"event: {ev.event}\ndata: {json.dumps({'run_id': ev.run_id, **ev.payload}, ensure_ascii=False)}\n\n"
