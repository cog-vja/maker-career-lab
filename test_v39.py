import unittest
from edinet_v39 import analyze,propose,number,inspect
from io import BytesIO
import zipfile

HTML="""<html><body><h2>連結損益計算書</h2><p>（単位：百万円）</p>
<table><tr><th>科目</th><th>2025年</th><th>2026年</th></tr>
<tr><td>売上高</td><td>715,379</td><td>767,351</td></tr>
<tr><td>営業利益</td><td>53,446</td><td>59,935</td></tr></table></body></html>"""
class TestV39(unittest.TestCase):
 def test_html_consolidated(self):
  d=analyze(HTML,'fixture')
  self.assertEqual(d['table_count'],1)
  self.assertEqual(d['candidates']['revenue_oku'][0]['value_jpy'],'767351000000')
  self.assertEqual(d['candidates']['prior_revenue_oku'][0]['value_jpy'],'715379000000')
  self.assertEqual(d['candidates']['operating_profit_oku'][0]['value_jpy'],'59935000000')
 def test_no_year_blocks(self):
  d=analyze(HTML.replace('2025年','前').replace('2026年','後'),'fixture')
  self.assertEqual(d['candidates']['revenue_oku'],[])
 def test_merged_cells_blocks(self):
  d=analyze(HTML.replace('<td>売上高</td>','<td rowspan="2">売上高</td>'),'fixture')
  self.assertEqual(d['candidates']['revenue_oku'],[])
 def test_multi_numeric_columns_block(self):
  d=analyze(HTML.replace('<td>715,379</td>','<td>1</td><td>715,379</td>'),'fixture')
  self.assertEqual(d['candidates']['revenue_oku'],[])
 def test_no_unit_blocks(self):
  d=analyze(HTML.replace('百万円',''),'fixture')
  self.assertEqual(d['candidates']['revenue_oku'],[])
 def test_unverified(self):
  d=analyze(HTML,'fixture')
  p=propose([d])
  self.assertEqual(p['revenue_oku']['status'],'CANDIDATE_UNVERIFIED')
  self.assertFalse(p['revenue_oku']['approved_for_publication'])
 def test_nonconsolidated_not_assumed(self):
  d=analyze(HTML.replace('連結損益計算書','損益計算書'),'fixture')
  self.assertEqual(d['statements'],[])
 def test_csv_statement_hint(self):
  d=analyze(HTML.replace('連結損益計算書','損益計算書'),'CSV:fixture','income')
  self.assertEqual(len(d['candidates']['revenue_oku']),1)
 def test_package_html(self):
  z=BytesIO()
  with zipfile.ZipFile(z,'w') as f:f.writestr('XBRL/PublicDoc/report.htm',HTML.encode('utf-8'))
  d,w=inspect(z.getvalue(),[])
  self.assertEqual(w,[])
  self.assertEqual(len(d),1)
 def test_parentheses_negative(self):
  self.assertEqual(number('(12,300)'),-12300)
if __name__=='__main__':unittest.main()
