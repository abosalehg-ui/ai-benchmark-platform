/* ========================================
   منصة البنشمارك - منطق الواجهة
   ======================================== */

const API = ''; // same origin

// ============ State ============
const state = {
  benchmarks: [],
  providers: [],
  selectedBenchmark: null,
  models: [], // [{provider, model}]
  ollamaModels: [],
  currentRunId: null,
  liveData: {}, // { "provider:model": { dots: [], n_correct, total_cost, ... } }
  chart: null,
};

// ============ Tabs ============
document.querySelectorAll('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
    if (btn.dataset.tab === 'history') loadHistory();
  });
});

// ============ Init ============
async function init() {
  loadKeys();
  await Promise.all([loadBenchmarks(), loadProviders(), loadOllamaModels()]);
  // نموذج افتراضي
  if (!state.models.length) addModelRow();
}

async function loadBenchmarks() {
  const r = await fetch(API + '/api/benchmarks');
  const data = await r.json();
  state.benchmarks = data.benchmarks;
  renderBenchmarks();
}

async function loadProviders() {
  const r = await fetch(API + '/api/providers');
  const data = await r.json();
  state.providers = data.providers;
}

async function loadOllamaModels() {
  const url = document.getElementById('key-ollama-url').value || 'http://localhost:11434';
  try {
    const r = await fetch(API + '/api/ollama/models?base_url=' + encodeURIComponent(url));
    const data = await r.json();
    state.ollamaModels = data.models || [];
  } catch {
    state.ollamaModels = [];
  }
}

function renderBenchmarks() {
  const c = document.getElementById('benchmark-list');
  c.innerHTML = '';
  state.benchmarks.forEach(b => {
    const card = document.createElement('div');
    card.className = 'bench-card';
    card.dataset.id = b.id;
    card.innerHTML = `<h4>${b.name}</h4><p>${b.description}</p>`;
    card.addEventListener('click', () => {
      state.selectedBenchmark = b.id;
      document.querySelectorAll('.bench-card').forEach(x => x.classList.remove('selected'));
      card.classList.add('selected');
      updateCostEstimate();
    });
    c.appendChild(card);
  });
}

// ============ Models ============
function addModelRow() {
  const idx = state.models.length;
  state.models.push({ provider: 'anthropic', model: '' });
  renderModels();
}

function renderModels() {
  const c = document.getElementById('model-picker');
  c.innerHTML = '';
  state.models.forEach((m, idx) => {
    const row = document.createElement('div');
    row.className = 'model-row';

    const provSel = document.createElement('select');
    state.providers.forEach(p => {
      const o = document.createElement('option');
      o.value = p.id;
      o.textContent = p.id;
      if (p.id === m.provider) o.selected = true;
      provSel.appendChild(o);
    });
    provSel.addEventListener('change', () => {
      state.models[idx].provider = provSel.value;
      state.models[idx].model = '';
      renderModels();
      updateCostEstimate();
    });

    const modelSel = document.createElement('select');
    const provider = state.providers.find(p => p.id === m.provider);
    let models = provider ? provider.models : [];
    if (m.provider === 'ollama') models = state.ollamaModels;
    if (!models.length) {
      const o = document.createElement('option');
      o.value = '';
      o.textContent = m.provider === 'ollama' ? '— لا توجد نماذج محلية —' : '— اختر —';
      modelSel.appendChild(o);
    }
    models.forEach(mn => {
      const o = document.createElement('option');
      o.value = mn;
      o.textContent = mn;
      if (mn === m.model) o.selected = true;
      modelSel.appendChild(o);
    });
    if (!m.model && models.length) {
      state.models[idx].model = models[0];
      modelSel.value = models[0];
    }
    modelSel.addEventListener('change', () => {
      state.models[idx].model = modelSel.value;
      updateCostEstimate();
    });

    const removeBtn = document.createElement('button');
    removeBtn.className = 'remove-btn';
    removeBtn.textContent = '×';
    removeBtn.addEventListener('click', () => {
      state.models.splice(idx, 1);
      renderModels();
      updateCostEstimate();
    });

    row.appendChild(provSel);
    row.appendChild(modelSel);
    row.appendChild(removeBtn);
    c.appendChild(row);
  });
}

document.getElementById('add-model-btn').addEventListener('click', addModelRow);

// ============ Cost Estimate ============
function updateCostEstimate() {
  const n = parseInt(document.getElementById('n-problems').value || '5', 10);
  const validModels = state.models.filter(m => m.provider && m.model);
  const calls = n * validModels.length;
  document.getElementById('cost-value').textContent =
    validModels.length === 0 ? '—' : `${calls} استدعاء (تقريباً)`;
}

document.getElementById('n-problems').addEventListener('input', updateCostEstimate);

// ============ Keys ============
function loadKeys() {
  ['anthropic', 'openai', 'gemini', 'openrouter'].forEach(p => {
    const v = localStorage.getItem('key_' + p);
    if (v) document.getElementById('key-' + p).value = v;
  });
  const ollamaUrl = localStorage.getItem('ollama_url');
  if (ollamaUrl) document.getElementById('key-ollama-url').value = ollamaUrl;
  const safety = localStorage.getItem('enforce_safety');
  if (safety !== null) document.getElementById('enforce-safety').checked = safety === 'true';
}

document.getElementById('save-keys-btn').addEventListener('click', () => {
  ['anthropic', 'openai', 'gemini', 'openrouter'].forEach(p => {
    const v = document.getElementById('key-' + p).value.trim();
    if (v) localStorage.setItem('key_' + p, v);
    else localStorage.removeItem('key_' + p);
  });
  localStorage.setItem('ollama_url', document.getElementById('key-ollama-url').value.trim());
  localStorage.setItem('enforce_safety', document.getElementById('enforce-safety').checked);
  document.getElementById('keys-status').textContent = '✓ تم الحفظ محلياً.';
  loadOllamaModels().then(renderModels);
  setTimeout(() => { document.getElementById('keys-status').textContent = ''; }, 3000);
});

function getKey(provider) {
  if (provider === 'ollama') return '';
  return localStorage.getItem('key_' + provider) || '';
}

// ============ Run ============
document.getElementById('run-btn').addEventListener('click', runBenchmark);

async function runBenchmark() {
  if (!state.selectedBenchmark) {
    alert('اختر بنشمارك أولاً');
    return;
  }
  const validModels = state.models.filter(m => m.provider && m.model);
  if (!validModels.length) {
    alert('اختر نموذج واحد على الأقل');
    return;
  }
  // تحقّق من المفاتيح
  for (const m of validModels) {
    if (m.provider !== 'ollama' && !getKey(m.provider)) {
      alert(`مفتاح ${m.provider} مفقود. ادخله من تبويب "المفاتيح"`);
      return;
    }
  }

  const n = parseInt(document.getElementById('n-problems').value || '5', 10);
  const targets = validModels.map(m => ({
    provider: m.provider,
    model: m.model,
    api_key: getKey(m.provider),
    base_url: m.provider === 'ollama' ? document.getElementById('key-ollama-url').value : null,
  }));

  // إعداد حَكَم تلقائياً للـ llm_judge: نختار أول نموذج Claude/OpenAI ليس مُختبراً
  let judge = null;
  if (state.selectedBenchmark === 'llm_judge') {
    const judgeProvider = ['anthropic', 'openai', 'gemini'].find(p => getKey(p));
    if (!judgeProvider) {
      alert('بنشمارك LLM-as-judge يحتاج مفتاح Anthropic/OpenAI/Gemini ليعمل كحَكَم');
      return;
    }
    const provInfo = state.providers.find(p => p.id === judgeProvider);
    judge = {
      provider: judgeProvider,
      model: provInfo.models[provInfo.models.length - 1], // آخر نموذج (عادةً الأرخص)
      api_key: getKey(judgeProvider),
    };
  }

  document.getElementById('run-btn').disabled = true;
  document.getElementById('progress-area').classList.remove('hidden');
  document.getElementById('run-summary').classList.add('hidden');
  state.liveData = {};
  validModels.forEach(m => {
    state.liveData[`${m.provider}:${m.model}`] = {
      provider: m.provider, model: m.model,
      dots: [], n_correct: 0, total_cost: 0, total_latency: 0, n_done: 0,
    };
  });
  renderLiveModels();

  // SSE via POST + ReadableStream
  try {
    const res = await fetch(API + '/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        benchmark: state.selectedBenchmark,
        n_problems: n,
        targets,
        judge,
      }),
    });

    if (!res.ok) throw new Error('فشل التشغيل: ' + (await res.text()));

    const reader = res.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let totalCalls = n * validModels.length;
    let doneCalls = 0;

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const events = buffer.split('\n\n');
      buffer = events.pop() || '';

      for (const block of events) {
        const lines = block.split('\n');
        let evType = '';
        let evData = '';
        for (const line of lines) {
          if (line.startsWith('event:')) evType = line.slice(6).trim();
          if (line.startsWith('data:')) evData = line.slice(5).trim();
        }
        if (!evType || !evData) continue;
        let payload = {};
        try { payload = JSON.parse(evData); } catch {}

        if (evType === 'start') {
          state.currentRunId = payload.run_id;
          document.getElementById('progress-text').textContent =
            `بدأ Run ${payload.run_id} — ${payload.total_calls} استدعاء`;
        } else if (evType === 'progress') {
          doneCalls++;
          const key = `${payload.provider}:${payload.model}`;
          const m = state.liveData[key];
          if (m) {
            m.dots.push(payload.error ? 'error' : (payload.correct ? 'correct' : 'wrong'));
            if (payload.correct) m.n_correct++;
            m.total_cost = payload.running_cost;
            m.total_latency += payload.latency_ms || 0;
            m.n_done++;
          }
          const pct = (doneCalls / totalCalls) * 100;
          document.getElementById('progress-fill').style.width = pct + '%';
          document.getElementById('progress-text').textContent =
            `${doneCalls}/${totalCalls} — ${payload.provider}/${payload.model} مسألة ${payload.i}/${payload.n}`;
          renderLiveModels();
        } else if (evType === 'model_done') {
          // نحفظ الإحصائيات النهائية
          const key = `${payload.provider}:${payload.model}`;
          if (state.liveData[key]) {
            state.liveData[key].final = payload;
          }
        } else if (evType === 'done') {
          await showSummary(state.currentRunId);
        } else if (evType === 'error') {
          alert('خطأ: ' + payload.error);
        }
      }
    }
  } catch (e) {
    alert('خطأ: ' + e.message);
  } finally {
    document.getElementById('run-btn').disabled = false;
  }
}

function renderLiveModels() {
  const c = document.getElementById('live-models');
  c.innerHTML = '';
  Object.values(state.liveData).forEach(m => {
    const total = m.n_done || 1;
    const acc = ((m.n_correct / total) * 100).toFixed(1);
    const div = document.createElement('div');
    div.className = 'live-model';
    div.innerHTML = `
      <div class="live-model-header">
        <span class="live-model-name">${m.provider} / ${m.model}</span>
        <span class="live-model-stat">${acc}% • $${m.total_cost.toFixed(4)}</span>
      </div>
      <div class="dot-grid">
        ${m.dots.map(d => `<div class="dot ${d}"></div>`).join('')}
      </div>
    `;
    c.appendChild(div);
  });
}

// ============ Summary ============
async function showSummary(runId) {
  const r = await fetch(API + '/api/runs/' + runId);
  const data = await r.json();
  const summary = document.getElementById('run-summary');
  summary.classList.remove('hidden');

  const tbl = document.getElementById('summary-table');
  let html = `<table>
    <tr><th>المزود</th><th>النموذج</th><th>الدقة</th><th>صحيح/الكل</th><th>التكلفة</th><th>زمن متوسط</th></tr>`;
  data.models.forEach(m => {
    html += `<tr>
      <td>${m.provider}</td>
      <td>${m.model}</td>
      <td class="score-cell">${(m.accuracy * 100).toFixed(1)}%</td>
      <td>${m.n_correct}/${m.n}</td>
      <td>$${(m.total_cost || 0).toFixed(4)}</td>
      <td>${(m.avg_latency_ms || 0).toFixed(0)}ms</td>
    </tr>`;
  });
  html += `</table>`;
  tbl.innerHTML = html;

  // Chart
  if (state.chart) state.chart.destroy();
  const ctx = document.getElementById('results-chart').getContext('2d');
  state.chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: data.models.map(m => `${m.provider}\n${m.model}`),
      datasets: [{
        label: 'دقة %',
        data: data.models.map(m => (m.accuracy * 100).toFixed(1)),
        backgroundColor: '#5b8def',
        borderColor: '#3e6dd1',
        borderWidth: 1,
      }],
    },
    options: {
      responsive: true,
      plugins: { legend: { labels: { color: '#e8ecf5' } } },
      scales: {
        y: { beginAtZero: true, max: 100, ticks: { color: '#8a93b0' }, grid: { color: '#232944' } },
        x: { ticks: { color: '#8a93b0' }, grid: { color: '#232944' } },
      },
    },
  });
}

document.getElementById('view-details-btn').addEventListener('click', async () => {
  if (!state.currentRunId) return;
  const r = await fetch(API + '/api/runs/' + state.currentRunId);
  const data = await r.json();
  const body = document.getElementById('modal-body');
  body.innerHTML = '<h2>تفاصيل Run ' + state.currentRunId + '</h2>';
  data.details.forEach(d => {
    const div = document.createElement('div');
    div.className = 'detail-result';
    const status = d.error ? 'error' : (d.correct ? 'success' : 'error');
    const statusText = d.error ? 'خطأ' : (d.correct ? 'صحيح' : 'خطأ');
    div.innerHTML = `
      <div class="detail-header">
        <span>${d.provider}/${d.model} · ${d.problem_id}</span>
        <span class="badge ${status}">${statusText}</span>
      </div>
      <div class="muted small">${d.judgment || ''}</div>
      <details><summary class="muted small">عرض رد النموذج</summary>
        <div class="detail-response">${escapeHtml(d.response_text || '')}</div>
      </details>
    `;
    body.appendChild(div);
  });
  document.getElementById('details-modal').classList.remove('hidden');
});

document.getElementById('modal-close').addEventListener('click', () => {
  document.getElementById('details-modal').classList.add('hidden');
});

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

// ============ History ============
async function loadHistory() {
  const r = await fetch(API + '/api/runs');
  const data = await r.json();
  const c = document.getElementById('history-list');
  c.innerHTML = '';
  if (!data.runs.length) {
    c.innerHTML = '<p class="muted">لا توجد اختبارات سابقة بعد.</p>';
    return;
  }
  data.runs.forEach(r => {
    const div = document.createElement('div');
    div.className = 'history-row';
    const date = new Date(r.created_at * 1000).toLocaleString('ar-SA');
    const acc = r.avg_score != null ? ((r.avg_score) * 100).toFixed(1) + '%' : '—';
    div.innerHTML = `
      <span class="history-id">#${r.id}</span>
      <div>
        <div class="history-bench">${r.benchmark}</div>
        <div class="history-meta">${date} · ${r.n_problems} مسألة · ${r.n_results} نتيجة</div>
      </div>
      <span class="history-score">${acc}</span>
      <span class="muted small">$${(r.total_cost || 0).toFixed(4)}</span>
      <span class="badge ${r.status === 'completed' ? 'success' : 'error'}">${r.status}</span>
    `;
    div.addEventListener('click', async () => {
      state.currentRunId = r.id;
      await showSummary(r.id);
      // ارجع لتبويب التشغيل عشان نشوف الملخص
      document.querySelector('.tab[data-tab="run"]').click();
    });
    c.appendChild(div);
  });
}

document.getElementById('refresh-history').addEventListener('click', loadHistory);

// ============ Boot ============
init();
