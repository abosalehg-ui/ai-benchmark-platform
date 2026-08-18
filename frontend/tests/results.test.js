/* اختبارات الدوال النقيّة في طبقة النتائج. */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { detailKey, groupByProblem, mergeDetailRows } from '../js/results.js';

const row = (pid, provider, model, extra = {}) =>
  ({ problem_id: pid, provider, model, ...extra });

test('detailKey يميّز نفس المسألة على نماذج مختلفة', () => {
  assert.notEqual(
    detailKey(row('p1', 'openai', 'gpt-5-mini')),
    detailKey(row('p1', 'anthropic', 'claude-opus-5')),
  );
  assert.equal(
    detailKey(row('p1', 'openai', 'gpt-5-mini')),
    detailKey(row('p1', 'openai', 'gpt-5-mini', { correct: true })),
  );
});

test('mergeDetailRows لا يكرّر صفّاً محمّلاً', () => {
  const first = mergeDetailRows([], [row('p1', 'openai', 'm'), row('p2', 'openai', 'm')]);
  assert.equal(first.length, 2);

  // نفس الصفحة تصل مرّتين (المستخدم فتح التفاصيل ثم المقارنة)
  const second = mergeDetailRows(first, [row('p1', 'openai', 'm'), row('p3', 'openai', 'm')]);
  assert.equal(second.length, 3);
  assert.deepEqual(second.map(d => d.problem_id), ['p1', 'p2', 'p3']);
});

test('mergeDetailRows لا يعدّل القائمة الأصلية', () => {
  const original = [row('p1', 'openai', 'm')];
  const merged = mergeDetailRows(original, [row('p2', 'openai', 'm')]);
  assert.equal(original.length, 1);
  assert.equal(merged.length, 2);
});

test('groupByProblem يجمع كل النماذج تحت المسألة نفسها', () => {
  const grouped = groupByProblem([
    row('p1', 'openai', 'a'), row('p1', 'anthropic', 'b'), row('p2', 'openai', 'a'),
  ]);
  assert.deepEqual(Object.keys(grouped), ['p1', 'p2']);
  assert.equal(grouped.p1.length, 2);
  assert.equal(grouped.p2.length, 1);
});

test('groupByProblem يرجع كائناً فارغاً لقائمة فارغة', () => {
  assert.deepEqual(groupByProblem([]), {});
});
