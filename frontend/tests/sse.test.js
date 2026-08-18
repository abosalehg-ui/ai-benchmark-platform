/* اختبارات محلّل SSE — لا يحتاج DOM ولا متصفّحاً. */
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { readSSE } from '../js/sse.js';

/** يبني قارئاً من قطع نصّية كما تصل من الشبكة (قد تنقسم في منتصف الحدث). */
function readerFrom(chunks) {
  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    start(controller) {
      for (const c of chunks) controller.enqueue(encoder.encode(c));
      controller.close();
    },
  });
  return stream.getReader();
}

async function collect(chunks) {
  const out = [];
  for await (const ev of readSSE(readerFrom(chunks))) out.push(ev);
  return out;
}

test('يحلّل أحداثاً كاملة', async () => {
  const events = await collect([
    'event: start\ndata: {"run_id":"a1","total_calls":4}\n\n',
    'event: progress\ndata: {"i":1,"correct":true}\n\n',
  ]);
  assert.equal(events.length, 2);
  assert.equal(events[0].event, 'start');
  assert.equal(events[0].data.run_id, 'a1');
  assert.equal(events[1].data.correct, true);
});

test('يتعامل مع حدث منقسم بين قطعتين', async () => {
  // الشبكة لا تحترم حدود الأحداث — القطع قد تنقسم في أي بايت
  const events = await collect([
    'event: progress\ndata: {"i":',
    '1,"model":"m"}\n\n',
  ]);
  assert.equal(events.length, 1);
  assert.deepEqual(events[0].data, { i: 1, model: 'm' });
});

test('يجمع أحداثاً متعددة في قطعة واحدة', async () => {
  const events = await collect([
    'event: a\ndata: {"n":1}\n\nevent: b\ndata: {"n":2}\n\n',
  ]);
  assert.deepEqual(events.map(e => e.event), ['a', 'b']);
});

test('يتجاهل حزمة تالفة بلا إسقاط البثّ', async () => {
  const events = await collect([
    'event: bad\ndata: {ليس JSON\n\n',
    'event: good\ndata: {"ok":true}\n\n',
  ]);
  assert.equal(events.length, 1);
  assert.equal(events[0].event, 'good');
});

test('يتجاهل كتلة بلا event أو بلا data', async () => {
  const events = await collect([': تعليق فقط\n\n', 'data: {"x":1}\n\n']);
  assert.equal(events.length, 0);
});

test('يحافظ على النصّ العربي', async () => {
  const events = await collect(['event: error\ndata: {"error":"لا توجد مسائل"}\n\n']);
  assert.equal(events[0].data.error, 'لا توجد مسائل');
});

test('يتجاهل بقايا غير مكتملة عند انتهاء البثّ', async () => {
  const events = await collect(['event: a\ndata: {"n":1}\n\nevent: b\ndata: {"n":2}']);
  assert.equal(events.length, 1);
});
