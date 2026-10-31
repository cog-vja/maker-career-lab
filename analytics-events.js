/* メーカーキャリアラボ GA4 events + related-reading navigation (v3.31)
 * - Existing GA4 event names and A8 tracking preserved.
 * - All analytics omit company names, free-form inputs and personal data.
 * - Add editorial links without rewriting existing article bodies or ad placements.
 */
(function () {
  'use strict';
  if (window.__mclGa4EventsAttached) return;
  window.__mclGa4EventsAttached = true;

  function record(eventName, params) {
    if (typeof window.gtag !== 'function') return;
    window.gtag('event', eventName, params || {});
  }

  // Link click collection: do not modify A8 hrefs, banner images, or attribution parameters.
  document.addEventListener('click', function (event) {
    var target = event.target;
    if (!target || typeof target.closest !== 'function') return;
    if (target.closest('#demo') && /\/company-check\.html$/.test(window.location.pathname)) {
      record('company_compare_demo_click', { tool: 'company_check' });
    }
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
    if (url.origin === window.location.origin && /\/company-check\.html$/.test(url.pathname) &&
        !/\/company-check\.html$/.test(window.location.pathname)) {
      record('company_compare_link_click', { source_page: window.location.pathname });
      record('mcl_article_to_tool_click', { source_page: window.location.pathname });
    }
  });

  // The compare-form handler in company-compare.js runs on the form target,
  // before this bubbling listener on document. Confirm the actual result/status
  // instead of counting an old visible result after an invalid submit.
  document.addEventListener('submit', function (event) {
    if (!event.target || event.target.id !== 'compare-form') return;
    record('company_compare_start', { tool: 'company_check' });
    var result = document.getElementById('results');
    var label = document.getElementById('result-label');
    var status = document.getElementById('status');
    var good = result && !result.hidden && label &&
      label.textContent === '公開財務データによる参考比較' &&
      status && status.textContent.indexOf('掲載データによる参考比較です。') === 0;
    if (good) {
      record('company_compare_complete', { tool: 'company_check' });
    } else {
      record('company_compare_validation_error', { tool: 'company_check' });
    }
  });

  function onReady(fn) {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', fn);
    else fn();
  }
  function createLink(path, caption) {
    var a = document.createElement('a');
    a.href = path;
    a.textContent = caption;
    return a;
  }
  function addRelatedHeadingLinks() {
    // Pair 5 original explanatory articles with 5 newer hands-on guides.
    // They serve different search intents, so do not replace their canonicals.
    var pairs = {
      'salary-market.html': ['年収と市場を具体的に比較する実践ガイド',
        '市場・企業・職種・個人の4階層を整理する基礎記事'],
      'manufacturer-profit.html': ['収益力のあるメーカーを見極める5つの問い',
        '利益率と給与の関係・財務指標の基本を解説する記事'],
      'industry-compare.html': ['業界を変えてスキルを活かす実践ワーク',
        '半導体・自動車・食品の収益構造を整理する基礎記事'],
      'it-scm-career.html': ['スキルの棚卸しワークシート',
        '社内SE・SCMの職務経歴書に使える基礎記事'],
      'agent-guide.html': ['転職相談前に希望条件を整理するガイド',
        'メーカー向け転職サービスの選び方を確認する記事']
    };
    var path = window.location.pathname;
    var m = path.match(/\/(articles\/)?(salary-market|manufacturer-profit|industry-compare|it-scm-career|agent-guide)\.html$/);
    if (!m) return;
    var original = m[2] + '.html';
    var inArticles = !!m[1];
    var h2s = document.querySelectorAll('h2');
    var heading = null;
    for (var i = 0; i < h2s.length; i++) {
      if ((h2s[i].textContent || '').trim() === '関連記事') { heading = h2s[i]; break; }
    }
    if (!heading || !heading.parentNode || document.getElementById('mcl-stage2-related')) return;

    var paragraph = document.createElement('p');
    paragraph.id = 'mcl-stage2-related';
    paragraph.className = 'muted';
    paragraph.appendChild(document.createTextNode(inArticles ? 'さらに基礎から読む：' : '実践ガイド：'));
    paragraph.appendChild(createLink(inArticles ? '../' + original : 'articles/' + original,
      pairs[original][inArticles ? 1 : 0]));
    paragraph.appendChild(document.createTextNode('。記事ごとに扱う情報と判断の目的が異なります。'));

    // The two new sector analyses are additional examples, not a replacement for general guides.
    if (original === 'industry-compare.html' || original === 'manufacturer-profit.html') {
      paragraph.appendChild(document.createTextNode(' 企業別データ：'));
      paragraph.appendChild(createLink(inArticles ? 'semiconductor-equipment-salary-profit.html' : 'articles/semiconductor-equipment-salary-profit.html',
        '半導体装置・検査関連9社'));
      paragraph.appendChild(document.createTextNode('／'));
      paragraph.appendChild(createLink(inArticles ? 'auto-parts-salary-profit.html' : 'articles/auto-parts-salary-profit.html',
        '自動車部品4社'));
    }
    heading.parentNode.insertBefore(paragraph, heading);
  }

  function addHomepageArticles() {
    var list = document.querySelector('#articles .article-list');
    if (!list || document.getElementById('mcl-stage2-article-semi')) return;
    var entries = [
      ['mcl-stage2-article-semi', 'articles/semiconductor-equipment-salary-profit.html',
        '半導体関連・企業比較', '半導体製造装置・検査関連9社の平均年収と営業利益率',
        'ディスコ・東京エレクトロンなどを比較。単体給与と連結利益率の違いも解説。'],
      ['mcl-stage2-article-auto', 'articles/auto-parts-salary-profit.html',
        '自動車部品・企業比較', '自動車部品メーカー4社の年収・利益率を比較',
        'デンソー・アイシン・豊田合成・小糸製作所を比較し、仕事選びの視点を整理。']
    ];
    entries.forEach(function (it) {
      var a = createLink(it[1], ''); a.id = it[0]; a.className = 'article-tile';
      var tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = it[2];
      var h = document.createElement('h3'); h.textContent = it[3];
      var p = document.createElement('p'); p.textContent = it[4];
      a.appendChild(tag); a.appendChild(h); a.appendChild(p); list.appendChild(a);
    });
    var heading = document.querySelector('#articles h2');
    if (heading && heading.textContent.indexOf('7つのキャリア') !== -1)
      heading.textContent = heading.textContent.replace('7つのキャリア', '9つのキャリア');
  }
  onReady(function () {
    addRelatedHeadingLinks();
    addHomepageArticles();
    // Missing data or a blocked data script should never be counted as a successful comparison.
    if (/\/company-check\.html$/.test(window.location.pathname) &&
        (!Array.isArray(window.MCL_COMPANIES) || window.MCL_COMPANIES.length === 0)) {
      record('mcl_data_load_error', { tool: 'company_check' });
    }
  });
})();
