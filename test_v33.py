import unittest
from decimal import Decimal
import edinet_v33 as v
class TestV33(unittest.TestCase):
 def test_salary_parent_company(self):
  ok,val=v.safe_candidate({'context':'CurrentYearInstant_NonConsolidatedMember','unit':'JPY','value':'10977033'},'average_salary_man');self.assertTrue(ok);self.assertEqual(val,'1097.7033')
 def test_salary_reject_group(self):
  self.assertFalse(v.safe_candidate({'context':'CurrentYearInstant','unit':'JPY','value':'10977033'},'average_salary_man')[0])
 def test_ratio_fraction(self):
  self.assertEqual(v.safe_candidate({'context':'CurrentYearInstant','unit':'pure','value':'0.75'},'equity_ratio_pct'),(True,'75.00'))
 def test_ratio_ambiguous(self):
  self.assertFalse(v.safe_candidate({'context':'CurrentYearInstant','unit':'pure','value':'75'},'equity_ratio_pct')[0])
 def test_derived(self):
  x=v.calculate({'revenue_oku':'11286.1','prior_revenue_oku':'7797.07','operating_profit_oku':'4991.2','operating_cf_oku':'3351.82'})
  self.assertEqual(x['operating_margin_pct'],'44.22')
 def test_segment_excluded(self):
  self.assertFalse(v.safe_candidate({'context':'CurrentYearDuration_SegmentMember','unit':'JPY','value':'100000000'},'revenue_oku')[0])
if __name__=='__main__':unittest.main()
