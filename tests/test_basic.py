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

    expected = {
        "anthropic", "openai", "gemini", "ollama", "openrouter",
        "groq", "mistral", "cohere", "xai",
    }
    assert set(PROVIDERS.keys()) == expected, f"المزودون المتوقعون: {expected}"

    # تجربة إنشاء واحد من كل نوع
    for name in PROVIDERS:
        p = make_provider(name, api_key="dummy")
        assert p.name == name


def test_new_providers_have_models_and_pricing():
    """كل المزودين الجدد لهم نماذج وأسعار معروفة."""
    from backend.pricing import get_price
    from backend.providers import PROVIDERS

    for name in ("groq", "mistral", "cohere", "xai"):
        cls = PROVIDERS[name]
        assert cls.available_models, f"{name} بدون نماذج"
        # كل نموذج له سعر
        for model in cls.available_models:
            price = get_price(name, model)
            assert price is not None, f"{name}/{model} بدون تسعير"
            assert price["input"] >= 0 and price["output"] >= 0


def test_estimate_tokens_from_text():
    """دالة تقدير التوكنات تعطي نتائج معقولة."""
    from backend.providers.base import estimate_tokens_from_text

    assert estimate_tokens_from_text("") == 0
    assert estimate_tokens_from_text("a") >= 1
    # نص عربي مكوّن من 30 حرفاً → ~10 توكن
    arabic = "هذا نص تجريبي يحتوي على عدّة كلمات."
    assert estimate_tokens_from_text(arabic) >= 5


def test_estimate_endpoint_logic():
    """منطق تقدير التكلفة يحسب بشكل صحيح."""
    from backend.benchmarks import make_benchmark
    from backend.pricing import get_price
    from backend.providers.base import estimate_tokens_from_text

    b = make_benchmark("saudi_legal")
    problems = b.load()[:3]
    sys_t = estimate_tokens_from_text(b.system_prompt or "")
    total = sum(estimate_tokens_from_text(b.build_prompt(p)) + sys_t for p in problems)
    assert total > 0

    price = get_price("anthropic", "claude-opus-4-7")
    cost = (total / 1_000_000) * price["input"] + (600 / 1_000_000) * price["output"]
    assert cost > 0


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
    assert result.backend in {"subprocess", "docker"}


def test_sandbox_backend_status_shape():
    """backend_status يرجع dict كامل ومتسق."""
    from backend.sandbox import backend_status, current_backend_name

    status = backend_status()
    assert "backend" in status
    assert status["backend"] in {"subprocess", "docker"}
    assert isinstance(status["docker_available"], bool)
    assert isinstance(status["is_isolated"], bool)
    assert status["backend"] == current_backend_name()


def test_sandbox_backend_selection_env(monkeypatch):
    """متغيّر SANDBOX_BACKEND يتحكم بالاختيار."""
    from backend.sandbox import current_backend_name

    monkeypatch.setenv("SANDBOX_BACKEND", "subprocess")
    assert current_backend_name() == "subprocess"

    monkeypatch.setenv("SANDBOX_BACKEND", "docker")
    assert current_backend_name() == "docker"

    # auto بدون docker = subprocess
    monkeypatch.setenv("SANDBOX_BACKEND", "auto")
    from backend.sandbox import docker_runner
    expected = "docker" if docker_runner.is_available() else "subprocess"
    assert current_backend_name() == expected


def test_docker_runner_skip_if_unavailable():
    """Docker runner — اختبار e2e فقط إذا Docker متاح وتم تفعيل RUN_DOCKER_TESTS."""
    import os
    import pytest
    from backend.sandbox import docker_runner

    if not docker_runner.is_available() or os.getenv("RUN_DOCKER_TESTS") != "1":
        pytest.skip("Docker غير متاح أو RUN_DOCKER_TESTS!=1")

    r = docker_runner.run(
        "print('hello from sandbox')", "", timeout=15,
    )
    assert r.backend == "docker"
    assert r.passed, f"فشل: {r.error} / {r.stderr}"
    assert "hello" in r.stdout


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


def test_tool_use_benchmark_loads_and_evaluates():
    """بنشمارك Tool Use يحمّل ويستخرج JSON ويقيّم بشكل صحيح."""
    import asyncio
    from backend.benchmarks import make_benchmark
    from backend.providers.base import ModelResponse

    b = make_benchmark("tool_use")
    problems = b.load()
    assert len(problems) >= 15

    # كل سؤال له tools + expected
    for p in problems:
        assert "tools" in p.metadata and len(p.metadata["tools"]) >= 1
        assert "tool" in p.reference and "arguments" in p.reference

    # اختبر دالة الاستخراج
    from backend.benchmarks.tool_use import ToolUseBenchmark
    assert ToolUseBenchmark.extract_json('{"tool": "x", "arguments": {}}') == {"tool": "x", "arguments": {}}
    assert ToolUseBenchmark.extract_json('قبل\n```json\n{"tool": "y", "arguments": {"a": 1}}\n```\nبعد') == {"tool": "y", "arguments": {"a": 1}}
    assert ToolUseBenchmark.extract_json("لا يوجد JSON") is None

    # اختبر التقييم على مثال
    p = problems[0]
    expected_json = f'{{"tool": "{p.reference["tool"]}", "arguments": {__import__("json").dumps(p.reference["arguments"], ensure_ascii=False)}}}'
    resp = ModelResponse(text=expected_json)
    score = asyncio.run(b.evaluate(p, resp))
    assert score.correct, f"التقييم فشل: {score.judgment}"

    # رد خاطئ
    resp2 = ModelResponse(text='{"tool": "wrong_tool", "arguments": {}}')
    score2 = asyncio.run(b.evaluate(p, resp2))
    assert not score2.correct


def test_saudi_dialects_benchmark_loads():
    """بنشمارك اللهجات السعودية يحمّل بشكل صحيح."""
    from backend.benchmarks import make_benchmark

    b = make_benchmark("saudi_dialects")
    problems = b.load()
    assert len(problems) >= 20
    # تنوّع اللهجات
    dialects = {p.metadata.get("dialect") for p in problems}
    assert "نجدية" in dialects
    assert "حجازية" in dialects
    # كل سؤال له 4 خيارات + إجابة + شرح
    for p in problems:
        assert len(p.metadata["choices"]) == 4
        assert p.reference in "أبجد"
        assert p.metadata.get("explanation")


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
        test_new_providers_have_models_and_pricing,
        test_estimate_tokens_from_text,
        test_estimate_endpoint_logic,
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
