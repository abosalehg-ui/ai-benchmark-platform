"""يزرع تشغيلاً وهمياً في قاعدة البيانات — لاختبار الواجهة بلا مفاتيح API.

يستخدمه اختبار الدخان في CI، ويصلح للتطوير المحلي: صفحات السجل والملخّص
والانحراف كلها فارغة قبل أوّل تشغيل حقيقي، فمراجعتها كانت تتطلّب إنفاق مال
على استدعاءات فعلية.

    python scripts/seed_demo_run.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import db  # noqa: E402
from backend.benchmarks import make_benchmark  # noqa: E402

BENCHMARK = "saudi_legal"
MODELS = [("anthropic", "claude-sonnet-5", 8), ("openai", "gpt-5.4", 6)]
N = 10


def seed() -> str:
    db.init_db()
    benchmark = make_benchmark(BENCHMARK)
    problems = benchmark.load()[:N]
    config = {
        "benchmark": BENCHMARK,
        "n_problems": N,
        "categories": [],
        "difficulties": [],
        # نفس الشكل الذي يكتبه ``runner`` حتى يختبر الدخان العرض الحقيقي
        "baselines": benchmark.guess_baselines(problems),
    }
    run_id = db.create_run(BENCHMARK, N, config)
    for provider, model, n_correct in MODELS:
        for i, problem in enumerate(problems):
            db.insert_result(
                run_id, provider, model, problem.id,
                correct=i < n_correct,
                raw_score=1.0 if i < n_correct else 0.0,
                latency_ms=120.0 + i,
                input_tokens=200, output_tokens=40,
                cost_usd=0.0004,
                response_text=f"الإجابة: {problem.reference}",
                judgment="بيانات تجريبية",
            )
    db.finish_run(run_id, "completed")
    return run_id


if __name__ == "__main__":
    print(seed())
