"""اختبارات أساسية للتحقق من سلامة المشروع."""
from __future__ import annotations

import sys
from pathlib import Path

# إضافة جذر المشروع للـ path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))


def test_providers_import():
    """تأكّد من أن كل المزودين يستوردون بنجاح."""
    from backend.providers import PROVIDERS, make_provider

    expected = {"anthropic", "openai", "gemini", "ollama", "openrouter"}
    assert set(PROVIDERS.keys()) == expected, f"المزودون المتوقعون: {expected}"

    # تجربة إنشاء واحد من كل نوع
    for name in PROVIDERS:
        p = make_provider(name, api_key="dummy")
        assert p.name == name


def test_benchmarks_load():
    """تأكّد من أن كل البنشماركات تحمّل بياناتها."""
    from backend.benchmarks import BENCHMARKS, make_benchmark

    for name in BENCHMARKS:
        b = make_benchmark(name)
        problems = b.load()
        assert len(problems) > 0, f"{name}: لا توجد مسائل"
        # تأكّد من صحة بنية المسألة
        p = problems[0]
        assert p.id
        assert p.prompt


def test_saudi_legal_has_30_questions():
    """البنشمارك السعودي المخصص يحتوي 30 سؤالاً على الأقل."""
    from backend.benchmarks import make_benchmark

    b = make_benchmark("saudi_legal")
    problems = b.load()
    assert len(problems) >= 30, f"المتوقّع 30+ سؤال، الفعلي: {len(problems)}"

    # تأكّد من وجود تصنيفات متنوعة
    categories = {p.metadata.get("category") for p in problems}
    assert len(categories) >= 5, f"المتوقع 5+ تصنيفات، الفعلي: {len(categories)}"


def test_sandbox_runs_simple_code():
    """الـ sandbox يشغّل كود بسيط بنجاح."""
    from backend.sandbox import run_python_code

    result = run_python_code(
        "def add(a, b): return a + b",
        "assert add(2, 3) == 5",
        timeout=5,
    )
    assert result.passed, f"فشل الاختبار: {result.error} / {result.stderr}"


def test_sandbox_blocks_dangerous_code():
    """الـ sandbox يمنع الكود الخطر."""
    from backend.sandbox import run_python_code

    result = run_python_code(
        "import os\nos.system('echo hi')",
        "",
        timeout=5,
    )
    assert not result.passed
    assert result.blocked_reason is not None


def test_sandbox_timeout():
    """الـ sandbox يوقف الحلقات اللانهائية."""
    from backend.sandbox import run_python_code

    result = run_python_code(
        "while True: pass",
        "",
        timeout=2,
        enforce_safety=False,
    )
    assert not result.passed
    assert result.timed_out


def test_gsm8k_extract_answer():
    """استخراج الإجابة الرقمية من رد GSM8K."""
    from backend.benchmarks.gsm8k import GSM8KBenchmark

    assert GSM8KBenchmark.extract_answer("Step by step... #### 42") == 42.0
    assert GSM8KBenchmark.extract_answer("The answer is 3.14") == 3.14
    assert GSM8KBenchmark.extract_answer("no number here") is None


def test_mmlu_extract_letter():
    """استخراج الحرف من رد MMLU."""
    from backend.benchmarks.mmlu import MMLUBenchmark

    assert MMLUBenchmark.extract_letter("Answer: B") == "B"
    assert MMLUBenchmark.extract_letter("I think C is correct") == "C"


def test_arabic_mmlu_extract_letter():
    """استخراج الحرف العربي من رد ArabicMMLU."""
    from backend.benchmarks.arabic_mmlu import ArabicMMLUBenchmark

    assert ArabicMMLUBenchmark.extract_letter("الإجابة: ب") == "ب"
    # مع همزة مختلفة
    assert ArabicMMLUBenchmark.extract_letter("الإجابة: أ") == "أ"


def test_db_lifecycle():
    """اختبار دورة حياة run كامل."""
    import os
    import tempfile

    # استخدم DB مؤقت
    with tempfile.TemporaryDirectory() as tmp:
        import backend.db as db
        from pathlib import Path
        db.DB_PATH = Path(tmp) / "test.db"

        db.init_db()
        run_id = db.create_run("humaneval", 5, {"test": True})
        assert run_id

        db.insert_result(
            run_id, "anthropic", "claude-opus-4-7", "p1",
            correct=True, raw_score=1.0, latency_ms=100.0,
            input_tokens=50, output_tokens=30, cost_usd=0.001,
            response_text="def f(): pass", judgment="passed",
        )

        db.finish_run(run_id, "completed")
        run = db.get_run(run_id)
        assert run is not None
        assert run["status"] == "completed"
        assert len(run["models"]) == 1


if __name__ == "__main__":
    # تشغيل سريع بدون pytest
    tests = [
        test_providers_import,
        test_benchmarks_load,
        test_saudi_legal_has_30_questions,
        test_sandbox_runs_simple_code,
        test_sandbox_blocks_dangerous_code,
        test_sandbox_timeout,
        test_gsm8k_extract_answer,
        test_mmlu_extract_letter,
        test_arabic_mmlu_extract_letter,
        test_db_lifecycle,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed + failed} نجحت")
    sys.exit(0 if failed == 0 else 1)
