import unittest
from decimal import Decimal
from edinet_v36 import GridParser,expand,statement_candidates,us_extract

class TestV36(unittest.TestCase):
    def block(self,html,element='ConsolidatedStatementOfIncomeUSGAAPTextBlock'):
        return {'html':html,'element':element,'file':'synthetic.csv'}
    def test_two_period_revenue(self):
        html='<table><tr><th>区分</th><th>2025年</th><th>2026年</th></tr><tr><td>単位：百万円</td></tr><tr><td>売上高</td><td>715,379</td><td>767,351</td></tr></table>'
        cur,_=statement_candidates(self.block(html),'revenue_oku')
        old,_=statement_candidates(self.block(html),'prior_revenue_oku')
        self.assertEqual(cur[0]['value_jpy'],'767351000000')
        self.assertEqual(old[0]['value_jpy'],'715379000000')
    def test_ambiguous_percentage_columns_rejected(self):
        html='<table><tr><th>区分</th><th>2025年</th><th>比率</th><th>2026年</th><th>比率</th></tr><tr><td>百万円</td></tr><tr><td>売上高</td><td>100</td><td>50</td><td>200</td><td>60</td></tr></table>'
        rows,diag=statement_candidates(self.block(html),'revenue_oku')
        self.assertEqual(rows,[]);self.assertEqual(len(diag),1)
    def test_missing_year_blocked(self):
        html='<table><tr><td>百万円</td></tr><tr><td>売上高</td><td>100</td><td>200</td></tr></table>'
        rows,_=statement_candidates(self.block(html),'revenue_oku');self.assertEqual(rows,[])
    def test_rowspan(self):
        p=GridParser();p.feed('<table><tr><td rowspan="2">A</td><td>1</td></tr><tr><td>2</td></tr></table>')
        grid=expand(p.tables[0]);self.assertEqual(grid[1][0]['text'],'A')
    def test_multiple_units_blocked(self):
        html='<table><tr><td>2025年</td><td>2026年</td></tr><tr><td>千円 百万円</td></tr><tr><td>売上高</td><td>1</td><td>2</td></tr></table>'
        rows,_=statement_candidates(self.block(html),'revenue_oku');self.assertEqual(rows,[])
    def test_no_automatic_publication(self):
        vals,proof,debug=us_extract([])
        self.assertIsNone(vals['revenue_oku']);self.assertIsNone(vals['equity_ratio_pct'])

if __name__=='__main__':unittest.main()
