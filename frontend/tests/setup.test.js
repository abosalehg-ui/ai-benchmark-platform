/* اختبارات قصّ عدد المسائل — المتصفّح لا يفرض max على القيم المكتوبة. */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { clampProblemCount } from '../js/setup.js';

test('يقصّ فوق الحدّ الأقصى للخادم', () => {
  assert.equal(clampProblemCount('9999', 200), 200);
});

test('يرفع ما دون الواحد', () => {
  assert.equal(clampProblemCount('0', 200), 1);
  assert.equal(clampProblemCount('-7', 200), 1);
});

test('يمرّر قيمة صالحة كما هي', () => {
  assert.equal(clampProblemCount('42', 200), 42);
});

test('يرجع الافتراضي لقيمة غير رقمية أو فارغة', () => {
  assert.equal(clampProblemCount('', 200), 5);
  assert.equal(clampProblemCount('abc', 200), 5);
  assert.equal(clampProblemCount(null, 200), 5);
  assert.equal(clampProblemCount(undefined, 200), 5);
});

test('الافتراضي نفسه لا يتجاوز الحدّ', () => {
  assert.equal(clampProblemCount('', 3), 3);
});

test('يقبل أرقاماً بمسافات زائدة', () => {
  assert.equal(clampProblemCount(' 12 ', 200), 12);
});
