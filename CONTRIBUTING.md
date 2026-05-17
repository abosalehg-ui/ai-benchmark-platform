# 🤝 المساهمة في منصة البنشمارك

شكراً لاهتمامك بالمساهمة! هذا الدليل يشرح كيف تساهم في المشروع.

## 🚀 البدء السريع

```bash
git clone https://github.com/abosalehg-ui/ai-benchmark-platform.git
cd ai-benchmark-platform
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install pytest ruff
```

تشغيل الاختبارات:
```bash
pytest tests/ -v
```

تشغيل linter:
```bash
ruff check backend/ tests/
```

تشغيل السيرفر محلياً:
```bash
uvicorn backend.main:app --reload --port 8000
```

## 🎯 مجالات المساهمة المرغوبة

### 1. توسيع البنشمارك السعودي ⭐
أكثر مجال يحتاج مساهمات. أضف أسئلة موثّقة لـ `backend/datasets/saudi_legal.json` بالشكل التالي:

```json
{
  "id": "sl_XXX",
  "category": "نظام العمل",
  "question": "نص السؤال",
  "choices": ["خيار 1", "خيار 2", "خيار 3", "خيار 4"],
  "answer": "ج",
  "explanation": "شرح مختصر",
  "source": "المصدر النظامي أو الشرعي"
}
```

**شرط**: لا تضف سؤالاً بدون مصدر موثوق (نظام، لائحة، فتوى معتمدة).

### 2. بنشماركات عربية جديدة
أضف ملف في `backend/benchmarks/` يرث من `BaseBenchmark`. راجع `saudi_legal.py` كمثال.

### 3. مزوّدون جدد
أضف ملف في `backend/providers/` يرث من `BaseProvider`. استخدم `_http.post_with_retry` للطلبات.

### 4. تحسينات الواجهة
- responsive للجوال
- ميزات إضافية (diff view، head-to-head، charts متقدّمة)

## ✅ قبل إرسال PR

- [ ] الكود يعمل محلياً
- [ ] `ruff check backend/ tests/` بدون أخطاء
- [ ] `pytest tests/` كل الاختبارات تنجح
- [ ] أضفت اختبارات للمنطق الجديد (إن أمكن)
- [ ] حدّثت README إذا أضفت ميزة كبيرة

## 🐛 الإبلاغ عن مشكلة

افتح Issue يحتوي:
- وصف للمشكلة
- خطوات إعادة الإنتاج
- السلوك المتوقع مقابل الفعلي
- نسخة Python ونظام التشغيل

## 📝 أسلوب الكود

- بايثون 3.10+
- type hints على الـ public functions
- docstrings عربية مختصرة
- اتبع PEP 8 (ruff يفحصها)

## 📜 الترخيص

بإرسال PR، أنت توافق على أن مساهمتك تُرخَّص تحت MIT.
