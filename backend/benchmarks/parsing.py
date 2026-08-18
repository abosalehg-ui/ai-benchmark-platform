"""دوال استخراج مشتركة بين البنشماركات.

كانت ``extract_letter`` مكرّرة حرفياً في arabic_mmlu و saudi_legal و
saudi_dialects — وبدأت تتباعد فعلاً (نسخة arabic_mmlu كان فيها فرع ثالث
غير موجود في الأخريين). التوحيد هنا يمنع التباعد ويجعل أي تحسين في
الاستخراج يفيد كل البنشماركات دفعة واحدة.
"""
from __future__ import annotations

import json
import re

ARABIC_LETTERS = "أبجد"
LATIN_LETTERS = "ABCD"

# الألف المجرّدة "ا" مستثناة عمداً: تطبيعها إلى "أ" يجعل أي كلمة فيها ألف
# تُطابق كحرف إجابة (مثل «لا يوجد حرف هنا» → تُقرأ كإجابة "أ").
_ALEF_VARIANTS = str.maketrans({"إ": "أ", "آ": "أ"})


def normalize_arabic_letter(text: str) -> str:
    """توحيد صور الألف المهموزة حتى تتطابق المقارنة (إ/آ → أ)."""
    return text.translate(_ALEF_VARIANTS)


def extract_arabic_letter(text: str) -> str | None:
    """استخراج حرف الإجابة العربي (أ/ب/ج/د) من ردّ النموذج."""
    if not text:
        return None
    text = normalize_arabic_letter(text)
    # نمطان فقط، وعمداً: النمط الثالث الذي كان في arabic_mmlu
    # (`([أبجد])[\s\.\،:]` — حرف متبوع بفاصل) يطابق النثر العربي العادي،
    # فـ«لا يوجد حرف هنا» كانت تُقرأ إجابةً «د» بسبب «يوجد ». توحيد
    # البنشماركات على النمطين المحافظين يمنع تسجيل إجابات وهمية.
    for pattern in (
        r"الإجابة\s*:\s*([أبجد])",   # الصيغة المطلوبة صراحةً
        r"\b([أبجد])\b",              # حرف معزول
    ):
        m = re.search(pattern, text)
        if m:
            return m.group(1)
    return None


def extract_latin_letter(text: str) -> str | None:
    """استخراج حرف الإجابة اللاتيني (A/B/C/D) من ردّ النموذج."""
    if not text:
        return None
    for pattern, flags in (
        (r"Answer\s*:\s*([A-D])", re.IGNORECASE),
        (r"\b([A-D])\b", 0),
    ):
        m = re.search(pattern, text, flags)
        if m:
            return m.group(1).upper()
    return None


def extract_number(text: str) -> float | None:
    """استخراج الإجابة الرقمية (صيغة ``#### <رقم>`` أوّلاً، ثم آخر رقم)."""
    if not text:
        return None
    m = re.search(r"####\s*(-?\d[\d,]*\.?\d*)", text)
    if m:
        try:
            return float(m.group(1).replace(",", ""))
        except ValueError:
            pass
    nums = re.findall(r"-?\d[\d,]*\.?\d*", text)
    for candidate in reversed(nums):
        try:
            return float(candidate.replace(",", ""))
        except ValueError:
            continue
    return None


def _iter_balanced_objects(text: str):
    """يمسح النص ويُنتج كل كائن ``{...}`` متوازن الأقواس.

    الـ regex السابق كان يدعم مستوى تداخل واحداً فقط، فأي ``arguments``
    فيها كائن داخل كائن كانت تفشل ويُحسب الخطأ على النموذج. الماسح هنا
    يعدّ العمق ويتجاهل الأقواس داخل السلاسل النصّية.
    """
    depth = 0
    start = -1
    in_string = False
    escaped = False
    for i, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start >= 0:
                    yield text[start:i + 1]
                    start = -1


def extract_json_object(text: str, *, required_key: str | None = None) -> dict | None:
    """يستخرج أوّل كائن JSON صالح من ردّ النموذج (يدعم التداخل العميق)."""
    if not text:
        return None
    candidates: list[str] = []
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.extend(_iter_balanced_objects(text))

    for candidate in candidates:
        try:
            obj = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if required_key is None or required_key in obj:
            return obj
    return None


def extract_rating(text: str, low: int = 1, high: int = 5) -> int | None:
    """استخراج درجة الحَكَم (``الدرجة: <رقم>`` ثم احتياطاً آخر الأسطر).

    نأخذ **آخر** مطابقة لا أوّلها: الحَكَم مُوجَّه ليكتب التبرير أوّلاً والدرجة
    في السطر الأخير، فأي رقم مبكّر (اقتباس من الإجابة، أو درجة مزروعة من
    النموذج المُختبَر) كان يفوز على الدرجة الحقيقية.

    ونرجع ``None`` عند وجود درجتين صريحتين مختلفتين: إشارة إلى تلاعب أو ارتباك،
    والصمت أصدق من رقم مخمَّن — الفرع الأعلى يعرضها «الحَكَم لم يعطِ درجة واضحة».
    """
    if not text:
        return None
    rng = f"[{low}-{high}]"
    explicit = re.findall(rf"الدرجة\s*:\s*({rng})", text)
    if explicit:
        if len(set(explicit)) > 1:
            return None
        return int(explicit[-1])
    last_lines = "\n".join(text.strip().split("\n")[-3:])
    fallback = re.findall(rf"\b({rng})\b", last_lines)
    if fallback:
        return int(fallback[-1])
    return None
