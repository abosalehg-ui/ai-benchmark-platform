/* أدوات DOM مشتركة: بناء عناصر بأمان، toast، ومودال قابل للوصول. */

/**
 * بناء عنصر. النصوص تُضاف عبر textContent فلا يمكن حقن HTML منها إطلاقاً —
 * هذا يحلّ محلّ بناء السلاسل بـ innerHTML الذي كان مصدر ثغرة XSS المخزَّنة.
 *
 * ملاحظة: لا توجد دالة تهريب في هذه الوحدة عمداً. وجودها كان يوحي بأن هناك
 * مسار بناء HTML نصّي ما زال يحتاجها — ولا يوجد: كل بناء يمرّ من هنا.
 */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : String(v));
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

/** استبدل محتوى عنصر بعناصر جديدة (بديل آمن لـ innerHTML = '...'). */
export function replaceChildren(target, ...children) {
  target.replaceChildren(...children.flat().filter(c => c != null && c !== false));
}

/* ============ Toast ============ */

const TOAST_ICONS = { success: '✓', error: '⚠', info: 'ℹ' };

export function showToast(msg, kind = 'success') {
  let t = document.getElementById('toast');
  if (!t) {
    t = h('div', { id: 'toast', class: 'toast', role: 'status', 'aria-live': 'polite' });
    document.body.appendChild(t);
  }
  t.className = `toast toast-${kind}`;
  t.textContent = `${TOAST_ICONS[kind] || ''} ${msg}`.trim();
  t.classList.add('toast-visible');
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.classList.remove('toast-visible'), kind === 'error' ? 6000 : 2400);
}

/** لافتة خطأ ثابتة أعلى الصفحة — للأعطال التي تمنع الاستخدام. */
export function showBanner(msg) {
  let b = document.getElementById('app-banner');
  if (!b) {
    b = h('div', { id: 'app-banner', class: 'app-banner', role: 'alert' });
    document.querySelector('main').prepend(b);
  }
  b.textContent = msg;
  b.hidden = false;
}

export function hideBanner() {
  const b = document.getElementById('app-banner');
  if (b) b.hidden = true;
}

/* ============ Modal قابل للوصول ============ */

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, details, [tabindex]:not([tabindex="-1"])';

let lastFocused = null;

function trapFocus(e) {
  const modal = document.getElementById('details-modal');
  if (modal.classList.contains('hidden') || e.key !== 'Tab') return;
  const items = [...modal.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
}

export function openModal(titleText) {
  const modal = document.getElementById('details-modal');
  lastFocused = document.activeElement;
  modal.classList.remove('hidden');
  document.body.classList.add('modal-open'); // يقفل تمرير الصفحة خلف المودال
  const heading = document.getElementById('modal-title');
  if (heading && titleText) heading.textContent = titleText;
  // التركيز على زر الإغلاق: نقطة بداية متوقّعة لمستخدم لوحة المفاتيح
  document.getElementById('modal-close').focus();
}

export function closeModal() {
  const modal = document.getElementById('details-modal');
  if (modal.classList.contains('hidden')) return;
  modal.classList.add('hidden');
  document.body.classList.remove('modal-open');
  if (lastFocused && document.contains(lastFocused)) lastFocused.focus();
  lastFocused = null;
}

export function initModal() {
  const modal = document.getElementById('details-modal');
  document.getElementById('modal-close').addEventListener('click', closeModal);
  // النقر على الخلفية (لا على المحتوى) يغلق
  modal.addEventListener('mousedown', e => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeModal();
    else trapFocus(e);
  });
}

/** جسم المودال — مكان كتابة المحتوى. */
export function modalBody() {
  return document.getElementById('modal-body');
}
