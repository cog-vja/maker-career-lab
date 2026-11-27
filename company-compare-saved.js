/* One saved comparison, kept entirely in the browser. */
(() => {
  'use strict';

  const key = 'mcl.compare.saved.v1';
  const byId = id => document.getElementById(id);
  const form = byId('compare-form');
  const panel = byId('compare-saved');
  if (!form || !panel || !Array.isArray(window.MCL_COMPANIES)) return;

  const companies = new Map(window.MCL_COMPANIES.map(company => [String(company.id), company]));
  const documents = new Map(window.MCL_COMPANIES.map(company => [company.sourceDocId, company]));
  const sources = byId('sources');
  const results = byId('results');
  const status = byId('compare-saved-status');
  const message = byId('compare-save-message');
  const summary = panel.querySelector('summary');
  const restore = byId('compare-saved-restore');
  const clear = byId('compare-saved-clear');
  const save = byId('compare-save-pair');

  function snapshot(company) {
    return {
      id: String(company.id),
      name: company.name,
      document: company.sourceDocId,
      period: company.period,
      scope: company.scope,
      salaryScope: company.salaryScope,
      gaap: company.accountingStandard,
      salary: Number.isFinite(company.averageSalary) ? company.averageSalary : null,
      revenue: Number.isFinite(company.revenue) ? company.revenue : null,
      profit: Number.isFinite(company.operatingProfit) ? company.operatingProfit : null,
    };
  }

  function readPeriod(text) {
    if (typeof text !== 'string' || !/^\d{4}-\d{2}-\d{2}〜\d{4}-\d{2}-\d{2}$/.test(text)) return null;
    const days = text.split('〜').map(day => {
      const stamp = Date.parse(day + 'T00:00:00Z');
      return Number.isFinite(stamp) && new Date(stamp).toISOString().slice(0, 10) === day
        ? stamp / 86400000 : NaN;
    });
    return days[0] < days[1] ? days : null;
  }

  function valid(entry) {
    return entry && typeof entry === 'object'
      && typeof entry.id === 'string' && /^[0-9A-Z]{4}$/.test(entry.id)
      && typeof entry.name === 'string' && entry.name.length > 0 && entry.name.length <= 160
      && typeof entry.document === 'string' && /^S[0-9A-Z]{7,15}$/.test(entry.document)
      && readPeriod(entry.period)
      && ['連結（給与のみ提出会社）', '提出会社単体（給与も同一法人）'].includes(entry.scope)
      && entry.salaryScope === '提出会社単体'
      && ['JP_GAAP', 'IFRS', 'US_GAAP'].includes(entry.gaap)
      && ['salary', 'revenue', 'profit'].every(field => entry[field] === null || Number.isFinite(entry[field]));
  }

  let items = [];
  let storage = 'available';
  let raw;
  try {
    raw = window.localStorage.getItem(key);
  } catch (_error) {
    storage = 'unavailable';
  }
  if (raw !== undefined && raw !== null) {
    try {
      if (raw.length > 8192) throw new TypeError('oversized');
      const stored = JSON.parse(raw);
      if (stored.version !== 1 || !Array.isArray(stored.items) || stored.items.length > 2
          || !stored.items.every(valid) || new Set(stored.items.map(item => item.id)).size !== stored.items.length) {
        throw new TypeError('invalid');
      }
      items = stored.items;
    } catch (_error) {
      storage = 'corrupt';
    }
  }

  function persist(next) {
    try {
      if (next.length) window.localStorage.setItem(key, JSON.stringify({ version: 1, items: next }));
      else window.localStorage.removeItem(key);
    } catch (_error) {
      return false;
    }
    items = next;
    storage = 'available';
    render();
    updateSave();
    return true;
  }

  function track(action) {
    // Never attach issuer identity, form values, snapshots, or timestamps.
    document.dispatchEvent(new CustomEvent('mcl:compare-saved-action', { detail: action }));
  }

  function currentFor(saved) {
    const current = companies.get(saved.id);
    // The public comparison dataset does not expose EDINET filer codes. Treat a
    // changed name with the same ticker as unresolved until reviewed.
    return current?.name === saved.name ? current : null;
  }

  const margin = value => value.revenue > 0 && value.profit !== null ? 100 * value.profit / value.revenue : null;

  function number(value, unit, digits) {
    return Number.isFinite(value) ? value.toLocaleString('ja-JP', { maximumFractionDigits: digits }) + unit : '未取得';
  }

  function metricLine(value) {
    const line = document.createElement('p');
    line.className = 'mcl-saved-metrics';
    line.append(text('span', `平均年間給与 ${number(value.salary, '万円', 1)}`),
      text('span', `営業利益率 ${number(margin(value), '%', 2)}`));
    return line;
  }

  function changeText(before, after) {
    const oldPeriod = readPeriod(before.period);
    const newPeriod = readPeriod(after.period);
    if (!oldPeriod || !newPeriod || before.scope !== after.scope ||
        before.salaryScope !== after.salaryScope || before.gaap !== after.gaap) {
      return '比較不可。会計基準、対象範囲、または決算期が異なります。';
    }

    let label = '';
    if (before.period !== after.period) {
      const oldDays = oldPeriod[1] - oldPeriod[0] + 1;
      const newDays = newPeriod[1] - newPeriod[0] + 1;
      if (oldPeriod[1] >= newPeriod[0] || Math.abs(newDays - oldDays) > 7) {
        return '比較不可。決算期の長さ、重なり、または時系列を確認してください。';
      }
      label = '新しい決算期。';
    } else if (before.document !== after.document) {
      label = '同じ決算期の書類が更新されました。訂正の有無は原本で確認できます。';
    }

    if (!label && before.salary !== null && before.salary === after.salary &&
        margin(before) !== null && margin(before) === margin(after)) {
      return '保存時と同じ数値です。';
    }
    const comparisons = [
      ['給与', before.salary, after.salary, '万円', 1],
      ['利益率', margin(before), margin(after), 'ポイント', 2],
    ];
    const values = comparisons.map(([name, then, now, unit, digits]) => {
      if (then === null || now === null) return name + 'は比較不可';
      const scale = 10 ** digits;
      const delta = Math.round((now - then) * scale) / scale;
      if (delta === 0) return name + 'は表示桁で変化なし';
      return name + ' ' + (delta > 0 ? '+' : '') + number(delta, unit, digits);
    }).join('、');
    if (!label && comparisons.some(([, then, now]) => then !== null && now !== null && then !== now)) {
      label = '同じ決算期・書類の掲載値に差があります。';
    }
    return label + values + '。';
  }

  function text(tag, value) {
    const node = document.createElement(tag);
    node.textContent = value;
    return node;
  }

  function actionButton(label, handler) {
    const button = text('button', label);
    button.type = 'button';
    button.className = 'mcl-saved-button';
    button.addEventListener('click', handler);
    return button;
  }

  function render() {
    summary.textContent = items.length ? `保存した比較（${items.length}社）` : '保存した比較';
    byId('compare-saved-empty').hidden = items.length !== 0;
    restore.hidden = items.length !== 2 || !items.every(currentFor);
    clear.hidden = !items.length && storage !== 'corrupt';
    const rows = items.map(item => {
      const li = document.createElement('li');
      const title = text('strong', item.name);
      const now = currentFor(item);
      li.append(title);
      if (now) {
        const after = snapshot(now);
        const current = text('p', `最新の対象期 ${after.period}`);
        current.className = 'compare-help';
        const change = text('p', changeText(item, after));
        change.className = 'compare-help';
        li.append(current, metricLine(after), change);
        if (item.period !== after.period || item.document !== after.document ||
            item.salary !== after.salary || margin(item) !== margin(after)) {
          const previous = text('p', `保存時の対象期 ${item.period}`);
          previous.className = 'compare-help';
          const previousMetrics = metricLine(item);
          previousMetrics.classList.add('compare-help');
          li.append(previous, previousMetrics);
        }
      } else {
        li.append(text('p', companies.has(item.id)
          ? '比較不可。現在の社名と一致せず、同じ提出会社か確認できません。'
          : '比較不可。現在の公開データに収録されていません。'));
      }
      const controls = document.createElement('div');
      controls.className = 'mcl-saved-actions';
      if (now) {
        const use = actionButton('比較候補Bに入れる', () => {
          byId('name-b').value = item.id;
          byId('hint-b').textContent = '';
          byId('name-b').focus();
        });
        use.setAttribute('aria-label', item.name + 'を比較候補Bに入れる');
        controls.append(use);
      }
      const remove = actionButton('保存を解除', () => {
        if (!persist(items.filter(saved => saved.id !== item.id))) {
          status.textContent = '保存を解除できませんでした。ブラウザの設定をご確認ください。';
          return;
        }
        summary.focus();
        status.textContent = item.name + 'の保存を解除しました。';
        track('remove');
      });
      remove.setAttribute('aria-label', item.name + 'の保存を解除');
      controls.append(remove);
      li.append(controls);
      return li;
    });
    byId('compare-saved-items').replaceChildren(...rows);
  }

  function displayedPair() {
    if (results.hidden) return [];
    const ids = Array.from(sources.querySelectorAll('.mcl-source-doc span'), node => {
      const documentId = node.textContent.match(/^EDINET書類ID：(S[0-9A-Z]{7,15})\s*$/)?.[1];
      return documents.get(documentId);
    });
    return ids.length === 2 && ids.every(Boolean) && ids[0].id !== ids[1].id ? ids.map(snapshot) : [];
  }

  function updateSave() {
    const pair = displayedPair();
    byId('compare-save-prompt').hidden = storage === 'unavailable' || !pair.length;
    if (JSON.stringify(items) === JSON.stringify(pair) && pair.length) {
      save.textContent = 'この2社は保存済み';
    } else {
      save.textContent = items.length ? 'この2社で保存を更新' : 'この2社を保存';
    }
  }

  save.addEventListener('click', () => {
    const pair = displayedPair();
    if (pair.length !== 2 || !pair.every(valid)) return;
    if (JSON.stringify(items) === JSON.stringify(pair)) {
      message.textContent = 'この比較は保存済みです。';
      return;
    }
    if (persist(pair)) {
      message.textContent = 'この2社を保存しました。';
      status.textContent = '';
      track('save');
    } else {
      message.textContent = '保存できませんでした。比較は引き続き利用できます。';
    }
  });

  restore.addEventListener('click', () => {
    if (items.length !== 2 || !items.every(currentFor)) return;
    byId('name-a').value = items[0].id;
    byId('name-b').value = items[1].id;
    byId('hint-a').textContent = '';
    byId('hint-b').textContent = '';
    form.requestSubmit();
    if (!results.hidden && byId('status').textContent.startsWith('掲載データによる参考比較です。')) {
      const title = byId('compare-title');
      title.tabIndex = -1;
      title.focus({ preventScroll: true });
      track('restore');
    }
  });

  clear.addEventListener('click', () => {
    const count = items.length;
    if (!persist([])) {
      status.textContent = '保存を削除できませんでした。ブラウザの設定をご確認ください。';
      return;
    }
    summary.focus();
    status.textContent = 'このブラウザの保存を削除しました。';
    if (count) track('remove');
  });

  summary.addEventListener('click', () => {
    if (!panel.open && items.length) track('open');
  });

  const observer = new MutationObserver(() => {
    message.textContent = '';
    updateSave();
  });
  observer.observe(sources, { childList: true });
  observer.observe(results, { attributes: true, attributeFilter: ['hidden'] });
  if (storage === 'corrupt') status.textContent = '保存内容を読み込めませんでした。削除してもう一度保存できます。';
  panel.hidden = storage === 'unavailable';
  render();
  updateSave();
})();
