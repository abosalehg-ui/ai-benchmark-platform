"""صحّة القياس نفسه: هل يفرّق البنشمارك بين نموذج يفهم ونموذج يخمّن؟

هذه الاختبارات ليست عن الكود بل عن **البيانات التي يعمل عليها الكود** — وهي
الفجوة التي مرّت من ثلاث مراجعات متتالية. قبل هذه الدفعة كان 130 من 150 إجابة
في ``saudi_legal`` على الحرف «ب»: نموذج يجيب «ب» بلا قراءة يحصل على 86.7%.
"""
from __future__ import annotations

from collections import Counter

import pytest

from backend.benchmarks import make_benchmark
from backend.benchmarks.baselines import guess_baselines
from backend.benchmarks.base import Problem
from backend.benchmarks.parsing import ARABIC_LETTERS, LATIN_LETTERS
from backend.benchmarks.shuffling import shuffle_choices

MCQ_BENCHMARKS = {
    "saudi_legal": ARABIC_LETTERS,
    "saudi_dialects": ARABIC_LETTERS,
    "arabic_mmlu": ARABIC_LETTERS,
    "mmlu": LATIN_LETTERS,
}


# ============ توزيع حرف الإجابة ============

@pytest.mark.parametrize("benchmark", sorted(MCQ_BENCHMARKS))
def test_answer_letter_is_not_predictable(benchmark):
    """لا حرف يستحوذ على أكثر من 40% من الإجابات.

    الحدّ 40% لا 25%: العيّنات الصغيرة (20 سؤالاً) تتقلّب حول التوزيع المتساوي،
    وحدٌّ ضيّق جداً يجعل الاختبار هشّاً بلا أن يمسك انحيازاً حقيقياً. ما نمنعه
    هنا هو الانحياز الفادح (86.7%) لا التذبذب الطبيعي.
    """
    problems = make_benchmark(benchmark).load()
    letters = Counter(p.reference for p in problems)
    top_letter, top_count = letters.most_common(1)[0]
    share = top_count / len(problems)
    assert share < 0.40, f"{benchmark}: «{top_letter}» تستحوذ على {share:.1%} — {dict(letters)}"


@pytest.mark.parametrize("benchmark", sorted(MCQ_BENCHMARKS))
def test_every_letter_is_used(benchmark):
    """كل الحروف الأربعة تظهر — «د» كانت غائبة تماماً من ثلاثة ملفات."""
    problems = make_benchmark(benchmark).load()
    used = {p.reference for p in problems}
    assert used == set(MCQ_BENCHMARKS[benchmark]), f"{benchmark}: حروف غائبة {set(MCQ_BENCHMARKS[benchmark]) - used}"


# ============ الخلط لا يفسد الإجابة ============

@pytest.mark.parametrize("benchmark", sorted(MCQ_BENCHMARKS))
def test_shuffling_preserves_the_correct_answer_text(benchmark):
    """الحرف تغيّر لكن **النصّ** الذي يشير إليه هو نفسه.

    هذا هو الاختبار الذي يمنع أسوأ عطل ممكن: خلط يقلب الإجابة الصحيحة فتصير
    كل النتائج مقلوبة بصمت ولا يلاحظ أحد.
    """
    bench = make_benchmark(benchmark)
    letters = MCQ_BENCHMARKS[benchmark]
    raw_items = {}
    from backend.benchmarks.base import _load_raw
    for item in _load_raw(bench.dataset_file):
        raw_items[item["id"]] = item

    for problem in bench.load():
        raw = raw_items[problem.id]
        original = raw["answer"].upper() if letters == LATIN_LETTERS else raw["answer"]
        original = original.replace("إ", "أ").replace("آ", "أ")
        expected_text = raw["choices"][letters.index(original)]
        actual_text = problem.metadata["choices"][letters.index(problem.reference)]
        assert actual_text == expected_text, problem.id
        assert sorted(problem.metadata["choices"]) == sorted(raw["choices"]), problem.id


@pytest.mark.parametrize("benchmark", sorted(MCQ_BENCHMARKS))
def test_shuffling_is_stable_across_reloads(benchmark):
    """ترتيب ثابت: هو جزء من الـ prompt، ومن مفتاح الـ cache، ومن معنى «نفس التشغيل».

    خلط عشوائي كان يجعل تشغيلين على نفس البنشمارك غير قابلين للمقارنة، وهو
    بالضبط ما تحتاجه صفحة الانحراف.
    """
    from backend.benchmarks.base import _load_raw

    first = make_benchmark(benchmark).load()
    _load_raw.cache_clear()
    second = make_benchmark(benchmark).load()

    assert [p.reference for p in first] == [p.reference for p in second]
    assert [p.metadata["choices"] for p in first] == [p.metadata["choices"] for p in second]


def test_shuffle_leaves_corrupt_rows_untouched():
    """حرف إجابة غير معروف لا يُسقط تحميل الداتاست ولا يُخلط بمعنى جديد."""
    choices = ["a", "b", "c", "d"]
    assert shuffle_choices(choices, "z", ARABIC_LETTERS, "seed") == (choices, "z")
    assert shuffle_choices([], "أ", ARABIC_LETTERS, "seed") == ([], "أ")
    # حرف يشير إلى خيار غير موجود (أربعة حروف، خياران)
    assert shuffle_choices(["a", "b"], "د", ARABIC_LETTERS, "seed") == (["a", "b"], "د")


def test_shuffle_actually_reorders():
    """تحقّق من أن الدالة تخلط فعلاً بدل أن تُعيد المدخل كما هو."""
    choices = [f"choice-{i}" for i in range(4)]
    orders = {
        tuple(shuffle_choices(choices, "أ", ARABIC_LETTERS, f"p{i}")[0])
        for i in range(20)
    }
    assert len(orders) > 1, "نفس الترتيب لكل البذور — الخلط لا يعمل"


# ============ خطّ الأساس ============

def _mcq(pid: str, answer: str, choices: list[str]) -> Problem:
    return Problem(id=pid, prompt="q", reference=answer, metadata={"choices": choices})


def test_baseline_reports_the_majority_letter_guess():
    problems = [
        _mcq("1", "أ", ["x", "y", "z", "w"]),
        _mcq("2", "أ", ["x", "y", "z", "w"]),
        _mcq("3", "ب", ["x", "y", "z", "w"]),
        _mcq("4", "ج", ["x", "y", "z", "w"]),
    ]
    base = guess_baselines(problems, ARABIC_LETTERS)
    assert base["majority_letter"] == "أ"
    assert base["majority_letter_accuracy"] == 0.5
    assert base["n"] == 4


def test_baseline_reports_the_longest_choice_guess():
    """الانحياز الذي لا يُصلحه الخلط: الإجابة الصحيحة مشروحة والمشتّتات مقتضبة."""
    problems = [
        _mcq("1", "ب", ["قصير", "إجابة مشروحة وطويلة جداً", "قصير", "قصير"]),
        _mcq("2", "د", ["قصير", "قصير", "قصير", "إجابة مشروحة وطويلة جداً"]),
        _mcq("3", "أ", ["قصير", "إجابة مشروحة وطويلة جداً", "قصير", "قصير"]),
    ]
    base = guess_baselines(problems, ARABIC_LETTERS)
    assert base["longest_choice_accuracy"] == pytest.approx(2 / 3, abs=0.001)


def test_tied_longest_choice_is_not_counted_as_a_guessable_win():
    """التعادل في الطول ليس استراتيجية يستطيع متخمّن اتّباعها."""
    problems = [_mcq("1", "أ", ["متساوي", "متساوي", "متساوي", "متساوي"])]
    assert guess_baselines(problems, ARABIC_LETTERS)["longest_choice_accuracy"] == 0.0


def test_baseline_is_none_for_non_mcq_benchmarks():
    """لا نخترع رقماً لبنشمارك ليس اختياراً من متعدّد."""
    for name in ("gsm8k", "humaneval", "tool_use", "llm_judge"):
        bench = make_benchmark(name)
        assert bench.guess_baselines(bench.load()) is None
    assert guess_baselines([], ARABIC_LETTERS) is None


@pytest.mark.parametrize("benchmark", sorted(MCQ_BENCHMARKS))
def test_real_datasets_expose_their_baseline(benchmark):
    """كل بنشمارك MCQ يعرض خطّ أساسه — الرقم المخفيّ هو الذي يضلّل."""
    bench = make_benchmark(benchmark)
    base = bench.guess_baselines(bench.load())
    assert base is not None
    assert 0.0 <= base["majority_letter_accuracy"] <= 1.0
    assert 0.0 <= base["longest_choice_accuracy"] <= 1.0
