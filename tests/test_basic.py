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


def test_saudi_legal_has_100_questions():
    """البنشمارك السعودي المخصص يحتوي 100 سؤال على الأقل."""
    from backend.benchmarks import make_benchmark

    b = make_benchmark("saudi_legal")
    problems = b.load()
    assert len(problems) >= 100, f"المتوقّع 100+ سؤال، الفعلي: {len(problems)}"

    # تأكّد من وجود تصنيفات متنوعة
    categories = {p.metadata.get("category") for p in problems}
    assert len(categories) >= 10, f"المتوقع 10+ تصنيفات، الفعلي: {len(categories)}"

    # تأكّد من وجود مستويات صعوبة
    difficulties = {p.metadata.get("difficulty") for p in problems}
    assert {"سهل", "متوسط", "صعب"}.issubset(difficulties), (
        f"يجب وجود المستويات الثلاثة، الفعلي: {difficulties}"
    )

    # كل سؤال له مصدر
    no_source = [p.id for p in problems if not p.metadata.get("source")]
    assert not no_source, f"أسئلة بدون مصدر: {no_source}"

    # كل سؤال له 4 خيارات
    bad_choices = [p.id for p in problems if len(p.metadata.get("choices", [])) != 4]
    assert not bad_choices, f"أسئلة بعدد خيارات غير 4: {bad_choices}"

    # IDs فريدة
    ids = [p.id for p in problems]
    assert len(ids) == len(set(ids)), "توجد IDs مكررة"


def test_saudi_legal_filters():
    """فلتر التصنيف والصعوبة في الـ runner يعمل بشكل صحيح."""
    from backend.benchmarks import make_benchmark
    from backend.runner import _filter_problems

    b = make_benchmark("saudi_legal")
    problems = b.load()

    # فلتر بتصنيف موجود
    filtered = _filter_problems(problems, ["نظام العمل"], [])
    assert filtered, "يجب إيجاد أسئلة في نظام العمل"
    assert all(p.metadata["category"] == "نظام العمل" for p in filtered)

    # فلتر بصعوبة "سهل"
    easy = _filter_problems(problems, [], ["سهل"])
    assert easy, "يجب إيجاد أسئلة سهلة"
    assert all(p.metadata["difficulty"] == "سهل" for p in easy)

    # فلتر مركّب: نظام العمل + متوسط
    combo = _filter_problems(problems, ["نظام العمل"], ["متوسط"])
    assert all(
        p.metadata["category"] == "نظام العمل" and p.metadata["difficulty"] == "متوسط"
        for p in combo
    )

    # فلتر فاضي = كل الأسئلة
    assert _filter_problems(problems, [], []) == problems


def test_get_benchmark_difficulties():
    """endpoint مستويات الصعوبة يرتّب المستويات بشكل مفهوم."""
    from backend.benchmarks import get_benchmark_difficulties

    diffs = get_benchmark_difficulties("saudi_legal")
    assert diffs == ["سهل", "متوسط", "صعب"]


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


def test_response_cache_roundtrip():
    """التخزين المؤقت يحفظ ويرجّع الاستجابة."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        import backend.db as db
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()

        key = db.make_cache_key("anthropic", "claude-haiku", "ما 1+1؟", "system", 0.0)
        assert db.cache_get(key) is None

        db.cache_put(
            key, "anthropic", "claude-haiku",
            text="2", input_tokens=10, output_tokens=1, cost_usd=0.0001, latency_ms=42.5,
        )

        got = db.cache_get(key)
        assert got is not None
        assert got["response_text"] == "2"
        assert got["input_tokens"] == 10

        # نفس المدخلات = نفس المفتاح
        key2 = db.make_cache_key("anthropic", "claude-haiku", "ما 1+1؟", "system", 0.0)
        assert key == key2

        # مدخل مختلف = مفتاح مختلف
        key3 = db.make_cache_key("anthropic", "claude-haiku", "ما 2+2؟", "system", 0.0)
        assert key3 != key

        stats = db.cache_stats()
        assert stats["entries"] == 1


def test_benchmark_categories_endpoint_logic():
    """البنشمارك السعودي يعرض تصنيفات متعددة."""
    from backend.benchmarks import get_benchmark_categories

    cats = get_benchmark_categories("saudi_legal")
    assert len(cats) >= 5
    # كل تصنيف عبارة عن string غير فاضي
    assert all(isinstance(c, str) and c for c in cats)


def test_run_request_accepts_new_options():
    """RunRequest يقبل الحقول الجديدة (cache, budget, categories)."""
    from backend.runner import RunRequest, ModelTarget

    req = RunRequest(
        benchmark="saudi_legal",
        targets=[ModelTarget(provider="ollama", model="x", api_key="")],
        n_problems=2,
        use_cache=False,
        budget_usd=0.50,
        categories=["نظام العمل"],
    )
    assert req.use_cache is False
    assert req.budget_usd == 0.50
    assert req.categories == ["نظام العمل"]


def test_head_to_head_matrix():
    """مصفوفة المقارنة الزوجية تحسب بشكل صحيح."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        import backend.db as db
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()

        run_id = db.create_run("saudi_legal", 3, {})
        # نموذج A: صحيح في p1 و p2، خطأ في p3
        # نموذج B: صحيح في p1 فقط
        for pid, a_correct, b_correct in [("p1", True, True), ("p2", True, False), ("p3", False, False)]:
            db.insert_result(run_id, "anthropic", "claude-x", pid,
                             correct=a_correct, raw_score=1.0 if a_correct else 0.0,
                             latency_ms=10, input_tokens=1, output_tokens=1, cost_usd=0,
                             response_text="", judgment="", error=None)
            db.insert_result(run_id, "openai", "gpt-x", pid,
                             correct=b_correct, raw_score=1.0 if b_correct else 0.0,
                             latency_ms=10, input_tokens=1, output_tokens=1, cost_usd=0,
                             response_text="", judgment="", error=None)
        db.finish_run(run_id)

        h2h = db.head_to_head(run_id)
        assert h2h is not None
        assert len(h2h["models"]) == 2
        models = h2h["models"]
        # نحدد فهرس كل نموذج
        idx = {(m["provider"], m["model"]): i for i, m in enumerate(models)}
        i_a = idx[("anthropic", "claude-x")]
        i_b = idx[("openai", "gpt-x")]

        # خلية A ضد B: both=1 (p1)، a_only=1 (p2)، b_only=0، both_wrong=1 (p3)
        cell = h2h["matrix"][i_a][i_b]
        assert cell["both_correct"] == 1
        assert cell["a_only"] == 1
        assert cell["b_only"] == 0
        assert cell["both_wrong"] == 1
        assert cell["n_compared"] == 3

        # القطر: نفس النموذج، a_only = b_only = 0
        diag = h2h["matrix"][i_a][i_a]
        assert diag["a_only"] == 0 and diag["b_only"] == 0


def test_head_to_head_returns_none_for_missing_run():
    """h2h يرجع None لـ run غير موجود."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        import backend.db as db
        db.DB_PATH = Path(tmp) / "test.db"
        db.init_db()
        assert db.head_to_head("nonexistent") is None


def test_db_lifecycle():
    """اختبار دورة حياة run كامل."""
    import tempfile
    from pathlib import Path

    # استخدم DB مؤقت
    with tempfile.TemporaryDirectory() as tmp:
        import backend.db as db
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
        test_saudi_legal_has_100_questions,
        test_saudi_legal_filters,
        test_get_benchmark_difficulties,
        test_sandbox_runs_simple_code,
        test_sandbox_blocks_dangerous_code,
        test_sandbox_timeout,
        test_gsm8k_extract_answer,
        test_mmlu_extract_letter,
        test_arabic_mmlu_extract_letter,
        test_head_to_head_matrix,
        test_head_to_head_returns_none_for_missing_run,
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
