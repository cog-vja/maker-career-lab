"""Stdlib-only regression tests, with optional real EDINET original fixture.

For full source verification set OMRON_ORIGINAL_ZIP to the previously downloaded
GitHub artifact or EDINET type=1 zip. Without it, synthetic tests still run.
"""
import io
import os
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

from edinet_v310 import (FilingTables, GenericTables, decode_original_html,
                         extract_original_type1, extract_table_metric, load_original,
                         located_cells, normalize_label, parse_amount, table_plan)

REPORT_NAME = 'XBRL/PublicDoc/0105010_fixture.htm'

def headers_income(percent=True):
    if percent:
        return '''<tr><th>区分</th><th>注記</th><th colspan="3">第88期 （自 2024年4月1日 至 2025年3月31日）</th><th colspan="3">第89期 （自 2025年4月1日 至 2026年3月31日）</th></tr>
        <tr><th>区分</th><th>注記番号</th><th colspan="2">金額（百万円）</th><th>百分比（％）</th><th colspan="2">金額（百万円）</th><th>百分比（％）</th></tr>'''
    return '''<tr><th>区分</th><th>注記</th><th colspan="2">第88期（2025年3月31日）</th><th colspan="2">第89期（2026年3月31日）</th></tr>
    <tr><th>区分</th><th>注記番号</th><th colspan="2">金額（百万円）</th><th colspan="2">金額（百万円）</th></tr>'''

def income_row(label, left, right, extra=''):
    return (f'<tr><td>{label}</td><td>(注記)</td><td></td><td>{left}</td><td>95.4</td>'
            f'<td></td><td>{right}</td><td>93.1</td>{extra}</tr>')

def make_fixture(include_definition=True, extra_row='', remove_header_unit=False,
                 reverse_years=False, merged_revenue=False):
    header = headers_income()
    if remove_header_unit:
        header = header.replace('金額（百万円）','金額')
    if reverse_years:
        header = header.replace('2025年','TEMP').replace('2026年','2025年').replace('TEMP','2026年')
    rows = [income_row('売上高','715,379','767,351'),
            income_row('売上原価','385,092','416,350'),
            income_row('販売費及び一般管理費','236,881','245,398'),
            income_row('試験研究開発費','39,960','45,668')]
    if merged_revenue:
        rows[0]=rows[0].replace('<td>売上高</td>','<td rowspan="2">売上高</td>')
    income = '<ix:nonnumeric name="jpcrp_cor:ConsolidatedStatementOfIncomeUSGAAPTextBlock"><table>' + header + ''.join(rows)+extra_row+'</table></ix:nonnumeric>'
    balance = '''<ix:nonnumeric name="jpcrp_cor:ConsolidatedBalanceSheetUSGAAPTextBlock"><table>
    <tr><td>区分</td><td>注記</td><td colspan="2">第88期（2025年3月31日）</td><td colspan="2">第89期（2026年3月31日）</td></tr>
    <tr><td>区分</td><td>注記</td><td>金額（百万円）</td><td>構成比（％）</td><td>金額（百万円）</td><td>構成比（％）</td></tr>
    <tr><td>資産合計</td><td></td><td>1,362,459</td><td>100.0</td><td>1,516,263</td><td>100.0</td></tr>
    <tr><td>株主資本合計</td><td></td><td>771,885</td><td>56.7</td><td>835,885</td><td>55.1</td></tr>
    <tr><td>非支配持分</td><td></td><td>162,547</td><td>11.9</td><td>164,677</td><td>10.9</td></tr>
    <tr><td>純資産合計</td><td></td><td>934,432</td><td>68.6</td><td>1,000,562</td><td>66.0</td></tr>
    <tr><td>負債合計</td><td></td><td>428,027</td><td>31.4</td><td>515,701</td><td>34.0</td></tr>
    </table></ix:nonnumeric>'''
    cf = '''<ix:nonnumeric name="jpcrp_cor:ConsolidatedStatementOfCashFlowsUSGAAPTextBlock"><table>
    <tr><td>区分</td><td colspan="2">第88期（2025年3月31日）</td><td colspan="2">第89期（2026年3月31日）</td></tr>
    <tr><td>区分</td><td colspan="2">金額（百万円）</td><td colspan="2">金額（百万円）</td></tr>
    <tr><td>営業活動によるキャッシュ・フロー</td><td></td><td>55,784</td><td></td><td>60,919</td></tr>
    <tr><td>営業活動によるキャッシュ・フローの追記</td><td></td><td>3,333</td><td></td><td>4,444</td></tr>
    </table></ix:nonnumeric>'''
    salary = '''<table><tr><td></td><td></td><td></td><td></td><td>2026年3月31日現在</td></tr>
    <tr><th>従業員数（人）</th><th>平均年齢（歳）</th><th>平均勤続年数（年）</th><th>平均年間給与（千円）</th><th>平均年間給与の対前事業年度増減率（％）</th></tr>
    <tr><td>3,855</td><td>44.5</td><td>14.8</td><td>8,882</td><td>8.3</td></tr></table>'''
    definition = 'なお、文中における「営業利益」は、「売上高」から「売上原価」、「販売費及び一般管理費」および「試験研究開発費」を控除したものを表示しています。' if include_definition else ''
    mem = io.BytesIO()
    with zipfile.ZipFile(mem,'w') as z:
        z.writestr(REPORT_NAME, '<html><body>'+income+balance+cf+'</body></html>')
        z.writestr('XBRL/PublicDoc/0102010_definition.htm', '<html>'+definition+'</html>')
        z.writestr('XBRL/PublicDoc/0104010_salary.htm', '<html>'+salary+'</html>')
    return mem.getvalue()

class ExtractorTests(unittest.TestCase):
    def test_synthetic_six_metrics(self):
        r=extract_original_type1(make_fixture(),'FIXTURE')
        self.assertEqual(r['candidate_values'],{
            'revenue_oku':'7673.51','prior_revenue_oku':'7153.79',
            'operating_profit_oku':'599.35','operating_cf_oku':'609.19',
            'equity_ratio_pct':'55.13','average_salary_man':'888.2'})
        self.assertEqual(r['issues'],[])
        self.assertTrue(all(r['accounting_cross_checks'].values()))
    def test_source_provenance_years_and_money_columns(self):
        r=extract_original_type1(make_fixture())
        e=r['provenance']['revenue'][0]
        self.assertEqual((e['prior_year'],e['current_year']),(2025,2026))
        self.assertEqual(e['prior_column'],[2,4])
        self.assertEqual(e['current_column'],[5,7])
        self.assertEqual((e['prior_jpy'],e['current_jpy']),('715379000000','767351000000'))
    def test_salary_growth_percent_not_confused(self):
        r=extract_original_type1(make_fixture())
        self.assertEqual(r['candidate_values']['average_salary_man'],'888.2')
        self.assertEqual(r['provenance']['average_salary_man'][0]['column'],[3,4])
    def test_cash_flow_supplemental_heading_not_confused(self):
        r=extract_original_type1(make_fixture())
        self.assertEqual(len(r['provenance']['operating_cash_flow']),1)
        self.assertEqual(r['candidate_values']['operating_cf_oku'],'609.19')
    def test_definition_absent_blocks_operating_profit(self):
        r=extract_original_type1(make_fixture(include_definition=False))
        self.assertIsNone(r['candidate_values']['operating_profit_oku'])
        self.assertTrue(any(i.get('metric')=='operating_profit' for i in r['issues']))
    def test_missing_money_unit_blocks(self):
        r=extract_original_type1(make_fixture(remove_header_unit=True))
        self.assertIsNone(r['candidate_values']['revenue_oku'])
    def test_reverse_years_blocks_income(self):
        r=extract_original_type1(make_fixture(reverse_years=True))
        self.assertIsNone(r['candidate_values']['revenue_oku'])
    def test_rowspan_in_metric_blocks(self):
        r=extract_original_type1(make_fixture(merged_revenue=True))
        self.assertIsNone(r['candidate_values']['revenue_oku'])
    def test_duplicate_conflict_blocks(self):
        r=extract_original_type1(make_fixture(extra_row=income_row('売上高','1','2')))
        self.assertIsNone(r['candidate_values']['revenue_oku'])
        self.assertTrue(any(i.get('error')=='conflicting_exact_table_candidates' for i in r['issues']))
    def test_invalid_numeric(self):
        self.assertIsNone(parse_amount('12%'))
        self.assertIsNone(parse_amount('－'))
        self.assertIsNone(parse_amount('1,234円'))
        self.assertEqual(parse_amount('△1,234'),Decimal('-1234'))
    def test_standalone_table_is_not_accepted(self):
        raw=make_fixture()
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            contents={n:z.read(n) for n in z.namelist()}
        contents[REPORT_NAME]=contents[REPORT_NAME].replace(b'ConsolidatedStatementOfIncomeUSGAAPTextBlock',b'CompanyOnlyIncomeTextBlock')
        mem=io.BytesIO()
        with zipfile.ZipFile(mem,'w') as z:
            for n,v in contents.items():z.writestr(n,v)
        r=extract_original_type1(mem.getvalue())
        self.assertIsNone(r['candidate_values']['revenue_oku'])
    def test_disallow_publication(self):
        r=extract_original_type1(make_fixture())
        self.assertEqual(r['quality_status'],'BLOCKED')
        self.assertEqual(r['publication_status'],'UNVERIFIED')
        self.assertFalse(r['approved_for_publication'])
    def test_balance_sheet_identity(self):
        r=extract_original_type1(make_fixture())
        self.assertTrue(r['accounting_cross_checks']['assets_equal_liabilities_plus_net_assets'])
        self.assertTrue(r['accounting_cross_checks']['net_assets_equal_parent_equity_plus_noncontrolling'])
    def test_artifact_zip_support(self):
        raw=make_fixture(); outer=io.BytesIO()
        with zipfile.ZipFile(outer,'w') as z:
            z.writestr('OMRON-S100YG81-type1-original.zip',raw)
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'artifact.zip';p.write_bytes(outer.getvalue())
            self.assertEqual(load_original(p),raw)

@unittest.skipUnless(os.environ.get('OMRON_ORIGINAL_ZIP'), 'real filing opt-in via OMRON_ORIGINAL_ZIP')
class ActualOmronFilingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.blob=load_original(os.environ['OMRON_ORIGINAL_ZIP'])
        cls.report=extract_original_type1(cls.blob,'S100YG81')
    def test_original_six_metrics(self):
        self.assertEqual(self.report['candidate_values'],{
            'revenue_oku':'7673.51','prior_revenue_oku':'7153.79',
            'operating_profit_oku':'599.35','operating_cf_oku':'609.19',
            'equity_ratio_pct':'55.13','average_salary_man':'888.2'})
    def test_original_issuer_operating_profit_formula(self):
        self.assertTrue(self.report['operating_profit_definition'])
        a=self.report['components_jpy']
        for period,expected in (('prior','53446000000'),('current','59935000000')):
            self.assertEqual(Decimal(a['revenue'][period+'_jpy'])
                -Decimal(a['cost_of_sales'][period+'_jpy'])
                -Decimal(a['selling_general_admin'][period+'_jpy'])
                -Decimal(a['research_development'][period+'_jpy']),Decimal(expected))
    def test_original_periods_correct(self):
        self.assertTrue(all(self.report['components_jpy'][x]['current_year']==2026
            and self.report['components_jpy'][x]['prior_year']==2025
            for x in ('revenue','operating_cash_flow','total_assets','parent_equity')))
    def test_original_balance_sheet_identities(self):
        self.assertTrue(all(self.report['accounting_cross_checks'].values()))
        self.assertEqual(self.report['issues'],[])
    def test_original_no_published_values(self):
        self.assertEqual(self.report['quality_status'],'BLOCKED')
        self.assertFalse(self.report['approved_for_publication'])
    def test_operating_profit_crosschecks_segment_table(self):
        # Independent reporting block: note on segment results, not income statement.
        totals=[]
        with zipfile.ZipFile(io.BytesIO(self.blob)) as z:
            for filename in z.namelist():
                if not filename.startswith('XBRL/PublicDoc/') or not filename.endswith('.htm'):continue
                collector=GenericTables();collector.feed(decode_original_html(z.read(filename)))
                for table in collector.statements['generic']['tables']:
                    for row in table:
                        if len(row)<4 or normalize_label(row[0]['text'])!='セグメント利益':continue
                        numbers=[parse_amount(cell['text']) for cell in row[1:]]
                        numbers=[v for v in numbers if v is not None]
                        if numbers:totals.append(numbers[-1])
        self.assertIn(Decimal('59935'),totals)
        self.assertIn(Decimal('53446'),totals)
        self.assertEqual(Decimal(self.report['components_jpy']['operating_profit']['current_jpy'])/Decimal(1000000),Decimal('59935'))

if __name__=='__main__':unittest.main()
