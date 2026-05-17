"""خادم FastAPI لمنصة البنشمارك."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import db
from backend.benchmarks import (
    BENCHMARKS,
    get_benchmark_categories,
    get_benchmark_difficulties,
    list_benchmarks,
)
from backend.providers import PROVIDERS
from backend.providers.ollama import OllamaProvider
from backend.runner import ModelTarget, RunRequest, event_to_sse, run_benchmark
from backend.pricing import PRICING

ROOT = Path(__file__).parent.parent
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="AI Benchmark Platform", version="0.1.0")

# المنصة مصمّمة للاستخدام المحلي. لو احتجت توسيع origins حدّد ALLOWED_ORIGINS كـ env.
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
_allowed = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def _startup() -> None:
    db.init_db()


# ================== المسارات API ==================

@app.get("/api/providers")
def get_providers():
    """قائمة المزودين والنماذج المتاحة لكل واحد."""
    out = []
    for name, cls in PROVIDERS.items():
        out.append({
            "id": name,
            "models": cls.available_models,
            "needs_api_key": name != "ollama",
        })
    return {"providers": out}


@app.get("/api/benchmarks")
def get_benchmarks():
    return {"benchmarks": list_benchmarks()}


@app.get("/api/pricing")
def get_pricing():
    return PRICING


@app.get("/api/ollama/models")
async def get_ollama_models(base_url: str = "http://localhost:11434"):
    """جلب النماذج المثبتة محلياً في Ollama.

    يرجع: {"models": [...], "error": str | null}
    """
    p = OllamaProvider(base_url=base_url)
    result = await p.list_local_models()
    return result


class RunRequestBody(BaseModel):
    benchmark: str
    n_problems: int = Field(default=10, ge=1, le=200)
    targets: list[dict]
    judge: dict | None = None
    use_cache: bool = True
    budget_usd: float | None = Field(default=None, ge=0)
    categories: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    enforce_safety: bool = True


@app.get("/api/benchmarks/{benchmark_id}/categories")
def get_categories(benchmark_id: str):
    """قائمة التصنيفات المتاحة في البنشمارك (لو الداتاست يدعمها)."""
    if benchmark_id not in BENCHMARKS:
        raise HTTPException(404, "بنشمارك غير معروف")
    return {"categories": get_benchmark_categories(benchmark_id)}


@app.get("/api/benchmarks/{benchmark_id}/difficulties")
def get_difficulties(benchmark_id: str):
    """قائمة مستويات الصعوبة المتاحة في البنشمارك."""
    if benchmark_id not in BENCHMARKS:
        raise HTTPException(404, "بنشمارك غير معروف")
    return {"difficulties": get_benchmark_difficulties(benchmark_id)}


class EstimateRequestBody(BaseModel):
    benchmark: str
    n_problems: int = Field(default=10, ge=1, le=200)
    targets: list[dict]
    categories: list[str] = Field(default_factory=list)
    difficulties: list[str] = Field(default_factory=list)
    avg_output_tokens: int = Field(default=200, ge=1, le=4000)


@app.post("/api/estimate")
def estimate_cost(req: EstimateRequestBody):
    """تقدير تكلفة التشغيل قبل الانطلاق.

    يحسب متوسط طول الـ prompt من الداتاست الفعلي، ثم يضرب في أسعار كل نموذج.
    """
    from backend.benchmarks import make_benchmark
    from backend.pricing import get_price
    from backend.providers.base import estimate_tokens_from_text
    from backend.runner import _filter_problems

    if req.benchmark not in BENCHMARKS:
        raise HTTPException(404, "بنشمارك غير معروف")

    benchmark = make_benchmark(req.benchmark)
    problems = _filter_problems(benchmark.load(), req.categories, req.difficulties)
    problems = problems[: req.n_problems]
    if not problems:
        return {"total_usd": 0.0, "per_target": [], "n_problems_effective": 0, "notes": "لا توجد مسائل بعد الفلترة"}

    sys_tokens = estimate_tokens_from_text(benchmark.system_prompt or "")
    prompt_tokens = [
        estimate_tokens_from_text(benchmark.build_prompt(p)) + sys_tokens
        for p in problems
    ]
    total_input_tokens = sum(prompt_tokens)
    total_output_tokens = req.avg_output_tokens * len(problems)

    per_target = []
    grand_total = 0.0
    for t in req.targets:
        provider = t.get("provider", "")
        model = t.get("model", "")
        price = get_price(provider, model)
        cost = 0.0
        if price:
            cost = (
                (total_input_tokens / 1_000_000) * price["input"]
                + (total_output_tokens / 1_000_000) * price["output"]
            )
        per_target.append({
            "provider": provider,
            "model": model,
            "estimated_input_tokens": total_input_tokens,
            "estimated_output_tokens": total_output_tokens,
            "estimated_cost_usd": round(cost, 6),
            "has_price": price is not None,
        })
        grand_total += cost

    return {
        "total_usd": round(grand_total, 6),
        "per_target": per_target,
        "n_problems_effective": len(problems),
        "notes": "تقدير تقريبي مبنياً على طول النص (~3 حرف/توكن). التكلفة الفعلية قد تختلف.",
    }


@app.post("/api/run")
async def post_run(req: RunRequestBody):
    """تشغيل بنشمارك مع streaming لحظي عبر SSE."""
    if req.benchmark not in BENCHMARKS:
        raise HTTPException(404, f"بنشمارك غير معروف: {req.benchmark}")

    targets = [
        ModelTarget(
            provider=t["provider"],
            model=t["model"],
            api_key=t.get("api_key", ""),
            base_url=t.get("base_url"),
        )
        for t in req.targets
    ]
    if not targets:
        raise HTTPException(400, "يجب اختيار نموذج واحد على الأقل")

    judge = None
    if req.judge:
        judge = ModelTarget(
            provider=req.judge["provider"],
            model=req.judge["model"],
            api_key=req.judge.get("api_key", ""),
        )

    run_req = RunRequest(
        benchmark=req.benchmark,
        targets=targets,
        n_problems=req.n_problems,
        judge=judge,
        use_cache=req.use_cache,
        budget_usd=req.budget_usd,
        categories=req.categories,
        difficulties=req.difficulties,
        enforce_safety=req.enforce_safety,
    )

    async def stream():
        async for ev in run_benchmark(run_req):
            yield event_to_sse(ev)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/runs")
def get_runs():
    return {"runs": db.list_runs()}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run غير موجود")
    return run


@app.get("/api/runs/{run_id}/h2h")
def get_run_h2h(run_id: str):
    """مصفوفة المقارنة الزوجية (Head-to-Head) للـ run."""
    h2h = db.head_to_head(run_id)
    if h2h is None:
        raise HTTPException(404, "Run غير موجود")
    return h2h


@app.get("/api/runs/{run_id}/export")
def export_run(run_id: str, format: str = "json"):
    """تصدير نتائج Run كاملة بصيغة JSON أو CSV."""
    run = db.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run غير موجود")

    fmt = format.lower()
    if fmt == "json":
        import json as _json
        body = _json.dumps(run, ensure_ascii=False, indent=2)
        return PlainTextResponse(
            body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="run_{run_id}.json"'},
        )
    if fmt == "csv":
        import csv
        import io
        buf = io.StringIO()
        cols = [
            "run_id", "provider", "model", "problem_id", "correct", "raw_score",
            "latency_ms", "input_tokens", "output_tokens", "cost_usd",
            "judgment", "error", "response_text",
        ]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for d in run.get("details", []):
            w.writerow({k: d.get(k, "") for k in cols})
        # BOM علشان Excel يفتح UTF-8 صح
        return PlainTextResponse(
            "﻿" + buf.getvalue(),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="run_{run_id}.csv"'},
        )
    raise HTTPException(400, "format يجب أن يكون json أو csv")


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    if not db.delete_run(run_id):
        raise HTTPException(404, "Run غير موجود")
    return {"ok": True}


@app.get("/api/cache/stats")
def get_cache_stats():
    return db.cache_stats()


@app.delete("/api/cache")
def clear_cache():
    n = db.cache_clear()
    return {"cleared": n}


# ================== الواجهة ==================

if FRONTEND_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
