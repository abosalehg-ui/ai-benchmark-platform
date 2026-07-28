/* كل نداءات الشبكة في مكان واحد، مع معالجة أخطاء موحّدة.
   كانت loadBenchmarks/loadProviders بلا try/catch، فسقوط الخادم يترك
   الصفحة فارغة بلا أي رسالة. */

const BASE = ''; // same origin

/** رمز الوصول الاختياري — يُستخدم فقط لو ضبط المشغّل API_TOKEN. */
function authHeaders() {
  const token = localStorage.getItem('api_token');
  return token ? { 'X-API-Token': token } : {};
}

export class ApiError extends Error {
  constructor(message, status, detail) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

/** يحوّل أخطاء التحقّق من Pydantic (422) إلى رسالة بشرية. */
function humanizeDetail(detail, status) {
  if (status === 401) return 'رمز الوصول مفقود أو خاطئ — أدخله من تبويب «المفاتيح».';
  if (Array.isArray(detail)) {
    const parts = detail.slice(0, 3).map(d => {
      const field = (d.loc || []).filter(x => x !== 'body').join('.');
      return field ? `${field}: ${d.msg}` : d.msg;
    });
    return parts.join(' • ');
  }
  if (typeof detail === 'string') return detail;
  return `فشل الطلب (HTTP ${status})`;
}

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(BASE + path, {
      ...options,
      headers: { ...(options.headers || {}), ...authHeaders() },
    });
  } catch (e) {
    throw new ApiError('تعذّر الاتصال بالخادم. تأكّد أنه يعمل على المنفذ 8000.', 0, null);
  }
  if (!res.ok) {
    let detail = null;
    try {
      detail = (await res.json()).detail;
    } catch { /* الجسم ليس JSON */ }
    throw new ApiError(humanizeDetail(detail, res.status), res.status, detail);
  }
  return res;
}

async function getJSON(path) {
  return (await request(path)).json();
}

async function postJSON(path, body) {
  return (await request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })).json();
}

export const api = {
  config: () => getJSON('/api/config'),
  benchmarks: () => getJSON('/api/benchmarks'),
  providers: () => getJSON('/api/providers'),
  sandboxStatus: () => getJSON('/api/sandbox/status'),
  pricing: () => getJSON('/api/pricing'),
  ollamaModels: url => getJSON('/api/ollama/models?base_url=' + encodeURIComponent(url)),
  estimate: body => postJSON('/api/estimate', body),
  runs: () => getJSON('/api/runs'),
  run: id => getJSON(`/api/runs/${encodeURIComponent(id)}`),
  h2h: id => getJSON(`/api/runs/${encodeURIComponent(id)}/h2h`),
  deleteRun: id => request(`/api/runs/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  cacheStats: () => getJSON('/api/cache/stats'),
  clearCache: async () => (await request('/api/cache', { method: 'DELETE' })).json(),

  /** التصدير عبر fetch ثم blob — window.location كان يفقد رأس المصادقة. */
  async downloadExport(runId, fmt) {
    const res = await request(`/api/runs/${encodeURIComponent(runId)}/export?format=${fmt}`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `run_${runId}.${fmt}`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  /** يبدأ تشغيلاً ويرجع القارئ الخام لبثّ SSE. */
  async startRun(body) {
    const res = await request('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    return res.body.getReader();
  },
};
