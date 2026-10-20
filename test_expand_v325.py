import csv
import json
from pathlib import Path
import tempfile
import unittest
from expand_manufacturers_v325 import parse_jpx,edinet_ticker,choose,GateError,stage,emit

class CheckExpansion(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.base=Path(self.tmp.name)
  self.public=self.base/'company-data.js'
  self.public.write_text('window.MCL_COMPANIES = [{"id":"6146","name":"既存社","revenue":10,"revenuePrev":9,"operatingProfit":1,"operatingCashFlow":1,"equityRatio":50,"averageSalary":600}];\nwindow.MCL_DATASET_META = {"count":1};\nwindow.MCL_DEMOS = [];',encoding='utf-8')
  self.jpx=self.base/'jpx.csv'
  with self.jpx.open('w',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['コード','銘柄名','33業種区分']);w.writeheader()
   for x in [('6146','既存社','機械'),('7777','新製造会社','電気機器'),('1111','金融会社','銀行業')]:
    w.writerow(dict(zip(w.fieldnames,x)))
 def tearDown(self):self.tmp.cleanup()
 def test_universe_sector_filtering(self):
  companies,invalid,current=parse_jpx(self.jpx,self.public)
  self.assertEqual([x['ticker'] for x in companies],['6146','7777'])
  self.assertEqual([x['stage'] for x in companies],['ALREADY_PUBLISHED','RESEARCH_UNVERIFIED'])
  self.assertFalse(invalid)
 def test_universe_failure_on_wrong_header(self):
  self.jpx.write_text('証券コード,銘柄名,17業種\n7777,新製造会社,製造業\n',encoding='utf-8')
  with self.assertRaises(GateError):parse_jpx(self.jpx,self.public)
 def test_edinet_code(self):
  self.assertEqual(edinet_ticker('61460'),'6146')
  self.assertEqual(edinet_ticker('123A0'),'123A')
  self.assertIsNone(edinet_ticker('bad'))
 def test_correction_blocks(self):
  def doc(docid,typ):
   return {'docID':docid,'docTypeCode':typ,'withdrawalStatus':'0','xbrlFlag':'1','csvFlag':'1',
           'periodStart':'2025-04-01','periodEnd':'2026-03-31','submitDateTime':'2026-06-01 14:00:00'}
  self.assertEqual(choose([doc('S100AAAA','120'),doc('S100BBBB','130')],__import__('datetime').date(2026,10,20))[0],'CORRECTED_FILING_REVIEW')
 def test_edinet_correction_without_period_is_not_silently_ignored(self):
  from datetime import date
  original={'docID':'S100AAAA','docTypeCode':'120','withdrawalStatus':'0',
   'xbrlFlag':'1','csvFlag':'1','periodStart':'2025-04-01',
   'periodEnd':'2026-03-31','submitDateTime':'2026-06-20 13:00'}
  corrected={'docID':'S100BBBB','docTypeCode':'130','withdrawalStatus':'0',
   'periodStart':None,'periodEnd':None,'submitDateTime':'2026-06-22 15:00'}
  self.assertEqual(choose([original,corrected],date(2026,10,20))[0],
   'CORRECTED_FILING_REVIEW')
 def test_earlier_correction_does_not_block_newer_annual_report(self):
  from datetime import date
  original={'docID':'S100AAAA','docTypeCode':'120','withdrawalStatus':'0',
   'xbrlFlag':'1','csvFlag':'1','periodStart':'2025-04-01',
   'periodEnd':'2026-03-31','submitDateTime':'2026-06-20 13:00'}
  corrected_old={'docID':'S100BBBB','docTypeCode':'130','withdrawalStatus':'0',
   'periodStart':None,'periodEnd':None,'submitDateTime':'2026-05-22 15:00'}
  state,selected=choose([original,corrected_old],date(2026,10,20))
  self.assertEqual(state,'SELECTED');self.assertEqual(selected['docID'],'S100AAAA')
 def test_manual_release_requires_threshold_and_six_metrics(self):
  data=self.base/'review';data.mkdir()
  record={'ticker':'7777','name':'新製造会社','status':'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW',
   'verifiedMetricCount':6,'industry':'電気機器','docID':'S100AAAA','periodStart':'2025-04-01','periodEnd':'2026-03-31',
   'gaap':'JP_GAAP','sourceOriginalSha256':'a'*64,'sourceXbrlSha256':'b'*64,
   'sourcePayloadFingerprint':'c'*64,'verifiedAt':'2026-10-20',
   'metrics':{a:{'status':'SOURCE_RECONCILED','value':'12.3'} for a in
    ('revenue_oku','prior_revenue_oku','operating_profit_oku','operating_cf_oku','equity_ratio_pct','average_salary_man')}}
  emit(data/'7777.json',record)
  approvals=self.base/'approvals.csv';approvals.write_text('ticker,approved\n7777,YES\n',encoding='utf-8')
  class A: pass
  args=A();args.public=str(self.public);args.audit_dir=str(data);args.approvals=str(approvals);args.require_count=1001;args.output=str(self.base/'stage')
  with self.assertRaises(GateError):stage(args)
  self.assertFalse((self.base/'stage'/'company-data.js').exists())
  args.require_count=2
  stage(args)
  staged=(self.base/'stage'/'company-data.js').read_text(encoding='utf-8')
  self.assertIn('"count":2',staged)
  self.assertIn('S100AAAA',staged)
  self.assertIn('既存社',staged)
  record['metrics']['average_salary_man']['status']='BLOCKED'
  emit(data/'7777.json',record)
  with self.assertRaises(GateError):stage(args)

if __name__=='__main__':unittest.main()
