/* メーカーキャリアラボ GA4 event instrumentation (v3.30)
 * 集計目的以外に利用しない。企業名、フォーム内容、個人情報は送信しない。
 */
(function () {
  'use strict';
  if (window.__mclGa4EventsAttached) return;
  window.__mclGa4EventsAttached = true;

  function record(eventName, params) {
    if (typeof window.gtag !== 'function') return;
    window.gtag('event', eventName, params || {});
  }

  // リンク操作のイベントを取得。A8の href・画像・広告コードは変更しない。
  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || typeof target.closest !== 'function') return;
    var link = target.closest('a[href]');
    if (!link) return;
    var href = link.getAttribute('href') || '';
    var url;
    try { url = new URL(href, window.location.href); }
    catch (_e) { return; }

    if (url.hostname === 'px.a8.net' && url.pathname.startsWith('/svt/ejp')) {
      var program = 'other';
      var code = url.searchParams.get('a8mat') || '';
      if (code.indexOf('6Z8ZLU') !== -1) program = 'factory_jobs';
      else if (code.indexOf('7JHQ6A') !== -1) program = 'science_students';
      record('affiliate_click', {
        affiliate_network: 'a8',
        affiliate_program: program,
        source_page: window.location.pathname
      });
      return;
    }
    // 企業比較ページへ進む記事リンクの利用回数
    if (url.origin === window.location.origin && /\/company-check\.html$/.test(url.pathname) &&
        !/\/company-check\.html$/.test(window.location.pathname)) {
      record('company_compare_link_click', {source_page: window.location.pathname});
    }
  });

  // 比較画面の結果が表示された場合のみ計測する。会社名・入力値は送信しない。
  document.addEventListener('submit', function (event) {
    if (!event.target || event.target.id !== 'compare-form') return;
    var result = document.getElementById('results');
    if (result && !result.hidden) {
      record('company_compare_complete', {tool: 'company_check'});
    }
  });
})();
