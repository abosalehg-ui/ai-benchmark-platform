"""بنشمارك GSM8K — مسائل رياضية كلامية."""
from __future__ import annotations

import re

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse


class GSM8KBenchmark(BaseBenchmark):
    name = "gsm8k"
    display_name = "GSM8K (رياضيات)"
    description = "حل مسائل رياضية بأسلوب chain-of-thought."
    dataset_file = "gsm8k_sample.json"

    @property
    def system_prompt(self) -> str:
        return (
            "You are a math tutor. Solve the problem step by step, "
            "then provide the final numerical answer on a new line "
            "in the format: #### <number>"
        )

    def _parse_problem(self, raw: dict) -> Problem:
        return Problem(
            id=raw["id"],
            prompt=raw["question"],
            reference=raw["answer"],  # رقم
        )

    def build_prompt(self, problem: Problem) -> str:
        return (
            f"Question: {problem.prompt}\n\n"
            f"Think step by step, then give the final numeric answer on a new line "
            f"as: #### <number>"
        )

    @staticmethod
    def extract_answer(text: str) -> float | None:
        """استخراج الإجابة الرقمية من رد النموذج."""
        # الصيغة المفضّلة: #### <number>
        m = re.search(r"####\s*(-?\d[\d,]*\.?\d*)", text)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except ValueError:
                pass
        # نأخذ آخر رقم في النص كاحتياط
        nums = re.findall(r"-?\d[\d,]*\.?\d*", text)
        if nums:
            try:
                return float(nums[-1].replace(",", ""))
            except ValueError:
                pass
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

        predicted = self.extract_answer(response.text)
        try:
            expected = float(problem.reference)
        except (TypeError, ValueError):
            expected = None

        correct = (
            predicted is not None
            and expected is not None
            and abs(predicted - expected) < 1e-3
        )

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else 0.0,
            model_response=response.text,
            judgment=f"متوقّع: {expected} | استخرجنا: {predicted}",
        )
