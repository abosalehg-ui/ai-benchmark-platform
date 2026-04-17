"""بنشمارك القانون السعودي والفقه — مخصّص.

يختبر فهم النموذج للأنظمة السعودية والمذهب الفقهي السائد.
"""
from __future__ import annotations

import re

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse


class SaudiLegalBenchmark(BaseBenchmark):
    name = "saudi_legal"
    display_name = "القانون السعودي والفقه"
    description = (
        "أسئلة في الأنظمة السعودية (العمل، الإيجار، الجزائي، التنفيذ) "
        "والفقه الإسلامي (عبادات، معاملات، أحوال شخصية)."
    )
    dataset_file = "saudi_legal.json"

    @property
    def system_prompt(self) -> str:
        return (
            "أنت خبير في الأنظمة السعودية والفقه الإسلامي. "
            "أجب على السؤال متعدد الخيارات بدقة. "
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
                "category": raw.get("category", "general"),
                "explanation": raw.get("explanation", ""),
                "source": raw.get("source", ""),
            },
        )

    def build_prompt(self, problem: Problem) -> str:
        choices = problem.metadata["choices"]
        letters = ["أ", "ب", "ج", "د"]
        formatted = "\n".join(f"{l}. {c}" for l, c in zip(letters, choices))
        category = problem.metadata.get("category", "")
        return (
            f"التصنيف: {category}\n\n"
            f"السؤال: {problem.prompt}\n\n"
            f"الخيارات:\n{formatted}\n\n"
            f"اختر الإجابة الصحيحة وأجب بصيغة: الإجابة: <حرف>"
        )

    @staticmethod
    def extract_letter(text: str) -> str | None:
        text = text.replace("إ", "أ").replace("آ", "أ")
        m = re.search(r"الإجابة\s*:\s*([أبجد])", text)
        if m:
            return m.group(1)
        m = re.search(r"\b([أبجد])\b", text)
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
        expected = problem.reference
        if expected:
            expected = expected.replace("إ", "أ").replace("آ", "أ")
        correct = predicted is not None and predicted == expected

        explanation = problem.metadata.get("explanation", "")
        judgment = f"متوقّع: {expected} | استخرجنا: {predicted}"
        if explanation and not correct:
            judgment += f" | الشرح: {explanation[:200]}"

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else 0.0,
            model_response=response.text,
            judgment=judgment,
        )
