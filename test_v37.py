import unittest,io,zipfile
import edinet_v37 as v37

class TestStructure(unittest.TestCase):
    def test_literal_html(self):
        v=v37.structural_view('<table><tr><td>1</td></tr></table>')
        self.assertEqual(v[0]['grid_tables'],1)
    def test_escaped_html(self):
        v=v37.structural_view('&lt;table&gt;&lt;tr&gt;&lt;td&gt;1&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;')
        self.assertEqual(v[0]['grid_tables'],0)
        self.assertEqual(v[1]['grid_tables'],1)
    def test_double_escaped(self):
        v=v37.structural_view('&amp;lt;table&amp;gt;&amp;lt;tr&amp;gt;&amp;lt;td&amp;gt;1&amp;lt;/td&amp;gt;&amp;lt;/tr&amp;gt;&amp;lt;/table&amp;gt;')
        self.assertEqual(v[-1]['grid_tables'],1)
    def test_plain_text(self):
        self.assertEqual(v37.structural_view('売上高 123')[0]['grid_tables'],0)
    def test_csv_zip(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            csv_text = '要素ID,コンテキストID,値\nConsolidatedStatementOfIncomeUSGAAPTextBlock,CurrentYearDuration,"&lt;table&gt;&lt;tr&gt;&lt;td&gt;売上高&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;"\n'
            z.writestr('a.csv',csv_text.encode('utf-16'))
        report=v37.csv_inspection(buf.getvalue())
        self.assertEqual(len(report['textblocks']),1)
        self.assertEqual(report['textblocks'][0]['structure'][1]['grid_tables'],1)
        self.assertNotIn('html',report['textblocks'][0])

if __name__=='__main__':unittest.main()
