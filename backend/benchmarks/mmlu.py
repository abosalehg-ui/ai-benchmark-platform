"""بنشمارك MMLU — أسئلة متعددة الخيارات في تخصصات متنوعة."""
from __future__ import annotations

import re

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse


class MMLUBenchmark(BaseBenchmark):
    name = "mmlu"
    display_name = "MMLU (معرفة عامة)"
    description = "أسئلة متعددة الخيارات في تخصصات متنوعة (طب، قانون، تاريخ...)."
    dataset_file = "mmlu_sample.json"

    @property
    def system_prompt(self) -> str:
        return (
            "Answer the multiple-choice question. "
            "Reply ONLY with a single letter (A, B, C, or D) on the last line "
            "in the format: Answer: <letter>"
        )

    def _parse_problem(self, raw: dict) -> Problem:
        return Problem(
            id=raw["id"],
            prompt=raw["question"],
            reference=raw["answer"],  # حرف A/B/C/D
            metadata={
                "choices": raw["choices"],
                "subject": raw.get("subject", "general"),
            },
        )

    def build_prompt(self, problem: Problem) -> str:
        choices = problem.metadata["choices"]
        letters = ["A", "B", "C", "D"]
        formatted = "\n".join(f"{l}. {c}" for l, c in zip(letters, choices))
        return (
            f"{problem.prompt}\n\n{formatted}\n\n"
            f"Reply with: Answer: <letter>"
        )

    @staticmethod
    def extract_letter(text: str) -> str | None:
        """استخراج الحرف من رد النموذج."""
        # نبحث عن "Answer: X" أولاً
        m = re.search(r"Answer\s*:\s*([A-D])", text, re.IGNORECASE)
        if m:
            return m.group(1).upper()
        # احتياطياً: أول حرف A-D معزول
        m = re.search(r"\b([A-D])\b", text)
        if m:
            return m.group(1).upper()
        return None

    async def evaluate(
        self,
        problem: Problem,
        response: ModelResponse,
        judge_provider: BaseProvider | None = None,
    ) -> Score:
        if response.is_error:
            return Score(
                problem_id=problem.id,
                correct=False,
                model_response=response.text,
                error=response.error,
            )

        predicted = self.extract_letter(response.text)
        expected = problem.reference.upper() if isinstance(problem.reference, str) else None
        correct = predicted is not None and predicted == expected

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else 0.0,
            model_response=response.text,
            judgment=f"متوقّع: {expected} | استخرجنا: {predicted}",
        )
