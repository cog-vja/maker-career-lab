#!/usr/bin/env python3
"""v3.20 source-integrity, publication, privacy and advertising regression tests."""
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import edinet_v320 as m

BASE=Path(__file__).resolve().parent

class QualityGateTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.master,cls.baseline,cls.audit=m.validate_frozen(BASE/'company-master-v319.json',BASE/'baseline-29-v320.js',BASE/'original-audit-v320.json')
  cls.merged=m.build_public(cls.master,cls.baseline,cls.audit)

 def test_source_counts(self):
  self.assertEqual(len(self.audit),79)
  self.assertEqual(sum(r['reconciled_count'] for r in self.audit),458)
  self.assertEqual(sum(r['reconciled_count']==6 for r in self.audit),73)
 def test_102_unique_and_prior_29_unchanged(self):
  self.assertEqual(len(self.merged),102)
  self.assertEqual(self.merged[:29],self.baseline)
  self.assertEqual(len(set(x['id'] for x in self.merged)),102)
 def test_blocked_never_published(self):
  self.assertFalse({'6501','5713','6301','7011','7012','6965','7741','7751'} & {x['id'] for x in self.merged})
 def test_every_new_row_has_6_valid_metrics(self):
  for x in self.merged[29:]:
   for k in m.PUBLIC_FIELDS:self.assertIsInstance(x[k],(int,float))
   self.assertEqual(x['salaryScope'],'提出会社単体')
   self.assertRegex(x['sourceDocId'],r'^S[0-9A-Z]{7,15}$')
   self.assertRegex(x['sourceSha256'],r'^[a-f0-9]{64}$')
   self.assertIn(x['accountingStandard'],('JP_GAAP','IFRS'))
 def test_data_js_semantically_same(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'company-data.js';p.write_text(m.generate_js(self.merged))
   a,_=m.public_js_read(p)
   self.assertEqual(a,self.merged)
 def test_baseline_tamper_denied(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'baseline.js';p.write_bytes((BASE/'baseline-29-v320.js').read_bytes()+b' ')
   with self.assertRaises(m.GateError):m.validate_frozen(BASE/'company-master-v319.json',p,BASE/'original-audit-v320.json')
 def test_source_tamper_denied(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'audit.json';p.write_bytes((BASE/'original-audit-v320.json').read_bytes()+b' ')
   with self.assertRaises(m.GateError):m.validate_frozen(BASE/'company-master-v319.json',BASE/'baseline-29-v320.js',p)
 def test_no_static_ad_links(self):
  p=BASE/'site-update-v320/company-check.html'
  s=p.read_text();self.assertIn('id="affiliate-slot"',s)
  self.assertIn('id="affiliate-disclosure"',s)
  self.assertIn(' hidden',s)
 def test_html_company_catalog(self):
  h=(BASE/'site-update-v320/company-check.html').read_text()
  self.assertIn('id="catalog-search"',h)
  self.assertIn('id="company-catalog"',h)
  self.assertIn('affiliate-render.js',h)
 def test_default_ads_disabled(self):
  self.assertTrue(m.validate_ads(m.load(BASE/'affiliate-v320.json')))
  self.assertFalse(m.load(BASE/'affiliate-v320.json')['enabled'])
 def test_malicious_ad_urls_rejected(self):
  legit={'version':'3.20','enabled':True,'placements':[{'slot':'compare-below-results','label':'案内を開く','sponsor':'広告主','url':'https://px.a8.net/svt/ejp?a8mat=TEST'}]}
  self.assertTrue(m.validate_ads(legit))
  for url in ('http://px.a8.net/bad','https://px.a8.net.evil.tld/svt/','https://evil.tld/','javascript:alert(1)','https://evil@px.a8.net/x','https://px.a8.net:443/x'):
   changed=copy.deepcopy(legit);changed['placements'][0]['url']=url
   if url.endswith(':443/x'):
    # Browser permits explicit default ports; review gate conservatively declines.
    pass
   with self.subTest(url=url),self.assertRaises(m.GateError):m.validate_ads(changed)
 def test_html_in_ad_labels_rejected(self):
  data={'version':'3.20','enabled':True,'placements':[{'slot':'compare-below-results','label':'<script>','sponsor':'A8','url':'https://px.a8.net/path'}]}
  with self.assertRaises(m.GateError):m.validate_ads(data)
 def test_zip_recompression_not_rejected(self):
  contents={'XBRL/PublicDoc/report.xbrl':b'<xbrl><fact value="1"/></xbrl>','note.txt':b'note'}
  outputs=[]
  for compression in (zipfile.ZIP_DEFLATED,zipfile.ZIP_STORED):
   b=io.BytesIO()
   with zipfile.ZipFile(b,'w',compression=compression) as z:
    for name,raw in contents.items():z.writestr(name,raw)
   outputs.append(b.getvalue())
  self.assertNotEqual(m.sha(outputs[0]),m.sha(outputs[1]))
  self.assertEqual(m.fingerprint_zip(outputs[0]),m.fingerprint_zip(outputs[1]))
 def test_changed_xbrl_rejected_by_fingerprint(self):
  def wrap(s):
   b=io.BytesIO()
   with zipfile.ZipFile(b,'w') as z:z.writestr('XBRL/PublicDoc/x.xbrl',s)
   return b.getvalue()
  self.assertNotEqual(m.fingerprint_zip(wrap(b'1')),m.fingerprint_zip(wrap(b'2')))
 def test_live_gate_required_without_explicit_local_override(self):
  class Fake:pass
  a=Fake();a.master=BASE/'company-master-v319.json';a.baseline=BASE/'baseline-29-v320.js';a.audit=BASE/'original-audit-v320.json';a.ads=BASE/'affiliate-v320.json';a.site_templates=BASE/'site-update-v320';a.output='not-created';a.live_result=None;a.live_progress=None;a.allow_local_frozen=False
  with self.assertRaises(m.GateError):m.stage(a)
 def test_manual_publication_only(self):
  class Fake:pass
  with tempfile.TemporaryDirectory() as d:
   a=Fake();a.master=BASE/'company-master-v319.json';a.baseline=BASE/'baseline-29-v320.js';a.audit=BASE/'original-audit-v320.json';a.ads=BASE/'affiliate-v320.json';a.site_templates=BASE/'site-update-v320';a.output=d;a.live_result=None;a.live_progress=None;a.allow_local_frozen=True
   report=m.stage(a)
   self.assertFalse(report['deployed_to_pages']);self.assertFalse(report['publication_approved_by_automation'])
   self.assertEqual(len(list((Path(d)/'site-ready').iterdir())),5)
   self.assertIn('"enabled":false', (Path(d)/'site-ready/affiliate-config.js').read_text())

if __name__=='__main__':unittest.main()
