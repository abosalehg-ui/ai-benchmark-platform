"""واجهة موحدة لكل البنشماركات."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.providers.base import BaseProvider, ModelResponse

DATASETS_DIR = Path(__file__).parent.parent / "datasets"


@dataclass
class Problem:
    """مسألة واحدة في بنشمارك."""
    id: str
    prompt: str
    reference: Any  # الإجابة الصحيحة (نصية، رقمية، كود اختبار...)
    metadata: dict = field(default_factory=dict)


@dataclass
class Score:
    """نتيجة تقييم مسألة واحدة."""
    problem_id: str
    correct: bool
    raw_score: float = 0.0  # بين 0 و 1
    model_response: str = ""
    judgment: str = ""  # تفسير التقييم
    error: str | None = None
    judge_cost_usd: float = 0.0  # تكلفة استدعاء الحَكَم (llm_judge) إن وُجد


@lru_cache(maxsize=32)
def _load_raw(dataset_file: str) -> tuple[dict, ...]:
    """يقرأ ملف الداتاست من القرص مرّة واحدة لكل عملية.

    ``list_benchmarks`` و``/api/estimate`` كانا يعيدان قراءة كل ملفات
    الداتاست وتحليل JSON في كل طلب. الملفات ثابتة أثناء عمر العملية،
    فالتخزين المؤقّت آمن ويوفّر قراءة قرص متكرّرة أثناء البثّ.
    """
    path = DATASETS_DIR / dataset_file
    if not path.exists():
        raise FileNotFoundError(f"داتاست غير موجود: {path}")
    with open(path, encoding="utf-8") as f:
        return tuple(json.load(f))


class BaseBenchmark(ABC):
    """واجهة أساسية لكل بنشمارك."""

    name: str = "base"
    display_name: str = "Base"
    description: str = ""
    dataset_file: str = ""

    def __init__(self, dataset_file: str | None = None):
        self.dataset_file = dataset_file or self.dataset_file

    def load(self) -> list[Problem]:
        """تحميل المسائل من الداتاست."""
        return [self._parse_problem(dict(item)) for item in _load_raw(self.dataset_file)]

    @abstractmethod
    def _parse_problem(self, raw: dict) -> Problem:
        """تحويل عنصر JSON إلى Problem."""
        ...

    @abstractmethod
    def build_prompt(self, problem: Problem) -> str:
        """بناء الـ prompt الذي سيُرسل للنموذج."""
        ...

    async def evaluate(
        self,
        problem: Problem,
        response: ModelResponse,
        judge_provider: BaseProvider | None = None,
    ) -> Score:
        """تقييم استجابة النموذج.

        Template method: يعالج حالة خطأ المزوّد مرّة واحدة هنا — كانت هذه
        الكتلة مكرّرة حرفياً في الثمانية بنشماركات، وكان أي بنشمارك جديد
        قد ينساها فيُقيَّم ردّ فارغ كإجابة خاطئة بدل خطأ تشغيل.
        """
        if response.is_error:
            return Score(
                problem_id=problem.id,
                correct=False,
                model_response=response.text,
                error=response.error,
            )
        return await self._evaluate_response(problem, response, judge_provider)

    @abstractmethod
    async def _evaluate_response(
        self,
        problem: Problem,
        response: ModelResponse,
        judge_provider: BaseProvider | None = None,
    ) -> Score:
        """التقييم الفعلي — يُستدعى فقط عندما تكون الاستجابة سليمة."""
        ...

    @property
    def system_prompt(self) -> str | None:
        """system prompt افتراضي للبنشمارك."""
        return None
