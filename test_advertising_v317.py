import unittest,copy,json
from pathlib import Path
from advertising_v317 import render,AdPolicyError
BASE=json.loads((Path(__file__).parent/'ad-placement-plan-v317.json').read_text(encoding='utf-8'))
class TestAdvertisingV317(unittest.TestCase):
 def setUp(self):
  self.ad=copy.deepcopy(BASE)
  self.ad.update(ads_enabled=True,campaigns=[{'slot':'after-insights','tracking_url':'https://approved.example/path?ref=123',
   'approved_domains':['approved.example'],'advertiser_approved':True,'label':'職務経歴書サービス','description':'サービスの案内'}])
 def test_disabled_default(self):self.assertEqual(render(BASE),'')
 def test_safe_card(self):
  out=render(self.ad)
  self.assertIn('rel="sponsored nofollow noopener noreferrer"',out)
  self.assertIn('PR',out)
 def test_http_rejected(self):
  self.ad['campaigns'][0]['tracking_url']='http://approved.example/path'
  with self.assertRaises(AdPolicyError):render(self.ad)
 def test_unapproved_rejected(self):
  self.ad['campaigns'][0]['advertiser_approved']=False
  with self.assertRaises(AdPolicyError):render(self.ad)
 def test_unapproved_host_rejected(self):
  self.ad['campaigns'][0]['tracking_url']='https://evil.example/path'
  with self.assertRaises(AdPolicyError):render(self.ad)
 def test_html_escaped(self):
  self.ad['campaigns'][0]['label']='サービス <script>click</script>'
  out=render(self.ad)
  self.assertNotIn('<script>',out)
  self.assertIn('&lt;script&gt;',out)
 def test_no_disclosure_rejected(self):
  self.ad['disclosure_template']='おすすめサービス'
  with self.assertRaises(AdPolicyError):render(self.ad)
 def test_financial_table_slot_rejected(self):
  self.ad['campaigns'][0]['slot']='inside-financial-table'
  with self.assertRaises(AdPolicyError):render(self.ad)
if __name__=='__main__':unittest.main()
