/* عرض النتائج: البثّ اللحظي، الملخّص، المقارنة الزوجية، التفاصيل، السجل. */

import { api } from './api.js';
import { baseChartOptions, themeColor } from './chart-theme.js';
import { h, modalBody, openModal, replaceChildren, showToast } from './dom.js';
import { DATE_LOCALE, liveKey, state } from './state.js';

/* رموز غير لونية لكل حالة — شبكة النتائج كانت تُميّز بالّلون وحده،
   فهي غير مقروءة لمن لديه عمى ألوان (نحو 8% من الذكور). */
const DOT_META = {
  correct: { glyph: '✓', label: 'صحيح' },
  wrong:   { glyph: '✗', label: 'خطأ' },
  error:   { glyph: '!', label: 'خطأ تشغيل' },
  cache:   { glyph: '⟲', label: 'من الـ cache' },
};

/* ============ النتائج اللحظية (رسم تزايدي) ============ */

export function resetLive(models) {
  state.liveData = {};
  for (const m of models) {
    state.liveData[liveKey(m.provider, m.model)] = {
      provider: m.provider, model: m.model,
      dots: [], n_correct: 0, n_errors: 0, n_cached: 0,
      total_cost: 0, total_latency: 0, n_done: 0,
    };
  }
  const container = document.getElementById('live-models');
  replaceChildren(container, Object.values(state.liveData).map(buildLiveCard));
  // مستمع واحد بالتفويض بدل مستمع لكل نقطة — كانت تُعاد الفهرسة
  // والربط لكل النقاط عند كل حدث، أي O(n²) عمليات DOM
  if (!container._delegated) {
    container.addEventListener('click', onDotClick);
    container.addEventListener('keydown', onDotKeydown);
    container._delegated = true;
  }
}

/**
 * تنقّل roving tabindex داخل شبكة النقاط.
 *
 * تشغيل 200 مسألة × 5 نماذج = 1000 زرّ في تسلسل Tab واحد؛ الوصول لجدول
 * الملخّص كان يحتاج ألف ضغطة. الآن نقطة واحدة لكل شبكة قابلة للوصول بـTab،
 * والتنقّل داخلها بالأسهم — نفس النمط المطبَّق على شريط التبويبات.
 */
function onDotKeydown(e) {
  const dot = e.target.closest?.('.dot');
  if (!dot) return;
  const grid = dot.parentElement;
  const dots = [...grid.querySelectorAll('.dot')];
  const i = dots.indexOf(dot);
  // في RTL السهم الأيسر يتقدّم والأيمن يرجع
  const delta = {
    ArrowLeft: 1, ArrowRight: -1,
    ArrowDown: 1, ArrowUp: -1,
    Home: -i, End: dots.length - 1 - i,
  }[e.key];
  if (delta === undefined) return;
  e.preventDefault();
  const next = dots[Math.min(Math.max(i + delta, 0), dots.length - 1)];
  if (!next || next === dot) return;
  dot.tabIndex = -1;
  next.tabIndex = 0;
  next.focus();
}

function buildLiveCard(m) {
  const key = liveKey(m.provider, m.model);
  return h('div', { class: 'live-model', dataset: { key } },
    h('div', { class: 'live-model-header' },
      h('span', { class: 'live-model-name' }, `${m.provider} / ${m.model}`),
      h('span', { class: 'live-model-stat', dataset: { role: 'stat' } }, '—'),
    ),
    // ``role="group"`` لا ``list``: كانت النقاط أزراراً بـ``role="listitem"``،
    // وهو يستبدل دور الزرّ في شجرة الوصول — فيعلن القارئ الصوتي «عنصر قائمة»
    // ولا يعرف المستخدم أنها قابلة للضغط أصلاً
    h('div', {
      class: 'dot-grid', dataset: { role: 'dots' },
      role: 'group', 'aria-label': `نتائج ${m.provider}/${m.model}`,
    }),
  );
}

/** يُلحق نقطة واحدة ويحدّث سطر الإحصاء — بلا إعادة بناء الشبكة. */
export function appendLiveResult(payload) {
  const key = liveKey(payload.provider, payload.model);
  const m = state.liveData[key];
  if (!m) return;

  let kind;
  if (payload.error) kind = 'error';
  else if (payload.cache_hit) kind = 'cache';
  else kind = payload.correct ? 'correct' : 'wrong';

  m.dots.push(kind);
  if (payload.correct) m.n_correct++;
  if (payload.error) m.n_errors++;
  if (payload.cache_hit) m.n_cached++;
  m.total_cost = payload.running_cost;
  m.total_latency += payload.latency_ms || 0;
  m.n_done++;

  const card = document.querySelector(`.live-model[data-key="${CSS.escape(key)}"]`);
  if (!card) return;

  const meta = DOT_META[kind];
  const latency = (payload.latency_ms || 0).toFixed(0);
  const grid = card.querySelector('[data-role="dots"]');
  const dot = h('button', {
    type: 'button',
    class: `dot dot-${kind}`,
    // النقطة الأولى وحدها في تسلسل Tab؛ البقيّة بالأسهم (roving tabindex)
    tabindex: grid.firstElementChild ? '-1' : '0',
    title: `${payload.problem_id} — ${meta.label} (${latency}ms)`,
    'aria-label': `${payload.problem_id}: ${meta.label}، ${latency} ملّي ثانية. اضغط للتفاصيل`,
    dataset: { pid: payload.problem_id || '', provider: m.provider, model: m.model },
  }, meta.glyph);
  grid.appendChild(dot);

  const acc = ((m.n_correct / (m.n_done || 1)) * 100).toFixed(1);
  const bits = [`${acc}%`, `$${(m.total_cost || 0).toFixed(4)}`];
  if (m.n_cached) bits.push(`${m.n_cached} cache`);
  if (m.n_errors) bits.push(`${m.n_errors} خطأ`);
  card.querySelector('[data-role="stat"]').textContent = bits.join(' • ');
}

function onDotClick(e) {
  const dot = e.target.closest('.dot');
  if (!dot || !dot.dataset.pid) return;
  showProblemDetail(dot.dataset.pid, dot.dataset.provider, dot.dataset.model);
}

/** لافتة تجميعية للأخطاء — كان نصّ الخطأ لا يصل للمستخدم إطلاقاً،
    فيظنّ النموذج ضعيفاً بينما المفتاح خاطئ. */
export function renderErrorSummary() {
  const box = document.getElementById('run-errors');
  const errors = Object.values(state.liveData).filter(m => m.n_errors > 0);
  if (!errors.length) {
    box.hidden = true;
    replaceChildren(box);
    return;
  }
  const total = errors.reduce((s, m) => s + m.n_errors, 0);
  replaceChildren(box,
    h('strong', {}, `⚠ ${total} استدعاء فشل`),
    ' — ',
    errors.map(m => `${m.provider}/${m.model}: ${m.n_errors}`).join(' • '),
    h('div', { class: 'muted small' }, 'افتح تفاصيل أي نقطة برتقالية لمعرفة السبب.'),
  );
  box.hidden = false;
}

/* ============ تفاصيل مسألة ============ */

export async function showProblemDetail(problemId, provider, model) {
  let detail = findDetail(problemId, provider, model);
  // كان يُعاد تحميل الـ run كاملاً (كل التفاصيل) لعرض صفّ واحد.
  // الآن نطلب صفوف هذا النموذج وحده من الـ endpoint المقسّم.
  if (!detail && state.currentRunId) {
    try {
      const page = await api.runDetails(state.currentRunId, { provider, model, limit: 500 });
      mergeDetails(page.details);
      detail = findDetail(problemId, provider, model);
    } catch (e) {
      showToast(e.message, 'error');
    }
  }

  const body = modalBody();
  if (!detail) {
    replaceChildren(body,
      h('p', { class: 'muted' }, 'لا توجد بيانات بعد — الـ run قد يكون قيد التشغيل.'),
    );
  } else {
    const status = detail.error ? 'error' : (detail.correct ? 'success' : 'error');
    const statusText = detail.error ? 'خطأ تشغيل' : (detail.correct ? 'صحيح' : 'خطأ');
    replaceChildren(body,
      h('div', { class: 'detail-header' },
        h('span', {}, `${detail.provider}/${detail.model}`),
        h('span', { class: `badge ${status}` }, statusText),
      ),
      detail.error && h('div', { class: 'detail-error' }, `سبب الفشل: ${detail.error}`),
      h('div', { class: 'muted small' }, detail.judgment || ''),
      h('div', { class: 'muted small' },
        `${(detail.latency_ms || 0).toFixed(0)}ms • $${(detail.cost_usd || 0).toFixed(6)}`),
      h('h3', { class: 'detail-subhead' }, 'رد النموذج:'),
      h('div', { class: 'detail-response' }, detail.response_text || ''),
    );
  }
  openModal(problemId);
}

function findDetail(problemId, provider, model) {
  return state.loadedDetails.find(d =>
    d.problem_id === problemId && d.provider === provider && d.model === model
  );
}

/** مفتاح هوية صفّ نتيجة: نفس المسألة على نفس النموذج. */
export const detailKey = d => `${d.problem_id}|${d.provider}|${d.model}`;

/** يدمج صفوفاً جديدة في قائمة موجودة بلا تكرار. دالة نقيّة قابلة للاختبار. */
export function mergeDetailRows(existing, incoming) {
  const seen = new Set(existing.map(detailKey));
  const out = existing.slice();
  for (const row of incoming) {
    if (!seen.has(detailKey(row))) {
      out.push(row);
      seen.add(detailKey(row));
    }
  }
  return out;
}

function mergeDetails(rows) {
  state.loadedDetails = mergeDetailRows(state.loadedDetails, rows);
}

/** يجمع صفوف النتائج حسب المسألة — أساس عرض المقارنة جنباً إلى جنب. */
export function groupByProblem(rows) {
  const byProblem = {};
  for (const d of rows) {
    (byProblem[d.problem_id] ||= []).push(d);
  }
  return byProblem;
}

/** يحمّل كل تفاصيل الـ run على صفحات — للعرض الكامل والمقارنة جنباً إلى جنب. */
async function loadAllDetails(runId) {
  const PAGE = 500;
  let offset = 0;
  let total = Infinity;
  const rows = [];
  while (offset < total) {
    const page = await api.runDetails(runId, { limit: PAGE, offset });
    total = page.total;
    rows.push(...page.details);
    if (!page.details.length) break;
    offset += page.details.length;
  }
  state.loadedDetails = rows;
  return rows;
}

/* ============ الملخّص ============ */

const SUMMARY_COLUMNS = [
  { key: 'provider', label: 'المزود' },
  { key: 'model', label: 'النموذج' },
  { key: 'accuracy', label: 'الدقة (95% CI)' },
  { key: 'avg_raw_score', label: 'المتوسط المرجّح' },
  { key: 'n_correct', label: 'صحيح/الكل' },
  { key: 'total_cost', label: 'التكلفة' },
  { key: 'avg_latency_ms', label: 'زمن متوسط' },
];

export async function showSummary(runId) {
  let data;
  try {
    data = await api.run(runId);
  } catch (e) {
    showToast(e.message, 'error');
    return;
  }
  state.currentRunData = data;
  state.currentRunId = runId;
  state.loadedDetails = [];  // تفاصيل run سابق لا تخصّ هذا
  document.getElementById('run-summary').classList.remove('hidden');

  if (data.models && data.models.length >= 2) renderH2H(runId);
  else document.getElementById('h2h-section').classList.add('hidden');

  state.summaryRows = data.models.slice();
  state.summarySort = { key: 'accuracy', dir: 'desc' };
  renderSummaryTable();
  renderBaseline(readBaselines(data));
  renderChart(data.models);
}

/** يستخرج خطّ الأساس من ``config_json`` المحفوظ مع الـrun. */
export function readBaselines(run) {
  try {
    return JSON.parse(run?.config_json || '{}').baselines || null;
  } catch {
    return null;
  }
}

/**
 * يعرض أعلى دقّة يبلغها متخمّن لا يقرأ السؤال.
 *
 * بلا هذا السطر تُقرأ «91% دقّة» كإنجاز حتى لو كان اختيار أطول خيار يبلغ 94.7%
 * على نفس العيّنة — وهو واقع بنشمارك القانون السعودي. الرقم المخفيّ هو الذي
 * يضلّل، لا الرقم المنخفض.
 */
export function renderBaseline(baselines) {
  const box = document.getElementById('summary-baseline');
  if (!baselines) {
    box.hidden = true;
    replaceChildren(box);
    return;
  }
  const pct = v => `${(v * 100).toFixed(1)}%`;
  replaceChildren(box,
    h('strong', {}, '📏 خطّ أساس التخمين على هذه العيّنة: '),
    h('span', {},
      `«دائماً ${baselines.majority_letter}» = `,
      h('bdi', {}, pct(baselines.majority_letter_accuracy)),
      ' · «أطول خيار» = ',
      h('bdi', {}, pct(baselines.longest_choice_accuracy)),
    ),
    h('div', { class: 'muted small' },
      'أي دقّة لا تتجاوز هذين الرقمين لا تدلّ على فهم النموذج للمحتوى.'),
  );
  box.hidden = false;
}

export function renderSummaryTable() {
  const rows = state.summaryRows.slice();
  const { key, dir } = state.summarySort;
  rows.sort((a, b) => {
    const av = a[key], bv = b[key];
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = (typeof av === 'number' && typeof bv === 'number')
      ? av - bv
      : String(av).localeCompare(String(bv), 'ar');
    return dir === 'asc' ? cmp : -cmp;
  });

  const headers = SUMMARY_COLUMNS.map(c => {
    const isSorted = c.key === key;
    const th = h('th', {
      class: 'sortable', scope: 'col',
      'aria-sort': isSorted ? (dir === 'asc' ? 'ascending' : 'descending') : 'none',
    },
      h('button', { type: 'button', class: 'sort-btn' },
        c.label, h('span', { class: 'sort-arrow', 'aria-hidden': 'true' },
          isSorted ? (dir === 'asc' ? '▲' : '▼') : ''),
      ),
    );
    th.querySelector('button').addEventListener('click', () => {
      if (state.summarySort.key === c.key) {
        state.summarySort.dir = state.summarySort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        state.summarySort = { key: c.key, dir: 'desc' };
      }
      renderSummaryTable();
    });
    return th;
  });

  const body = rows.map(m => h('tr', {},
    h('td', {}, m.provider),
    h('td', {}, m.model),
    h('td', { class: 'score-cell' },
      `${((m.accuracy ?? 0) * 100).toFixed(1)}% `,
      h('span', { class: 'ci' }, `±${((m.ci_margin || 0) * 100).toFixed(1)}`),
    ),
    h('td', {}, `${((m.avg_raw_score ?? 0) * 100).toFixed(1)}%`),
    h('td', {}, `${m.n_correct}/${m.n}`),
    h('td', {}, `$${(m.total_cost || 0).toFixed(4)}`),
    h('td', {}, `${(m.avg_latency_ms || 0).toFixed(0)}ms`),
  ));

  const table = h('table', {},
    h('caption', { class: 'muted small' },
      'الدقة نسبة الإجابات الصحيحة (وعليها فاصل الثقة). '
      + 'المتوسط المرجّح يحتسب الدرجات الجزئية في البنشماركات التي تدعمها.'),
    h('thead', {}, h('tr', {}, ...headers)),
    h('tbody', {}, ...body),
  );
  replaceChildren(document.getElementById('summary-table'),
    h('div', { class: 'table-scroll' }, table));
}

export function copySummaryAsMarkdown() {
  if (!state.summaryRows.length) {
    showToast('لا توجد نتائج لنسخها', 'error');
    return;
  }
  const header = '| المزود | النموذج | الدقة (95% CI) | المتوسط المرجّح | صحيح/الكل | التكلفة | زمن متوسط |';
  const sep = '|---|---|---|---|---|---|---|';
  const rows = state.summaryRows.map(m =>
    `| ${m.provider} | ${m.model} | ${((m.accuracy ?? 0) * 100).toFixed(1)}% ± ${((m.ci_margin || 0) * 100).toFixed(1)} `
    + `| ${((m.avg_raw_score ?? 0) * 100).toFixed(1)}% | ${m.n_correct}/${m.n} `
    + `| $${(m.total_cost || 0).toFixed(4)} | ${(m.avg_latency_ms || 0).toFixed(0)}ms |`
  ).join('\n');
  const md = `${header}\n${sep}\n${rows}\n`;

  navigator.clipboard.writeText(md)
    .then(() => showToast('تم النسخ كـ Markdown'))
    .catch(() => {
      const ta = h('textarea', { style: { position: 'fixed', opacity: '0' } });
      ta.value = md;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      ta.remove();
      showToast('تم النسخ');
    });
}

/* ============ المخطّط ============ */

export function renderChart(models) {
  if (state.chart) state.chart.destroy();
  const ctx = document.getElementById('results-chart').getContext('2d');

  state.chart = new Chart(ctx, {
    type: 'bar',
    data: {
      // مصفوفة = أسطر متعدّدة في Chart.js؛ السلسلة بـ \n كانت تُعرض سطراً واحداً
      labels: models.map(m => [m.provider, m.model]),
      datasets: [{
        label: 'دقة %',
        data: models.map(m => ((m.accuracy ?? 0) * 100).toFixed(1)),
        backgroundColor: themeColor('--primary', '#5b8def'),
        borderColor: themeColor('--primary-deep', '#3e6dd1'),
        borderWidth: 1,
      }],
    },
    options: baseChartOptions(),
  });
}

export function refreshChartTheme() {
  if (state.chart && state.currentRunData?.models) renderChart(state.currentRunData.models);
}

/* ============ المقارنة الزوجية ============ */

export async function renderH2H(runId) {
  const section = document.getElementById('h2h-section');
  const container = document.getElementById('h2h-matrix');
  let data;
  try {
    data = await api.h2h(runId);
  } catch {
    section.classList.add('hidden');
    return;
  }
  const { models, matrix } = data;
  if (!models || models.length < 2) {
    section.classList.add('hidden');
    return;
  }
  section.classList.remove('hidden');

  const head = h('tr', {}, h('th', { scope: 'col' }, ''),
    ...models.map(m => h('th', { scope: 'col' }, m.model)));

  const rows = matrix.map((row, i) => h('tr', {},
    h('th', { scope: 'row' }, models[i].model),
    ...row.map((cell, j) => {
      if (i === j) return h('td', { class: 'h2h-cell h2h-diag' }, '—');
      const pct = cell.a_wins_pct;
      const cls = pct > 0 ? 'h2h-win' : (cell.b_only > 0 ? 'h2h-lose' : 'h2h-tie');
      const title = `الصف تفوّق وحده: ${cell.a_only} • العمود تفوّق وحده: ${cell.b_only}`
        + ` • كلاهما صحيح: ${cell.both_correct} • كلاهما خطأ: ${cell.both_wrong}`
        + ` • مقارَن: ${cell.n_compared}`;
      return h('td', {
        class: `h2h-cell ${cls}`, title,
        style: { '--intensity': String(Math.min(pct / 50, 1)) },
      },
        `${pct}%`,
        h('br'),
        h('span', { class: 'h2h-detail' }, `${cell.a_only}/${cell.n_compared}`),
        // نفس نصّ الـtitle لقارئ الشاشة: كان الوصول إليه بالفأرة وحدها
        h('span', { class: 'sr-only' }, title),
      );
    }),
  ));

  replaceChildren(container,
    h('table', { class: 'h2h-table' }, h('thead', {}, head), h('tbody', {}, ...rows)));
}

/* ============ العرض الكامل والمقارنة جنباً إلى جنب ============ */

export async function showAllDetails() {
  if (!state.currentRunId) return;
  let rows;
  try {
    rows = await loadAllDetails(state.currentRunId);
  } catch (e) {
    showToast(e.message, 'error');
    return;
  }
  const items = rows.map(d => {
    const status = d.error ? 'error' : (d.correct ? 'success' : 'error');
    const statusText = d.error ? 'خطأ تشغيل' : (d.correct ? 'صحيح' : 'خطأ');
    return h('div', { class: 'detail-result' },
      h('div', { class: 'detail-header' },
        h('span', {}, `${d.provider}/${d.model} · ${d.problem_id}`),
        h('span', { class: `badge ${status}` }, statusText),
      ),
      d.error && h('div', { class: 'detail-error' }, d.error),
      h('div', { class: 'muted small' }, d.judgment || ''),
      h('details', {},
        h('summary', { class: 'muted small' }, 'عرض رد النموذج'),
        h('div', { class: 'detail-response' }, d.response_text || ''),
      ),
    );
  });
  replaceChildren(modalBody(), items);
  openModal(`تفاصيل Run ${state.currentRunId}`);
}

export async function showDiffView() {
  if (!state.currentRunId) {
    showToast('لا توجد بيانات لعرضها', 'error');
    return;
  }
  let rows;
  try {
    rows = await loadAllDetails(state.currentRunId);
  } catch (e) {
    showToast(e.message, 'error');
    return;
  }
  if (!rows.length) {
    showToast('لا توجد بيانات لعرضها', 'error');
    return;
  }
  const byProblem = groupByProblem(rows);

  const sections = Object.entries(byProblem).map(([pid, results]) => {
    const allSame = new Set(results.map(r => r.correct)).size === 1;
    const cells = results.map(r => {
      const status = r.error ? 'error' : (r.correct ? 'success' : 'error');
      return h('div', { class: `diff-cell diff-${status}` },
        h('div', { class: 'diff-cell-header' },
          h('span', { class: 'muted small' }, `${r.provider}/${r.model}`),
          h('span', { class: `badge ${status}` },
            r.error ? 'خطأ تشغيل' : (r.correct ? 'صحيح' : 'خطأ')),
        ),
        h('div', { class: 'diff-response' }, (r.response_text || '').slice(0, 800)),
        r.judgment && h('div', { class: 'muted small' }, r.judgment),
      );
    });
    return h('div', { class: 'diff-problem' },
      h('div', { class: `diff-problem-header ${allSame ? 'diff-agree' : 'diff-disagree'}` },
        h('strong', {}, pid),
        h('span', { class: 'muted small' }, allSame ? '✓ توافق' : '⚠ اختلاف'),
      ),
      h('div', { class: 'diff-grid' }, ...cells),
    );
  });

  replaceChildren(modalBody(),
    h('p', { class: 'muted small' }, 'كل صف يعرض نفس السؤال على كل النماذج.'),
    sections,
  );
  openModal(`مقارنة جنباً إلى جنب — Run ${state.currentRunId}`);
}

/* ============ السجل ============ */

/* كانت كل حالة غير "completed" تُعرض بشارة حمراء وبنصّها الإنجليزي الخام،
   فتشغيل "قيد التشغيل" يبدو فشلاً و"توقّف بالميزانية" يبدو عطلاً. */
const STATUS_META = {
  completed: { badge: 'success', label: 'مكتمل' },
  completed_with_errors: { badge: 'warn', label: 'مكتمل مع أخطاء' },
  running: { badge: 'info', label: 'قيد التشغيل' },
  aborted_budget: { badge: 'warn', label: 'توقّف: الميزانية' },
  aborted_disconnect: { badge: 'warn', label: 'توقّف: انقطاع' },
  failed: { badge: 'error', label: 'فشل' },
};

/** وصف حالة تشغيل. دالة نقيّة قابلة للاختبار بلا DOM. */
export function describeStatus(status) {
  return STATUS_META[status] || { badge: 'error', label: status || 'غير معروف' };
}

export async function loadHistory() {
  const container = document.getElementById('history-list');
  replaceChildren(container, h('p', { class: 'muted' }, 'جارٍ التحميل...'));
  let data;
  try {
    data = await api.runs();
  } catch (e) {
    replaceChildren(container, h('p', { class: 'muted' }, e.message));
    return;
  }
  if (!data.runs.length) {
    replaceChildren(container, h('p', { class: 'muted' }, 'لا توجد اختبارات سابقة بعد.'));
    return;
  }

  const rows = data.runs.map(r => {
    // 'ar-SA' وحده يُفعّل التقويم الهجري في Intl. و'nu-latn' ضروري كذلك:
    // بدونه تظهر التواريخ بأرقام هندية بجانب $0.0040 بأرقام عربية في نفس الصفّ
    const date = new Date(r.created_at * 1000)
      .toLocaleString(DATE_LOCALE, { dateStyle: 'medium', timeStyle: 'short' });
    const acc = r.avg_score != null ? `${(r.avg_score * 100).toFixed(1)}%` : '—';

    const open = h('button', {
      type: 'button', class: 'history-open',
      'aria-label': `فتح نتائج التشغيل ${r.id}`,
    },
      h('span', { class: 'history-id' }, `#${r.id}`),
      h('span', {},
        h('span', { class: 'history-bench' }, r.benchmark),
        h('span', { class: 'history-meta' },
          `${date} · ${r.n_problems} مسألة · ${r.n_results} نتيجة`),
      ),
      h('span', { class: 'history-score' }, acc),
      h('span', { class: 'muted small' }, `$${(r.total_cost || 0).toFixed(4)}`),
      (() => {
        const meta = describeStatus(r.status);
        return h('span', { class: `badge ${meta.badge}`, title: r.status }, meta.label);
      })(),
    );
    open.addEventListener('click', async () => {
      await showSummary(r.id);
      document.querySelector('.tab[data-tab="run"]').click();
    });

    const del = h('button', {
      type: 'button', class: 'icon-btn remove-btn',
      'aria-label': `حذف التشغيل ${r.id}`, title: 'حذف',
    }, '🗑');
    del.addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm(`حذف التشغيل #${r.id} نهائياً؟ لا يمكن التراجع.`)) return;
      try {
        await api.deleteRun(r.id);
        showToast('حُذف التشغيل');
        if (state.currentRunId === r.id) {
          state.currentRunId = null;
          state.currentRunData = null;
          document.getElementById('run-summary').classList.add('hidden');
        }
        loadHistory();
      } catch (err) {
        showToast(err.message, 'error');
      }
    });

    return h('div', { class: 'history-row' }, open, del);
  });
  replaceChildren(container, rows);
}
