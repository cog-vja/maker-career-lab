"""Standards-neutral ten-company integration and defensive merge regression."""
import json
import unittest
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from edinet_v310 import extract_original_type1
from edinet_v311 import integrate,build_summary,validate_original,METRICS
from test_v310 import make_fixture

DOC='S100YG81'
FILING={'docID':DOC,'periodEnd':'2026-03-31'}
BASE={'accounting_standard':{'standard':'US_GAAP','confidence':'high'},
 'selected_values':{k:None for k in METRICS},
 'provenance':{},'filing':FILING}
BASE['selected_values']['average_salary_man']='888.2'

class IntegrationTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.original=extract_original_type1(make_fixture(),DOC)
 def test_synthetic_complete_six(self):
  r=integrate(BASE,FILING,self.original)
  self.assertEqual(r['selected_values'],self.original['candidate_values'])
  self.assertEqual(len(r['source_review']['merges']),5)
  self.assertEqual(r['publication_status'],'UNVERIFIED')
  self.assertEqual(r['quality_gate']['status'],'BLOCKED')
  self.assertFalse(r['approved_for_publication'])
 def test_id_mismatch_blocks(self):
  other={**self.original,'docID':'WRONG'}
  r=integrate(BASE,FILING,other)
  self.assertIsNone(r['selected_values']['revenue_oku'])
  self.assertEqual(r['source_review']['type1_error'],'docid_mismatch')
 def test_filing_year_mismatch_blocks(self):
  r=integrate(BASE,{**FILING,'periodEnd':'2025-03-31'},self.original)
  self.assertIsNone(r['selected_values']['revenue_oku'])
 def test_balance_identity_mismatch_blocks(self):
  o=deepcopy(self.original);o['accounting_cross_checks']['assets_equal_liabilities_plus_net_assets']=False
  r=integrate(BASE,FILING,o)
  self.assertIsNone(r['selected_values']['revenue_oku'])
 def test_no_definition_blocks(self):
  o=deepcopy(self.original);o['operating_profit_definition']=[]
  r=integrate(BASE,FILING,o)
  self.assertIsNone(r['selected_values']['revenue_oku'])
 def test_missing_source_blocks(self):
  o=deepcopy(self.original);o['provenance']['average_salary_man']=[]
  r=integrate(BASE,FILING,o)
  self.assertIsNone(r['selected_values']['revenue_oku'])
 def test_conflict_blocks_metric(self):
  b=deepcopy(BASE);b['selected_values']['revenue_oku']='1.23'
  r=integrate(b,FILING,self.original)
  self.assertIsNone(r['selected_values']['revenue_oku'])
  self.assertIn('revenue_oku',r['source_review']['conflicts'])
 def test_non_us_unchanged(self):
  b=deepcopy(BASE);b['accounting_standard']['standard']='IFRS'
  r=integrate(b,FILING,self.original)
  self.assertEqual(r['selected_values'],b['selected_values'])
  self.assertEqual(r['source_review']['merges'],{})
 def test_missing_type1_preserves_old(self):
  r=integrate(BASE,FILING,source_error='timeout')
  self.assertEqual(r['selected_values'],BASE['selected_values'])
  self.assertEqual(r['source_review']['type1_error'],'timeout')
 def test_derived_recomputed(self):
  r=integrate(BASE,FILING,self.original)
  self.assertIsNotNone(r['derived_values']['operating_margin_pct'])
 def test_input_immutable(self):
  b=deepcopy(BASE);integrate(b,FILING,self.original)
  self.assertEqual(b,BASE)
 def test_summary_complete(self):
  r=integrate(BASE,FILING,self.original)
  s=build_summary({'ticker':'6645','target_name':'fixture','selected':FILING},r)
  self.assertEqual(s['metric_count'],6)
  self.assertEqual(s['type1_merges'],5)
 def test_original_validation(self):
  self.assertTrue(validate_original(FILING,self.original)[0])
  self.assertEqual(self.original['candidate_values']['revenue_oku'],'7673.51')

if __name__=='__main__':unittest.main()
