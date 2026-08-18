"""بنشمارك MMLU — أسئلة متعددة الخيارات في تخصصات متنوعة."""
from __future__ import annotations

from backend.benchmarks.base import BaseBenchmark, EvalContext, Problem, Score
from backend.benchmarks.parsing import LATIN_LETTERS, extract_latin_letter
from backend.providers.base import ModelResponse


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
        formatted = "\n".join(
            f"{letter}. {choice}"
            for letter, choice in zip(LATIN_LETTERS, choices)
        )
        return (
            f"{problem.prompt}\n\n{formatted}\n\n"
            f"Reply with: Answer: <letter>"
        )

    async def _evaluate_response(
        self,
        problem: Problem,
        response: ModelResponse,
        ctx: EvalContext,
    ) -> Score:
        predicted = extract_latin_letter(response.text)
        expected = problem.reference.upper() if isinstance(problem.reference, str) else None
        correct = predicted is not None and predicted == expected

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else 0.0,
            model_response=response.text,
            judgment=f"متوقّع: {expected} | استخرجنا: {predicted}",
        )
