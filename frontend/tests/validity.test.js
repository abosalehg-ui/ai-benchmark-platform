/* اختبارات الدوال النقيّة المضافة في دفعة إصلاح مراجعة مِحَك 2026-09. */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { describeStatus, readBaselines } from '../js/results.js';
import { pickDefaultBenchmark } from '../js/drift.js';
import { preferredTheme } from '../js/state.js';

/* ============ حالات السجل ============ */

test('كل حالة تشغيل لها نصّ عربي ولون يفرّقها', () => {
  const statuses = [
    'completed', 'completed_with_errors', 'running',
    'aborted_budget', 'aborted_disconnect', 'failed',
  ];
  const labels = statuses.map(s => describeStatus(s).label);
  assert.equal(new Set(labels).size, statuses.length, 'نصوص متكرّرة');
  for (const label of labels) assert.ok(!/^[a-z_]+$/.test(label), `نصّ خام: ${label}`);
});

test('«قيد التشغيل» ليست فشلاً', () => {
  // كانت كل حالة غير completed تُعرض بشارة حمراء
  assert.notEqual(describeStatus('running').badge, 'error');
  assert.notEqual(describeStatus('aborted_budget').badge, 'error');
  assert.equal(describeStatus('completed').badge, 'success');
  assert.equal(describeStatus('failed').badge, 'error');
});

test('حالة غير معروفة لا تكسر العرض', () => {
  const meta = describeStatus('something_new');
  assert.equal(meta.label, 'something_new');
  assert.ok(meta.badge);
});

/* ============ خطّ الأساس ============ */

test('خطّ الأساس يُقرأ من config المحفوظ مع الـrun', () => {
  const run = { config_json: JSON.stringify({ baselines: { n: 5, majority_letter: 'ب' } }) };
  assert.equal(readBaselines(run).majority_letter, 'ب');
});

test('config تالف أو غائب لا يُسقط الملخّص', () => {
  assert.equal(readBaselines({ config_json: '{{{' }), null);
  assert.equal(readBaselines({}), null);
  assert.equal(readBaselines(null), null);
  assert.equal(readBaselines({ config_json: '{}' }), null);
});

/* ============ بنشمارك الانحراف الافتراضي ============ */

test('يفتح على البنشمارك الأكثر تشغيلاً لا على أوّل خيار أبجدياً', () => {
  const runs = [
    { benchmark: 'saudi_legal' }, { benchmark: 'saudi_legal' }, { benchmark: 'gsm8k' },
  ];
  assert.equal(pickDefaultBenchmark(runs, ['humaneval', 'gsm8k', 'saudi_legal'], null), 'saudi_legal');
});

test('اختيار المستخدم في تبويب التشغيل يسبق إحصاء السجل', () => {
  const runs = [{ benchmark: 'saudi_legal' }, { benchmark: 'saudi_legal' }];
  assert.equal(pickDefaultBenchmark(runs, ['gsm8k', 'saudi_legal'], 'gsm8k'), 'gsm8k');
});

test('سجل فارغ يرجع لأوّل بنشمارك متاح بدل قيمة فارغة', () => {
  assert.equal(pickDefaultBenchmark([], ['humaneval', 'gsm8k'], null), 'humaneval');
  assert.equal(pickDefaultBenchmark(null, ['humaneval'], null), 'humaneval');
  assert.equal(pickDefaultBenchmark([], [], null), '');
});

test('تشغيلات لبنشمارك لم يعد موجوداً تُتجاهل', () => {
  const runs = [{ benchmark: 'removed_bench' }, { benchmark: 'gsm8k' }];
  assert.equal(pickDefaultBenchmark(runs, ['humaneval', 'gsm8k'], null), 'gsm8k');
});

/* ============ المظهر ============ */

test('تفضيل النظام يُحترم في أوّل زيارة', () => {
  assert.equal(preferredTheme(null, true), 'light');
  assert.equal(preferredTheme(null, false), 'dark');
});

test('اختيار المستخدم المحفوظ يسبق تفضيل النظام', () => {
  assert.equal(preferredTheme('dark', true), 'dark');
  assert.equal(preferredTheme('light', false), 'light');
});

test('قيمة محفوظة تالفة لا تُطبَّق', () => {
  assert.equal(preferredTheme('neon', true), 'light');
});
