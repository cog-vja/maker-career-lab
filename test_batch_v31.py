import unittest
from unittest.mock import patch
import edinet_batch_v31 as b

class BatchTests(unittest.TestCase):
 def test_match_five_digit_code(self):
  self.assertEqual(b.match({'secCode':'68570'}),'6857')
 def test_reject_unknown(self):
  self.assertIsNone(b.match({'secCode':'99990'}))
 def test_annual_only(self):
  self.assertTrue(b.annual({'docTypeCode':'120','csvFlag':'1','withdrawalStatus':'0'}))
  self.assertFalse(b.annual({'docTypeCode':'130','csvFlag':'1'}))
  self.assertFalse(b.annual({'docTypeCode':'120','csvFlag':'0'}))
 def test_missing_secret(self):
  with patch.dict('os.environ',{'EDINET_API_KEY':''}):
   with self.assertRaises(RuntimeError): b.run(1,0,'/tmp/not-used',1)

if __name__=='__main__':unittest.main()
