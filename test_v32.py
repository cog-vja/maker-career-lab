import io,unittest,zipfile
from edinet_v32 import analyze,parse_file
class TestV32(unittest.TestCase):
 def test_9_column_japanese_header(self):
  hdr='要素ID\t項目名\tコンテキストID\t相対年度\t連結・個別\t期間・時点\tユニットID\t単位\t値\n'
  row='jpcrp_cor:NetSales\t売上高\tCurrentYearDuration\t当期\t連結\t期間\tJPY\t円\t12300000000\n'
  raw=('\ufeff'+hdr+row).encode('utf-16')
  diag,facts=parse_file(raw,'sample.csv')
  self.assertEqual(diag['matched_tags'],1)
  self.assertEqual(facts[0]['value'],'12300000000')
  z=io.BytesIO()
  with zipfile.ZipFile(z,'w') as archive:archive.writestr('sample.csv',raw)
  report=analyze(z.getvalue())
  self.assertEqual(report['selected_values']['revenue_oku'],'123')
 def test_unknown_header_is_not_silently_guessed(self):
  diag,facts=parse_file('a,b,c\n1,2,3\n'.encode(),'sample.csv')
  self.assertEqual(facts,[])
  self.assertEqual(diag['mapping'],{})
if __name__=='__main__':unittest.main()
