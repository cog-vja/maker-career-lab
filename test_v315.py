import unittest,tempfile,json
from pathlib import Path
from build_release_v315 import stage
from build_release_v314 import ReleaseError
ROOT=Path(__file__).parent
class TestV315(unittest.TestCase):
 def test_preview_no_real_companies(self):
  with tempfile.TemporaryDirectory() as d:
   x=stage(ROOT/'fixtures-v314.zip',d,'preview')
   self.assertEqual(x['actual_companies'],0)
   self.assertIn('window.MCL_COMPANIES = [];',(Path(d)/'site-ready/company-data.js').read_text())
 def test_publish_needs_approval(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ReleaseError):stage(ROOT/'fixtures-v314.zip',d,'publish')
 def test_digest_bound_approval(self):
  with tempfile.TemporaryDirectory() as d:
   a=Path(d)/'approval.json';a.write_text(json.dumps({'approved':True,'release_version':'3.14','artifact_sha256':'incorrect'}))
   with self.assertRaises(ReleaseError):stage(ROOT/'fixtures-v314.zip',Path(d)/'out','publish',a)
 def test_absent_template_fails(self):
  with tempfile.TemporaryDirectory() as d:
   with self.assertRaises(ReleaseError):stage(ROOT/'fixtures-v314.zip',Path(d)/'out','preview',site_dir=d)
 def test_mobile_markup(self):
  page=(ROOT/'site-reference/company-check.html').read_text()
  self.assertIn('name="viewport"',page)
  self.assertIn('id="sources"',page)
 def test_file_digests(self):
  with tempfile.TemporaryDirectory() as d:
   x=stage(ROOT/'fixtures-v314.zip',d,'preview')
   self.assertEqual(len(x['file_sha256']),3)
if __name__=='__main__':unittest.main()
