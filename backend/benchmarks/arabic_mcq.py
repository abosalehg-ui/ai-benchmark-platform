"""أساس مشترك لبنشماركات الاختيار من متعدّد بالعربية.

``saudi_legal`` و``saudi_dialects`` و``arabic_mmlu`` كانت متطابقة بنسبة
تتجاوز 85% (نفس ``_parse_problem``، نفس بناء الخيارات، نفس ``evaluate``
حرفياً). الفروق الحقيقية: ملف الداتاست، وسطر العنوان أعلى السؤال.
"""
from __future__ import annotations

from backend.benchmarks.base import BaseBenchmark, EvalContext, Problem, Score
from backend.benchmarks.baselines import guess_baselines
from backend.benchmarks.parsing import (
    ARABIC_LETTERS,
    extract_arabic_letter,
    normalize_arabic_letter,
)
from backend.benchmarks.shuffling import shuffle_choices
from backend.providers.base import ModelResponse


class ArabicMCQBenchmark(BaseBenchmark):
    """بنشمارك اختيار من متعدّد بالعربية بأربعة خيارات (أ/ب/ج/د)."""

    #: حقول إضافية تُنسخ من الـ JSON إلى metadata لكل مسألة
    extra_metadata_fields: tuple[str, ...] = ()
    #: قيمة التصنيف/الصعوبة الافتراضية. ``None`` = لا نضيف الحقل أصلاً
    #: (مهمّ: وجود الحقل يجعل الواجهة تعرض فلتراً له)
    default_category: str | None = "general"
    default_difficulty: str | None = "متوسط"
    #: هل نُلحق الشرح بالحكم عند الخطأ؟
    show_explanation_on_error: bool = True
    expert_role: str = "أنت خبير في اللغة العربية."

    @property
    def system_prompt(self) -> str:
        return (
            f"{self.expert_role} "
            "أجب على السؤال متعدد الخيارات بدقة. "
            "أعطِ الإجابة في السطر الأخير بصيغة: الإجابة: <حرف> "
            "حيث الحرف واحد من: أ، ب، ج، د"
        )

    def _parse_problem(self, raw: dict) -> Problem:
        # الخلط الحتمي يُصلح انحياز موضع الإجابة في الداتاست (انظر
        # ``shuffling.py``): 130 من 150 إجابة في saudi_legal كانت على «ب».
        # يجري هنا لا في ``build_prompt`` حتى يكون الترتيب واحداً في الـ prompt
        # وفي الإجابة المرجعية وفي أي عرض للخيارات.
        choices, answer = shuffle_choices(
            raw["choices"],
            normalize_arabic_letter(raw["answer"]) if isinstance(raw["answer"], str) else raw["answer"],
            ARABIC_LETTERS,
            seed=f"{self.name}:{raw['id']}",
        )
        metadata: dict = {"choices": choices}

        category = raw.get("category", self.default_category)
        if category is not None:
            metadata["category"] = category
        difficulty = raw.get("difficulty", self.default_difficulty)
        if difficulty is not None:
            metadata["difficulty"] = difficulty

        explanation = raw.get("explanation", "")
        if explanation:
            metadata["explanation"] = explanation
        for field_name in self.extra_metadata_fields:
            metadata[field_name] = raw.get(field_name, "")

        return Problem(
            id=raw["id"],
            prompt=raw["question"],
            reference=answer,
            metadata=metadata,
        )

    def guess_baselines(self, problems: list[Problem]) -> dict | None:
        return guess_baselines(problems, ARABIC_LETTERS)

    def _header(self, problem: Problem) -> str:
        """سطر السياق أعلى السؤال. تُعاد كتابته في كل بنشمارك فرعي."""
        return ""

    def build_prompt(self, problem: Problem) -> str:
        choices = problem.metadata["choices"]
        formatted = "\n".join(
            f"{letter}. {choice}"
            for letter, choice in zip(ARABIC_LETTERS, choices)
        )
        header = self._header(problem)
        prefix = f"{header}\n\n" if header else ""
        return (
            f"{prefix}السؤال: {problem.prompt}\n\n"
            f"الخيارات:\n{formatted}\n\n"
            f"اختر الإجابة الصحيحة وأجب بصيغة: الإجابة: <حرف>"
        )

    async def _evaluate_response(
        self,
        problem: Problem,
        response: ModelResponse,
        ctx: EvalContext,
    ) -> Score:
        predicted = extract_arabic_letter(response.text)
        expected = (
            normalize_arabic_letter(problem.reference)
            if isinstance(problem.reference, str)
            else None
        )
        correct = predicted is not None and predicted == expected

        judgment = f"متوقّع: {expected} | استخرجنا: {predicted}"
        explanation = problem.metadata.get("explanation", "")
        if self.show_explanation_on_error and explanation and not correct:
            judgment += f" | الشرح: {explanation[:200]}"

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else 0.0,
            model_response=response.text,
            judgment=judgment,
        )
