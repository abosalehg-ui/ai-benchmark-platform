"""بنشمارك ArabicMMLU — أسئلة متعددة الخيارات بالعربية."""
from __future__ import annotations

import re

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse


class ArabicMMLUBenchmark(BaseBenchmark):
    name = "arabic_mmlu"
    display_name = "ArabicMMLU (لغة عربية)"
    description = "أسئلة متعددة الخيارات بالعربية في تخصصات متنوعة."
    dataset_file = "arabic_mmlu_sample.json"

    @property
    def system_prompt(self) -> str:
        return (
            "أجب على السؤال متعدد الخيارات. "
            "أعطِ الإجابة في السطر الأخير بصيغة: الإجابة: <حرف> "
            "حيث الحرف واحد من: أ، ب، ج، د"
        )

    def _parse_problem(self, raw: dict) -> Problem:
        return Problem(
            id=raw["id"],
            prompt=raw["question"],
            reference=raw["answer"],
            metadata={
                "choices": raw["choices"],
                "subject": raw.get("subject", "general"),
            },
        )

    def build_prompt(self, problem: Problem) -> str:
        choices = problem.metadata["choices"]
        letters = ["أ", "ب", "ج", "د"]
        formatted = "\n".join(f"{l}. {c}" for l, c in zip(letters, choices))
        return (
            f"السؤال: {problem.prompt}\n\nالخيارات:\n{formatted}\n\n"
            f"أجب بصيغة: الإجابة: <حرف>"
        )

    @staticmethod
    def extract_letter(text: str) -> str | None:
        """استخراج الحرف العربي من رد النموذج."""
        # تطبيع: تحويل alef hamza variants
        text = text.replace("إ", "أ").replace("آ", "أ")
        m = re.search(r"الإجابة\s*:\s*([أبجد])", text)
        if m:
            return m.group(1)
        # احتياطياً: أول حرف عربي معزول
        m = re.search(r"\b([أبجد])\b", text)
        if m:
            return m.group(1)
        # خيار ثالث: نبحث عن "هي أ" أو "هو ب"
        m = re.search(r"\b([أبجد])[\s\.\،]", text)
        if m:
            return m.group(1)
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
        expected = problem.reference if isinstance(problem.reference, str) else None
        # تطبيع الإجابة المتوقّعة
        if expected:
            expected = expected.replace("إ", "أ").replace("آ", "أ")
        correct = predicted is not None and predicted == expected

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else 0.0,
            model_response=response.text,
            judgment=f"متوقّع: {expected} | استخرجنا: {predicted}",
        )
