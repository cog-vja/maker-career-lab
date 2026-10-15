import unittest
from edinet_v38 import inspect_instance, inspect_original, match_metric
from io import BytesIO
import zipfile
XML=b"""<?xml version="1.0" encoding="UTF-8"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:us-gaap="http://fasb.org/us-gaap/2025-01-31">
 <xbrli:context id="C1"><xbrli:entity><xbrli:identifier scheme="test">1</xbrli:identifier></xbrli:entity>
 <xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:unit id="JPY"><xbrli:measure>iso4217:JPY</xbrli:measure></xbrli:unit>
 <us-gaap:Revenues contextRef="C1" unitRef="JPY" decimals="-6">767351000000</us-gaap:Revenues>
 <us-gaap:OperatingIncomeLoss contextRef="C1" unitRef="JPY" decimals="-6">12500000000</us-gaap:OperatingIncomeLoss>
</xbrli:xbrl>"""
class TestV38(unittest.TestCase):
 def test_metric_family(self):
  self.assertEqual(match_metric('Revenues'),['revenue_oku'])
  self.assertEqual(match_metric('InventoriesNet'),[])
 def test_context_and_unit(self):
  r=inspect_instance(XML,'test.xbrl')
  self.assertEqual(r['candidate_count'],2)
  self.assertEqual(r['candidates'][0]['context']['end'],'2026-03-31')
  self.assertIn('JPY',r['candidates'][0]['unit'])
 def test_original_publicdoc_only(self):
  f=BytesIO()
  with zipfile.ZipFile(f,'w') as z:
   z.writestr('XBRL/PublicDoc/a.xbrl',XML)
   z.writestr('XBRL/AuditDoc/b.xbrl',XML)
  r=inspect_original(f.getvalue())
  self.assertEqual(r['instance_count'],1)
  self.assertEqual(r['reconciliation'],'PENDING')
 def test_unparseable(self):
  with self.assertRaises(Exception):inspect_instance(b'<invalid','bad.xbrl')
if __name__=='__main__':unittest.main()
