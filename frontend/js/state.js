/* حالة التطبيق المشتركة. */

/**
 * لغة عرض التواريخ والأرقام.
 *
 * 'ar-SA' وحده يُفعّل التقويم الهجري في Intl، و'nu-latn' يمنع الأرقام الهندية:
 * بدونه كان السجل يعرض التاريخ بأرقام هندية بجانب $0.0040 بأرقام عربية في
 * نفس الصفّ، بينما كل الأرقام الأخرى في الواجهة تمرّ من toFixed.
 */
export const DATE_LOCALE = 'ar-SA-u-ca-gregory-nu-latn';

export const state = {
  benchmarks: [],
  providers: [],
  config: { max_problems: 200, max_targets: 10, auth_required: false },
  selectedBenchmark: null,
  selectedCategories: new Set(),
  selectedDifficulties: new Set(),
  models: [],            // [{provider, model}]
  judge: { provider: '', model: '' },  // اختيار المستخدم للحَكَم (llm_judge)
  ollamaModels: [],
  ollamaError: null,
  sandbox: null,             // حالة الـ sandbox — تقرّر ظهور موافقة التنفيذ بلا عزل
  currentRunId: null,
  currentRunData: null,       // الملخّص فقط (بلا details)
  loadedDetails: [],          // صفوف التفاصيل المحمّلة على صفحات
  liveData: {},          // { "provider:model": {...} }
  chart: null,
  driftData: null,          // آخر استجابة /api/drift
  driftChart: null,
  summaryRows: [],
  summarySort: { key: 'accuracy', dir: 'desc' },
};

export const PROVIDER_KEYS = [
  'anthropic', 'openai', 'gemini', 'openrouter',
  'groq', 'mistral', 'cohere', 'xai',
];

export function getKey(provider) {
  if (provider === 'ollama') return '';
  return localStorage.getItem('key_' + provider) || '';
}

export function ollamaUrl() {
  return document.getElementById('key-ollama-url').value.trim() || 'http://localhost:11434';
}

export function liveKey(provider, model) {
  return `${provider}:${model}`;
}

/**
 * المظهر الافتراضي: اختيار المستخدم المحفوظ، وإلا تفضيل نظامه، وإلا الداكن.
 *
 * كان الافتراضي 'dark' دائماً، فمتصفّح مضبوط على المظهر الفاتح يُفتح داكناً في
 * أوّل زيارة ولا يُحترم تفضيله إلا بعد ضغطة يدوية.
 */
export function preferredTheme(saved, prefersLight) {
  if (saved === 'light' || saved === 'dark') return saved;
  return prefersLight ? 'light' : 'dark';
}
