"""بنشمارك HumanEval — تقييم البرمجة بتشغيل كود فعلي."""
from __future__ import annotations

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse
from backend.sandbox import extract_python_code, run_python_code


class HumanEvalBenchmark(BaseBenchmark):
    name = "humaneval"
    display_name = "HumanEval (برمجة)"
    description = "تقييم قدرة النموذج على كتابة دوال بايثون صحيحة."
    dataset_file = "humaneval_sample.json"

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert Python programmer. "
            "Complete the function below. Return ONLY the complete function code "
            "inside a ```python code block. No explanations."
        )

    def _parse_problem(self, raw: dict) -> Problem:
        return Problem(
            id=raw["task_id"],
            prompt=raw["prompt"],
            reference={
                "test": raw["test"],
                "entry_point": raw["entry_point"],
                "canonical_solution": raw.get("canonical_solution", ""),
            },
        )

    def build_prompt(self, problem: Problem) -> str:
        return (
            f"Complete this Python function:\n\n"
            f"```python\n{problem.prompt}\n```\n\n"
            f"Return the complete function (with signature) inside ```python ... ```"
        )

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

        code = extract_python_code(response.text)
        # نضيف توقيع الدالة الأصلي إذا الموديل ما رجّعه
        if problem.reference["entry_point"] not in code:
            code = problem.prompt + "\n" + code

        test_code = (
            problem.reference["test"]
            + f"\ncheck({problem.reference['entry_point']})"
        )
        result = run_python_code(code, test_code, timeout=10)

        return Score(
            problem_id=problem.id,
            correct=result.passed,
            raw_score=1.0 if result.passed else 0.0,
            model_response=response.text,
            judgment=(
                "اجتاز كل الاختبارات"
                if result.passed
                else f"فشل: {result.error or 'خطأ'} | stderr: {result.stderr[:300]}"
            ),
            error=result.blocked_reason,
        )
