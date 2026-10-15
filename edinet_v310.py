#!/usr/bin/env python3
"""EDINET v3.10: source-scoped, period-aware US GAAP HTML statement extractor.

Works with EDINET type=1 original XBRL ZIP without dependencies. Extracts
consolidated financial statement *presentation* values, not numeric facts
from standalone financial statements. Ambiguities are blocked, not guessed.

This module does not write to the public site. Source reconciliation remains
necessary for any document not explicitly tested against the original.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import unicodedata
import zipfile
from collections import defaultdict
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

STATEMENT_ELEMENTS = {
    'income': 'ConsolidatedStatementOfIncomeUSGAAPTextBlock',
    'balance': 'ConsolidatedBalanceSheetUSGAAPTextBlock',
    'cashflow': 'ConsolidatedStatementOfCashFlowsUSGAAPTextBlock',
}
METRICS = {
    'revenue': ('income', ('売上高', '純売上高', '売上収益')),
    'cost_of_sales': ('income', ('売上原価',)),
    'selling_general_admin': ('income', ('販売費及び一般管理費', '販売費及び一般管理費用')),
    'research_development': ('income', ('試験研究開発費', '研究開発費')),
    'operating_cash_flow': ('cashflow', ('営業活動によるキャッシュ・フロー', '営業活動によるキャッシュフロー')),
    'total_assets': ('balance', ('資産合計', '総資産')),
    'parent_equity': ('balance', ('株主資本合計', '当社株主資本合計', '親会社株主持分合計')),
    'noncontrolling_interest': ('balance', ('非支配持分',)),
    'total_net_assets': ('balance', ('純資産合計',)),
    'total_liabilities': ('balance', ('負債合計',)),
}


def normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', text)).strip()


def normalize_label(text: str) -> str:
    return re.sub(r'[\s・:：()（）\-‐－]', '', normalize_text(text))


def parse_amount(text: str):
    text = normalize_text(text).replace(',', '').replace('△', '-').replace('▲', '-').replace('−', '-')
    text = text.replace('－', '-').strip()
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    if not re.fullmatch(r'-?\d+(?:\.\d+)?', text):
        return None
    value = Decimal(text)
    return value if value.is_finite() else None


def span(cell):
    try:
        col = int(cell['colspan'])
        row = int(cell['rowspan'])
    except (TypeError, ValueError, KeyError):
        return None
    if not 1 <= col <= 100 or not 1 <= row <= 100:
        return None
    return col, row


def located_cells(row):
    """Visual-column coordinates for cells with colspan; rows with rowspan rejected."""
    output = []
    col = 0
    for cell in row:
        shape = span(cell)
        if shape is None or shape[1] != 1:
            return None
        n, _ = shape
        output.append((col, col + n, cell))
        col += n
    return output


def statement_kind(tag_name):
    if not tag_name:
        return None
    for kind, suffix in STATEMENT_ELEMENTS.items():
        if tag_name.rsplit(':', 1)[-1].lower() == suffix.lower():
            return kind
    return None


class FilingTables(HTMLParser):
    """Capture tables *only* inside named, consolidated statement TextBlocks."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ix_context = []
        self.table_stack = []
        self.statements = defaultdict(lambda: {'tables': [], 'text_parts': []})

    @property
    def active(self):
        return next((k for k in reversed(self.ix_context) if k), None)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'ix:nonnumeric':
            self.ix_context.append(statement_kind(a.get('name')))
        if tag == 'table' and self.active:
            self.table_stack.append({'kind': self.active, 'rows': [], 'row': None, 'cell': None})
        if not self.table_stack:
            return
        tab = self.table_stack[-1]
        if tag == 'tr':
            tab['row'] = []
        elif tag in ('td', 'th') and tab['row'] is not None:
            tab['cell'] = {'text': '', 'colspan': a.get('colspan', '1'), 'rowspan': a.get('rowspan', '1')}

    def handle_data(self, data):
        if self.active:
            self.statements[self.active]['text_parts'].append(data)
        if self.table_stack and self.table_stack[-1]['cell'] is not None:
            self.table_stack[-1]['cell']['text'] += data

    def handle_endtag(self, tag):
        if self.table_stack:
            tab = self.table_stack[-1]
            if tag in ('td', 'th') and tab['row'] is not None and tab['cell'] is not None:
                tab['cell']['text'] = normalize_text(tab['cell']['text'])
                tab['row'].append(tab['cell'])
                tab['cell'] = None
            elif tag == 'tr' and tab['row'] is not None:
                if tab['row']:
                    tab['rows'].append(tab['row'])
                tab['row'] = None
            elif tag == 'table':
                completed = self.table_stack.pop()
                self.statements[completed['kind']]['tables'].append(completed['rows'])
        if tag == 'ix:nonnumeric' and self.ix_context:
            self.ix_context.pop()


class GenericTables(FilingTables):
    """Capture all HTML tables for issuer's standalone average salary section."""
    @property
    def active(self):
        return 'generic'


def extract_average_salary(original_zip):
    """Employee table's reported thousand-yen average, converted to 10k yen.

    Reject the adjacent salary *growth percent* column and duplicates.
    """
    candidates = []
    with zipfile.ZipFile(io.BytesIO(original_zip)) as z:
        names = sorted(n for n in z.namelist() if '/PublicDoc/' in n and n.lower().endswith(('.htm', '.html')))
        for name in names:
            member = z.getinfo(name)
            if member.file_size > 8_000_000:
                continue
            parser = GenericTables(); parser.feed(decode_original_html(z.read(name)))
            for ti, table in enumerate(parser.statements['generic']['tables']):
                if len(table) < 3:
                    continue
                header = located_cells(table[1])
                value_row = located_cells(table[2])
                if header is None or value_row is None:
                    continue
                salary_cols = [(start, end, cell) for start, end, cell in header
                               if re.fullmatch(r'平均年間給与千円', normalize_label(cell['text']))]
                if len(salary_cols) != 1:
                    continue
                year_matches = re.findall(r'20\d{2}', normalize_text(' '.join(c['text'] for c in table[0])))
                if len(set(year_matches)) != 1:
                    continue
                start, end, _ = salary_cols[0]
                eligible = [parse_amount(c['text']) for a, b, c in value_row if a >= start and b <= end]
                eligible = [v for v in eligible if v is not None]
                if len(eligible) != 1 or eligible[0] < 0:
                    continue
                candidates.append({'value_man': str(eligible[0] / Decimal(10)),
                                   'salary_thousand_jpy': str(eligible[0]),
                                   'year': int(year_matches[0]),
                                   'source_file': name, 'table_index': ti,
                                   'row_index': 2, 'column': [start, end]})
    unique = {(c['year'], c['value_man']) for c in candidates}
    if len(unique) == 1:
        return candidates[0], candidates, None
    return None, candidates, 'average_salary_ambiguous_or_missing'


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
    def handle_data(self, data):
        self.parts.append(data)


def decode_original_html(data):
    # XHTML emitted by EDINET is normally UTF-8; avoid silent replacement chars.
    for encoding in ('utf-8-sig', 'utf-16', 'cp932'):
        try:
            return data.decode(encoding)
        except UnicodeError:
            continue
    raise ValueError('Unrecognized or corrupted EDINET HTML encoding')


def table_plan(rows):
    """Read 2 fiscal-year groups and their 金額 columns from a two-tier header."""
    if len(rows) < 3:
        return None, 'too_few_rows'
    for first_i in range(min(4, len(rows) - 2)):
        headers = located_cells(rows[first_i])
        if headers is None:
            continue
        periods = []
        for start, end, cell in headers:
            # Duration headers include both starting and ending fiscal years.
            years = [int(x) for x in re.findall(r'20\d{2}', normalize_text(cell['text']))]
            if years and ('第' in cell['text'] or '年' in normalize_text(cell['text'])):
                periods.append({'start': start, 'end': end, 'year': max(years)})
        if len(periods) != 2 or not periods[0]['year'] < periods[1]['year']:
            continue
        money_row = located_cells(rows[first_i + 1])
        if money_row is None:
            return None, 'bad_money_header_row'
        money = []
        for start, end, cell in money_row:
            h = normalize_text(cell['text'])
            m = re.search(r'金額\s*\(?\s*(百万円|千円|億円)\s*\)?', h)
            if m:
                money.append({'start': start, 'end': end,
                              'unit': m.group(1), 'multiplier': {'百万円': 10**6, '千円': 10**3, '億円': 10**8}[m.group(1)]})
        mapped = []
        for period in periods:
            aligned = [m for m in money if period['start'] <= m['start'] and m['end'] <= period['end']]
            if len(aligned) != 1:
                return None, 'missing_or_ambiguous_money_column'
            mapped.append({**period, **{'money_start': aligned[0]['start'], 'money_end': aligned[0]['end'],
                                         'multiplier': aligned[0]['multiplier'], 'unit': aligned[0]['unit']}})
        if mapped[0]['unit'] != mapped[1]['unit']:
            return None, 'mismatched_period_units'
        return {'periods': mapped, 'data_start': first_i + 2}, None
    return None, 'cannot_detect_two_fiscal_periods'


def extract_table_metric(table, metric, labels, source, table_i):
    plan, reason = table_plan(table)
    if plan is None:
        return [], {'reason': reason, 'table': table_i}
    matches = []
    for row_i, row in enumerate(table[plan['data_start']:], plan['data_start']):
        located = located_cells(row)
        if located is None:
            continue
        label = next((c['text'] for start, end, c in located if start == 0), '')
        if normalize_label(label) not in {normalize_label(l) for l in labels}:
            continue
        numbers = []
        for period in plan['periods']:
            eligible = [parse_amount(c['text']) for start, end, c in located
                        if start >= period['money_start'] and end <= period['money_end']]
            eligible = [n for n in eligible if n is not None]
            if len(eligible) != 1:
                return [], {'reason': 'money_cell_ambiguous', 'row': row_i,
                            'period': period['year'], 'numeric_count': len(eligible)}
            numbers.append({'year': period['year'], 'amount_jpy': eligible[0] * period['multiplier']})
        matches.append({'metric': metric, 'label': label, 'source_file': source,
                        'statement': METRICS[metric][0],
                        'table_index': table_i, 'row_index': row_i,
                        'prior_year': numbers[0]['year'], 'current_year': numbers[1]['year'],
                        'prior_jpy': str(numbers[0]['amount_jpy']),
                        'current_jpy': str(numbers[1]['amount_jpy']),
                        'unit': plan['periods'][0]['unit'],
                        'prior_column': [plan['periods'][0]['money_start'], plan['periods'][0]['money_end']],
                        'current_column': [plan['periods'][1]['money_start'], plan['periods'][1]['money_end']]})
    return matches, None


def detect_operating_profit_definition(original_zip):
    """Do not compute 'operating profit' unless issuer's disclosure defines it."""
    evidence = []
    with zipfile.ZipFile(io.BytesIO(original_zip)) as z:
        names = sorted(n for n in z.namelist() if '/PublicDoc/' in n and n.lower().endswith(('.htm', '.html')))
        for name in names:
            raw = z.read(name)
            if len(raw) > 8_000_000:
                continue
            parser = VisibleText();parser.feed(decode_original_html(raw))
            text = normalize_text(' '.join(parser.parts))
            for m in re.finditer('営業利益', text):
                segment = normalize_text(text[m.start():m.start() + 250])
                # Keep issuer's exact four-term definition, not accounting profit before tax.
                if ('営業利益」は' in segment and '「売上高」から' in segment
                        and '控除' in segment
                        and all(x in segment for x in ('売上原価', '販売費及び一般管理費', '試験研究開発費'))):
                    evidence.append({'file': name, 'definition_excerpt': segment[:190]})
                    break
    return evidence


def extract_original_type1(original_zip: bytes, docid=None):
    sources = defaultdict(list)
    issues = []
    with zipfile.ZipFile(io.BytesIO(original_zip)) as z:
        names = sorted(n for n in z.namelist() if '/PublicDoc/' in n and n.lower().endswith(('.htm', '.html')))
        if not names:
            raise ValueError('PublicDoc HTML not found')
        for name in names:
            member = z.getinfo(name)
            if member.file_size > 8_000_000:
                issues.append({'file': name, 'error': 'oversized_html'})
                continue
            parser = FilingTables();parser.feed(decode_original_html(z.read(name)))
            for kind, block in parser.statements.items():
                for ti, table in enumerate(block['tables']):
                    for metric, (metric_kind, labels) in METRICS.items():
                        if kind != metric_kind:
                            continue
                        candidates, issue = extract_table_metric(table, metric, labels, name, ti)
                        sources[metric].extend(candidates)
                        if issue and issue['reason'] not in ('too_few_rows', 'cannot_detect_two_fiscal_periods'):
                            issues.append({'source_file': name, 'statement': kind, **issue})
    extracted = {}
    provenance = {}
    for metric in METRICS:
        candidates = sources[metric]
        unique = {(c['prior_year'], c['current_year'], c['prior_jpy'], c['current_jpy']) for c in candidates}
        if len(unique) == 1:
            candidate = candidates[0]
            extracted[metric] = {'prior_jpy': candidate['prior_jpy'], 'current_jpy': candidate['current_jpy'],
                                 'prior_year': candidate['prior_year'], 'current_year': candidate['current_year']}
            provenance[metric] = candidates
        else:
            extracted[metric] = None
            if len(unique) > 1:
                issues.append({'metric': metric, 'error': 'conflicting_exact_table_candidates', 'candidate_count': len(unique)})
            provenance[metric] = candidates[:20]
    operating_profit_definitions = detect_operating_profit_definition(original_zip)
    required_profit = ('revenue', 'cost_of_sales', 'selling_general_admin', 'research_development')
    if operating_profit_definitions and all(extracted[k] for k in required_profit):
        # Require same two periods; do not combine mismatched fiscal year filings.
        periods = {(extracted[k]['prior_year'], extracted[k]['current_year']) for k in required_profit}
        if len(periods) == 1:
            op = {}
            for period in ('prior', 'current'):
                income = Decimal(extracted['revenue'][period + '_jpy'])
                costs = sum((Decimal(extracted[k][period + '_jpy']) for k in required_profit[1:]), Decimal(0))
                op[period + '_jpy'] = str(income - costs)
            extracted['operating_profit'] = op
        else:
            extracted['operating_profit'] = None
            issues.append({'metric': 'operating_profit', 'error': 'periods_do_not_match'})
    else:
        extracted['operating_profit'] = None
        issues.append({'metric': 'operating_profit', 'error': 'issuer_definition_or_components_missing'})

    a, eq = extracted['total_assets'], extracted['parent_equity']
    if a and eq and a['current_year'] == eq['current_year'] and a['prior_year'] == eq['prior_year']:
        d = Decimal(a['current_jpy']);e = Decimal(eq['current_jpy'])
        if d > 0 and 0 <= e <= d:
            extracted['equity_ratio_pct'] = str((e / d * 100).quantize(Decimal('0.01')))
        else:
            extracted['equity_ratio_pct'] = None
            issues.append({'metric': 'equity_ratio_pct', 'error': 'asset_equity_range'})
    else:
        extracted['equity_ratio_pct'] = None
    values = {}
    for target, source, period in (
            ('revenue_oku', 'revenue', 'current'),
            ('prior_revenue_oku', 'revenue', 'prior'),
            ('operating_profit_oku', 'operating_profit', 'current'),
            ('operating_cf_oku', 'operating_cash_flow', 'current')):
        entry = extracted[source]
        values[target] = str(Decimal(entry[period+'_jpy']) / Decimal(100_000_000)) if entry else None
    values['equity_ratio_pct'] = extracted['equity_ratio_pct']
    salary, salary_sources, salary_error = extract_average_salary(original_zip)
    values['average_salary_man'] = salary['value_man'] if salary else None
    provenance['average_salary_man'] = salary_sources
    if salary_error:
        issues.append({'metric': 'average_salary_man', 'error': salary_error})
    checks = {}
    if all(extracted[k] for k in ('total_assets', 'total_liabilities', 'total_net_assets')):
        checks['assets_equal_liabilities_plus_net_assets'] = all(
            Decimal(extracted['total_assets'][period+'_jpy']) ==
            Decimal(extracted['total_liabilities'][period+'_jpy']) + Decimal(extracted['total_net_assets'][period+'_jpy'])
            for period in ('prior', 'current'))
    if all(extracted[k] for k in ('total_net_assets', 'parent_equity', 'noncontrolling_interest')):
        checks['net_assets_equal_parent_equity_plus_noncontrolling'] = all(
            Decimal(extracted['total_net_assets'][period+'_jpy']) ==
            Decimal(extracted['parent_equity'][period+'_jpy']) + Decimal(extracted['noncontrolling_interest'][period+'_jpy'])
            for period in ('prior', 'current'))
    if any(not v for v in checks.values()):
        issues.append({'error': 'consolidated_balance_sheet_identity_mismatch'})
    # No salary in consolidated statements; v3.6 CSV continues to own salary.
    return {'docID': docid, 'candidate_values': values, 'components_jpy': extracted,
            'provenance': dict(provenance), 'operating_profit_definition': operating_profit_definitions,
            'accounting_cross_checks': checks,
            'issues': issues, 'publication_status': 'UNVERIFIED', 'quality_status': 'BLOCKED',
            'approved_for_publication': False,
            'data_policy': 'source_confirmed_locally_only; no automatic public release'}


def load_original(path):
    """Accept either EDINET original ZIP or GitHub Artifact ZIP containing it."""
    data = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = z.namelist()
        if any('/PublicDoc/' in n for n in files):
            return data
        originals = [n for n in files if n.lower().endswith('-type1-original.zip')]
        if len(originals) != 1:
            raise ValueError('expected one original type=1 ZIP inside artifact')
        raw = z.read(originals[0])
        with zipfile.ZipFile(io.BytesIO(raw)) as inner:
            if not any('/PublicDoc/' in n for n in inner.namelist()):
                raise ValueError('original archive lacks PublicDoc')
        return raw


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--original', required=True, help='EDINET type=1 ZIP or Actions artifact ZIP')
    p.add_argument('--docid', default='S100YG81')
    p.add_argument('--output', default='omron-extraction-v310.json')
    args = p.parse_args()
    result = extract_original_type1(load_original(args.original), args.docid)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result['candidate_values'], ensure_ascii=False, indent=2))
    missing = [k for k, v in result['candidate_values'].items() if v is None]
    if missing:
        raise SystemExit('Unresolved candidate values: ' + ', '.join(missing))


if __name__ == '__main__':
    main()
