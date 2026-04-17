"""واجهة موحدة لكل البنشماركات."""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
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
        path = DATASETS_DIR / self.dataset_file
        if not path.exists():
            raise FileNotFoundError(f"داتاست غير موجود: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return [self._parse_problem(item) for item in data]

    @abstractmethod
    def _parse_problem(self, raw: dict) -> Problem:
        """تحويل عنصر JSON إلى Problem."""
        ...

    @abstractmethod
    def build_prompt(self, problem: Problem) -> str:
        """بناء الـ prompt الذي سيُرسل للنموذج."""
        ...

    @abstractmethod
    async def evaluate(
        self,
        problem: Problem,
        response: ModelResponse,
        judge_provider: BaseProvider | None = None,
    ) -> Score:
        """تقييم استجابة النموذج."""
        ...

    @property
    def system_prompt(self) -> str | None:
        """system prompt افتراضي للبنشمارك."""
        return None
