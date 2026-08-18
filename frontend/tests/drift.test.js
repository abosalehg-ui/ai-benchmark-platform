/* اختبارات الدوال النقيّة في تتبّع الانحراف — بلا DOM. */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { describeChange, formatPointDate } from '../js/drift.js';

test('غياب المقارنة يُعرض بلا سهم اتجاه', () => {
  const d = describeChange(null);
  assert.equal(d.kind, 'none');
  assert.equal(d.glyph, '—');
});

test('انخفاض ذو دلالة يُوسم هبوطاً', () => {
  const d = describeChange({ delta_pct_points: -37.5, significant: true });
  assert.equal(d.kind, 'down');
  assert.equal(d.glyph, '▼');
  assert.match(d.label, /انخفاض 37\.5 نقطة/);
  assert.match(d.label, /ذو دلالة/);
});

test('ارتفاع ذو دلالة يُوسم صعوداً', () => {
  const d = describeChange({ delta_pct_points: 12, significant: true });
  assert.equal(d.kind, 'up');
  assert.equal(d.glyph, '▲');
  assert.match(d.label, /ارتفاع 12 نقطة/);
});

test('فرق غير ذي دلالة يُوسم تقلّب عيّنة لا انحرافاً', () => {
  // هذا جوهر الميزة: إنذار كاذب يدفع المستخدم لتغيير نموذج بلا سبب
  const d = describeChange({ delta_pct_points: -20, significant: false });
  assert.equal(d.kind, 'noise');
  assert.match(d.label, /ضمن تقلّب العيّنة/);
  assert.doesNotMatch(d.label, /ذو دلالة/);
});

test('صفر تغيّر لا يُعرض سهماً', () => {
  const d = describeChange({ delta_pct_points: 0, significant: false });
  assert.equal(d.kind, 'flat');
  assert.equal(d.glyph, '=');
});

test('اللون وحده لا يحمل المعنى — لكل حالة رمز مميّز', () => {
  const glyphs = [
    describeChange({ delta_pct_points: 5, significant: true }).glyph,
    describeChange({ delta_pct_points: -5, significant: true }).glyph,
    describeChange({ delta_pct_points: 0, significant: false }).glyph,
    describeChange(null).glyph,
  ];
  assert.equal(new Set(glyphs).size, glyphs.length);
});

test('التاريخ ميلادي بأرقام لاتينية لا هجري', () => {
  // 'ar-SA' وحده يُفعّل التقويم الهجري في Intl فتختلف التواريخ عن ملفات التصدير
  const label = formatPointDate(1750000000);
  assert.match(label, /\d/, `لا أرقام لاتينية في: ${label}`);
  assert.doesNotMatch(label, /هـ/);
});
