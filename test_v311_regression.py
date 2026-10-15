"""Optional locally cached nine-company outcome regression (no EDINET calls)."""
import json,os,unittest,zipfile
from pathlib import Path
from edinet_v311 import integrate,METRICS
from edinet_v310 import extract_original_type1,load_original

class BaselineRegression(unittest.TestCase):
 def test_v36_all_ten_preserved_with_only_omron_filled(self):
  archive=os.getenv('V36_REVIEW_ZIP')
  original_path=os.getenv('OMRON_ORIGINAL_ZIP')
  if not archive or not original_path or not Path(archive).exists() or not Path(original_path).exists():
   self.skipTest('optional frozen v3.6 results + original not supplied')
  original=extract_original_type1(load_original(original_path),'S100YG81')
  with zipfile.ZipFile(archive) as z:
   files=[n for n in z.namelist() if n.endswith('-v36.json')]
   self.assertEqual(len(files),10)
   total=0
   for n in files:
    base=json.loads(z.read(n));filing=base['filing']
    if filing['docID']=='S100YG81':
     merged=integrate(base,filing,original)
     self.assertEqual(len(merged['source_review']['merges']),5)
    else:
     merged=integrate(base,filing)
     self.assertEqual(base['selected_values'],merged['selected_values'])
     self.assertEqual(base['derived_values'],merged['derived_values'])
     self.assertFalse(merged['source_review']['merges'])
    self.assertEqual(merged['quality_gate']['status'],'BLOCKED')
    total+=sum(merged['selected_values'].get(k) is not None for k in METRICS)
   self.assertEqual(total,60)
if __name__=='__main__':unittest.main()
