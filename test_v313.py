"""v3.13 safety contracts: malformed, ambiguous, nonconsolidated, and wrong-source facts fail closed."""
import hashlib
import io
import unittest
import zipfile
from copy import deepcopy
from decimal import Decimal
from edinet_v313 import (
    METRICS, DEFINITIONS, original_instance, audit_numeric_original,
    check_zip, percent, reconcile, load_offline_sources,
)

FILING={'docID':'S100TEST','edinetCode':'E00001',
 'periodStart':'2025-04-01','periodEnd':'2026-03-31'}
FACTS={
 'NetSales':('CurrentYearDuration','JPY','100000000000'),
 'NetSalesPrior':('Prior1YearDuration','JPY','80000000000'),
 'OperatingIncome':('CurrentYearDuration','JPY','20000000000'),
 'NetCashProvidedByUsedInOperatingActivities':('CurrentYearDuration','JPY','5000000000'),
 'Assets':('CurrentYearInstant','JPY','100000000000'),
 'ShareholdersEquity':('CurrentYearInstant','JPY','65000000000'),
 'ValuationAndTranslationAdjustments':('CurrentYearInstant','JPY','5000000000'),
 'EquityToAssetRatioSummaryOfBusinessResults':('CurrentYearInstant','pure','0.7'),
 'AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees':(
    'CurrentYearInstant_NonConsolidatedMember','JPY','12000000'),
}

def make_original(*,mutate=None,extra=''):
    f=deepcopy(FACTS)
    if mutate:mutate(f)
    context='''
<xbrli:context id="CurrentYearDuration"><xbrli:entity><xbrli:identifier scheme="test">E00001-000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="Prior1YearDuration"><xbrli:entity><xbrli:identifier scheme="test">E00001-000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-04-01</xbrli:startDate><xbrli:endDate>2025-03-31</xbrli:endDate></xbrli:period></xbrli:context>
<xbrli:context id="CurrentYearInstant"><xbrli:entity><xbrli:identifier scheme="test">E00001-000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>
<xbrli:context id="CurrentYearInstant_NonConsolidatedMember"><xbrli:entity><xbrli:identifier scheme="test">E00001-000</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period><xbrli:scenario><xbrldi:explicitMember dimension="a:ConsolidatedOrNonConsolidatedAxis">a:NonConsolidatedMember</xbrldi:explicitMember></xbrli:scenario></xbrli:context>'''
    for key,item in list(f.items()):
        if key=='NetSalesPrior':continue
    x=['<?xml version="1.0" encoding="UTF-8"?>',
      '<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:a="http://disclosure.edinet-fsa.go.jp/taxonomy/jppfs/2025-11-01/jppfs_cor" xmlns:salary="http://disclosure.edinet-fsa.go.jp/taxonomy/jpcrp/2025-11-01/jpcrp_cor">',
      '<xbrli:unit id="JPY"><xbrli:measure>iso4217:JPY</xbrli:measure></xbrli:unit>',
      '<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>',context]
    for name,(ctx,unit,value) in f.items():
        tag='NetSales' if name=='NetSalesPrior' else name
        ns='salary' if (tag.startswith('AverageAnnualSalary') or tag.startswith('EquityToAssetRatio') or tag.startswith('RatioOfOwnersEquityToGrossAssets')) else 'a'
        x.append('<%s:%s contextRef="%s" unitRef="%s">%s</%s:%s>'%(ns,tag,ctx,unit,value,ns,tag))
    x.append(extra)
    x.append('</xbrli:xbrl>')
    xml=''.join(x).encode()
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('XBRL/PublicDoc/example_E00001-000_2026-03-31.xbrl',xml)
    return b.getvalue()

def base_candidate():
    return {'accounting_standard':{'standard':'JP_GAAP'},'filing':dict(FILING),
    'selected_values':{'revenue_oku':'1000','prior_revenue_oku':'800',
       'operating_profit_oku':'200','operating_cf_oku':'50',
       'equity_ratio_pct':'75.00','average_salary_man':'1200'},
    'quality_gate':{},'provenance':{}}

class TestV313(unittest.TestCase):
 def test_contract_standards(self):
    self.assertEqual(set(DEFINITIONS),{'JP_GAAP','IFRS','US_GAAP'})
    self.assertNotIn('NetAssets',DEFINITIONS['JP_GAAP']['parent_equity'])
 def test_original_jp_gaap_all_six(self):
    r=audit_numeric_original(make_original(),FILING,'JP_GAAP')
    self.assertEqual(r['values']['equity_ratio_pct'],'70.00')
    self.assertEqual(r['values']['average_salary_man'],'1200')
    self.assertEqual(r['values']['prior_revenue_oku'],'800')
 def test_jp_ratio_repair(self):
    result=reconcile(base_candidate(),FILING,make_original())
    self.assertEqual(result['selected_values']['equity_ratio_pct'],'70.00')
    self.assertEqual(result['source_reconciliation']['reconciled_count'],6)
    self.assertEqual(result['source_reconciliation']['correction_count'],1)
    self.assertFalse(result['approved_for_publication'])
    self.assertEqual(result['quality_gate']['status'],'BLOCKED')
 def test_other_metric_disagreement_blocks(self):
    c=base_candidate();c['selected_values']['revenue_oku']='999'
    r=reconcile(c,FILING,make_original())
    self.assertIsNone(r['selected_values']['revenue_oku'])
    self.assertEqual(r['source_reconciliation']['metrics']['revenue_oku']['status'],'BLOCKED_DISAGREEMENT')
 def test_wrong_docid_blocks_all(self):
    c=base_candidate();c['filing']['docID']='S100BAD'
    r=reconcile(c,FILING,make_original())
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
    self.assertTrue(all(r['selected_values'][k] is None for k in METRICS))
 def test_manifest_hash_mismatch_blocks(self):
    r=reconcile(base_candidate(),FILING,make_original(),'0'*64)
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
 def test_duplicate_conflicting_tags_block(self):
    extra='<a:NetSales contextRef="CurrentYearDuration" unitRef="JPY">19999999999</a:NetSales>'
    r=reconcile(base_candidate(),FILING,make_original(extra=extra))
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
 def test_salary_single_company_context_required(self):
    z=make_original()
    with zipfile.ZipFile(io.BytesIO(z)) as a:xml=a.read(a.namelist()[0])
    xml=xml.replace(b'a:NonConsolidatedMember',b'a:ConsolidatedMember')
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as a:a.writestr('XBRL/PublicDoc/example_E00001-000_2026-03-31.xbrl',xml)
    with self.assertRaisesRegex(ValueError,'salary context'):original_instance(b.getvalue(),FILING)
 def test_currency_unit_block(self):
    def wrong(f):f['Assets']=('CurrentYearInstant','pure','100000000000')
    with self.assertRaisesRegex(ValueError,'missing permitted fact'):
     audit_numeric_original(make_original(mutate=wrong),FILING,'JP_GAAP')
 def test_prevent_net_assets_as_equity(self):
    def wrong(f):
     f.pop('ShareholdersEquity');f['NetAssets']=('CurrentYearInstant','JPY','80000000000')
    r=reconcile(base_candidate(),FILING,make_original(mutate=wrong))
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
 def test_disclosed_ratio_conflict_blocks(self):
    def wrong(f):f['EquityToAssetRatioSummaryOfBusinessResults']=('CurrentYearInstant','pure','0.8')
    r=reconcile(base_candidate(),FILING,make_original(mutate=wrong))
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
 def test_nonfinite_blocks(self):
    def bad(f):f['NetSales']=('CurrentYearDuration','JPY','NaN')
    r=reconcile(base_candidate(),FILING,make_original(mutate=bad))
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
 def test_source_bad_zip(self):
    r=reconcile(base_candidate(),FILING,b'not a zip')
    self.assertEqual(r['source_reconciliation']['reconciled_count'],0)
 def test_percent_round_half_up(self):
    self.assertEqual(percent(Decimal('50.005'),Decimal('100')),Decimal('50.01'))
 def test_ifrs_alternate_revenue_alias(self):
    def ifrs(f):
     renames={'NetSales':'RevenueIFRS', 'NetSalesPrior':'RevenueIFRSPrior',
       'OperatingIncome':'OperatingProfitLossIFRS',
       'NetCashProvidedByUsedInOperatingActivities':'NetCashProvidedByUsedInOperatingActivitiesIFRS',
       'Assets':'AssetsIFRS','ShareholdersEquity':'EquityAttributableToOwnersOfParentIFRS',
       'EquityToAssetRatioSummaryOfBusinessResults':'RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults'}
     new={}
     for k,v in f.items():
      if k=='ValuationAndTranslationAdjustments':continue
      if k=='ShareholdersEquity':v=('CurrentYearInstant','JPY','70000000000')
      new[renames.get(k,k)]=v
     f.clear();f.update(new)
    # Prior alias fixture needs same local tag as current, different context.
    b=make_original(mutate=ifrs)
    with zipfile.ZipFile(io.BytesIO(b)) as z:xml=z.read(z.namelist()[0])
    xml=xml.replace(b'RevenueIFRSPrior',b'RevenueIFRS')
    xml=xml.replace(b'/taxonomy/jppfs/2025-11-01/jppfs_cor',b'/taxonomy/jpigp/2025-11-01/jpigp_cor')
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as z:
     z.writestr('XBRL/PublicDoc/example_E00001-000_2026-03-31.xbrl',xml)
    r=audit_numeric_original(out.getvalue(),FILING,'IFRS')
    self.assertEqual(r['values']['revenue_oku'],'1000')
    self.assertEqual(r['values']['prior_revenue_oku'],'800')
    self.assertEqual(r['values']['equity_ratio_pct'],'70.00')
 def test_no_ticker_branching(self):
    import inspect,edinet_v313
    src=inspect.getsource(edinet_v313.audit_numeric_original)
    self.assertNotIn('ticker',src)
    self.assertNotIn('6506',src)
if __name__=='__main__':unittest.main()
