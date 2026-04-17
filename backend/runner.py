"""محرّك تشغيل البنشمارك مع تتبّع التقدّم."""
from __future__ import annotations

import asyncio
import json
from dataclasses import asdict, dataclass
from typing import AsyncIterator

from backend import db
from backend.benchmarks import make_benchmark
from backend.providers import make_provider


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


@dataclass
class ProgressEvent:
    event: str  # "start" | "progress" | "result" | "model_done" | "done" | "error"
    run_id: str
    payload: dict


async def run_benchmark(req: RunRequest) -> AsyncIterator[ProgressEvent]:
    """يشغّل البنشمارك ويُنتج أحداث تقدّم لحظية (async generator)."""
    benchmark = make_benchmark(req.benchmark)
    problems = benchmark.load()[: req.n_problems]
    n = len(problems)

    config = {
        "benchmark": req.benchmark,
        "n_problems": n,
        "models": [{"provider": t.provider, "model": t.model} for t in req.targets],
        "judge": (
            {"provider": req.judge.provider, "model": req.judge.model}
            if req.judge else None
        ),
    }
    run_id = db.create_run(req.benchmark, n, config)

    yield ProgressEvent(
        event="start",
        run_id=run_id,
        payload={
            "n_problems": n,
            "n_models": len(req.targets),
            "total_calls": n * len(req.targets),
        },
    )

    judge_provider = None
    if req.judge:
        judge_provider = make_provider(
            req.judge.provider, req.judge.api_key, req.judge.base_url
        )
        # نضع الموديل المختار في أول القائمة عشان evaluate تستخدمه
        judge_provider.available_models = [req.judge.model]

    try:
        for target in req.targets:
            provider = make_provider(target.provider, target.api_key, target.base_url)
            n_correct = 0
            total_cost = 0.0
            total_latency = 0.0

            for i, problem in enumerate(problems):
                prompt = benchmark.build_prompt(problem)
                response = await provider.complete(
                    prompt=prompt,
                    model=target.model,
                    max_tokens=2048,
                    temperature=0.0,
                    system=benchmark.system_prompt,
                )
                score = await benchmark.evaluate(problem, response, judge_provider)

                if score.correct:
                    n_correct += 1
                total_cost += response.cost_usd
                total_latency += response.latency_ms

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
                    cost_usd=response.cost_usd,
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
                        "i": i + 1,
                        "n": n,
                        "correct": score.correct,
                        "running_accuracy": n_correct / (i + 1),
                        "running_cost": round(total_cost, 6),
                        "latency_ms": round(response.latency_ms, 1),
                        "error": score.error or response.error,
                    },
                )

            yield ProgressEvent(
                event="model_done",
                run_id=run_id,
                payload={
                    "provider": target.provider,
                    "model": target.model,
                    "accuracy": n_correct / max(n, 1),
                    "n_correct": n_correct,
                    "n_total": n,
                    "total_cost": round(total_cost, 6),
                    "avg_latency_ms": round(total_latency / max(n, 1), 1),
                },
            )

        db.finish_run(run_id, "completed")
        yield ProgressEvent(event="done", run_id=run_id, payload={})

    except Exception as e:
        db.finish_run(run_id, "failed")
        yield ProgressEvent(
            event="error", run_id=run_id, payload={"error": f"{type(e).__name__}: {e}"}
        )


def event_to_sse(ev: ProgressEvent) -> str:
    """تحويل ProgressEvent إلى تنسيق Server-Sent Events."""
    return f"event: {ev.event}\ndata: {json.dumps({'run_id': ev.run_id, **ev.payload}, ensure_ascii=False)}\n\n"
