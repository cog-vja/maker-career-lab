import io,unittest,zipfile
import edinet_v35 as v

class TestV35(unittest.TestCase):
 def test_gaap_ranking_ignores_lower_conflicting_tags(self):
  facts=[{'element':'AssetsIFRS','context':'CurrentYearInstant','unit':'JPY','value':'1000','file':'x'},
         {'element':'TotalAssetsIFRSSummaryOfBusinessResults','context':'CurrentYearInstant','unit':'JPY','value':'1200','file':'x'},
         {'element':'EquityAttributableToOwnersOfParentIFRS','context':'CurrentYearInstant','unit':'JPY','value':'600','file':'x'}]
  ratio,detail=v.ranked_equity_ratio(facts,{'standard':'IFRS'})
  self.assertEqual(ratio,'60.00')
 def test_same_priority_conflict_blocks(self):
  facts=[{'element':'AssetsIFRS','context':'CurrentYearInstant','unit':'JPY','value':str(n),'file':'x'} for n in (100,200)]
  facts.append({'element':'EquityAttributableToOwnersOfParentIFRS','context':'CurrentYearInstant','unit':'JPY','value':'50','file':'x'})
  ratio,detail=v.ranked_equity_ratio(facts,{'standard':'IFRS'})
  self.assertIsNone(ratio)
 def test_rejects_nonconsolidated(self):
  facts=[{'element':'AssetsIFRS','context':'CurrentYearInstant_NonConsolidatedMember','unit':'JPY','value':'1000','file':'x'}]
  self.assertIsNone(v.ranked_equity_ratio(facts,{'standard':'IFRS'})[0])
 def test_table_simple(self):
  html='<p>（単位：百万円）</p><table><tr><th>科目</th><th>2025年3月期</th><th>2026年3月期</th></tr><tr><td>売上高</td><td>715379</td><td>767351</td></tr></table>'
  curr,_=v.table_candidates(html,('売上高',));prior,_=v.table_candidates(html,('売上高',),True)
  self.assertEqual(curr[0]['value_jpy'],'767351000000');self.assertEqual(prior[0]['value_jpy'],'715379000000')
 def test_rejects_percent_columns(self):
  html='<p>（単位：百万円）</p><table><tr><th>科目</th><th>2025</th><th>比率</th><th>2026</th><th>比率</th></tr><tr><td>売上高</td><td>715379</td><td>100</td><td>767351</td><td>100</td></tr></table>'
  self.assertFalse(v.table_candidates(html,('売上高',))[0])
 def test_rejects_merged_cells(self):
  html='<p>百万円</p><table><tr><td>科目</td><td>2025</td><td>2026</td></tr><tr><td>売上高</td><td colspan="2">100</td></tr></table>'
  self.assertFalse(v.table_candidates(html,('売上高',))[0])
 def test_rejects_no_year(self):
  html='<p>百万円</p><table><tr><td>売上高</td><td>10</td><td>20</td></tr></table>'
  self.assertFalse(v.table_candidates(html,('売上高',))[0])
 def test_us_gaap_no_company_logic(self):
  html='<p>（単位：百万円）</p><table><tr><th>科目</th><th>2025年</th><th>2026年</th></tr><tr><td>売上高</td><td>1</td><td>2</td></tr><tr><td>営業利益</td><td>3</td><td>4</td></tr></table>'
  rows=[{'element':'ConsolidatedStatementOfIncomeUSGAAPTextBlock','html':html,'file':'x'}]
  vals,_,_=v.us_gaap_extract(rows)
  self.assertEqual(vals['revenue_oku'],'0.02');self.assertEqual(vals['prior_revenue_oku'],'0.01')
 def test_no_auto_publish(self):
  q=v.crosscheck({'revenue_oku':'100'},{},{'standard':'IFRS'})
  self.assertFalse(q['ready_for_publication']);self.assertEqual(q['status'],'BLOCKED')
 def test_non_numeric_rejected(self):self.assertIsNone(v.numeric('100.0%'))

if __name__=='__main__':unittest.main()
