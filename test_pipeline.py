import csv, io, json, unittest, zipfile
from edinet_pipeline import extract_metrics

class PipelineTests(unittest.TestCase):
 def sample(self,rows):
  out=io.BytesIO()
  with zipfile.ZipFile(out,'w') as z:
   s=io.StringIO(); w=csv.writer(s,delimiter='\t');w.writerows(rows)
   z.writestr('XBRL_TO_CSV/sample.csv',s.getvalue().encode('utf-16'))
  return out.getvalue()
 def test_extract_and_unit_conversion(self):
  blob=self.sample([['jpcrp_cor:NetSales','CurrentYearDuration','200000000000','JPY'],['jpcrp_cor:OperatingIncome','CurrentYearDuration','10000000000','JPY'],['jpcrp_cor:NetSales','Prior1YearDuration','180000000000','JPY'],['jpcrp_cor:NetCashProvidedByUsedInOperatingActivities','CurrentYearDuration','15000000000','JPY']])
  values,_=extract_metrics(blob)
  self.assertEqual(values['revenue_oku'],'2000')
  self.assertEqual(values['operating_profit_oku'],'100')
  self.assertEqual(values['prior_revenue_oku'],'1800')
  self.assertEqual(values['operating_cf_oku'],'150')
 def test_reject_nonconsolidated_and_conflict(self):
  blob=self.sample([['NetSales','CurrentYearDuration_NonConsolidatedMember','100000000','JPY'],['NetSales','CurrentYearDuration','200000000','JPY'],['Revenue','CurrentYearDuration','300000000','JPY']])
  values,trace=extract_metrics(blob)
  self.assertEqual(values['revenue_oku'],'')
  self.assertTrue(any('conflicting' in str(x) for x in trace['revenue_oku']))
 def test_salary_and_ratio_fail_closed(self):
  blob=self.sample([['AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees','CurrentYearDuration','9000000','JPY'],['EquityToAssetRatio','CurrentYearInstant','0.5','pure']])
  values,_=extract_metrics(blob)
  self.assertEqual(values['average_salary_man'],'900')
  self.assertEqual(values['equity_ratio_pct'],'')

if __name__=='__main__':unittest.main()
