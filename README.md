# 🧪 منصة بنشمارك نماذج الذكاء الاصطناعي

<div align="right" dir="rtl">

منصة مفتوحة المصدر لاختبار ومقارنة نماذج الذكاء الاصطناعي المختلفة على بنشماركات حقيقية — تشغيل كود فعلي، أسئلة متعددة الخيارات، مهام عربية مخصصة، وتقييم بـ LLM-as-judge.

**الفكرة:** قارن Claude وGPT وGemini والنماذج المحلية (Ollama) جنباً إلى جنب على نفس المسائل، مع قياس الدقة والتكلفة وزمن الاستجابة — كل ذلك من واجهة ويب واحدة.

</div>

---

## ✨ المزايا

- **5 مزودين مدعومين:** Anthropic (Claude)، OpenAI (GPT)، Google (Gemini)، Ollama (نماذج محلية)، OpenRouter (DeepSeek, Mistral, Qwen, Llama)
- **6 بنشماركات متنوعة:**
  - `HumanEval` — برمجة بايثون (تشغيل كود فعلي في sandbox)
  - `GSM8K` — مسائل رياضية
  - `MMLU` — معرفة عامة متعددة التخصصات
  - `ArabicMMLU` — أسئلة عربية متعددة الخيارات
  - **`Saudi Legal & Fiqh`** — بنشمارك مخصص للأنظمة السعودية والفقه الإسلامي (30 سؤال)
  - `LLM-as-Judge` — تقييم المهام الإبداعية بنموذج محايد
- **تتبّع لحظي عبر SSE** — شوف النتائج تتحدّث سؤال بسؤال
- **حساب تكلفة تلقائي** لكل مزود ونموذج
- **مفاتيح آمنة** — تُحفظ في `localStorage` المتصفح فقط، ما تنرفع لأي خادم سوى مزود النموذج نفسه
- **واجهة عربية RTL أنيقة** — Vanilla JS بدون build step
- **تاريخ كامل** لكل الاختبارات في SQLite محلياً

---

## 📋 لقطة سريعة

```
اختر بنشمارك → اختر نماذج → شغّل → قارن النتائج
       ↓              ↓          ↓           ↓
   6 خيارات     Claude/GPT/    SSE     دقة + تكلفة
                Gemini/...    لحظي    + زمن استجابة
```

---

## 🚀 التشغيل السريع

### المتطلبات
- Python 3.10+
- (اختياري) Ollama مثبّت محلياً لاختبار النماذج المحلية

### التثبيت والتشغيل

```bash
# استنساخ المشروع
git clone https://github.com/abosalehg-ui/ai-benchmark-platform.git
cd ai-benchmark-platform

# بيئة افتراضية
python3 -m venv .venv
source .venv/bin/activate          # Linux/Mac
# .venv\Scripts\activate           # Windows

# تثبيت المتطلبات
pip install -r requirements.txt

# تشغيل السيرفر
uvicorn backend.main:app --reload --port 8000
```

افتح المتصفح على: **http://localhost:8000**

---

## 🔑 إدارة المفاتيح

المفاتيح تُحفظ في `localStorage` المتصفح فقط. لا تُرسَل للخادم ولا لأي طرف ثالث سوى مزود النموذج نفسه عند تنفيذ الطلب.

1. افتح تبويب "المفاتيح" في الواجهة
2. أدخل مفاتيح المزودين اللي تبي تختبرهم
3. اضغط "حفظ"

للاستخدام الشخصي: لا تحتاج نشر السيرفر لأي أحد. شغّله محلياً فقط.

---

## 🧩 البنشمارك السعودي المخصّص

بنشمارك حصري صُمّم لاختبار فهم النماذج للقانون السعودي والفقه الإسلامي، يغطي:

- **نظام العمل:** ساعات العمل، مكافأة نهاية الخدمة، الإجازات، حالات الفصل
- **نظام الإيجار:** منصة إيجار، التوثيق
- **نظام التنفيذ:** أوامر التنفيذ، الحجز، الإفصاح
- **مكافحة الجرائم المعلوماتية:** التشهير، الاحتيال الإلكتروني
- **نظام الشركات:** ذ.م.م، المؤسسة الفردية، رأس المال
- **أنظمة المرافعات:** الاختصاص، مدد الاستئناف، منصة ناجز
- **الفقه الإسلامي:** عبادات، معاملات، أحوال شخصية، مواريث
- **النظام الجزائي:** حق الاستعانة بمحامٍ، التوقيف

كل سؤال مع الإجابة الصحيحة + شرح + المصدر النظامي/الشرعي.

---

## 🏗️ البنية التقنية

```
ai-benchmark-platform/
├── backend/
│   ├── providers/          # واجهة موحدة لكل المزودين
│   │   ├── base.py
│   │   ├── claude.py
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   ├── ollama.py
│   │   └── openrouter.py
│   ├── benchmarks/         # البنشماركات
│   │   ├── base.py
│   │   ├── humaneval.py
│   │   ├── gsm8k.py
│   │   ├── mmlu.py
│   │   ├── arabic_mmlu.py
│   │   ├── saudi_legal.py  # ⭐ مخصص
│   │   └── llm_judge.py
│   ├── datasets/           # بيانات الاختبار (JSON)
│   ├── sandbox.py          # تشغيل الكود بأمان
│   ├── pricing.py          # أسعار النماذج
│   ├── runner.py           # محرّك التشغيل + SSE
│   ├── db.py               # SQLite
│   └── main.py             # FastAPI
├── frontend/
│   ├── index.html          # واجهة RTL
│   ├── app.js              # منطق الواجهة
│   └── styles.css          # تصميم
├── data/                   # قاعدة البيانات (تُنشأ تلقائياً)
├── requirements.txt
└── README.md
```

### تدفّق البيانات

```
Frontend ──POST /api/run──> FastAPI
                              │
                              ▼
                          Runner
                         ╱   │   ╲
                        ▼    ▼    ▼
                  Provider  Benchmark  Sandbox
                    API     evaluate   (لـ كود)
                        ╲   │   ╱
                         ▼  ▼  ▼
                         SQLite
                          │
          Frontend ◄──SSE stream──  (لحظي)
```

---

## 🔒 الأمان

- **sandbox لتشغيل الكود:** `subprocess` مع `timeout=10s` + قائمة سوداء للاستيرادات الخطرة (os.system, subprocess, socket, urllib...). قابل للتعطيل من الإعدادات للمطوّرين المتقدّمين.
- **مفاتيح API:** تُرسَل مع كل طلب كـ parameter ولا تُخزَّن على الخادم أبداً.
- **لا يوجد ads ولا تتبّع:** المشروع مفتوح المصدر بالكامل.

**تنبيه:** إذا نشرت السيرفر للعموم، أي شخص يقدر يستخدم مفاتيحه عليه. لا ننصح بالنشر العام إلا خلف authentication.

---

## 🛠️ إضافة بنشمارك جديد

1. أنشئ ملف في `backend/benchmarks/my_benchmark.py` يرث من `BaseBenchmark`
2. حدّد `name`، `display_name`، `dataset_file`
3. نفّذ `_parse_problem`، `build_prompt`، `evaluate`
4. أنشئ الداتاست JSON في `backend/datasets/`
5. سجّله في `backend/benchmarks/__init__.py`

مثال مبسّط:

```python
from backend.benchmarks.base import BaseBenchmark, Problem, Score

class MyBenchmark(BaseBenchmark):
    name = "my_benchmark"
    display_name = "بنشماركي"
    dataset_file = "my_data.json"

    def _parse_problem(self, raw):
        return Problem(id=raw["id"], prompt=raw["q"], reference=raw["a"])

    def build_prompt(self, problem):
        return problem.prompt

    async def evaluate(self, problem, response, judge_provider=None):
        correct = response.text.strip() == problem.reference
        return Score(problem_id=problem.id, correct=correct,
                     raw_score=1.0 if correct else 0.0,
                     model_response=response.text)
```

---

## 📊 مثال للنتيجة

| النموذج | HumanEval | GSM8K | ArabicMMLU | القانون السعودي |
|---------|-----------|-------|------------|-----------------|
| Claude Opus 4.7 | 92% | 94% | 87% | 83% |
| GPT-4o | 89% | 93% | 79% | 71% |
| Gemini 1.5 Pro | 85% | 91% | 81% | 68% |
| Qwen 2.5 72B (Ollama) | 78% | 82% | 73% | 54% |

*(أرقام توضيحية — شغّل البنشمارك بنفسك للنتائج الحقيقية)*

---

## 🤝 المساهمة

المشروع مفتوح للمساهمات. خصوصاً:
- إضافة بنشماركات عربية إضافية
- توسيع بنشمارك القانون السعودي بأسئلة موثّقة
- دعم مزودين جدد (Cohere, Groq, ...)
- تحسين الواجهة

---

## 📜 الترخيص

MIT — انظر [LICENSE](LICENSE)

## 👤 المطوّر

[@abosalehg-ui](https://github.com/abosalehg-ui) — عبدالكريم

---

<div align="center">

**صُنع بـ ❤️ من المدينة المنوّرة**

</div>
