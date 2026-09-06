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


@dataclass
class JudgeSpec:
    """نموذج الحَكَم صراحةً: المزوّد + اسم النموذج.

    كان النموذج يُمرَّر بتحوير ``judge_provider.available_models`` من ``runner``
    قبل الاستدعاء — قناة جانبية تنكسر بصمت: أي استدعاء لـ ``evaluate`` من خارج
    ``runner`` كان يقع على أوّل نموذج في كتالوج المزوّد بدل النموذج المقصود.
    """
    provider: BaseProvider
    model: str


@dataclass
class EvalContext:
    """كل ما يحتاجه التقييم خارج المسألة والاستجابة.

    ``enforce_safety`` كان يصل إلى ``RunRequest`` ثم لا يُقرأ أبداً، فخانة
    «تفعيل فحص أمان الكود» في الواجهة كانت بلا أي أثر. تمريره هنا يُكمل المسار
    من الواجهة إلى الـ sandbox.
    """
    judge: JudgeSpec | None = None
    enforce_safety: bool = True
    use_cache: bool = True


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
    #: هل يحتاج هذا البنشمارك نموذج حَكَم؟ يفرضه الخادم قبل بدء أي إنفاق
    needs_judge: bool = False
    #: هل ينفّذ هذا البنشمارك كوداً يُنتجه النموذج؟ يقرّر تحذير الـ sandbox
    executes_code: bool = False

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
        ctx: EvalContext | None = None,
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
        return await self._evaluate_response(problem, response, ctx or EvalContext())

    @abstractmethod
    async def _evaluate_response(
        self,
        problem: Problem,
        response: ModelResponse,
        ctx: EvalContext,
    ) -> Score:
        """التقييم الفعلي — يُستدعى فقط عندما تكون الاستجابة سليمة."""
        ...

    @property
    def system_prompt(self) -> str | None:
        """system prompt افتراضي للبنشمارك."""
        return None

    def guess_baselines(self, problems: list[Problem]) -> dict | None:
        """خطوط أساس التخمين لهذه المسائل، أو ``None`` إن كانت لا تنطبق.

        بنشماركات الاختيار من متعدّد تُعيد كتابتها (انظر ``baselines.py``):
        بلا خطّ أساس معروض تُقرأ «91% دقّة» كإنجاز حتى لو كان متخمّن يبلغ 94%.
        البنشماركات المفتوحة (كود، رياضيات، حَكَم) لا خطّ أساس تخمين لها.
        """
        return None
