"""بنشمارك Tool Use — يقيس قدرة النموذج على اختيار الأداة المناسبة
وتعبئة معاملاتها بصيغة JSON.

يقدّم للنموذج: سيناريو + قائمة أدوات (مع schemas)
يتوقّع: كائن JSON من الشكل {"tool": "...", "arguments": {...}}
"""
from __future__ import annotations

import json
import re

from backend.benchmarks.base import BaseBenchmark, Problem, Score
from backend.providers.base import BaseProvider, ModelResponse


class ToolUseBenchmark(BaseBenchmark):
    name = "tool_use"
    display_name = "استخدام الأدوات (Function Calling)"
    description = (
        "يقيس قدرة النموذج على اختيار الأداة المناسبة من قائمة "
        "وملء معاملاتها بصيغة JSON صحيحة."
    )
    dataset_file = "tool_use.json"

    @property
    def system_prompt(self) -> str:
        return (
            "أنت مساعد ذكي يستخدم الأدوات لتنفيذ طلبات المستخدم. "
            "اختر الأداة المناسبة من القائمة المعطاة، واملأ معاملاتها بدقّة. "
            "أعد الإجابة فقط بصيغة JSON من الشكل:\n"
            '{"tool": "اسم_الأداة", "arguments": {"key": "value"}}\n'
            "لا تضف نصاً خارج JSON."
        )

    def _parse_problem(self, raw: dict) -> Problem:
        return Problem(
            id=raw["id"],
            prompt=raw["scenario"],
            reference={
                "tool": raw["expected"]["tool"],
                "arguments": raw["expected"]["arguments"],
            },
            metadata={
                "tools": raw["tools"],
                "category": raw.get("category", "general"),
                "difficulty": raw.get("difficulty", "متوسط"),
                "required_args": raw["expected"].get("required_args", list(raw["expected"]["arguments"].keys())),
            },
        )

    def build_prompt(self, problem: Problem) -> str:
        tools_json = json.dumps(problem.metadata["tools"], ensure_ascii=False, indent=2)
        return (
            f"الأدوات المتاحة:\n```json\n{tools_json}\n```\n\n"
            f"الطلب: {problem.prompt}\n\n"
            "أجب بـ JSON واحد فقط:"
        )

    @staticmethod
    def extract_json(text: str) -> dict | None:
        """يستخرج أوّل كائن JSON صالح من نص النموذج."""
        # حاول كتلة ```json ... ```
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        candidates = []
        if m:
            candidates.append(m.group(1))
        # حاول كل كتلة بين {}
        for c in re.finditer(r"\{(?:[^{}]|(?:\{[^{}]*\}))*\}", text, re.DOTALL):
            candidates.append(c.group(0))
        for cand in candidates:
            try:
                obj = json.loads(cand)
                if isinstance(obj, dict) and "tool" in obj:
                    return obj
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def _normalize(v):
        """تطبيع القيم للمقارنة المرنة."""
        if isinstance(v, str):
            return v.strip().lower()
        return v

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

        parsed = self.extract_json(response.text)
        expected = problem.reference
        required = problem.metadata["required_args"]

        if parsed is None:
            return Score(
                problem_id=problem.id,
                correct=False,
                model_response=response.text,
                judgment="فشل في استخراج JSON صالح من الرد",
            )

        tool_match = self._normalize(parsed.get("tool")) == self._normalize(expected["tool"])
        args = parsed.get("arguments") or parsed.get("args") or {}
        args_match = all(
            self._normalize(args.get(k)) == self._normalize(expected["arguments"].get(k))
            for k in required
        )

        correct = tool_match and args_match
        judgment_parts = [f"الأداة المتوقّعة: {expected['tool']}، المعطاة: {parsed.get('tool')}"]
        if not tool_match:
            judgment_parts.append("(غير مطابقة)")
        if not args_match:
            missing = [k for k in required if self._normalize(args.get(k)) != self._normalize(expected["arguments"].get(k))]
            judgment_parts.append(f"معاملات خاطئة/ناقصة: {missing}")

        return Score(
            problem_id=problem.id,
            correct=correct,
            raw_score=1.0 if correct else (0.5 if tool_match else 0.0),
            model_response=response.text,
            judgment=" | ".join(judgment_parts),
        )
