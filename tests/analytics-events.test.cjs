const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');

const script = readFileSync(join(__dirname, '../dist/analytics-events.js'), 'utf8');

function openPage(path) {
  const events = [];
  const listeners = new Map();
  const window = {
    location: new URL(path, 'https://maker-career-lab.com/'),
    gtag(command, name) {
      if (command === 'event') events.push(name);
    },
  };
  const document = {
    readyState: 'interactive',
    querySelector: () => null,
    querySelectorAll: () => [],
    addEventListener: (name, listener) => listeners.set(name, listener),
  };
  runInNewContext(script, { document, URL, window });
  return { events, listeners, window };
}

test('data load check waits for deferred company data', () => {
  const page = openPage('/company-check');
  assert.deepEqual(page.events, []);
  page.window.MCL_COMPANIES = [{}];
  page.listeners.get('DOMContentLoaded')();
  assert.deepEqual(page.events, []);
});

test('a failed company data load still emits an error', () => {
  const page = openPage('/company-check');
  page.listeners.get('DOMContentLoaded')?.();
  assert.deepEqual(page.events, ['mcl_data_load_error']);
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
