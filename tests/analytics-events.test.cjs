const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

const script = readFileSync(join(__dirname, '../dist/analytics-events.js'), 'utf8');

function openPage(path) {
  const events = [];
  const parameters = [];
  const listeners = new Map();
  const window = {
    location: new URL(path, 'https://maker-career-lab.com/'),
    gtag(command, name, params) {
      if (command === 'event') {
        events.push(name);
        parameters.push(JSON.parse(JSON.stringify(params)));
      }
    },
  };
  const document = {
    readyState: 'interactive',
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  runInNewContext(script, { document, URL, window });
  return { events, parameters, listeners, window };
}

test('data load check waits for deferred company data', () => {
  const page = openPage('/company-check');
  assert.deepEqual(page.events, []);
  page.window.MCL_COMPANIES = [{}];
  page.listeners.get('DOMContentLoaded')();
  assert.deepEqual(page.events, []);
});

function click(page, href, cta = null, placement = null) {
  const link = {
    getAttribute: (attr) => ({ href, 'data-mcl-cta': cta })[attr],
    closest: (selector) => selector === placement ? link : null,
  };
  page.listeners.get('click')({
    target: { closest: (selector) => selector === 'a[href]' ? link : null },
  });
}

test('phase 1 CTA classifications are allowlisted and do not pass query strings', () => {
  const path = '/articles/production-management-career';
  const page = openPage(path + '?private=input');
  click(page, '../company-check', 'compare_tool');
  click(page, 'manufacturer-engineer-agent-selection#mcl-makersjob', 'service_guide');
  click(page, 'https://example.test/articles/manufacturer-engineer-agent-selection', 'service_guide');
  assert.deepEqual(page.events, [
    'company_compare_link_click', 'mcl_article_to_tool_click', 'mcl_funnel_action',
  ]);
  assert.deepEqual(page.parameters, [
    { source_page: path, cta_type: 'compare_tool' },
    { source_page: path, cta_type: 'compare_tool' },
    { source_page: path, cta_type: 'service_guide', content_group: 'career_decision',
      funnel_action: 'phase1_service_guide' },
  ]);
});

test('affiliate click records only the program and fixed placement, once', () => {
  const url = 'https://px.a8.net/svt/ejp?a8mat=4BEHXF+78RXAA+test';
  for (const [path, selector, placement] of [
    ['/company-check', null, 'compare_page'],
    ['/articles/agent-guide', 'article', 'article_inline'],
    ['/articles/it-scm-career', '#mcl-onecareer-floating', 'floating'],
  ]) {
    const page = openPage(path);
    click(page, url, null, selector);
    assert.deepEqual(page.events, ['affiliate_click']);
    assert.deepEqual(page.parameters, [{
      affiliate_network: 'a8', affiliate_program: 'onecareer',
      affiliate_placement: placement, source_page: path,
    }]);
  }
});

test('a failed company data load still emits an error', () => {
  const page = openPage('/company-check');
  page.listeners.get('DOMContentLoaded')?.();
  assert.deepEqual(page.events, ['mcl_data_load_error']);
});

test('related article click counts one internal navigation and omits query strings', () => {
  const page = openPage('/articles/quality-assurance-career?query=synthetic');
  click(page, '/articles/procurement-career?input=synthetic#work', 'article_related');
  click(page, '/articles/quality-assurance-career#work', 'article_related');
  click(page, 'https://example.test/articles/procurement-career', 'article_related');
  click(page, '/articles/procurement-career');
  assert.deepEqual(page.events, ['mcl_article_related_click']);
  assert.deepEqual(page.parameters, [{
    source_page: '/articles/quality-assurance-career', target_article: '/articles/procurement-career',
  }]);
});

test('article-to-tool click counts only article sources', () => {
  for (const [source, target, isArticle] of [
    ['/', '/company-check', false],
    ['/about', '/company-check', false],
    ['/articles/manufacturer-career-checklist', '/company-check', true],
    ['/salary-market', '/company-check', true],
    ['/maker-career-lab/articles/salary-market.html', '../company-check.html', true],
    ['/maker-career-lab/salary-market.html', 'company-check.html', true],
  ]) {
    const page = openPage(source);
    page.listeners.get('click')({
      target: { closest: (selector) => selector === 'a[href]' ? { getAttribute: () => target } : null },
    });
    const expected = ['company_compare_link_click'];
    if (isArticle) expected.push('mcl_article_to_tool_click');
    assert.deepEqual(page.events, expected, source);
  }
});
