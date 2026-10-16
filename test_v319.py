"""v3.19 safety tests: company roster, immutable evidence, release and discovery."""
import copy
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import patch
import edinet_v319 as m
ROOT=Path(__file__).resolve().parent

class V319Tests(unittest.TestCase):
 def setUp(self):
  d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup)
  self.tmp=Path(d.name)
  self.master=m.master_validate(ROOT/'company-master-v319.json',ROOT/'company-master-v318.json',ROOT/'v318-originals-manifest-v319.json')
 def stage(self,current=None,output=None):
  return m.review_and_stage(self.master,ROOT/'approved-ten-company-data-v319.js',current or ROOT/'approved-ten-company-data-v319.js',
   ROOT/'company-master-v318.json',ROOT/'filing-selections-v317.json',ROOT/'approved-ten-baseline-v318.json',
   ROOT/'v317-review-v318.zip',output or self.tmp)
 def test_controlled_count(self):
  self.assertEqual(len(self.master['companies']),110)
  self.assertEqual({k:sum(r['stage']==k for r in self.master['companies']) for k in m.STAGES},m.STAGES)
 def test_50_unique_new_codes(self):
  rows=self.master['companies'];self.assertEqual(len(set(x['ticker'] for x in rows)),110)
  self.assertEqual(len([x for x in rows if x['stage']=='DISCOVERY_PENDING']),50)
 def test_30_original_manifest_ids(self):
  frozen=m.load_json(ROOT/'v318-originals-manifest-v319.json')
  self.assertEqual(len(frozen['companies']),30)
  self.assertEqual(len(set(x['docID'] for x in frozen['companies'])),30)
  self.assertEqual(sum(x['original_zip_bytes'] for x in frozen['companies'])>30_000_000,True)
 def test_frozen_manifest_change_rejected(self):
  x=m.load_json(ROOT/'v318-originals-manifest-v319.json')
  x['companies'][0]['docID']='S100ZZZZ';p=self.tmp/'changed.json';m.dump_json(p,x)
  with self.assertRaisesRegex(m.GateError,'manifest SHA256 mismatch'):
   m.master_validate(ROOT/'company-master-v319.json',ROOT/'company-master-v318.json',p)
 def test_master_changed_prior_name_rejected(self):
  x=copy.deepcopy(self.master);x['companies'][0]['name']='other'
  p=self.tmp/'changed.json';m.dump_json(p,x)
  with self.assertRaisesRegex(m.GateError,'previous master identity'):
   m.master_validate(p,ROOT/'company-master-v318.json',ROOT/'v318-originals-manifest-v319.json')
 def test_master_new_code_duplicate_rejected(self):
  x=copy.deepcopy(self.master);x['companies'][-1]['ticker']=x['companies'][0]['ticker']
  p=self.tmp/'changed.json';m.dump_json(p,x)
  with self.assertRaisesRegex(m.GateError,'duplicate/invalid'):
   m.master_validate(p,ROOT/'company-master-v318.json',ROOT/'v318-originals-manifest-v319.json')
 def test_release_29_includes_exact_source_19(self):
  out=self.stage()
  self.assertEqual(out['staged_public_count'],29)
  arr=m.parse_public_js(self.tmp/'site-ready/company-data.js')
  self.assertEqual(len(arr),29)
  self.assertNotIn('6501',{x['id'] for x in arr})
  self.assertEqual({x['id'] for x in arr[10:]},{r['ticker'] for r in self.master['companies'] if r['stage']=='RELEASE_READY_29'})
 def test_10_baseline_unchanged(self):
  self.stage()
  old=m.parse_public_js(ROOT/'approved-ten-company-data-v319.js')
  new=m.parse_public_js(self.tmp/'site-ready/company-data.js')
  self.assertEqual(new[:10],old)
  self.assertEqual(len(new[:10]),10)
 def test_dataset_metadata_version(self):
  self.stage()
  text=(self.tmp/'site-ready/company-data.js').read_text()
  self.assertIn('window.MCL_DATASET_META = {"version":"3.19"',text)
 def test_release_is_deterministic(self):
  self.stage()
  first=(self.tmp/'site-ready/company-data.js').read_bytes()
  self.stage()
  self.assertEqual(first,(self.tmp/'site-ready/company-data.js').read_bytes())
 def test_idempotent_when_29_already_live(self):
  self.stage()
  path=self.tmp/'site-ready/company-data.js'
  result=self.stage(current=path,output=self.tmp/'second')
  self.assertEqual(result['previous_live_count'],29)
  self.assertEqual(path.read_bytes(),(self.tmp/'second/site-ready/company-data.js').read_bytes())
 def test_edited_29_values_rejected(self):
  self.stage()
  text=(self.tmp/'site-ready/company-data.js').read_text()
  text=text.replace('4368.89','4368.90',1)
  p=self.tmp/'bad.js';p.write_text(text)
  with self.assertRaisesRegex(m.GateError,'unexpected values'):
   self.stage(current=p,output=self.tmp/'bad-out')
 def test_edited_10_values_rejected(self):
  text=(ROOT/'approved-ten-company-data-v319.js').read_text().replace('4368.89','4368.90')
  p=self.tmp/'bad.js';p.write_text(text)
  with self.assertRaises(m.GateError):self.stage(current=p)
 def test_no_git_deploy(self):
  self.stage()
  self.assertEqual(m.load_json(self.tmp/'release-summary-v319.json')['deployed_to_github_pages'],False)
 def test_no_pending_companies_in_site(self):
  self.stage()
  data=m.parse_public_js(self.tmp/'site-ready/company-data.js')
  pending={r['ticker'] for r in self.master['companies'] if r['stage'] not in ('PUBLISHED_BASELINE','RELEASE_READY_29')}
  self.assertFalse({x['id'] for x in data}&pending)
 def test_discovery_empty(self):
  result=m.discover(self.master,self.tmp,date(2026,10,16),2,0,False,listing=lambda day:[])
  self.assertEqual(result['not_found'],50)
  self.assertEqual(result['originals_downloaded'],0)
 def test_discovery_one_valid(self):
  d=date(2026,10,16)
  x={'secCode':'68560','docTypeCode':'120','withdrawalStatus':'0','csvFlag':'1','xbrlFlag':'1',
     'docID':'S100ABCDE','periodStart':'2025-01-01','periodEnd':'2025-12-31',
     'submitDateTime':'2026-03-10 09:00','edinetCode':'E11111','docDescription':'有価証券報告書','filerName':'テスト'}
  result=m.discover(self.master,self.tmp,d,2,0,False,listing=lambda day:[x] if day==d else [])
  self.assertEqual(result['found_unverified'],1)
  self.assertEqual(result['not_found'],49)
  self.assertFalse((self.tmp/'site-ready').exists())
 def test_correction_blocks(self):
  d=date(2026,10,16)
  x={'secCode':'68560','docTypeCode':'120','withdrawalStatus':'0','csvFlag':'1','xbrlFlag':'1',
     'docID':'S100ABCDE','periodStart':'2025-01-01','periodEnd':'2025-12-31',
     'submitDateTime':'2026-03-10 09:00','edinetCode':'E11111','docDescription':'有価証券報告書'}
  y=dict(x,docTypeCode='130',docID='S100ABCD9')
  result=m.discover(self.master,self.tmp,d,1,0,False,listing=lambda day:[x,y])
  self.assertEqual(result['found_unverified'],0)
  self.assertEqual(result['needs_review'],1)
 def test_failed_day_never_selects(self):
  d=date(2026,10,16)
  x={'secCode':'68560','docTypeCode':'120','withdrawalStatus':'0','csvFlag':'1','xbrlFlag':'1',
     'docID':'S100ABCDE','periodStart':'2025-01-01','periodEnd':'2025-12-31',
     'submitDateTime':'2026-03-10 09:00','edinetCode':'E11111','docDescription':'有価証券報告書'}
  def reader(day):
   if day!=d:raise ValueError('simulated outage')
   return [x]
  result=m.discover(self.master,self.tmp,d,2,0,False,listing=reader)
  self.assertEqual(result['days_failed'],1)
  self.assertEqual(result['found_unverified'],0)
 def test_wrong_original_zip_rejected(self):
  d=date(2026,10,16)
  x={'secCode':'68560','docTypeCode':'120','withdrawalStatus':'0','csvFlag':'1','xbrlFlag':'1',
     'docID':'S100ABCDE','periodStart':'2025-01-01','periodEnd':'2025-12-31',
     'submitDateTime':'2026-03-10 09:00','edinetCode':'E11111','docDescription':'有価証券報告書'}
  result=m.discover(self.master,self.tmp,d,1,0,True,listing=lambda day:[x],originals=lambda docid:b'not a ZIP')
  self.assertEqual(result['originals_failed'],1)
  self.assertEqual(result['originals_downloaded'],0)
 def test_real_zip_candidate_staged_without_publish(self):
  d=date(2026,10,16)
  x={'secCode':'68560','docTypeCode':'120','withdrawalStatus':'0','csvFlag':'1','xbrlFlag':'1',
     'docID':'S100ABCDE','periodStart':'2025-01-01','periodEnd':'2025-12-31',
     'submitDateTime':'2026-03-10 09:00','edinetCode':'E11111','docDescription':'有価証券報告書'}
  bio=io.BytesIO()
  with zipfile.ZipFile(bio,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('XBRL/PublicDoc/demo.xbrl','<xbrl/>')
  result=m.discover(self.master,self.tmp,d,1,0,True,listing=lambda day:[x],originals=lambda docid:bio.getvalue())
  self.assertEqual(result['originals_downloaded'],1)
  self.assertTrue((self.tmp/'originals-batch-01/6856-S100ABCDE-type1.zip').is_file())
  self.assertFalse((self.tmp/'site-ready').exists())
 def test_api_key_not_logged(self):
  with self.assertRaisesRegex(m.GateError,'EDINET_API_KEY missing'):
   m.discover(self.master,self.tmp,date(2026,10,16),1,0,False,key=None,listing=None)
 def test_future_date_rejected(self):
  with self.assertRaisesRegex(m.GateError,'future'):
   m.discover(self.master,self.tmp,date(2099,1,1),1,0,False,listing=lambda d:[])
 def test_delay_range_rejected(self):
  with self.assertRaises(m.GateError):m.discover(self.master,self.tmp,date(2026,10,16),1,21,False,listing=lambda d:[])

if __name__=='__main__':unittest.main()
