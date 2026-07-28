/* شاشة الإعداد: اختيار البنشمارك، الفلاتر، النماذج، المفاتيح، تقدير التكلفة. */

import { api, ApiError } from './api.js';
import { h, replaceChildren, showToast } from './dom.js';
import { PROVIDER_KEYS, getKey, ollamaUrl, state } from './state.js';

/* ============ البنشماركات ============ */

export function renderBenchmarks() {
  const list = document.getElementById('benchmark-list');
  if (!state.benchmarks.length) {
    replaceChildren(list, h('p', { class: 'muted small' }, 'لا توجد بنشماركات متاحة.'));
    return;
  }
  const cards = state.benchmarks.map(b => {
    const meta = [
      `${b.problems_count} سؤال`,
      b.categories?.length ? `${b.categories.length} تصنيف` : null,
      b.difficulties?.length ? `${b.difficulties.length} مستوى صعوبة` : null,
    ].filter(Boolean).join(' • ');

    const card = h('button', {
      class: 'bench-card',
      type: 'button',
      'aria-pressed': 'false',
      dataset: { id: b.id },
    },
      h('h4', {}, b.name),
      h('p', {}, b.description),
      h('small', { class: 'muted' }, meta),
    );

    card.addEventListener('click', () => {
      state.selectedBenchmark = b.id;
      state.selectedCategories = new Set();
      state.selectedDifficulties = new Set();
      list.querySelectorAll('.bench-card').forEach(x => {
        x.classList.remove('selected');
        x.setAttribute('aria-pressed', 'false');
      });
      card.classList.add('selected');
      card.setAttribute('aria-pressed', 'true');
      renderChips('categories', b.categories || [], state.selectedCategories);
      renderChips('difficulties', b.difficulties || [], state.selectedDifficulties);
      updateCostEstimate();
    });
    return card;
  });
  replaceChildren(list, cards);
}

function renderChips(kind, values, selectedSet) {
  const wrap = document.getElementById(`${kind}-wrap`);
  const list = document.getElementById(`${kind}-list`);
  if (!values.length) {
    replaceChildren(list);
    wrap.classList.add('hidden');
    return;
  }
  wrap.classList.remove('hidden');
  const chips = values.map(v => {
    const chip = h('button', {
      class: 'cat-chip',
      type: 'button',
      'aria-pressed': 'false',
    }, v);
    chip.addEventListener('click', () => {
      const active = selectedSet.has(v);
      if (active) selectedSet.delete(v); else selectedSet.add(v);
      chip.classList.toggle('active', !active);
      chip.setAttribute('aria-pressed', String(!active));
      // كان هذا مفقوداً: تبديل الفلتر يغيّر عدد المسائل الفعلي
      // فيبقى التقدير المعروض للعدد الكامل بصمت
      updateCostEstimate();
    });
    return chip;
  });
  replaceChildren(list, chips);
}

/* ============ النماذج ============ */

export function addModelRow() {
  if (state.models.length >= state.config.max_targets) {
    showToast(`الحدّ الأقصى ${state.config.max_targets} نماذج في التشغيل الواحد`, 'error');
    return;
  }
  state.models.push({ provider: 'anthropic', model: '' });
  renderModels();
  updateCostEstimate();
}

export function renderModels() {
  const container = document.getElementById('model-picker');
  const rows = state.models.map((m, idx) => {
    const provSel = h('select', { 'aria-label': `المزوّد للنموذج ${idx + 1}` },
      ...state.providers.map(p =>
        h('option', { value: p.id, selected: p.id === m.provider }, p.id)
      ),
    );
    provSel.addEventListener('change', async () => {
      state.models[idx].provider = provSel.value;
      state.models[idx].model = '';
      if (provSel.value === 'ollama') await loadOllamaModels();
      renderModels();
      updateCostEstimate();
    });

    const provider = state.providers.find(p => p.id === m.provider);
    let models = provider ? provider.models : [];
    if (m.provider === 'ollama') models = state.ollamaModels;

    const options = [];
    if (!models.length) {
      const label = m.provider === 'ollama'
        ? (state.ollamaError ? '⚠ تعذّر جلب نماذج Ollama' : '— لا توجد نماذج محلية —')
        : '— اختر —';
      options.push(h('option', { value: '' }, label));
    }
    if (!m.model && models.length) state.models[idx].model = models[0];
    options.push(...models.map(mn =>
      h('option', { value: mn, selected: mn === state.models[idx].model }, mn)
    ));

    const modelSel = h('select', { 'aria-label': `النموذج ${idx + 1}` }, ...options);
    modelSel.addEventListener('change', () => {
      state.models[idx].model = modelSel.value;
      updateCostEstimate();
    });

    const row = h('div', { class: 'model-row' }, provSel, modelSel);

    if (m.provider === 'ollama') {
      const refresh = h('button', {
        class: 'icon-btn', type: 'button',
        title: 'تحديث نماذج Ollama', 'aria-label': 'تحديث نماذج Ollama',
      }, '↻');
      refresh.addEventListener('click', async () => {
        refresh.disabled = true;
        refresh.textContent = '⏳';
        await loadOllamaModels();
        renderModels();
      });
      row.append(refresh);
    }

    const remove = h('button', {
      class: 'icon-btn remove-btn', type: 'button',
      'aria-label': `إزالة النموذج ${idx + 1}`,
    }, '×');
    remove.addEventListener('click', () => {
      state.models.splice(idx, 1);
      renderModels();
      updateCostEstimate();
    });
    row.append(remove);
    return row;
  });
  replaceChildren(container, rows);
}

export async function loadOllamaModels() {
  try {
    const data = await api.ollamaModels(ollamaUrl());
    state.ollamaModels = data.models || [];
    state.ollamaError = data.error || null;
  } catch (e) {
    state.ollamaModels = [];
    state.ollamaError = e instanceof ApiError ? e.message : String(e);
  }
}

/* ============ تقدير التكلفة ============ */

let estimateTimer = null;

export function updateCostEstimate() {
  const out = document.getElementById('cost-value');
  const n = clampProblems();
  const validModels = state.models.filter(m => m.provider && m.model);

  if (!validModels.length || !state.selectedBenchmark) {
    out.textContent = '—';
    return;
  }
  const calls = n * validModels.length;
  out.textContent = `${calls} استدعاء — جارٍ التقدير...`;

  clearTimeout(estimateTimer);
  estimateTimer = setTimeout(async () => {
    try {
      const data = await api.estimate({
        benchmark: state.selectedBenchmark,
        n_problems: n,
        targets: validModels.map(m => ({ provider: m.provider, model: m.model })),
        categories: [...state.selectedCategories],
        difficulties: [...state.selectedDifficulties],
      });
      const effective = data.n_problems_effective;
      const realCalls = effective * validModels.length;
      const cost = (data.total_usd || 0).toFixed(4);
      const noPrice = (data.per_target || []).filter(t => !t.has_price).length;
      const note = noPrice ? ` (${noPrice} نموذج بدون تسعير معروف)` : '';
      const filtered = effective !== n ? ` — بعد الفلترة: ${effective} مسألة` : '';
      out.textContent = `${realCalls} استدعاء — تقريباً $${cost}${note}${filtered}`;
    } catch {
      out.textContent = `${calls} استدعاء`;
    }
  }, 400);
}

/** يقصّ عدد المسائل على حدود الخادم — المتصفح لا يفرض max على القيم المكتوبة. */
export function clampProblems() {
  const input = document.getElementById('n-problems');
  let n = parseInt(input.value || '5', 10);
  if (!Number.isFinite(n)) n = 5;
  n = Math.min(Math.max(n, 1), state.config.max_problems);
  if (String(n) !== input.value) input.value = String(n);
  return n;
}

/* ============ المفاتيح ============ */

export function loadKeys() {
  for (const p of PROVIDER_KEYS) {
    const v = localStorage.getItem('key_' + p);
    if (v) document.getElementById('key-' + p).value = v;
  }
  const url = localStorage.getItem('ollama_url');
  if (url) document.getElementById('key-ollama-url').value = url;
  const token = localStorage.getItem('api_token');
  if (token) document.getElementById('key-api-token').value = token;
  const safety = localStorage.getItem('enforce_safety');
  if (safety !== null) document.getElementById('enforce-safety').checked = safety === 'true';
}

export function saveKeys() {
  for (const p of PROVIDER_KEYS) {
    const v = document.getElementById('key-' + p).value.trim();
    if (v) localStorage.setItem('key_' + p, v);
    else localStorage.removeItem('key_' + p);
  }
  localStorage.setItem('ollama_url', ollamaUrl());
  const token = document.getElementById('key-api-token').value.trim();
  if (token) localStorage.setItem('api_token', token);
  else localStorage.removeItem('api_token');
  localStorage.setItem('enforce_safety', document.getElementById('enforce-safety').checked);
  showToast('تم الحفظ محلياً في هذا المتصفح');
  loadOllamaModels().then(renderModels);
}

export { getKey };
