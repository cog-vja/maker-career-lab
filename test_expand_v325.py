import csv
import json
from pathlib import Path
import tempfile
import unittest
from expand_manufacturers_v325 import parse_jpx,edinet_ticker,choose,GateError,stage,emit

class CheckExpansion(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.base=Path(self.tmp.name)
  self.public=self.base/'company-data.js'
  self.public.write_text('window.MCL_COMPANIES = [{"id":"6146","name":"既存社","revenue":10,"revenuePrev":9,"operatingProfit":1,"operatingCashFlow":1,"equityRatio":50,"averageSalary":600}];\nwindow.MCL_DATASET_META = {"count":1};\nwindow.MCL_DEMOS = [];',encoding='utf-8')
  self.jpx=self.base/'jpx.csv'
  with self.jpx.open('w',encoding='utf-8',newline='') as f:
   w=csv.DictWriter(f,fieldnames=['コード','銘柄名','33業種区分']);w.writeheader()
   for x in [('6146','既存社','機械'),('7777','新製造会社','電気機器'),('1111','金融会社','銀行業')]:
    w.writerow(dict(zip(w.fieldnames,x)))
 def tearDown(self):self.tmp.cleanup()
 def test_universe_sector_filtering(self):
  companies,invalid,current=parse_jpx(self.jpx,self.public)
  self.assertEqual([x['ticker'] for x in companies],['6146','7777'])
  self.assertEqual([x['stage'] for x in companies],['ALREADY_PUBLISHED','RESEARCH_UNVERIFIED'])
  self.assertFalse(invalid)
 def test_universe_failure_on_wrong_header(self):
  self.jpx.write_text('証券コード,銘柄名,17業種\n7777,新製造会社,製造業\n',encoding='utf-8')
  with self.assertRaises(GateError):parse_jpx(self.jpx,self.public)
 def test_edinet_code(self):
  self.assertEqual(edinet_ticker('61460'),'6146')
  self.assertEqual(edinet_ticker('123A0'),'123A')
  self.assertIsNone(edinet_ticker('bad'))
 def test_correction_blocks(self):
  def doc(docid,typ):
   return {'docID':docid,'docTypeCode':typ,'withdrawalStatus':'0','xbrlFlag':'1','csvFlag':'1',
           'periodStart':'2025-04-01','periodEnd':'2026-03-31','submitDateTime':'2026-06-01 14:00:00'}
  self.assertEqual(choose([doc('S100AAAA','120'),doc('S100BBBB','130')],__import__('datetime').date(2026,10,20))[0],'CORRECTED_FILING_REVIEW')
 def test_edinet_correction_without_period_is_not_silently_ignored(self):
  from datetime import date
  original={'docID':'S100AAAA','docTypeCode':'120','withdrawalStatus':'0',
   'xbrlFlag':'1','csvFlag':'1','periodStart':'2025-04-01',
   'periodEnd':'2026-03-31','submitDateTime':'2026-06-20 13:00'}
  corrected={'docID':'S100BBBB','docTypeCode':'130','withdrawalStatus':'0',
   'periodStart':None,'periodEnd':None,'submitDateTime':'2026-06-22 15:00'}
  self.assertEqual(choose([original,corrected],date(2026,10,20))[0],
   'CORRECTED_FILING_REVIEW')
 def test_earlier_correction_does_not_block_newer_annual_report(self):
  from datetime import date
  original={'docID':'S100AAAA','docTypeCode':'120','withdrawalStatus':'0',
   'xbrlFlag':'1','csvFlag':'1','periodStart':'2025-04-01',
   'periodEnd':'2026-03-31','submitDateTime':'2026-06-20 13:00'}
  corrected_old={'docID':'S100BBBB','docTypeCode':'130','withdrawalStatus':'0',
   'periodStart':None,'periodEnd':None,'submitDateTime':'2026-05-22 15:00'}
  state,selected=choose([original,corrected_old],date(2026,10,20))
  self.assertEqual(state,'SELECTED');self.assertEqual(selected['docID'],'S100AAAA')
 def test_manual_release_requires_threshold_and_six_metrics(self):
  data=self.base/'review';data.mkdir()
  record={'ticker':'7777','name':'新製造会社','status':'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW',
   'verifiedMetricCount':6,'industry':'電気機器','docID':'S100AAAA','periodStart':'2025-04-01','periodEnd':'2026-03-31',
   'gaap':'JP_GAAP','sourceOriginalSha256':'a'*64,'sourceXbrlSha256':'b'*64,
   'sourcePayloadFingerprint':'c'*64,'verifiedAt':'2026-10-20',
   'metrics':{a:{'status':'SOURCE_RECONCILED','value':'12.3'} for a in
    ('revenue_oku','prior_revenue_oku','operating_profit_oku','operating_cf_oku','equity_ratio_pct','average_salary_man')}}
  emit(data/'7777.json',record)
  approvals=self.base/'approvals.csv';approvals.write_text('ticker,approved\n7777,YES\n',encoding='utf-8')
  class A: pass
  args=A();args.public=str(self.public);args.audit_dir=str(data);args.approvals=str(approvals);args.require_count=1001;args.output=str(self.base/'stage')
  with self.assertRaises(GateError):stage(args)
  self.assertFalse((self.base/'stage'/'company-data.js').exists())
  args.require_count=2
  stage(args)
  staged=(self.base/'stage'/'company-data.js').read_text(encoding='utf-8')
  self.assertIn('"count":2',staged)
  self.assertIn('S100AAAA',staged)
  self.assertIn('既存社',staged)
  record['metrics']['average_salary_man']['status']='BLOCKED'
  emit(data/'7777.json',record)
  with self.assertRaises(GateError):stage(args)


# v3.25.1 isolated source-fixture tests; no EDINET API request required.
import io
import zipfile
from decimal import Decimal
from expand_manufacturers_v325 import _audit_one

XBRL_HEAD = '''<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance"
 xmlns:xbrldi="http://xbrl.org/2006/xbrldi"
 xmlns:jppfs_cor="http://sample.example/jppfs_cor"
 xmlns:jpcrp_cor="http://sample.example/jpcrp_cor"
 xmlns:dei="http://sample.example/jpdei_cor">
{contexts}
<xbrli:unit id="JPY"><xbrli:measure>iso4217:JPY</xbrli:measure></xbrli:unit>
<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>
<dei:AccountingStandardsDEI>Japan GAAP</dei:AccountingStandardsDEI>
{dei}
{facts}
</xbrli:xbrl>'''


def _xbrl_original(standalone=True, declare=True, equity_ratio='0.60',
                   valuation=None, wrong_dimension=False, salary=True):
    ctx_suffix='_NonConsolidatedMember' if standalone else ''
    def context(name,p,dim):
        dimension=''
        if dim:
            member='OtherMember' if wrong_dimension else 'NonConsolidatedMember'
            dimension=(f'<xbrli:scenario><xbrldi:explicitMember '
               f'dimension="jpcrp:ConsolidatedOrNonConsolidatedAxis">'
               f'jpcrp:{member}</xbrldi:explicitMember></xbrli:scenario>')
        return (f'<xbrli:context id="{name}"><xbrli:entity>'
                f'<xbrli:identifier scheme="edinet">E12345</xbrli:identifier>'
                f'{dimension}</xbrli:entity><xbrli:period>{p}</xbrli:period></xbrli:context>')
    periods={
      'CurrentYearDuration':'<xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate>',
      'Prior1YearDuration':'<xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate>',
      'CurrentYearInstant':'<xbrli:instant>2026-03-31</xbrli:instant>',
    }
    contexts=[context(name+ctx_suffix,p,standalone) for name,p in periods.items()]
    sal='CurrentYearInstant_NonConsolidatedMember'
    if not standalone:contexts.append(context(sal,periods['CurrentYearInstant'],True))
    facts=[]
    def fact(name,v,ctx,ns='jppfs_cor',unit='JPY'):
        facts.append(f'<{ns}:{name} contextRef="{ctx}" unitRef="{unit}">{v}</{ns}:{name}>')
    d='CurrentYearDuration'+ctx_suffix
    p='Prior1YearDuration'+ctx_suffix
    i='CurrentYearInstant'+ctx_suffix
    fact('NetSales','1000000000',d)
    fact('NetSales','800000000',p)
    fact('OperatingIncome','200000000',d)
    fact('NetCashProvidedByUsedInOperatingActivities','100000000',d)
    fact('Assets','1000000000',i)
    fact('ShareholdersEquity','600000000',i)
    if valuation is not None: fact('ValuationAndTranslationAdjustments',valuation,i)
    fact('EquityToAssetRatioSummaryOfBusinessResults',equity_ratio,i,ns='jpcrp_cor',unit='pure')
    if salary:fact('AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees','7000000',sal,'jpcrp_cor')
    dei=('<dei:WhetherConsolidatedFinancialStatementsArePreparedDEI>'+('false' if standalone else 'true')+'</dei:WhetherConsolidatedFinancialStatementsArePreparedDEI>') if declare else ''
    raw=XBRL_HEAD.format(contexts='\n'.join(contexts),dei=dei,facts='\n'.join(facts)).encode()
    buff=io.BytesIO()
    with zipfile.ZipFile(buff,'w',compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr('XBRL/PublicDoc/jpcrp000000-asr-E12345-2026-03-31.xbrl',raw)
    return buff.getvalue()

class VerifyV3251Standalone(unittest.TestCase):
    def setUp(self):
        self.filing={'secCode':'77770','docID':'S100AAAA','edinetCode':'E12345',
                     'periodStart':'2025-04-01','periodEnd':'2026-03-31','filerName':'Test Solo'}
    def audit(self,**kwargs):
        return _audit_one(self.filing,'Test Solo','機械',_xbrl_original(**kwargs))
    def test_solo_only_if_dei_false_and_all_six_verified(self):
        r=self.audit()
        self.assertEqual(r['status'],'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW')
        self.assertEqual(r['financialScope'],'提出会社単体')
        self.assertEqual(r['verifiedMetricCount'],6)
        self.assertEqual(Decimal(r['metrics']['equity_ratio_pct']['value']),Decimal('60'))
        self.assertFalse(r['approved_for_publication'])
        self.assertEqual(r['metrics']['revenue_oku']['method'],'dei_declared_standalone_taxonomy')
        self.assertFalse(r['metrics']['equity_ratio_pct']['evidence']['valuation_assumed_zero'])
    def test_solo_mismatch_ratio_is_blocked(self):
        r=self.audit(equity_ratio='0.75')
        self.assertEqual(r['status'],'BLOCKED_INCOMPLETE')
        self.assertEqual(r['verifiedMetricCount'],5)
        self.assertEqual(r['metrics']['equity_ratio_pct']['status'],'BLOCKED')
    def test_solo_context_not_exact_rejected(self):
        with self.assertRaisesRegex(GateError,'dimension'):
            self.audit(wrong_dimension=True)
    def test_solo_without_dei_cannot_fallback(self):
        with self.assertRaises(ValueError):self.audit(declare=False)
    def test_consolidated_legacy_path_unchanged(self):
        r=self.audit(standalone=False,valuation='0')
        self.assertEqual(r['financialScope'],'連結')
        self.assertEqual(r['verifiedMetricCount'],6)
        self.assertEqual(r['status'],'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW')
        self.assertEqual(r['metrics']['equity_ratio_pct']['method'],'standard_taxonomy')
    def test_consolidated_missing_valuation_requires_ratio_crosscheck(self):
        r=self.audit(standalone=False)
        self.assertEqual(r['verifiedMetricCount'],6)
        self.assertEqual(r['metrics']['equity_ratio_pct']['method'],
          'direct_disclosure_corroborated_without_valuation_fact')
        r=self.audit(standalone=False,equity_ratio='0.65')
        self.assertEqual(r['verifiedMetricCount'],5)
    def test_solo_salary_missing_remains_blocked(self):
        r=self.audit(salary=False)
        self.assertEqual(r['status'],'BLOCKED_INCOMPLETE')
        self.assertEqual(r['verifiedMetricCount'],5)
    def test_solo_publication_staging_labels_scope_correctly(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            baseline=root/'company-data.js'
            baseline.write_text('window.MCL_COMPANIES = [{"id":"6146","name":"既存社","revenue":10}]; '
              'window.MCL_DATASET_META = {"count":1}; window.MCL_DEMOS = [];',encoding='utf-8')
            audited=self.audit()
            auditdir=root/'audits';auditdir.mkdir()
            emit(auditdir/'7777.json',audited)
            approvals=root/'approved.csv';approvals.write_text('ticker,approved\n7777,YES\n')
            stage(SimpleNamespace(public=str(baseline),audit_dir=str(auditdir),
                  approvals=str(approvals),require_count=2,output=str(root/'stage')))
            _,_,rows,_=__import__('expand_manufacturers_v325').parse_public(root/'stage'/'company-data.js')
            self.assertEqual(rows[0]['name'],'既存社')
            self.assertEqual(rows[1]['scope'],'提出会社単体（給与も同一法人）')
            self.assertEqual(rows[1]['sourceDocId'],'S100AAAA')
            self.assertEqual(rows[1]['id'],'7777')

if __name__=='__main__':unittest.main()
