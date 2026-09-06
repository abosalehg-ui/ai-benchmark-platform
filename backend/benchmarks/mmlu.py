"""بنشمارك MMLU — أسئلة متعددة الخيارات في تخصصات متنوعة."""
from __future__ import annotations

from backend.benchmarks.base import BaseBenchmark, EvalContext, Problem, Score
from backend.benchmarks.baselines import guess_baselines
from backend.benchmarks.parsing import LATIN_LETTERS, extract_latin_letter
from backend.benchmarks.shuffling import shuffle_choices
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
        # خلط حتمي مثل البنشماركات العربية: نصف إجابات هذا الملف على B وحده،
        # ولا خيار واحد على D (انظر ``shuffling.py``)
        choices, answer = shuffle_choices(
            raw["choices"],
            raw["answer"].upper() if isinstance(raw["answer"], str) else raw["answer"],
            LATIN_LETTERS,
            seed=f"{self.name}:{raw['id']}",
        )
        return Problem(
            id=raw["id"],
            prompt=raw["question"],
            reference=answer,  # حرف A/B/C/D بعد الخلط
            metadata={
                "choices": choices,
                "subject": raw.get("subject", "general"),
            },
        )

    def guess_baselines(self, problems: list[Problem]) -> dict | None:
        return guess_baselines(problems, LATIN_LETTERS)

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
