"""خطّ الأساس: أعلى دقّة يبلغها متخمّن لا يقرأ السؤال.

**لماذا هذه الوحدة موجودة:** الخلط الحتمي في ``shuffling.py`` أصلح انحياز
**موضع** الإجابة (86.7% ← 28.7% في ``saudi_legal``)، لكنه لا يستطيع إصلاح
انحياز **الصياغة**: في نفس الملف يبقى الخيار الصحيح هو الأطول في 94.7% من
الأسئلة، لأن كاتب السؤال يشرح الإجابة الصحيحة («90 يوماً قابلة للتمديد إلى 180
يوماً باتفاق الطرفين») ويكتفي في المشتّتات بعبارة قصيرة («30 يوماً غير قابلة
للتمديد»). إصلاح ذلك يعني إعادة كتابة المشتّتات بيد مختصّ، وهو خارج ما يستطيع
الكود عمله.

ما يستطيع الكود عمله: **ألّا يخفي الرقم**. حين تعرض المنصّة «91% دقّة» بجانب
«خطّ الأساس: أطول خيار = 94.7%» يعرف القارئ فوراً أن النتيجة لا تعني شيئاً عن
فهم النموذج للأنظمة السعودية. الرقم المعروض بلا خطّ أساس هو الذي يضلّل.

يُحسب على **مسائل التشغيل الفعلية** بعد الفلترة والقصّ، لا على الداتاست كاملاً:
من يشغّل خمس مسائل يحتاج خطّ الأساس لتلك الخمس.
"""
from __future__ import annotations

from collections import Counter

from backend.benchmarks.base import Problem


def guess_baselines(problems: list[Problem], letters: str) -> dict | None:
    """خطوط أساس التخمين لمجموعة مسائل اختيار من متعدّد.

    يرجع ``None`` إذا لم تكن المسائل صالحة للحساب (فارغة، أو بلا خيارات، أو
    مراجعها ليست حروفاً) — لا نخترع رقماً لبنشمارك ليس من هذا النوع.
    """
    if not problems:
        return None

    references = [p.reference for p in problems if isinstance(p.reference, str)]
    if len(references) != len(problems):
        return None

    n = len(problems)
    counts = Counter(references)
    majority_letter, majority_hits = counts.most_common(1)[0]

    # «أطول خيار» يُحتسب فقط حين يكون هناك أطول **وحيد**: التعادل ليس استراتيجية
    # يستطيع متخمّن اتّباعها، فاحتسابه نجاحاً يضخّم خطّ الأساس بلا وجه حق
    longest_hits = 0
    for problem in problems:
        choices = problem.metadata.get("choices") or []
        index = letters.find(problem.reference)
        if not choices or index < 0 or index >= len(choices):
            return None
        lengths = [len(str(c)) for c in choices]
        if lengths[index] == max(lengths) and lengths.count(max(lengths)) == 1:
            longest_hits += 1

    return {
        "n": n,
        "majority_letter": majority_letter,
        "majority_letter_accuracy": round(majority_hits / n, 4),
        "longest_choice_accuracy": round(longest_hits / n, 4),
    }
