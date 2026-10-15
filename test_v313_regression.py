"""Real EDINET-original regression. Runs when fixture paths are supplied via env.

Artifacts are private and must not be committed to the public GitHub repo.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from edinet_v313 import run_offline

class TestV313RealOriginals(unittest.TestCase):
 def test_all_ten_originals_sixty_metrics(self):
  keys=('V313_CANDIDATES','V313_NINE_ORIGINALS','V313_OMRON_ORIGINAL')
  paths=[os.environ.get(k) for k in keys]
  if not all(paths):self.skipTest('Real original ZIPs not bundled with repository')
  for path in paths:
   if not Path(path).is_file():self.fail('Fixture missing: '+path)
  with tempfile.TemporaryDirectory() as temp:
   rows=run_offline(*paths,temp)
   self.assertEqual(len(rows),10)
   self.assertEqual(sum(x['reconciled_count'] for x in rows),60)
   self.assertEqual(sum(x['correction_count'] for x in rows),6)
   self.assertEqual(sum(x['blocked_metric_count'] for x in rows),0)
   self.assertTrue(all(x['quality_status']=='BLOCKED' for x in rows))
   self.assertTrue(all(x['publication_status']=='UNVERIFIED' for x in rows))
   by_ticker={x['ticker']:x for x in rows}
   self.assertEqual(by_ticker['8035']['equity_ratio_pct'],'71.52')
   self.assertEqual(by_ticker['6954']['equity_ratio_pct'],'89.20')
   self.assertEqual(by_ticker['6841']['equity_ratio_pct'],'65.36')
   self.assertEqual(by_ticker['6645']['equity_ratio_pct'],'55.13')
   summary=json.loads((Path(temp)/'summary.json').read_text(encoding='utf-8'))
   self.assertFalse(summary['public_release_approved'])
if __name__=='__main__':unittest.main()
