/* حالة التطبيق المشتركة. */

export const state = {
  benchmarks: [],
  providers: [],
  config: { max_problems: 200, max_targets: 10, auth_required: false },
  selectedBenchmark: null,
  selectedCategories: new Set(),
  selectedDifficulties: new Set(),
  models: [],            // [{provider, model}]
  ollamaModels: [],
  ollamaError: null,
  currentRunId: null,
  currentRunData: null,
  liveData: {},          // { "provider:model": {...} }
  chart: null,
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
