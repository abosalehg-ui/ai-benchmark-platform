"""بنشمارك القانون السعودي والفقه — مخصّص.

يختبر فهم النموذج للأنظمة السعودية والمذهب الفقهي السائد.
"""
from __future__ import annotations

from backend.benchmarks.arabic_mcq import ArabicMCQBenchmark
from backend.benchmarks.base import Problem


class SaudiLegalBenchmark(ArabicMCQBenchmark):
    name = "saudi_legal"
    display_name = "القانون السعودي والفقه"
    description = (
        "أسئلة في الأنظمة السعودية (العمل، الإيجار، الجزائي، التنفيذ) "
        "والفقه الإسلامي (عبادات، معاملات، أحوال شخصية)."
    )
    dataset_file = "saudi_legal.json"
    extra_metadata_fields = ("source",)
    expert_role = "أنت خبير في الأنظمة السعودية والفقه الإسلامي."

    def _header(self, problem: Problem) -> str:
        category = problem.metadata.get("category", "")
        difficulty = problem.metadata.get("difficulty", "")
        header = f"التصنيف: {category}"
        if difficulty:
            header += f" • الصعوبة: {difficulty}"
        return header
