/* إعداد ESLint مسطّح (flat config) — بلا اعتماديات مثبّتة في المستودع.
   يُشغَّل في CI عبر `npx --yes eslint@9`.

   الهدف الأساسي: إمساك الكود الميت والمراجع غير المعرَّفة. هذان بالضبط ما
   نجا منهما `escapeHtml` الميتة والـ CSS الميت — أدوات بايثون كانت تفحص
   backend/ بينما 2,684 سطر واجهة بلا أي فاحص. */
export default [
  {
    files: ['js/**/*.js', 'tests/**/*.js'],
    languageOptions: {
      ecmaVersion: 2023,
      sourceType: 'module',
      globals: {
        // متصفّح
        document: 'readonly', window: 'readonly', navigator: 'readonly',
        localStorage: 'readonly', fetch: 'readonly', console: 'readonly',
        setTimeout: 'readonly', clearTimeout: 'readonly', confirm: 'readonly',
        CSS: 'readonly', TextDecoder: 'readonly', TextEncoder: 'readonly',
        URL: 'readonly', URLSearchParams: 'readonly', Node: 'readonly',
        getComputedStyle: 'readonly', matchMedia: 'readonly',
        ReadableStream: 'readonly',
        // Chart.js محمّل عبر <script> من frontend/vendor
        Chart: 'readonly',
      },
    },
    rules: {
      'no-undef': 'error',
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      'no-implicit-globals': 'error',
      'no-var': 'error',
      'prefer-const': 'error',
      eqeqeq: ['error', 'smart'],
    },
  },
];
