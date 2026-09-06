"""محرّك تشغيل البنشمارك مع تتبّع التقدّم."""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import AsyncIterator, Awaitable, Callable

from backend import db
from backend.benchmarks import filter_problems, make_benchmark
from backend.benchmarks.base import BaseBenchmark, EvalContext, JudgeSpec, Problem
from backend.completion import complete_with_cache
from backend.logging_config import get_logger
from backend.pricing import get_price
from backend.providers import make_provider
from backend.sandbox import backend_status

logger = get_logger(__name__)


def _get_concurrency() -> int:
    """مستوى التزامن لكل نموذج (عدد الاستدعاءات المتوازية). قابل للضبط عبر env."""
    try:
        val = int(os.getenv("RUN_CONCURRENCY", "5"))
    except ValueError:
        return 5
    return max(1, min(val, 32))


def _get_target_concurrency(n_targets: int) -> int:
    """كم نموذجاً يُختبَر في وقت واحد. الافتراضي: كلّها بالتوازي.

    صمّام أمان لمن يضرب حدود المعدّل عند مزوّد واحد بعدّة نماذج: ضبط
    ``RUN_TARGET_CONCURRENCY=1`` يعيد السلوك التسلسلي القديم.
    """
    try:
        val = int(os.getenv("RUN_TARGET_CONCURRENCY", "0"))
    except ValueError:
        return n_targets
    return n_targets if val <= 0 else min(val, n_targets)


class StopReason(str, Enum):
    """سبب توقّف التشغيل قبل إكماله.

    كان سلسلة نصّية تُقارن بـ``"budget"`` و``"disconnect"`` في ثلاثة مواضع
    متباعدة؛ خطأ مطبعي في أيّها كان يمرّ بصمت ويقلب الحالة النهائية.
    """

    BUDGET = "budget"
    DISCONNECT = "disconnect"


#: الحالة النهائية المقابلة لكل سبب توقّف
_STATUS_BY_STOP_REASON = {
    StopReason.DISCONNECT: "aborted_disconnect",
    StopReason.BUDGET: "aborted_budget",
}


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
    event: str  # "start" | "progress" | "result" | "model_done" | "done" | "error"
                # | "budget_exceeded" | "budget_unreliable" | "sandbox_warning"
                # | "model_error"
    run_id: str
    payload: dict


@dataclass
class TargetStats:
    """إحصاءات تراكمية لنموذج واحد أثناء تشغيله."""
    n_correct: int = 0
    completed: int = 0
    total_cost: float = 0.0
    total_latency: float = 0.0

    @property
    def accuracy(self) -> float:
        return self.n_correct / max(self.completed, 1)

    @property
    def avg_latency_ms(self) -> float:
        return self.total_latency / max(self.completed, 1)


class RunBudget:
    """التكلفة التراكمية عبر كل النماذج، محميّة بقفل.

    كانت تُمرَّر داخلاً وخارجاً في كل ``yield`` لأن النماذج تُشغَّل بالتتابع.
    مع تشغيلها بالتوازي صارت حالة مشتركة، فجُمِعت هنا مع قفلها بدل أن تُنسَخ
    بين المولّدات وتضيع تحديثاتها.
    """

    def __init__(self, limit: float | None = None):
        self.limit = limit
        self.spent = 0.0
        self._announced = False
        self._lock = asyncio.Lock()

    async def add(self, amount: float) -> tuple[float, bool, bool]:
        """يضيف تكلفة ويرجع ``(المجموع، هل بلغنا الحدّ، هل نحن أوّل من بلغه)``.

        ``first`` يضمن حدث ``budget_exceeded`` واحداً مهما تجاوزه من نموذج
        بالتوازي، بينما ``exceeded`` يوقف كل النماذج لا الأوّل وحده.
        """
        async with self._lock:
            self.spent += amount
            exceeded = self.limit is not None and self.spent >= self.limit
            first = exceeded and not self._announced
            if first:
                self._announced = True
            return self.spent, exceeded, first


def unpriced_targets(targets: list[ModelTarget]) -> list[str]:
    """النماذج التي لا نملك سعرها — حدّ الميزانية لا يراها.

    ``estimate_cost`` يرجع ``0.0`` عند غياب السعر، فتشغيل بحدّ ``$0.50`` على
    نموذج بلا تسعير يبقى عند ``0.00`` طول الوقت والحدّ **لا يُفعَّل أبداً**.
    Ollama مستثنى: تكلفته صفر فعلاً لا مجهولة.
    """
    return [
        f"{t.provider}/{t.model}"
        for t in targets
        if t.provider != "ollama" and get_price(t.provider, t.model) is None
    ]


async def _record_result(
    *,
    run_id: str,
    target: ModelTarget,
    problem: Problem,
    response,
    score,
    cache_hit: bool,
    call_cost: float,
    stats: TargetStats,
    n: int,
    spent: float,
) -> ProgressEvent:
    """يحفظ نتيجة مسألة واحدة ويبني حدث تقدّمها.

    استُخرجت من حلقة ``_run_target``: بقاؤها هناك كان يجعل الحلقة أربعة مستويات
    تداخل تخلط الجدولة بالتخزين ببناء الأحداث، فلا تُقرأ في شاشة واحدة.

    الكتابة في thread: استدعاء SQLite متزامن هنا يجمّد حلقة الأحداث وبثّ SSE
    لبقيّة النماذج معه.
    """
    error = score.error or response.error
    await asyncio.to_thread(
        db.insert_result,
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
        error=error,
    )
    return ProgressEvent(
        event="progress",
        run_id=run_id,
        payload={
            "provider": target.provider,
            "model": target.model,
            "problem_id": problem.id,
            "i": stats.completed,
            "n": n,
            "correct": score.correct,
            "running_accuracy": stats.accuracy,
            "running_cost": round(stats.total_cost, 6),
            "grand_total_cost": round(spent, 6),
            "latency_ms": round(response.latency_ms, 1),
            "cache_hit": cache_hit,
            "error": error,
        },
    )


async def _run_target(
    *,
    run_id: str,
    target: ModelTarget,
    problems: list[Problem],
    benchmark: BaseBenchmark,
    ctx: EvalContext,
    budget: RunBudget,
    concurrency: int,
    stop_event: asyncio.Event,
    is_disconnected: Callable[[], Awaitable[bool]] | None,
) -> AsyncIterator[tuple[ProgressEvent | None, StopReason | None]]:
    """يشغّل كل مسائل نموذج واحد بالتوازي ويُنتج أحداث التقدّم.

    يُنتج أزواج ``(event, stop_reason)`` حيث ``stop_reason`` من ``StopReason``
    أو ``None``. فصلها عن الحلقة الخارجية أبقى
    ``run_benchmark`` قابلاً للقراءة بدل نطاق واحد يجمع الجدولة والتكلفة
    والتخزين وبثّ الأحداث.
    """
    provider = make_provider(target.provider, target.api_key, target.base_url)
    stats = TargetStats()
    n = len(problems)
    sem = asyncio.Semaphore(concurrency)

    async def _process(problem: Problem):
        async with sem:
            prompt = benchmark.build_prompt(problem)
            response, cache_hit = await complete_with_cache(
                provider,
                prompt=prompt,
                model=target.model,
                system=benchmark.system_prompt,
                max_tokens=2048,
                temperature=0.0,
                use_cache=ctx.use_cache,
            )
            score = await benchmark.evaluate(problem, response, ctx)
            return problem, response, score, cache_hit

    tasks = [asyncio.create_task(_process(p)) for p in problems]
    stop_reason: StopReason | None = None
    try:
        for fut in asyncio.as_completed(tasks):
            problem, response, score, cache_hit = await fut
            stats.completed += 1
            # تكلفة المسألة = تكلفة النموذج + تكلفة الحَكَم (إن وُجد)
            call_cost = response.cost_usd + score.judge_cost_usd

            if score.correct:
                stats.n_correct += 1
            stats.total_cost += call_cost
            stats.total_latency += response.latency_ms
            spent, over_budget, first_over = await budget.add(call_cost)

            event = await _record_result(
                run_id=run_id, target=target, problem=problem, response=response,
                score=score, cache_hit=cache_hit, call_cost=call_cost,
                stats=stats, n=n, spent=spent,
            )
            yield (event, None)

            # فحص الميزانية بعد كل استدعاء (تقريبي: قد يتجاوز بمقدار
            # الاستدعاءات المتوازية المتبقّية قيد التنفيذ)
            if over_budget:
                stop_reason = StopReason.BUDGET
                if first_over:
                    logger.info(
                        "run %s: تجاوز الميزانية (%.6f >= %.6f)",
                        run_id, spent, budget.limit,
                    )
                    yield (
                        ProgressEvent(
                            event="budget_exceeded",
                            run_id=run_id,
                            payload={
                                "budget_usd": budget.limit,
                                "spent_usd": round(spent, 6),
                                "message": "تم تجاوز الميزانية المحدّدة. توقّف التشغيل.",
                            },
                        ),
                        stop_reason,
                    )
                else:
                    # نموذج آخر أعلن التجاوز — نتوقّف بصمت بلا حدث مكرّر
                    yield (None, stop_reason)
                break

            # لو أغلق العميل الاتصال نوقف ونلغي الباقي (لا نُنفق بلا فائدة)
            if is_disconnected is not None and await is_disconnected():
                stop_reason = StopReason.DISCONNECT
                logger.info("run %s: العميل أغلق الاتصال — إيقاف", run_id)
                yield (None, stop_reason)
                break

            # نموذج آخر أوقف التشغيل (ميزانية أو انقطاع) — لا نُكمل الإنفاق
            if stop_event.is_set():
                break
    finally:
        # إلغاء أي استدعاءات معلّقة وابتلاع استثناءات الإلغاء
        for tk in tasks:
            if not tk.done():
                tk.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    if stop_reason is not StopReason.DISCONNECT:
        yield (
            ProgressEvent(
                event="model_done",
                run_id=run_id,
                payload={
                    "provider": target.provider,
                    "model": target.model,
                    "accuracy": stats.accuracy,
                    "n_correct": stats.n_correct,
                    "n_total": stats.completed,
                    "total_cost": round(stats.total_cost, 6),
                    "avg_latency_ms": round(stats.avg_latency_ms, 1),
                },
            ),
            stop_reason,
        )


def _build_eval_context(req: RunRequest) -> EvalContext:
    """يبني سياق التقييم — الحَكَم صريح بدل تحوير كتالوج المزوّد."""
    judge = None
    if req.judge:
        judge = JudgeSpec(
            provider=make_provider(
                req.judge.provider, req.judge.api_key, req.judge.base_url
            ),
            model=req.judge.model,
        )
    return EvalContext(
        judge=judge,
        enforce_safety=req.enforce_safety,
        use_cache=req.use_cache,
    )


async def run_benchmark(
    req: RunRequest,
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
) -> AsyncIterator[ProgressEvent]:
    """يشغّل البنشمارك ويُنتج أحداث تقدّم لحظية (async generator).

    ``is_disconnected``: دالة اختيارية تُرجع True إذا أغلق العميل الاتصال،
    فنوقف التشغيل ونلغي الاستدعاءات المعلّقة بدل إنفاق تكلفة بلا فائدة.

    النماذج تُختبَر **بالتوازي**: زمن التشغيل صار أطول نموذج لا مجموع النماذج،
    وهو ما تعنيه منصّة غرضها المقارنة. الميزانية تبقى مشتركة عبر ``RunBudget``.
    """
    benchmark = make_benchmark(req.benchmark)
    all_problems = benchmark.load()
    filtered = filter_problems(all_problems, req.categories, req.difficulties)
    problems = filtered[: req.n_problems]
    n = len(problems)

    # خطّ أساس التخمين على **مسائل هذا التشغيل** بعد الفلترة والقصّ: من يشغّل
    # خمس مسائل يحتاج خطّ الأساس لتلك الخمس لا للداتاست كاملاً. يُحفظ في
    # ``config`` ليظهر في السجل أيضاً، لا في التشغيل الحيّ وحده.
    baselines = benchmark.guess_baselines(problems)

    config = {
        "benchmark": req.benchmark,
        "n_problems": n,
        "baselines": baselines,
        "models": [{"provider": t.provider, "model": t.model} for t in req.targets],
        "judge": (
            {"provider": req.judge.provider, "model": req.judge.model}
            if req.judge else None
        ),
        "use_cache": req.use_cache,
        "budget_usd": req.budget_usd,
        "categories": req.categories,
        "difficulties": req.difficulties,
        "enforce_safety": req.enforce_safety,
    }
    run_id = await asyncio.to_thread(db.create_run, req.benchmark, n, config)
    logger.info(
        "run %s: بدء %s — %d مسألة × %d نموذج",
        run_id, req.benchmark, n, len(req.targets),
    )

    yield ProgressEvent(
        event="start",
        run_id=run_id,
        payload={
            "n_problems": n,
            "n_models": len(req.targets),
            "total_calls": n * len(req.targets),
            "use_cache": req.use_cache,
            "budget_usd": req.budget_usd,
            "baselines": baselines,
        },
    )

    # الفلترة قد تُنتج صفر مسائل. بدون هذا الفحص يُنشَأ run فارغ وتظهر
    # للمستخدم دقّة 0% بدل رسالة تشرح أن الفلتر لم يطابق شيئاً.
    if n == 0:
        await asyncio.to_thread(db.finish_run, run_id, "failed")
        yield ProgressEvent(
            event="error",
            run_id=run_id,
            payload={
                "error": "لا توجد مسائل مطابقة للفلاتر المختارة — "
                         "وسّع التصنيف أو مستوى الصعوبة."
            },
        )
        return

    # تحذير قبل أي إنفاق: حدّ الميزانية لا يرى النماذج التي لا نملك سعرها
    if req.budget_usd is not None:
        unpriced = unpriced_targets(req.targets)
        if unpriced:
            logger.warning("run %s: حدّ ميزانية مع نماذج بلا سعر: %s", run_id, unpriced)
            yield ProgressEvent(
                event="budget_unreliable",
                run_id=run_id,
                payload={
                    "models": unpriced,
                    "message": (
                        "حدّ الميزانية لا يشمل هذه النماذج — لا نملك أسعارها فتُحسب "
                        "تكلفتها صفراً، ولن يوقف الحدّ التشغيل مهما أُنفق."
                    ),
                },
            )

    # تحذير قبل أي تنفيذ: كود النماذج سيُشغَّل على الجهاز بلا عزل حقيقي
    if benchmark.executes_code:
        # في thread: ``backend_status`` قد يشغّل ``docker version`` بمهلة 5
        # ثوانٍ، واستدعاؤه هنا مباشرةً كان يجمّد بثّ SSE لكل المستخدمين طوال
        # تلك المدّة على جهاز فيه docker في الـPATH وdaemon متوقّف
        sandbox = await asyncio.to_thread(backend_status)
        if not sandbox["is_isolated"]:
            logger.warning("run %s: تشغيل كود بلا عزل (%s)", run_id, sandbox["backend"])
            yield ProgressEvent(
                event="sandbox_warning",
                run_id=run_id,
                payload={
                    "backend": sandbox["backend"],
                    "docker_available": sandbox["docker_available"],
                    "message": (
                        "كود النماذج سيُنفَّذ على جهازك بلا عزل حقيقي. "
                        "ثبّت Docker أو اضبط SANDBOX_BACKEND=docker قبل النشر."
                    ),
                },
            )

    ctx = _build_eval_context(req)
    budget = RunBudget(limit=req.budget_usd)
    stop_event = asyncio.Event()
    stop_reasons: list[StopReason] = []
    errors: list[tuple[ModelTarget, BaseException]] = []
    queue: asyncio.Queue = asyncio.Queue()
    target_sem = asyncio.Semaphore(_get_target_concurrency(len(req.targets)))
    concurrency = _get_concurrency()
    _DONE = object()

    async def _pump(target: ModelTarget) -> None:
        """يشغّل نموذجاً واحداً ويدفع أحداثه في الطابور المشترك."""
        try:
            async with target_sem:
                if stop_event.is_set():
                    return
                async for event, reason in _run_target(
                    run_id=run_id,
                    target=target,
                    problems=problems,
                    benchmark=benchmark,
                    ctx=ctx,
                    budget=budget,
                    concurrency=concurrency,
                    stop_event=stop_event,
                    is_disconnected=is_disconnected,
                ):
                    if event is not None:
                        await queue.put(event)
                    if reason:
                        stop_reasons.append(reason)
                        stop_event.set()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — نُبلّغ عنه حدثاً ونُكمل البقيّة
            logger.exception("run %s: فشل النموذج %s/%s", run_id, target.provider, target.model)
            errors.append((target, e))
            # حدث لهذا النموذج وحده بدل إسقاط الـ run: نتائج النماذج الأخرى
            # محفوظة وصحيحة، وكان ``raise errors[0]`` يعلّمها كلّها «failed»
            await queue.put(ProgressEvent(
                event="model_error",
                run_id=run_id,
                payload={
                    "provider": target.provider,
                    "model": target.model,
                    "error": f"{type(e).__name__}: {e}",
                    "message": (
                        f"توقّف {target.provider}/{target.model} بخطأ — "
                        "بقيّة النماذج أكملت وتظهر نتائجها."
                    ),
                },
            ))
        finally:
            await queue.put(_DONE)

    pumps = [asyncio.create_task(_pump(t)) for t in req.targets]
    try:
        remaining = len(pumps)
        while remaining:
            item = await queue.get()
            if item is _DONE:
                remaining -= 1
                continue
            yield item

        stop_reason = stop_reasons[0] if stop_reasons else None
        if stop_reason is not None:
            final_status = _STATUS_BY_STOP_REASON[stop_reason]
        else:
            final_status = "completed_with_errors" if errors else "completed"
        await asyncio.to_thread(db.finish_run, run_id, final_status)
        logger.info("run %s: انتهى بحالة %s", run_id, final_status)
        if stop_reason is not StopReason.DISCONNECT:
            yield ProgressEvent(
                event="done",
                run_id=run_id,
                payload={
                    "status": final_status,
                    "failed_models": [
                        f"{t.provider}/{t.model}" for t, _ in errors
                    ],
                },
            )

    except asyncio.CancelledError:
        await asyncio.to_thread(db.finish_run, run_id, "aborted_disconnect")
        logger.info("run %s: أُلغي", run_id)
        raise
    except Exception as e:
        await asyncio.to_thread(db.finish_run, run_id, "failed")
        logger.exception("run %s: فشل غير متوقّع", run_id)
        yield ProgressEvent(
            event="error", run_id=run_id, payload={"error": f"{type(e).__name__}: {e}"}
        )
    finally:
        # لو هُجِر المولّد (أغلق العميل الاتصال) لا نترك استدعاءات معلّقة تُنفق
        stop_event.set()
        for tk in pumps:
            if not tk.done():
                tk.cancel()
        await asyncio.gather(*pumps, return_exceptions=True)


def event_to_sse(ev: ProgressEvent) -> str:
    """تحويل ProgressEvent إلى تنسيق Server-Sent Events."""
    return f"event: {ev.event}\ndata: {json.dumps({'run_id': ev.run_id, **ev.payload}, ensure_ascii=False)}\n\n"
