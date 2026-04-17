"""خادم FastAPI لمنصة البنشمارك."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import db
from backend.benchmarks import BENCHMARKS, list_benchmarks
from backend.providers import PROVIDERS
from backend.providers.ollama import OllamaProvider
from backend.runner import ModelTarget, RunRequest, event_to_sse, run_benchmark
from backend.pricing import PRICING

ROOT = Path(__file__).parent.parent
FRONTEND_DIR = ROOT / "frontend"

app = FastAPI(title="AI Benchmark Platform", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
    n_problems: int = Field(default=10, ge=1, le=100)
    targets: list[dict]
    judge: dict | None = None


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


@app.delete("/api/runs/{run_id}")
def delete_run(run_id: str):
    if not db.delete_run(run_id):
        raise HTTPException(404, "Run غير موجود")
    return {"ok": True}


# ================== الواجهة ==================

if FRONTEND_DIR.exists():
    @app.get("/")
    def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
