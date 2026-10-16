import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
import edinet_v318 as v

ROOT=Path(__file__).resolve().parent
ARGS=dict(review_zip=ROOT/'v317-review-v318.zip',master_path=ROOT/'company-master-v318.json',
          selections_path=ROOT/'filing-selections-v317.json',old_js=(ROOT/'company-data.js' if (ROOT/'company-data.js').is_file() else ROOT/'reference-only/company-data.js'),
          baseline_path=ROOT/'approved-ten-baseline-v318.json')

class V318Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.addCleanup(self.tmp.cleanup)
  self.out=Path(self.tmp.name)/'output'
 def review(self):return v.review_source(**ARGS,output=self.out)
 def test_master_is_ten_twenty_thirty(self):
  master=v.load_master(ARGS['master_path'])
  self.assertEqual(len(master['companies']),60)
  self.assertEqual(len(v.master_pending(master)),30)
 def test_baseline_immutable(self):
  old=v.public_companies(ARGS['old_js'])
  self.assertEqual(len(old),10)
  self.assertEqual(v.sha(v.canonical(old)),v.BASELINE_SEMANTIC_SHA256)
 def test_frozen_source_119_and_19(self):
  s,c,template,old=self.review()
  self.assertEqual(s['reconciled_metrics'],119)
  self.assertEqual(s['eligible_for_human_approval'],19)
  self.assertEqual(len(template['eligible_document_ids']),19)
  self.assertNotIn('6501',{x['id'] for x in c})
  self.assertEqual({x['id'] for x in c}&{x['id'] for x in old},set())
 def test_review_csv_six_by_twenty(self):
  import csv
  self.review()
  with (self.out/'metric-audit-v318.csv').open(encoding='utf-8-sig',newline='') as f:
   rows=list(csv.DictReader(f))
  self.assertEqual(len(rows),120)
  self.assertEqual(sum(x['status']=='SOURCE_RECONCILED' for x in rows),119)
  self.assertEqual([x['ticker'] for x in rows if x['status']=='BLOCKED'],['6501'])
 def test_approval_template_defaults_false(self):
  _,_,approval,_=self.review()
  self.assertIs(approval['approved'],False)
  with self.assertRaises(v.GateError):v.validate_approval(None,approval)
 def test_approval_must_bind_all_tickers_and_digest(self):
  _,_,t,_=self.review()
  bad=dict(t,approved=True,reviewer_confirmation='I reviewed and approve publication of the nineteen fully reconciled new companies')
  bad['eligible_document_ids']=dict(bad['eligible_document_ids'],**{'7203':'S99999999'})
  p=self.out/'bad-approval.json';v.write_json(p,bad)
  with self.assertRaisesRegex(v.GateError,'approval binding mismatch'):v.validate_approval(p,t)
 def test_approval_good_can_stage_29_but_no_deploy(self):
  s,c,t,old=self.review()
  valid=dict(t,approved=True,reviewer_confirmation='I reviewed and approve publication of the nineteen fully reconciled new companies')
  p=self.out/'approval.json';v.write_json(p,valid)
  v.validate_approval(p,t)
  js=v.js_for(old+c,s['review_artifact_sha256'])
  target=self.out/'staged.js';target.write_text(js,encoding='utf-8')
  restored=v.public_companies.__globals__['json'].loads(js.split('window.MCL_COMPANIES = ',1)[1].split(';\n',1)[0])
  self.assertEqual(restored[:10],old)
  self.assertEqual(len(restored),29)
  self.assertFalse((self.out/'site-ready'/'company-data.js').exists())
 def test_source_review_tamper_rejected(self):
  with zipfile.ZipFile(ARGS['review_zip']) as z, zipfile.ZipFile(self.out.parent/'tampered.zip','w') as out:
   for item in z.infolist():
    raw=z.read(item.filename)
    if item.filename.endswith('7729-S100YEOP-v317.json'):
     obj=json.loads(raw);obj['metrics']['revenue_oku']['value']='999999'
     raw=v.canonical(obj)
    out.writestr(item.filename,raw)
  with self.assertRaisesRegex(v.GateError,'artifact content changed'):
   v.review_source(**dict(ARGS,review_zip=self.out.parent/'tampered.zip'),output=self.out)
 def test_baseline_data_tamper_rejected(self):
  src=ARGS['old_js'].read_text('utf-8').replace('4368.89','4368.90')
  p=self.out.parent/'altered.js';p.write_text(src)
  with self.assertRaises(v.GateError):v.public_companies(p)
 def test_source_extension_correlated(self):
  with zipfile.ZipFile(ARGS['review_zip']) as z:
   j=json.loads(z.read('7203-S100Y8NY-v317.json'))
  v.validate_evidence('revenue_oku',j['metrics']['revenue_oku'])
  changed=json.loads(json.dumps(j['metrics']['revenue_oku']))
  changed['evidence']['element_sources'][1]['value_jpy']='300000000'
  with self.assertRaises(v.GateError):v.validate_evidence('revenue_oku',changed)
 def test_future_date_discovery_rejected(self):
  with self.assertRaisesRegex(v.GateError,'future'):
   v.discovery(ARGS['master_path'],ARGS['old_js'],ARGS['baseline_path'],self.out,
               date(2099,1,1),1,0,list_reader=lambda day:[])
 def test_discovery_synthetic_daily_candidates(self):
  day=date(2026,10,16)
  fake={'secCode':'67230','docTypeCode':'120','withdrawalStatus':'0',
        'csvFlag':'1','xbrlFlag':'1','docID':'S100ABCDE','periodStart':'2025-01-01',
        'periodEnd':'2025-12-31','submitDateTime':'2026-03-10 09:00',
        'edinetCode':'E99999','docDescription':'有価証券報告書','filerName':'テスト'}
  def listing(dt):return [fake] if dt==day else []
  summary=v.discovery(ARGS['master_path'],ARGS['old_js'],ARGS['baseline_path'],self.out,
                      day,2,0,list_reader=listing)
  self.assertEqual(summary['found_unverified'],1)
  self.assertEqual(summary['not_found'],29)
  self.assertEqual(summary['originals_downloaded'],0)
  self.assertFalse((self.out/'site-ready').exists())
 def test_failed_daily_list_blocks_selection(self):
  day=date(2026,10,16)
  fake={'secCode':'67230','docTypeCode':'120','withdrawalStatus':'0',
        'csvFlag':'1','xbrlFlag':'1','docID':'S100ABCDE','periodStart':'2025-01-01',
        'periodEnd':'2025-12-31','submitDateTime':'2026-03-10 09:00'}
  def listing(dt):
   if dt!=day:raise ValueError('simulated outage')
   return [fake]
  summary=v.discovery(ARGS['master_path'],ARGS['old_js'],ARGS['baseline_path'],self.out,
                      day,2,0,list_reader=listing)
  self.assertFalse(summary['listing_complete'])
  self.assertEqual(summary['found_unverified'],0)
  self.assertEqual(summary['daily_lists_failed'],1)
 def test_negative_amount_not_allowed_for_revenue(self):
  with self.assertRaises(v.GateError):v.safe_decimal(None)
  with self.assertRaises(v.GateError):v.safe_decimal(float('nan'))
 def test_discovery_does_not_change_root_js(self):
  raw=ARGS['old_js'].read_bytes()
  v.discovery(ARGS['master_path'],ARGS['old_js'],ARGS['baseline_path'],self.out,
              date(2026,10,16),1,0,list_reader=lambda d:[])
  self.assertEqual(raw,ARGS['old_js'].read_bytes())

if __name__=='__main__':unittest.main()
