/* اختبار دخان في متصفّح حقيقي (Chromium عبر Playwright).

   لماذا هذا الملف موجود: مراجعة 2026-09 وجدت أن مخطّط الدقّة **لا يظهر
   إطلاقاً** عند فتح تشغيل من السجل — الـcanvas كان داخل عنصر مخفيّ فارتفاعه
   صفر. لا اختبار وحدة يمسك ذلك: الدوال كلها تعمل، والـDOM يُبنى، والشيء
   الوحيد الخاطئ هو أن أحداً لا يراه. لذلك تفحص هذه الاختبارات ما **يُرى**
   فعلاً في متصفّح، لا ما تُرجعه الدوال.

   يحتاج خادماً يعمل على BASE_URL وفيه **تشغيلان** على الأقل — فحص الانحراف
   لا يُظهر شيئاً بأقلّ من تشغيلين لنفس (البنشمارك، النموذج). سكربت الزرع
   ينشئهما:
       python scripts/seed_demo_run.py
       uvicorn backend.main:app --port 8000 &
       node frontend/tests/smoke.mjs

   SMOKE_CHROMIUM=/path/to/chromium يتخطّى تنزيل نسخة Playwright.
*/
import assert from 'node:assert/strict';
import { chromium } from 'playwright';

const BASE_URL = process.env.SMOKE_BASE_URL || 'http://localhost:8000';
/* SMOKE_CHROMIUM: مسار متصفّح جاهز، لمن لا يريد تنزيل نسخة Playwright. */
const LAUNCH = process.env.SMOKE_CHROMIUM ? { executablePath: process.env.SMOKE_CHROMIUM } : {};
const results = [];

async function check(name, fn) {
  try {
    await fn();
    results.push({ name, ok: true });
    console.log(`  ok   ${name}`);
  } catch (e) {
    results.push({ name, ok: false, error: e.message });
    console.log(`  FAIL ${name}\n       ${e.message}`);
  }
}

const browser = await chromium.launch(LAUNCH);

async function newPage(options = {}) {
  const page = await (await browser.newContext(options)).newPage();
  page.consoleErrors = [];
  page.on('console', m => { if (m.type() === 'error') page.consoleErrors.push(m.text()); });
  page.on('pageerror', e => page.consoleErrors.push(String(e)));
  return page;
}

/* ============ سطح المكتب ============ */

const page = await newPage({ viewport: { width: 1400, height: 900 } });
await page.goto(BASE_URL, { waitUntil: 'networkidle' });

await check('الصفحة تُحمّل بلا أخطاء console', () => {
  assert.deepEqual(page.consoleErrors, [], page.consoleErrors.join(' | '));
});

await check('بطاقات البنشمارك تظهر', async () => {
  const n = await page.locator('.bench-card').count();
  assert.ok(n > 0, 'لا توجد بطاقات بنشمارك');
});

await page.click('.tab[data-tab="history"]');
await page.waitForSelector('.history-row', { timeout: 10000 });

await check('شارة الحالة بالعربية لا بالنصّ الخام', async () => {
  const label = await page.locator('.history-row .badge').first().textContent();
  assert.ok(!/^[a-z_]+$/.test(label.trim()), `شارة بنصّ خام: ${label}`);
});

await page.locator('.history-row .history-open').first().click();
await page.waitForSelector('#run-summary:not(.hidden)', { timeout: 10000 });

await check('مخطّط الدقّة مرئي فعلاً عند فتح تشغيل من السجل', async () => {
  // ننتظر الحجم الفعلي لا مهلة ثابتة: Chart.js يضبط أبعاد الـcanvas بعد
  // الإدراج، فالقياس الفوري يعطي ارتفاعاً وسيطاً (~27px) لا صفراً ولا نهائياً
  try {
    await page.waitForFunction(() => {
      const c = document.getElementById('results-chart');
      return c && c.offsetParent !== null && c.getBoundingClientRect().height > 40;
    }, { timeout: 10000 });
  } catch {
    const box = await page.evaluate(() => {
      const c = document.getElementById('results-chart');
      return { visible: c.offsetParent !== null, height: Math.round(c.getBoundingClientRect().height) };
    });
    assert.fail(box.visible
      ? `المخطّط مرئي لكن ارتفاعه بقي ${box.height}px`
      : 'الـcanvas داخل عنصر مخفيّ — هذا هو العطل الذي وُجد في مراجعة 2026-09');
  }
});

await check('جدول الملخّص فيه صفوف', async () => {
  assert.ok(await page.locator('#summary-table tbody tr').count() > 0);
});

await check('خطّ أساس التخمين معروض مع النتائج', async () => {
  const hidden = await page.locator('#summary-baseline').isHidden();
  assert.equal(hidden, false, 'خطّ الأساس مخفيّ — الرقم بلا سياق يضلّل');
  const text = await page.locator('#summary-baseline').textContent();
  assert.match(text, /أطول خيار/);
});

await page.click('.tab[data-tab="drift"]');
await page.waitForTimeout(1500);

await check('تبويب الانحراف يفتح على بنشمارك فيه بيانات', async () => {
  const empty = await page.locator('#drift-empty').isVisible();
  const rows = await page.locator('#drift-table tbody tr').count();
  const selected = await page.locator('#drift-benchmark').inputValue();
  assert.equal(empty, false, `فُتح على «${selected}» بلا تشغيلات`);
  assert.ok(rows > 0, `لا صفوف في جدول الانحراف لـ«${selected}»`);
});

await check('لا أخطاء console بعد التنقّل الكامل', () => {
  assert.deepEqual(page.consoleErrors, [], page.consoleErrors.join(' | '));
});

/* ============ الجوّال ============ */

const mobile = await newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
await mobile.goto(BASE_URL, { waitUntil: 'networkidle' });

await check('لا تمرير أفقي عند 390px', async () => {
  const { scrollW, innerW } = await mobile.evaluate(() => ({
    scrollW: document.documentElement.scrollWidth, innerW: window.innerWidth,
  }));
  assert.ok(scrollW <= innerW, `عرض التمرير ${scrollW} > ${innerW}`);
});

await check('أهداف اللمس التفاعلية لا تقلّ عن 24px', async () => {
  const small = await mobile.evaluate(() => [...document.querySelectorAll('button, select, input')]
    .filter(el => el.offsetParent !== null)
    .map(el => {
      const r = el.getBoundingClientRect();
      return { name: (el.textContent || el.id || el.name || '').trim().slice(0, 24), h: Math.round(r.height) };
    })
    .filter(x => x.h > 0 && x.h < 24));
  assert.deepEqual(small, [], JSON.stringify(small));
});

await browser.close();

const failed = results.filter(r => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} نجح`);
if (failed.length) process.exit(1);
