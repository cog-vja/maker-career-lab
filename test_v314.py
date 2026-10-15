import json, tempfile, unittest, zipfile
from pathlib import Path
from copy import deepcopy
from build_release_v314 import inspect_review,build,verify_approval,ReleaseError,EXPECTED_TICKERS

class V314Tests(unittest.TestCase):
 def setUp(self):
  self.f=tempfile.TemporaryDirectory();self.addCleanup(self.f.cleanup)
  self.p=Path(self.f.name)/'source.zip'
  self.p.write_bytes(Path(__file__).with_name('fixtures-v314.zip').read_bytes())
 def mutate(self,fn):
  with zipfile.ZipFile(self.p) as z:entries={n:z.read(n) for n in z.namelist()}
  fn(entries)
  with zipfile.ZipFile(self.p,'w',zipfile.ZIP_DEFLATED) as z:
   for n,v in entries.items():z.writestr(n,v)
 def test_site_mapping(self):
  r=inspect_review(self.p)
  c=r['companies'][0]
  required={'name','aliases','revenue','revenuePrev','operatingProfit','operatingCashFlow','equityRatio','averageSalary','period','scope','salaryScope','sourceLabel','sourceUrl'}
  self.assertTrue(required.issubset(c.keys()))
  self.assertEqual(len(r['companies']),10)
 def test_all_sixty(self):
  r=inspect_review(self.p);self.assertEqual(r['metrics_verified'],60)
  self.assertEqual(tuple(r['document_ids']),EXPECTED_TICKERS)
 def test_preview_contains_no_real_companies(self):
  out=Path(self.f.name)/'preview';build(self.p,out,'preview')
  js=(out/'company-data.js').read_text()
  self.assertIn('MCL_COMPANIES = [];',js)
  self.assertNotIn('株式会社アドバンテスト',js)
 def test_requires_approval(self):
  with self.assertRaises(ReleaseError):build(self.p,Path(self.f.name)/'publish','publish')
 def test_wrong_approval_digest(self):
  r=inspect_review(self.p)
  a=Path(self.f.name)/'approval.json'
  a.write_text(json.dumps({'release_version':'3.14','approved':True,'artifact_sha256':'bad',
    'document_ids':r['document_ids'],'reviewer_confirmation':'I reviewed and approve the ten companies and sixty metrics for public release'}))
  with self.assertRaises(ReleaseError):verify_approval(a,r)
 def test_approved_release(self):
  r=inspect_review(self.p);a=Path(self.f.name)/'approval.json'
  a.write_text(json.dumps({'release_version':'3.14','approved':True,'artifact_sha256':r['artifact_sha256'],
   'document_ids':r['document_ids'],'reviewer_confirmation':'I reviewed and approve the ten companies and sixty metrics for public release'}))
  out=Path(self.f.name)/'approved';build(self.p,out,'publish',a)
  text=(out/'company-data.js').read_text();self.assertIn('株式会社アドバンテスト',text)
  self.assertIn('"status": "PUBLISHED"',text)
 def test_value_tampering_blocked(self):
  def change(d):
   f=next(x for x in d if x.startswith('6146-') and x.endswith('-v313.json'))
   o=json.loads(d[f]);o['selected_values']['revenue_oku']='1';d[f]=json.dumps(o).encode()
  self.mutate(change)
  with self.assertRaisesRegex(ReleaseError,'value_mismatch'):inspect_review(self.p)
 def test_docid_tampering_blocked(self):
  def change(d):
   f=next(x for x in d if x.startswith('6146-') and x.endswith('-v313.json'))
   o=json.loads(d[f]);o['filing']['docID']='S0000000';d[f]=json.dumps(o).encode()
  self.mutate(change)
  with self.assertRaisesRegex(ReleaseError,'docID_mismatch'):inspect_review(self.p)
 def test_unverified_metric_blocked(self):
  def change(d):
   f=next(x for x in d if x.startswith('6146-') and x.endswith('-v313.json'))
   o=json.loads(d[f]);o['provenance']['average_salary_man']['verification']='UNVERIFIED';d[f]=json.dumps(o).encode()
  self.mutate(change)
  with self.assertRaisesRegex(ReleaseError,'not_source_reconciled'):inspect_review(self.p)
 def test_missing_company_blocked(self):
  def change(d):
   s=json.loads(d['summary.json']);s['companies'].pop();d['summary.json']=json.dumps(s).encode()
  self.mutate(change)
  with self.assertRaises(ReleaseError):inspect_review(self.p)
 def test_previous_block_flag_required(self):
  def change(d):
   s=json.loads(d['summary.json']);s['companies'][0]['publication_status']='PUBLISHED';d['summary.json']=json.dumps(s).encode()
  self.mutate(change)
  with self.assertRaisesRegex(ReleaseError,'unexpected_previous_quality_state'):inspect_review(self.p)
if __name__=='__main__':unittest.main()
