import json, unittest, hashlib, zipfile, io
from copy import deepcopy
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import release_v322 as r
import discover_25_v322 as d
import monthly_edinet_v322 as m

ROOT=Path(__file__).resolve().parent
FIXTURE=ROOT/'fixtures/verification-offline-v322.json'

class TestFrozenRelease(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.master,cls.base,cls.audit,cls.locks=r.validate_inputs()
  cls.good=r.read_json(FIXTURE)

 def test_unique_225(self):
  self.assertEqual(len({x['ticker'] for x in self.master['companies']}),225)
 def test_102_baseline_unique(self):
  self.assertEqual(len(self.base),102)
  self.assertEqual(len({x['id'] for x in self.base}),102)
 def test_eighty_seven_source_entries(self):
  self.assertEqual(len(self.audit),87)
  self.assertEqual(len(self.locks),87)
 def test_83_eligible_and_four_blocked(self):
  self.assertEqual(sum(x['reconciled_count']==6 for x in self.audit),83)
  self.assertEqual(sum(x['reconciled_count']<6 for x in self.audit),4)
 def test_25_unverified_target_list(self):
  self.assertEqual(sum(x['stage']=='ADDITIONAL_RESEARCH_UNVERIFIED' for x in self.master['companies']),25)
 def test_all_83_publication_flags_false_in_source(self):
  self.assertTrue(all(not v.get('approved_for_publication') for x in self.audit for v in x['metrics'].values()))
 def test_staging_generates_185_rows_and_keeps_baseline_102(self):
  with TemporaryDirectory() as tmp:
   summary=r.stage(FIXTURE,tmp,current_js=ROOT/'baseline-102-v322.js')
   merged,meta,demos=r.js_dataset(Path(tmp)/'site-ready/company-data.js')
   self.assertEqual(merged[:102],self.base)
   self.assertEqual(len(merged),185)
   self.assertEqual(summary['staged_public_count'],185)
   self.assertFalse(summary['automatically_deployed'])
   self.assertEqual(meta['independent_EDINET_CSV_crosscheck'],False)
   self.assertEqual(len(list((Path(tmp)/'site-ready').iterdir())),6)
 def test_missing_source_proof_denied(self):
  with TemporaryDirectory() as tmp:
   p=Path(tmp)/'verification.json';j=deepcopy(self.good);j['rows'].pop();p.write_text(json.dumps(j))
   with self.assertRaises(r.GateError):r.stage(p,tmp)
 def test_wrong_xbrl_hash_denied(self):
  with TemporaryDirectory() as tmp:
   p=Path(tmp)/'verification.json';j=deepcopy(self.good);j['rows'][0]['xbrl_sha256']='0'*64;p.write_text(json.dumps(j))
   with self.assertRaisesRegex(r.GateError,'release evidence conflict'):r.stage(p,tmp)
 def test_wrong_company_id_denied(self):
  with TemporaryDirectory() as tmp:
   p=Path(tmp)/'verification.json';j=deepcopy(self.good);j['rows'][0]['ticker']='9999';p.write_text(json.dumps(j))
   with self.assertRaises(r.GateError):r.stage(p,tmp)
 def test_duplicate_company_proof_denied(self):
  with TemporaryDirectory() as tmp:
   p=Path(tmp)/'verification.json';j=deepcopy(self.good);j['rows'][1]['ticker']=j['rows'][0]['ticker'];p.write_text(json.dumps(j))
   with self.assertRaises(r.GateError):r.stage(p,tmp)
 def test_changed_current_published_values_denied(self):
  with TemporaryDirectory() as tmp:
   changed=(ROOT/'baseline-102-v322.js').read_text().replace('4368.89','4368.90',1)
   p=Path(tmp)/'company-data.js';p.write_text(changed)
   with self.assertRaisesRegex(r.GateError,'current site baseline changed'):r.stage(FIXTURE,tmp,current_js=p)
 def test_185_input_allowed_when_original_102_preserved(self):
  with TemporaryDirectory() as tmp:
   r.stage(FIXTURE,tmp)
   p=Path(tmp)/'site-ready/company-data.js'
   summary=r.stage(FIXTURE,tmp,current_js=p)
   self.assertEqual(summary['staged_public_count'],185)
 def test_102_data_meta_unchanged(self):
  self.assertEqual(r.js_dataset(ROOT/'baseline-102-v322.js')[1]['count'],102)
 def test_report_not_falsely_csv_verified(self):
  self.assertIs(self.good['crosschecked_against_independent_EDINET_CSV'],False)
 def test_all_original_evidence_hex_sha(self):
  for x in self.locks.values():
   self.assertEqual(len(x['xbrl_sha256']),64)
   int(x['xbrl_sha256'],16)
 def test_identity_of_first_real_source_and_repack(self):
  # Verify one real frozen source, and repackaging the container without changing XML.
  batch='/mnt/data/edinet-v321-originals-batch-01.zip'
  if not Path(batch).exists():self.skipTest('original ZIPs absent on GitHub runner')
  with zipfile.ZipFile(batch) as z:raw=z.read('1301-S100YE8K.zip')
  orig=next(x for x in self.audit if x['ticker']=='1301')
  proof=r.verify_one(raw,orig,self.locks['1301'])
  self.assertEqual(proof['verified_metrics'],6)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   buf=io.BytesIO()
   with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_STORED) as y:
    for name in z.namelist():y.writestr(name,z.read(name))
  proof2=r.verify_one(buf.getvalue(),orig,self.locks['1301'])
  self.assertEqual(proof2['xbrl_sha256'],proof['xbrl_sha256'])
  self.assertNotEqual(proof2['observed_zip_sha256'],proof['observed_zip_sha256'])
 def test_xbrl_content_tamper_blocked(self):
  batch='/mnt/data/edinet-v321-originals-batch-01.zip'
  if not Path(batch).exists():self.skipTest('original ZIPs absent on GitHub runner')
  with zipfile.ZipFile(batch) as z:raw=z.read('1301-S100YE8K.zip')
  filename,xml=r.uncompressed_xbrl(raw)
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   buf=io.BytesIO()
   with zipfile.ZipFile(buf,'w') as y:
    for name in z.namelist():
     content=z.read(name)
     if name==filename:content=content.replace(b'334612000000',b'334612000001',1)
     y.writestr(name,content)
  orig=next(x for x in self.audit if x['ticker']=='1301')
  with self.assertRaisesRegex(r.GateError,'frozen XBRL contents changed'):r.verify_one(buf.getvalue(),orig,self.locks['1301'])

class TestMonthlyAndResearch(unittest.TestCase):
 def test_dynamic_read_102(self):
  rows,_=m.read_public(ROOT/'baseline-102-v322.js')
  self.assertEqual(len(rows),102)
 def test_dynamic_read_185(self):
  rows,_=m.read_public(ROOT/'offline-validation/site-ready/company-data.js') if (ROOT/'offline-validation/site-ready/company-data.js').exists() else m.read_public(ROOT/'baseline-102-v322.js')
  self.assertIn(len(rows),(102,185))
 def test_monthly_225_master(self):
  self.assertEqual(len(m.read_master(ROOT/'company-master-v322.json')),225)
 def test_monthly_no_new_filing_no_update_102(self):
  with TemporaryDirectory() as tmp:
   result=m.run(ROOT/'company-master-v322.json',ROOT/'baseline-102-v322.js',tmp,days=1,delay=0,
      day_fetcher=lambda d:[],zip_fetcher=lambda d:self.fail('unexpected ZIP'),as_of=date(2026,10,17))
   self.assertEqual(result['published_count'],102)
   self.assertEqual(result['published_updates_fully_reconciled'],0)
   self.assertFalse(list(Path(tmp).glob('*REVIEW-ONLY.js')))
 def test_monthly_no_new_filing_no_update_185(self):
  with TemporaryDirectory() as tmp:
   r.stage(ROOT/'fixtures/verification-offline-v322.json',tmp)
   pub=Path(tmp)/'site-ready/company-data.js'
   result=m.run(ROOT/'company-master-v322.json',pub,Path(tmp)/'monthly',days=1,delay=0,
       day_fetcher=lambda d:[],zip_fetcher=lambda d:self.fail('unexpected ZIP'),as_of=date(2026,10,17))
   self.assertEqual(result['published_count'],185)
   self.assertEqual(result['published_updates_fully_reconciled'],0)
 def test_25_research_not_published_with_no_filings(self):
  with TemporaryDirectory() as tmp:
   res=d.run(ROOT/'company-master-v322.json',tmp,days=1,download=False,delay=0,
        day_fetch=lambda d:[],as_of=date(2026,10,17))
   self.assertEqual(len(res),25)
   self.assertTrue(all(x['status']=='NOT_FOUND' for x in res))
 def test_25_discovery_rejects_invalid_days(self):
  with self.assertRaises(d.m.UpdateError):d.run(ROOT/'company-master-v322.json','unused',days=401,download=False,day_fetch=lambda d:[])
 def test_edinet_ambiguity_not_auto_accepted(self):
  a={'docID':'S100AAAA','docTypeCode':'120','withdrawalStatus':'0','xbrlFlag':'1','csvFlag':'1',
     'periodStart':'2025-04-01','periodEnd':'2026-03-31','submitDateTime':'2026-06-01 12:00:00','secCode':'57150'}
  b={**a,'docID':'S100BBBB'}
  self.assertEqual(m.select([a,b],None,date(2026,10,17))['status'],'AMBIGUOUS')
 def test_corrections_require_manual_review(self):
  a={'docID':'S100AAAA','docTypeCode':'120','withdrawalStatus':'0','xbrlFlag':'1','csvFlag':'1',
     'periodStart':'2025-04-01','periodEnd':'2026-03-31','submitDateTime':'2026-06-01 12:00:00','secCode':'57150'}
  b={**a,'docID':'S100BBBB','docTypeCode':'130'}
  self.assertEqual(m.select([a,b],None,date(2026,10,17))['status'],'CORRECTION_REVIEW')

if __name__=='__main__':unittest.main()
