"""يزرع تشغيلات وهمية في قاعدة البيانات — لاختبار الواجهة بلا مفاتيح API.

يستخدمه اختبار الدخان في CI، ويصلح للتطوير المحلي: صفحات السجل والملخّص
والانحراف كلها فارغة قبل أوّل تشغيل حقيقي، فمراجعتها كانت تتطلّب إنفاق مال
على استدعاءات فعلية.

**تشغيلان لا واحد، عمداً:** صفحة الانحراف تحتاج تشغيلين على الأقل لنفس
(البنشمارك، النموذج) لتُظهر أي شيء. زرع تشغيل واحد كان يترك التبويب فارغاً
فيفشل فحص الدخان — وهو ما حدث فعلاً في CI بينما مرّ محلياً على قاعدة فيها
تشغيلات قديمة متراكمة.

التشغيلان متطابقا النطاق (نفس عدد المسائل، بلا فلاتر) حتى يكونا قابلين
للمقارنة فيُحسب لهما ``latest_change`` بدل أن يُوسما «نطاقات مختلطة».

    python scripts/seed_demo_run.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend import db  # noqa: E402
from backend.benchmarks import make_benchmark  # noqa: E402

BENCHMARK = "saudi_legal"
N = 10
DAY = 86400.0

#: تشغيلان: القديم ثم الأحدث، وبينهما فرق دقّة يُظهر اتجاهاً في صفحة الانحراف
RUNS = [
    {"age_days": 9, "models": [("anthropic", "claude-sonnet-5", 7), ("openai", "gpt-5.4", 5)]},
    {"age_days": 0, "models": [("anthropic", "claude-sonnet-5", 8), ("openai", "gpt-5.4", 6)]},
]


def _seed_one(benchmark, problems, config, models, created_at) -> str:
    run_id = db.create_run(BENCHMARK, N, config)
    for provider, model, n_correct in models:
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
    # التاريخ يُضبط يدوياً: التشغيلان يُنشآن في نفس الثانية وإلا بدا التتبّع
    # كأنه لحظة واحدة، و«المدى» صفر يوم
    with db.get_conn() as conn:
        conn.execute("UPDATE runs SET created_at = ? WHERE id = ?", (created_at, run_id))
    return run_id


def seed() -> list[str]:
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
    now = time.time()
    return [
        _seed_one(benchmark, problems, config, spec["models"], now - spec["age_days"] * DAY)
        for spec in RUNS
    ]


if __name__ == "__main__":
    print(" ".join(seed()))
