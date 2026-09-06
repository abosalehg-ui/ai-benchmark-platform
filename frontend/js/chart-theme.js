/* ألوان المخطّطات وخياراتها المشتركة.

   كانت `themeColor` منسوخة حرفياً في results.js و drift.js، ومعها كتلة خيارات
   Chart.js (الحركة المعطّلة عند prefers-reduced-motion، ألوان المحاور والشبكة).
   تغيير لون واحد كان يحتاج تعديلين متطابقين — وهو بالضبط ما يجعلهما يتباعدان.

   الألوان تُقرأ من متغيّرات CSS عند البناء لا عند التعريف، فتبديل المظهر يحتاج
   إعادة بناء المخطّط (لذلك يوجد refreshChartTheme في كل وحدة). */

/** يقرأ متغيّر CSS من الجذر مع قيمة احتياطية. */
export function themeColor(name, fallback) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

/** ألوان السلاسل بالترتيب — تتبدّل مع المظهر الفاتح/الداكن. */
export const SERIES_VARS = ['--primary', '--success', '--accent', '--danger', '--warning'];

/** لون السلسلة رقم i (يلتفّ عند تجاوز عدد الألوان). */
export function seriesColor(i) {
  return themeColor(SERIES_VARS[i % SERIES_VARS.length], '#5b8def');
}

/**
 * الخيارات المشتركة لكل مخطّطات المنصّة: تجاوب، احترام تفضيل تقليل الحركة،
 * وألوان نصّ وشبكة من المظهر الحالي.
 */
export function baseChartOptions() {
  const cText = themeColor('--text', '#e8ecf5');
  const cMuted = themeColor('--text-muted', '#8a93b0');
  const cGrid = themeColor('--border-soft', '#232944');
  return {
    responsive: true,
    animation: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? false : undefined,
    plugins: { legend: { labels: { color: cText } } },
    scales: {
      y: { beginAtZero: true, max: 100, ticks: { color: cMuted }, grid: { color: cGrid } },
      x: { ticks: { color: cMuted }, grid: { color: cGrid } },
    },
  };
}
