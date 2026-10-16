"""Offline and optional real-source test suite for v3.17. No API key required."""
import copy,io,json,os,unittest,zipfile,hashlib
from decimal import Decimal as D
from pathlib import Path
from unittest.mock import patch
import edinet_v317 as x

ROOT=Path(__file__).parent
SPEC=json.loads((ROOT/'filing-selections-v317.json').read_text(encoding='utf-8'))
TOYOTA=next(e for e in SPEC['companies'] if e['ticker']=='7203')
HITACHI=next(e for e in SPEC['companies'] if e['ticker']=='6501')
EXT_URI='http://disclosure.edinet-fsa.go.jp/jpcrp030000/asr/001/E02144-000/2026-03-31/01/2026-06-10'

def fixture_facts(filing=TOYOTA['filing'],values=(50684952000000,)):
    output={}
    for context in ('CurrentYearDuration','Prior1YearDuration'):
        for tag in x.EXTENSION_REVENUE:
            output[(tag,context)]=[{'element':tag,'contextRef':context,'namespace':EXT_URI,
               'unit':['iso4217:JPY'],'value':str(values[0])}]
    return output

class TestV317(unittest.TestCase):
    def test_20_distinct_companies(self):
        self.assertEqual(len(x.validate_selection(SPEC)),20)
    def test_issuer_namespace(self):
        self.assertTrue(x.issuer_namespace(EXT_URI,TOYOTA['filing']))
        self.assertFalse(x.issuer_namespace(EXT_URI,HITACHI['filing']))
    def test_correlated_revenue(self):
        amount,proof=x.extension_revenue(fixture_facts(),TOYOTA['filing'],'CurrentYearDuration')
        self.assertEqual(amount,D('50684952000000'))
        self.assertEqual(len(proof['element_names']),3)
    def test_conflicting_extension_values_blocked(self):
        f=fixture_facts();f[('SalesRevenuesIFRS','CurrentYearDuration')][0]['value']='1'
        with self.assertRaisesRegex(ValueError,'conflicting'):x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration')
    def test_missing_second_tag_blocked(self):
        f=fixture_facts()
        f={k:v for k,v in f.items() if k[0]=='TotalNetRevenuesIFRS'}
        with self.assertRaisesRegex(ValueError,'independent'):x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration')
    def test_no_total_tag_blocked(self):
        f=fixture_facts();f={k:v for k,v in f.items() if k[0]!='TotalNetRevenuesIFRS'}
        with self.assertRaisesRegex(ValueError,'independent'):x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration')
    def test_segment_sales_ignored(self):
        f=fixture_facts();f.pop(('SalesRevenuesIFRS','CurrentYearDuration'))
        f.pop(('OperatingRevenuesIFRSKeyFinancialData','CurrentYearDuration'))
        f[('SalesOfProductsIFRS','CurrentYearDuration')]=[{'element':'SalesOfProductsIFRS','namespace':EXT_URI,'unit':['iso4217:JPY'],'value':'50684952000000'}]
        with self.assertRaises(ValueError):x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration')
    def test_wrong_company_rejected(self):
        with self.assertRaises(ValueError):x.extension_revenue(fixture_facts(),HITACHI['filing'],'CurrentYearDuration')
    def test_wrong_unit_rejected(self):
        f=fixture_facts();f[('TotalNetRevenuesIFRS','CurrentYearDuration')][0]['unit']=['iso4217:USD']
        with self.assertRaises(ValueError):x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration')
    def test_extra_duplicate_consistent_allowed(self):
        f=fixture_facts();f[('TotalNetRevenuesIFRS','CurrentYearDuration')].append(copy.deepcopy(f[('TotalNetRevenuesIFRS','CurrentYearDuration')][0]))
        n,_=x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration');self.assertEqual(n,D('50684952000000'))
    def test_wrong_context_blocked(self):
        f={k:v for k,v in fixture_facts().items() if k[1]=='Prior1YearDuration'}
        with self.assertRaises(ValueError):x.extension_revenue(f,TOYOTA['filing'],'CurrentYearDuration')
    def test_huge_company_count_blocked(self):
        spec=copy.deepcopy(SPEC);spec['companies']=spec['companies']*11
        with self.assertRaises(ValueError):x.validate_selection(spec)
    def test_duplicate_ticker_rejected(self):
        spec=copy.deepcopy(SPEC);spec['companies'][1]['ticker']=spec['companies'][0]['ticker']
        with self.assertRaises(ValueError):x.validate_selection(spec)
    def test_unapproved_only(self):
        spec=copy.deepcopy(SPEC);spec['companies'][0]['publish_approved']=True
        with self.assertRaisesRegex(ValueError,'publication'):x.validate_selection(spec)
    def test_invalid_doc_type(self):
        spec=copy.deepcopy(SPEC);spec['companies'][0]['filing']['docTypeCode']='130'
        with self.assertRaises(ValueError):x.validate_selection(spec)
    def test_partial_fail_closed(self):
        r={'metrics':{}};x.record_failure(r,'operating_profit_oku','not comparable')
        self.assertIsNone(r['metrics']['operating_profit_oku']['value'])
        self.assertFalse(r['metrics']['operating_profit_oku']['approved_for_publication'])
    def test_safe_ad_plan(self):
        ads=json.loads((ROOT/'ad-placement-plan-v317.json').read_text(encoding='utf-8'))
        self.assertFalse(ads['ads_enabled'])
        self.assertEqual(ads['campaigns'],[])
        self.assertIn('PR',ads['disclosure_template'])
    def test_real_source_20_companies_if_available(self):
        artifact=os.getenv('V317_ORIGINAL_ARTIFACT')
        if not artifact:self.skipTest('Set V317_ORIGINAL_ARTIFACT to verify all source originals offline')
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            result=x.run(ROOT/'filing-selections-v317.json',temp,'offline',artifact,delay=0)
            self.assertEqual(result['companies_processed'],20)
            self.assertEqual(result['reconciled_metrics'],119)
            self.assertEqual(result['blocked_metrics'],1)
            self.assertEqual(result['fully_reconciled_companies'],19)
            toy=json.loads(next(Path(temp).glob('7203-*-v317.json')).read_text())
            hit=json.loads(next(Path(temp).glob('6501-*-v317.json')).read_text())
            self.assertEqual(toy['metrics']['revenue_oku']['value'],'506849.52')
            self.assertEqual(toy['metrics']['prior_revenue_oku']['value'],'480367.04')
            self.assertEqual(hit['metrics']['operating_profit_oku']['status'],'BLOCKED')
            self.assertEqual(hit['supplemental']['value_oku'],'11992.75')
            self.assertFalse(result['public_release_approved'])



class SourcePayloadIntegrityTests(unittest.TestCase):
    def _archive(self, compression, year=2026, mutated=False):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w',compression=compression) as z:
            for name,data in (
                ('XBRL/PublicDoc/main.xbrl',b'<xbrl>trusted</xbrl>' if not mutated else b'<xbrl>changed</xbrl>'),
                ('XBRL/PublicDoc/page.htm',b'<html>source</html>'),
                ('XBRL/AuditDoc/notes.txt',b'notes')):
                meta=zipfile.ZipInfo(name,date_time=(year,1,2,3,4,6))
                meta.compress_type=compression
                z.writestr(meta,data)
        return out.getvalue()
    def test_repacked_zip_with_same_payload_passes(self):
        a=self._archive(zipfile.ZIP_STORED,2025)
        b=self._archive(zipfile.ZIP_DEFLATED,2026)
        self.assertNotEqual(hashlib.sha256(a).hexdigest(),hashlib.sha256(b).hexdigest())
        self.assertEqual(x.source_payload_manifest(a)[0],x.source_payload_manifest(b)[0])
    def test_real_payload_mutation_fails(self):
        a=self._archive(zipfile.ZIP_STORED)
        b=self._archive(zipfile.ZIP_STORED,mutated=True)
        self.assertNotEqual(x.source_payload_manifest(a)[0],x.source_payload_manifest(b)[0])
    def test_missing_required_payload_anchor_fails(self):
        buff=io.BytesIO()
        with zipfile.ZipFile(buff,'w') as z:z.writestr('XBRL/PublicDoc/a.htm','x')
        with self.assertRaisesRegex(ValueError,'PublicDoc'):
            x.source_payload_manifest(buff.getvalue())
    def test_duplicate_member_names_fail(self):
        buff=io.BytesIO()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',UserWarning)
            with zipfile.ZipFile(buff,'w') as z:
                z.writestr('XBRL/PublicDoc/a.xbrl',b'a')
                z.writestr('XBRL/PublicDoc/a.xbrl',b'a')
        with self.assertRaisesRegex(ValueError,'duplicate'):
            x.source_payload_manifest(buff.getvalue())
    def test_missing_frozen_content_digest_rejected(self):
        s=copy.deepcopy(SPEC)
        del s['companies'][0]['source_payload_sha256']
        with self.assertRaisesRegex(ValueError,'payload hash'):
            x.validate_selection(s)

if __name__=='__main__':unittest.main()
