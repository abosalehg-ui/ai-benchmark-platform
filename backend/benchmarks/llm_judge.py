"""بنشمارك LLM-as-judge — تقييم مهام مفتوحة بنموذج محايد.

الفكرة: نسأل النموذج (المُختبَر) سؤالاً مفتوحاً، ثم نسأل نموذجاً آخر (الحَكَم)
أن يقيّم الإجابة على مقياس 1-5 مع تبرير.

تحذير: لو الحَكَم نفس عائلة النموذج المُختبَر، يحصل تحيّز. لذا نطلب من المستخدم
اختيار حَكَم محايد (مثلاً: GPT-4o يحكم على Claude والعكس).
"""
from __future__ import annotations

import re

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse


class LLMJudgeBenchmark(BaseBenchmark):
    name = "llm_judge"
    display_name = "LLM-as-judge (مهام إبداعية)"
    description = (
        "تقييم مهام مفتوحة (كتابة، تلخيص، ترجمة، إجابة استشارية) "
        "بواسطة نموذج حَكَم محايد على مقياس 1-5."
    )
    dataset_file = "llm_judge_sample.json"

    @property
    def system_prompt(self) -> str:
        return "أجب على السؤال بأفضل ما لديك. كن دقيقاً ومفيداً ومختصراً قدر الإمكان."

    def _parse_problem(self, raw: dict) -> Problem:
        return Problem(
            id=raw["id"],
            prompt=raw["question"],
            reference=raw.get("rubric", "الجودة العامة، الدقة، الفهم، البلاغة."),
            metadata={"category": raw.get("category", "general")},
        )

    def build_prompt(self, problem: Problem) -> str:
        return problem.prompt

    @staticmethod
    def _build_judge_prompt(question: str, answer: str, rubric: str) -> str:
        return f"""أنت حَكَم خبير ومحايد. قيّم إجابة نموذج ذكاء اصطناعي على السؤال التالي.

السؤال:
{question}

إجابة النموذج:
{answer}

معايير التقييم:
{rubric}

قيّم الإجابة من 1 إلى 5 حيث:
1 = سيئة جداً
2 = ضعيفة
3 = مقبولة
4 = جيدة
5 = ممتازة

أعطِ تبريراً موجزاً (سطر أو سطرين) ثم في السطر الأخير اكتب:
الدرجة: <رقم>"""

    @staticmethod
    def extract_score(text: str) -> int | None:
        m = re.search(r"الدرجة\s*:\s*([1-5])", text)
        if m:
            return int(m.group(1))
        # احتياطياً: نبحث عن أي رقم 1-5 في الأسطر الأخيرة
        last_lines = "\n".join(text.strip().split("\n")[-3:])
        m = re.search(r"\b([1-5])\b", last_lines)
        if m:
            return int(m.group(1))
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
        if judge_provider is None:
            return Score(
                problem_id=problem.id,
                correct=False,
                model_response=response.text,
                error="LLM-as-judge يحتاج نموذج حَكَم — لم يُحدَّد",
            )

        judge_prompt = self._build_judge_prompt(
            problem.prompt, response.text, str(problem.reference)
        )
        # نختار أول موديل متاح للحَكَم
        judge_model = (
            judge_provider.available_models[0]
            if judge_provider.available_models
            else "default"
        )
        judge_response = await judge_provider.complete(
            judge_prompt, model=judge_model, max_tokens=512, temperature=0.0
        )

        if judge_response.is_error:
            return Score(
                problem_id=problem.id,
                correct=False,
                model_response=response.text,
                error=f"خطأ في الحَكَم: {judge_response.error}",
            )

        score_value = self.extract_score(judge_response.text)
        if score_value is None:
            return Score(
                problem_id=problem.id,
                correct=False,
                model_response=response.text,
                judgment=f"الحَكَم لم يعطِ درجة واضحة: {judge_response.text[:300]}",
            )

        # نعتبرها "صحيحة" إذا الدرجة 4 أو 5
        return Score(
            problem_id=problem.id,
            correct=score_value >= 4,
            raw_score=(score_value - 1) / 4.0,  # نطبّع لـ 0..1
            model_response=response.text,
            judgment=f"درجة الحَكَم: {score_value}/5 — {judge_response.text[:300]}",
        )
