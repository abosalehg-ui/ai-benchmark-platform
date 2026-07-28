/* نقطة الدخول: التبويبات، المظهر، الإقلاع، وتشغيل البنشمارك. */

import { api, ApiError } from './api.js';
import { h, hideBanner, initModal, replaceChildren, showBanner, showToast } from './dom.js';
import {
  addModelRow, clampProblems, loadKeys, loadOllamaModels,
  renderBenchmarks, renderModels, saveKeys, updateCostEstimate,
} from './setup.js';
import {
  appendLiveResult, copySummaryAsMarkdown, loadHistory, refreshChartTheme,
  renderErrorSummary, resetLive, showAllDetails, showDiffView, showSummary,
} from './results.js';
import { readSSE } from './sse.js';
import { getKey, state } from './state.js';

/* ============ التبويبات (نمط tablist قابل للوصول) ============ */

function initTabs() {
  const tabs = [...document.querySelectorAll('.tab')];

  function activate(tab) {
    for (const t of tabs) {
      const on = t === tab;
      t.classList.toggle('active', on);
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    }
    document.querySelectorAll('.tab-content').forEach(c => {
      c.classList.toggle('active', c.id === 'tab-' + tab.dataset.tab);
    });
    if (tab.dataset.tab === 'history') loadHistory();
  }

  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => activate(tab));
    tab.addEventListener('keydown', e => {
      // في RTL: السهم الأيسر يتقدّم والأيمن يرجع
      const delta = { ArrowLeft: 1, ArrowRight: -1, Home: -i, End: tabs.length - 1 - i }[e.key];
      if (delta === undefined) return;
      e.preventDefault();
      const next = tabs[(i + delta + tabs.length) % tabs.length];
      next.focus();
      activate(next);
    });
  });
}

/* ============ المظهر ============ */

function initTheme() {
  const saved = localStorage.getItem('theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  const btn = document.getElementById('theme-toggle');
  btn.setAttribute('aria-pressed', String(saved === 'light'));
  btn.addEventListener('click', () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    btn.setAttribute('aria-pressed', String(next === 'light'));
    refreshChartTheme(); // المخطّط يقرأ الألوان من CSS عند البناء فقط
  });
}

/* ============ حالة الـ sandbox ============ */

async function loadSandboxStatus() {
  const el = document.getElementById('sandbox-status');
  try {
    const data = await api.sandboxStatus();
    el.className = `sandbox-status ${data.is_isolated ? 'sandbox-ok' : 'sandbox-warn'}`;
    replaceChildren(el,
      `${data.is_isolated ? '🛡️' : '⚠️'} `,
      h('strong', {}, data.backend),
      ` — ${data.note}`,
    );
  } catch {
    el.textContent = 'تعذّر التحقّق من الـ sandbox';
  }
}

/* ============ التشغيل ============ */

function collectJudge() {
  const judgeProvider = ['anthropic', 'openai', 'gemini'].find(p => getKey(p));
  if (!judgeProvider) return null;
  const info = state.providers.find(p => p.id === judgeProvider);
  if (!info?.models?.length) return null;
  return {
    provider: judgeProvider,
    // آخر نموذج في القائمة هو الأصغر/الأرخص حسب ترتيبنا في backend/providers
    model: info.models[info.models.length - 1],
    api_key: getKey(judgeProvider),
  };
}

async function runBenchmark() {
  if (!state.selectedBenchmark) {
    showToast('اختر بنشمارك أولاً', 'error');
    return;
  }
  const validModels = state.models.filter(m => m.provider && m.model);
  if (!validModels.length) {
    showToast('اختر نموذجاً واحداً على الأقل', 'error');
    return;
  }
  const missing = validModels.find(m => m.provider !== 'ollama' && !getKey(m.provider));
  if (missing) {
    showToast(`مفتاح ${missing.provider} مفقود — أدخله من تبويب «المفاتيح»`, 'error');
    return;
  }

  let judge = null;
  if (state.selectedBenchmark === 'llm_judge') {
    judge = collectJudge();
    if (!judge) {
      showToast('بنشمارك LLM-as-judge يحتاج مفتاح Anthropic أو OpenAI أو Gemini ليعمل كحَكَم', 'error');
      return;
    }
  }

  const n = clampProblems();
  const budgetVal = parseFloat(document.getElementById('budget-usd').value);
  const body = {
    benchmark: state.selectedBenchmark,
    n_problems: n,
    targets: validModels.map(m => ({
      provider: m.provider,
      model: m.model,
      api_key: getKey(m.provider),
      base_url: m.provider === 'ollama'
        ? document.getElementById('key-ollama-url').value.trim()
        : null,
    })),
    judge,
    use_cache: document.getElementById('use-cache').checked,
    budget_usd: Number.isFinite(budgetVal) && budgetVal > 0 ? budgetVal : null,
    categories: [...state.selectedCategories],
    difficulties: [...state.selectedDifficulties],
    enforce_safety: (localStorage.getItem('enforce_safety') ?? 'true') === 'true',
  };

  const runBtn = document.getElementById('run-btn');
  runBtn.disabled = true;
  runBtn.textContent = '⏳ جارٍ التشغيل...';
  document.getElementById('progress-area').classList.remove('hidden');
  document.getElementById('run-summary').classList.add('hidden');
  document.getElementById('budget-warning').hidden = true;
  resetLive(validModels);
  renderErrorSummary();
  setProgress(0, 'جارٍ البدء...');

  try {
    const reader = await api.startRun(body);
    // العدد الحقيقي يصل مع حدث start بعد الفلترة؛ التقدير المحلي كان
    // يترك الشريط عالقاً دون 100% كلّما قلّت المسائل عن المطلوب
    let totalCalls = n * validModels.length;
    let doneCalls = 0;

    for await (const { event, data } of readSSE(reader)) {
      if (event === 'start') {
        state.currentRunId = data.run_id;
        totalCalls = data.total_calls || totalCalls;
        setProgress(0, `بدأ Run ${data.run_id} — ${totalCalls} استدعاء`);
      } else if (event === 'progress') {
        doneCalls++;
        appendLiveResult(data);
        const suffix = data.cache_hit ? ' (من الـ cache)' : '';
        setProgress(
          (doneCalls / totalCalls) * 100,
          `${doneCalls}/${totalCalls} — ${data.provider}/${data.model} مسألة ${data.i}/${data.n}${suffix}`,
        );
      } else if (event === 'budget_exceeded') {
        const warn = document.getElementById('budget-warning');
        warn.textContent =
          `⚠ تجاوز الميزانية: أُنفق $${data.spent_usd.toFixed(4)} من حدّ $${data.budget_usd.toFixed(2)}. توقّف التشغيل.`;
        warn.hidden = false;
      } else if (event === 'done') {
        renderErrorSummary();
        await showSummary(state.currentRunId);
      } else if (event === 'error') {
        showToast(data.error, 'error');
      }
    }
  } catch (e) {
    showToast(e instanceof ApiError ? e.message : `خطأ: ${e.message}`, 'error');
  } finally {
    runBtn.disabled = false;
    runBtn.textContent = '▶ شغّل الاختبار';
  }
}

function setProgress(pct, text) {
  const bar = document.getElementById('progress-bar');
  const fill = document.getElementById('progress-fill');
  fill.style.width = `${Math.min(pct, 100)}%`;
  bar.setAttribute('aria-valuenow', String(Math.round(pct)));
  document.getElementById('progress-text').textContent = text;
}

/* ============ الإقلاع ============ */

function showSkeleton() {
  replaceChildren(document.getElementById('benchmark-list'),
    ...Array.from({ length: 4 }, () => h('div', { class: 'skeleton skeleton-card' })));
}

async function init() {
  initTabs();
  initTheme();
  initModal();
  loadKeys();
  showSkeleton();

  document.getElementById('add-model-btn').addEventListener('click', addModelRow);
  document.getElementById('run-btn').addEventListener('click', runBenchmark);
  document.getElementById('save-keys-btn').addEventListener('click', saveKeys);
  document.getElementById('n-problems').addEventListener('input', updateCostEstimate);
  document.getElementById('refresh-history').addEventListener('click', loadHistory);
  document.getElementById('view-details-btn').addEventListener('click', showAllDetails);
  document.getElementById('view-diff-btn').addEventListener('click', showDiffView);
  document.getElementById('copy-md-btn').addEventListener('click', copySummaryAsMarkdown);
  document.getElementById('export-json-btn')
    .addEventListener('click', () => exportRun('json'));
  document.getElementById('export-csv-btn')
    .addEventListener('click', () => exportRun('csv'));
  document.getElementById('clear-cache-btn').addEventListener('click', clearCache);

  try {
    const [config, benchmarks, providers] = await Promise.all([
      api.config(), api.benchmarks(), api.providers(),
    ]);
    hideBanner();
    state.config = config;
    state.benchmarks = benchmarks.benchmarks;
    state.providers = providers.providers;
    document.getElementById('n-problems').max = String(config.max_problems);
    renderBenchmarks();
  } catch (e) {
    showBanner(e.message);
    replaceChildren(document.getElementById('benchmark-list'));
    return;
  }

  // غير حرجة: فشلها لا يمنع استخدام المنصّة
  await Promise.allSettled([loadOllamaModels(), loadSandboxStatus(), refreshCacheStats()]);
  if (!state.models.length) addModelRow();
  renderModels();
}

async function exportRun(fmt) {
  if (!state.currentRunId) {
    showToast('لا يوجد Run محدّد للتصدير', 'error');
    return;
  }
  try {
    await api.downloadExport(state.currentRunId, fmt);
  } catch (e) {
    showToast(e.message, 'error');
  }
}

async function refreshCacheStats() {
  try {
    const s = await api.cacheStats();
    document.getElementById('cache-stats').textContent =
      `${s.entries} استجابة محفوظة — تعادل $${(s.cached_cost_value_usd || 0).toFixed(4)} موفّرة`;
  } catch {
    document.getElementById('cache-stats').textContent = 'تعذّر قراءة إحصاءات الـ cache';
  }
}

async function clearCache() {
  if (!confirm('تفريغ الـ cache؟ إعادة التشغيل بعدها ستُنفق تكلفة من جديد.')) return;
  try {
    const r = await api.clearCache();
    showToast(`فُرِّغ الـ cache (${r.cleared} مدخل)`);
    refreshCacheStats();
  } catch (e) {
    showToast(e.message, 'error');
  }
}

init();
