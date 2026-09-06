/* تتبّع الانحراف عبر الزمن: مخطّط خطّي + جدول التغيّر لكل نموذج.

   الفكرة: تشغيلات نفس (بنشمارك، نموذج) كانت جزراً منفصلة في السجل. هنا تُربط
   لتُظهر الاتجاه — لأن المزوّدين يحدّثون النماذج خلف نفس اسم الإصدار أحياناً.

   المزلق الذي نتجنّبه في العرض: لا نرسم خطّاً متصلاً بين نقاط مختلفة النطاق
   (عدد مسائل أو فلاتر مختلفة) بلا تحذير — الفرق حينها من العيّنة لا من النموذج. */

import { api } from './api.js';
import { baseChartOptions, seriesColor, themeColor } from './chart-theme.js';
import { h, replaceChildren, showToast } from './dom.js';
import { DATE_LOCALE, state } from './state.js';

/** تنسيق تاريخ قصير. 'ar-SA' وحده يُفعّل التقويم الهجري في Intl. */
export function formatPointDate(epochSeconds) {
  return new Date(epochSeconds * 1000)
    .toLocaleDateString(DATE_LOCALE, { month: 'short', day: 'numeric' });
}

/**
 * سهم الاتجاه ونصّه. دالة نقيّة — الجدول والقارئ الصوتي يستخدمانها معاً.
 * `significant` من الخادم: عدم تداخل فاصلَي ويلسون (اختبار محافظ).
 */
export function describeChange(change) {
  if (!change) return { glyph: '—', label: 'لا مقارنة متاحة', kind: 'none' };
  const pts = change.delta_pct_points;
  if (pts === 0) return { glyph: '=', label: 'بلا تغيّر', kind: 'flat' };
  const dir = pts > 0 ? 'ارتفاع' : 'انخفاض';
  const kind = change.significant ? (pts > 0 ? 'up' : 'down') : 'noise';
  const suffix = change.significant ? 'ذو دلالة' : 'ضمن تقلّب العيّنة';
  return {
    glyph: pts > 0 ? '▲' : '▼',
    label: `${dir} ${Math.abs(pts)} نقطة مئوية — ${suffix}`,
    kind,
  };
}

/* ============ التحميل والعرض ============ */

export async function loadDrift() {
  const select = document.getElementById('drift-benchmark');
  const benchmark = select.value;
  if (!benchmark) return;

  const includePartial = document.getElementById('drift-include-partial').checked;
  let data;
  try {
    data = await api.drift(benchmark, { includePartial });
  } catch (e) {
    showToast(e.message, 'error');
    return;
  }
  state.driftData = data;
  renderDrift(data);
}

function renderDrift(data) {
  const empty = document.getElementById('drift-empty');
  const figure = document.getElementById('drift-chart-figure');
  const warning = document.getElementById('drift-scope-warning');

  const trackable = data.trackable || [];
  if (!trackable.length) {
    destroyChart();
    figure.hidden = true;
    warning.hidden = true;
    replaceChildren(document.getElementById('drift-table'));
    empty.hidden = false;
    empty.textContent = data.n_models
      ? 'كل نموذج هنا له تشغيل واحد فقط — التتبّع يحتاج تشغيلين على الأقل لنفس النموذج على هذا البنشمارك.'
      : 'لا توجد تشغيلات مكتملة لهذا البنشمارك بعد.';
    return;
  }

  empty.hidden = true;
  figure.hidden = false;
  renderScopeWarning(trackable, warning);
  renderChart(trackable);
  renderTable(trackable);
}

/** تحذير حين تخلط سلسلة نطاقات مختلفة — الفرق قد يكون من العيّنة. */
function renderScopeWarning(series, box) {
  const mixed = series.filter(s => s.mixed_scopes);
  if (!mixed.length) {
    box.hidden = true;
    replaceChildren(box);
    return;
  }
  replaceChildren(box,
    h('strong', {}, '⚠ سلاسل تخلط نطاقات مختلفة'),
    h('div', {},
      mixed.map(s => `${s.provider}/${s.model}`).join('، ')
      + ' — التشغيلات تختلف في عدد المسائل أو الفلاتر، فجزء من الفرق قد يكون من العيّنة لا من النموذج.'),
    h('div', { class: 'muted small' },
      'عمود «التغيّر» يقارن آخر تشغيلين متطابقَي النطاق فقط، ويبقى فارغاً إن لم يوجد نظير.'),
  );
  box.hidden = false;
}

/* ============ المخطّط ============ */

function destroyChart() {
  if (state.driftChart) {
    state.driftChart.destroy();
    state.driftChart = null;
  }
}

function renderChart(series) {
  destroyChart();
  const ctx = document.getElementById('drift-chart').getContext('2d');
  const cMuted = themeColor('--text-muted', '#8a93b0');
  const cGrid = themeColor('--border-soft', '#232944');

  const datasets = series.map((s, i) => {
    const color = seriesColor(i);
    return {
      label: `${s.provider}/${s.model}`,
      data: s.points.map(p => ({ x: p.created_at * 1000, y: +(p.accuracy * 100).toFixed(1) })),
      borderColor: color,
      backgroundColor: color,
      tension: 0.2,
      pointRadius: 4,
      pointHoverRadius: 6,
      // خطّ متقطّع للسلاسل مختلطة النطاق: إشارة بصرية أن الوصل غير مضمون
      borderDash: s.mixed_scopes ? [6, 4] : [],
    };
  });

  state.driftChart = new Chart(ctx, {
    type: 'line',
    data: { datasets },
    options: {
      ...baseChartOptions(),
      parsing: false,
      plugins: {
        ...baseChartOptions().plugins,
        tooltip: {
          callbacks: {
            title: items => formatPointDate(items[0].parsed.x / 1000),
            label: item => `${item.dataset.label}: ${item.parsed.y}%`,
          },
        },
      },
      scales: {
        x: {
          type: 'linear',
          ticks: { color: cMuted, callback: v => formatPointDate(v / 1000) },
          grid: { color: cGrid },
        },
        y: {
          beginAtZero: true, max: 100,
          ticks: { color: cMuted, callback: v => `${v}%` },
          grid: { color: cGrid },
        },
      },
    },
  });
}

/** يُعاد بناء المخطّط عند تبديل المظهر — الألوان تُقرأ من CSS عند البناء فقط. */
export function refreshDriftChartTheme() {
  const trackable = state.driftData?.trackable || [];
  if (state.driftChart && trackable.length) renderChart(trackable);
}

/* ============ الجدول ============ */

function renderTable(series) {
  const headers = ['النموذج', 'التشغيلات', 'أول دقّة', 'آخر دقّة (95% CI)', 'التغيّر', 'المدى', 'النطاق']
    .map(label => h('th', { scope: 'col' }, label));

  const rows = series.map(s => {
    const first = s.points[0];
    const last = s.points[s.points.length - 1];
    const change = s.latest_change;
    const desc = describeChange(change);

    return h('tr', {},
      h('td', {}, `${s.provider}/${s.model}`),
      h('td', {}, String(s.n_runs)),
      h('td', {}, h('bdi', {}, `${(first.accuracy * 100).toFixed(1)}%`)),
      // bdi يعزل الأرقام والإشارات عن اتجاه الفقرة، وإلا عُرض (-37.5) كـ(37.5-)
      h('td', { class: 'score-cell' },
        h('bdi', {}, `${(last.accuracy * 100).toFixed(1)}%`),
        ' ',
        h('bdi', { class: 'ci' }, `±${(last.ci_margin * 100).toFixed(1)}`),
      ),
      h('td', { class: `drift-change drift-${desc.kind}` },
        change
          ? [
              h('span', { 'aria-hidden': 'true' }, `${desc.glyph} `),
              h('bdi', {}, `${change.delta_pct_points > 0 ? '+' : ''}${change.delta_pct_points}`),
            ]
          : '—',
        h('span', { class: 'sr-only' }, ` ${desc.label}`),
      ),
      h('td', { class: 'muted small' },
        change ? h('bdi', {}, `${change.days_apart} يوم`) : '—'),
      h('td', { class: 'muted small' }, last.scope_label),
    );
  });

  const table = h('table', {},
    h('caption', { class: 'muted small' },
      'عمود «التغيّر» بالنقاط المئوية بين آخر تشغيلين متطابقَي النطاق. '
      + 'يُوسم «ذو دلالة» فقط إذا لم يتداخل فاصلا ويلسون — اختبار محافظ يتجنّب '
      + 'الإنذار الكاذب من العيّنات الصغيرة.'),
    h('thead', {}, h('tr', {}, ...headers)),
    h('tbody', {}, ...rows),
  );
  replaceChildren(document.getElementById('drift-table'),
    h('div', { class: 'table-scroll' }, table));
}

/* ============ التهيئة ============ */

export function initDrift() {
  document.getElementById('drift-benchmark').addEventListener('change', loadDrift);
  document.getElementById('drift-include-partial').addEventListener('change', loadDrift);
}

/**
 * البنشمارك الأولى بالعرض: ما اختاره المستخدم، وإلا الأكثر تشغيلاً في سجلّه.
 *
 * كان التبويب يفتح على أوّل خيار في القائمة (humaneval) حتى لو كانت كل
 * التشغيلات على بنشمارك آخر، فيستقبل المستخدم «لا توجد تشغيلات» ولا يعرف أن
 * عليه تغيير القائمة. دالة نقيّة قابلة للاختبار بلا DOM ولا شبكة.
 */
export function pickDefaultBenchmark(runs, available, selected) {
  if (selected && available.includes(selected)) return selected;
  const counts = new Map();
  for (const run of runs || []) {
    if (!available.includes(run.benchmark)) continue;
    counts.set(run.benchmark, (counts.get(run.benchmark) || 0) + 1);
  }
  let best = null;
  let bestCount = 0;
  for (const [benchmark, count] of counts) {
    if (count > bestCount) {
      best = benchmark;
      bestCount = count;
    }
  }
  return best || available[0] || '';
}

/** يملأ قائمة البنشماركات عند فتح التبويب ثم يحمّل البيانات. */
export async function openDriftTab() {
  const select = document.getElementById('drift-benchmark');
  if (!select.options.length && state.benchmarks.length) {
    replaceChildren(select, ...state.benchmarks.map(b =>
      h('option', { value: b.id }, b.name)
    ));
    let runs = [];
    try {
      runs = (await api.runs()).runs || [];
    } catch {
      // السجل غير حرج هنا — نكتفي بما اختاره المستخدم أو بأوّل بنشمارك
    }
    select.value = pickDefaultBenchmark(
      runs, state.benchmarks.map(b => b.id), state.selectedBenchmark,
    );
  }
  loadDrift();
}
