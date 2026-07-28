"""اختبارات البنشماركات: التحميل، جودة الداتاست، الاستخراج، والتقييم."""
from __future__ import annotations

import asyncio
import json

import pytest

from backend.benchmarks import BENCHMARKS, filter_problems, get_benchmark_difficulties, make_benchmark
from backend.benchmarks.parsing import (
    extract_arabic_letter,
    extract_json_object,
    extract_latin_letter,
    extract_number,
    extract_rating,
)
from backend.providers.base import ModelResponse


def _run(coro):
    return asyncio.run(coro)


# ============ التحميل ============

@pytest.mark.parametrize("name", sorted(BENCHMARKS))
def test_benchmark_loads_and_builds_prompt(name):
    b = make_benchmark(name)
    problems = b.load()
    assert problems, f"{name}: لا توجد مسائل"
    p = problems[0]
    assert p.id and p.prompt
    assert b.build_prompt(p)


@pytest.mark.parametrize("name", sorted(BENCHMARKS))
def test_error_response_short_circuits_to_error_score(name):
    """الحارس صار في BaseBenchmark — نتأكّد أن كل بنشمارك يرثه."""
    b = make_benchmark(name)
    p = b.load()[0]
    resp = ModelResponse(text="", error="HTTP 401: مفتاح API غير صالح")
    score = _run(b.evaluate(p, resp))
    assert score.correct is False
    assert score.error == "HTTP 401: مفتاح API غير صالح"


# ============ جودة الداتاست السعودي ============

def test_saudi_legal_dataset_quality():
    problems = make_benchmark("saudi_legal").load()
    assert len(problems) >= 150

    cats = {}
    for p in problems:
        cats[p.metadata.get("category")] = cats.get(p.metadata.get("category"), 0) + 1
    assert len(cats) >= 13
    assert not [c for c, n in cats.items() if n < 10]

    difficulties = {p.metadata.get("difficulty") for p in problems}
    assert {"سهل", "متوسط", "صعب"}.issubset(difficulties)

    assert not [p.id for p in problems if not p.metadata.get("source")]
    assert not [p.id for p in problems if len(p.metadata.get("choices", [])) != 4]
    ids = [p.id for p in problems]
    assert len(ids) == len(set(ids)), "توجد IDs مكررة"


def test_saudi_dialects_dataset_quality():
    problems = make_benchmark("saudi_dialects").load()
    assert len(problems) >= 20
    dialects = {p.metadata.get("dialect") for p in problems}
    assert {"نجدية", "حجازية"} <= dialects
    for p in problems:
        assert len(p.metadata["choices"]) == 4
        assert p.reference in "أبجد"
        assert p.metadata.get("explanation")


def test_tool_use_dataset_quality():
    problems = make_benchmark("tool_use").load()
    assert len(problems) >= 15
    for p in problems:
        assert len(p.metadata["tools"]) >= 1
        assert "tool" in p.reference and "arguments" in p.reference


# ============ الفلترة ============

def test_filter_problems():
    problems = make_benchmark("saudi_legal").load()

    by_cat = filter_problems(problems, ["نظام العمل"], [])
    assert by_cat
    assert all(p.metadata["category"] == "نظام العمل" for p in by_cat)

    easy = filter_problems(problems, [], ["سهل"])
    assert easy
    assert all(p.metadata["difficulty"] == "سهل" for p in easy)

    combo = filter_problems(problems, ["نظام العمل"], ["متوسط"])
    assert all(
        p.metadata["category"] == "نظام العمل" and p.metadata["difficulty"] == "متوسط"
        for p in combo
    )
    assert filter_problems(problems, [], []) == problems
    assert filter_problems(problems, ["لا يوجد"], []) == []


def test_difficulties_are_ordered_meaningfully():
    assert get_benchmark_difficulties("saudi_legal") == ["سهل", "متوسط", "صعب"]


def test_arabic_mmlu_exposes_no_empty_facets():
    """الداتاست بلا تصنيف/صعوبة — يجب ألا تظهر فلاتر فارغة في الواجهة."""
    from backend.benchmarks import get_benchmark_categories

    assert get_benchmark_categories("arabic_mmlu") == []
    assert get_benchmark_difficulties("arabic_mmlu") == []


# ============ دوال الاستخراج المشتركة ============

@pytest.mark.parametrize("text,expected", [
    ("الإجابة: ب", "ب"),
    ("الإجابة: إ", "أ"),          # تطبيع صور الألف
    ("أعتقد أن ج هي الصحيحة", "ج"),
    ("لا يوجد حرف هنا", None),
])
def test_extract_arabic_letter(text, expected):
    assert extract_arabic_letter(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Answer: B", "B"),
    ("answer: c", "C"),
    ("I think C is correct", "C"),
    ("nothing", None),
])
def test_extract_latin_letter(text, expected):
    assert extract_latin_letter(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("Step by step... #### 42", 42.0),
    ("#### 1,234", 1234.0),
    ("The answer is 3.14", 3.14),
    ("no number here", None),
])
def test_extract_number(text, expected):
    assert extract_number(text) == expected


def test_extract_json_handles_deep_nesting():
    """الـ regex السابق كان يدعم مستوى تداخل واحداً فقط."""
    nested = '{"tool": "book", "arguments": {"trip": {"legs": [{"from": "RUH"}]}}}'
    got = extract_json_object(nested, required_key="tool")
    assert got == json.loads(nested)


def test_extract_json_variants():
    assert extract_json_object('{"tool": "x", "arguments": {}}', required_key="tool")["tool"] == "x"
    fenced = 'قبل\n```json\n{"tool": "y", "arguments": {"a": 1}}\n```\nبعد'
    assert extract_json_object(fenced, required_key="tool")["tool"] == "y"
    assert extract_json_object("لا يوجد JSON", required_key="tool") is None
    # أقواس داخل سلسلة نصّية لا تكسر الماسح
    tricky = '{"tool": "t", "arguments": {"note": "قوس } هنا"}}'
    assert extract_json_object(tricky, required_key="tool")["tool"] == "t"


def test_extract_rating():
    assert extract_rating("تبرير...\nالدرجة: 4") == 4
    assert extract_rating("جيدة جداً\n5") == 5
    assert extract_rating("بلا درجة") is None


# ============ التقييم ============

def test_arabic_mcq_scores_correct_and_wrong():
    b = make_benchmark("saudi_legal")
    p = b.load()[0]
    good = _run(b.evaluate(p, ModelResponse(text=f"الإجابة: {p.reference}")))
    assert good.correct and good.raw_score == 1.0

    wrong_letter = next(c for c in "أبجد" if c != p.reference)
    bad = _run(b.evaluate(p, ModelResponse(text=f"الإجابة: {wrong_letter}")))
    assert not bad.correct
    assert "الشرح" in bad.judgment or not p.metadata.get("explanation")


def test_tool_use_evaluation():
    b = make_benchmark("tool_use")
    p = b.load()[0]
    payload = json.dumps(
        {"tool": p.reference["tool"], "arguments": p.reference["arguments"]},
        ensure_ascii=False,
    )
    assert _run(b.evaluate(p, ModelResponse(text=payload))).correct
    wrong = _run(b.evaluate(p, ModelResponse(text='{"tool": "nope", "arguments": {}}')))
    assert not wrong.correct
    assert wrong.raw_score == 0.0


def test_llm_judge_requires_a_judge():
    b = make_benchmark("llm_judge")
    p = b.load()[0]
    score = _run(b.evaluate(p, ModelResponse(text="إجابة")))
    assert not score.correct
    assert "حَكَم" in score.error


def test_llm_judge_propagates_judge_cost_even_on_failure():
    """تكلفة الحَكَم كانت تضيع في مسارات الفشل فلا تُحتسب في الميزانية."""
    from backend.providers.base import BaseProvider

    class _Judge(BaseProvider):
        name = "fake"
        available_models = ["judge-model"]

        async def complete(self, prompt, model, max_tokens=1024, temperature=0.0, system=None):
            return ModelResponse(text="لا درجة هنا", cost_usd=0.02)

    b = make_benchmark("llm_judge")
    p = b.load()[0]
    score = _run(b.evaluate(p, ModelResponse(text="إجابة"), _Judge(api_key="")))
    assert score.judge_cost_usd == 0.02
