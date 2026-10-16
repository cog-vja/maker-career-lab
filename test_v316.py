import hashlib,io,json,os,sys,tempfile,unittest,zipfile
from datetime import date,timedelta
from pathlib import Path
from unittest.mock import patch
from discover_edinet_v316 import (load_master,assert_existing_publication,sec_ticker,
 clean_entry,valid_annual,choose_candidate,run,fetch_original,DiscoveryError)
from validate_site_v316 import stage

ROOT=Path(__file__).parent
APPROVED={"id":"6857","name":"株式会社アドバンテスト","sourceDocId":"S100YKTA","sourceSha256":"a"*64}

def filing(ticker='7729',doc='S100ABCDEFG',end='2026-03-31',dtype='120',**extra):
    obj={'docID':doc,'edinetCode':'E12345','secCode':ticker+'0','filerName':'テスト会社',
         'docDescription':'有価証券報告書','docTypeCode':dtype,
         'submitDateTime':'2026-06-25 10:30','periodStart':'2025-04-01',
         'periodEnd':end,'csvFlag':'1','xbrlFlag':'1','withdrawalStatus':'0'}
    obj.update(extra);return obj

class MasterTests(unittest.TestCase):
    def test_master_exactly_thirty(self):
        m=load_master(ROOT/'company-master-v316.json')
        self.assertEqual(len(m['companies']),30)
        self.assertEqual(sum(c['stage']=='PUBLISHED' for c in m['companies']),10)
        self.assertEqual(sum(c['stage']=='DISCOVERY_PENDING' for c in m['companies']),20)
    def test_all_tickers_unique(self):
        m=load_master(ROOT/'company-master-v316.json')
        self.assertEqual(len(set(c['ticker'] for c in m['companies'])),30)
    def test_no_pending_approved_docids(self):
        m=load_master(ROOT/'company-master-v316.json')
        self.assertTrue(all(c['source_doc_id'] is None and c['edinet_code'] is None for c in m['companies'] if c['stage']=='DISCOVERY_PENDING'))
    def test_no_invalid_extra_entry(self):
        m=load_master(ROOT/'company-master-v316.json');m['companies'].append(dict(m['companies'][-1]))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'m.json';p.write_text(json.dumps(m))
            with self.assertRaises(DiscoveryError):load_master(p)
    def test_approved_data_must_match(self):
        m=load_master(ROOT/'company-master-v316.json')
        data=[{'id':c['ticker'],'name':c['name'],
               'sourceDocId':c['source_doc_id'],'sourceSha256':'a'*64}
              for c in m['companies'] if c['stage']=='PUBLISHED']
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'company-data.js'
            p.write_text('window.MCL_COMPANIES = '+json.dumps(data,ensure_ascii=False)+';')
            r=assert_existing_publication(m,p)
            self.assertEqual(len(r['published_tickers']),10)
    def test_company_master_does_not_contain_values(self):
        m=load_master(ROOT/'company-master-v316.json')
        self.assertFalse(any('revenue' in c or 'averageSalary' in c for c in m['companies']))

class DiscoveryTests(unittest.TestCase):
    def setUp(self):self.as_of=date(2026,10,16)
    def test_sec_code_match(self):
        self.assertEqual(sec_ticker('77290'),'7729')
        self.assertIsNone(sec_ticker('77291'))
        self.assertIsNone(sec_ticker('7729abc'))
    def test_strict_issuer(self):
        self.assertFalse(valid_annual(filing(secCode='68570'),'7729',self.as_of))
    def test_latest_period_selected(self):
        old=filing(doc='S100ABCDEFG',end='2025-03-31',periodStart='2024-04-01')
        new=filing(doc='S100ABCDEFH')
        result=choose_candidate([old,new],'7729',self.as_of)
        self.assertEqual(result['selected']['docID'],'S100ABCDEFH')
        self.assertEqual(result['status'],'DISCOVERED_UNVERIFIED')
    def test_duplicate_latest_blocked(self):
        r=choose_candidate([filing(doc='S100ABCDEFG'),filing(doc='S100ABCDEFH')],'7729',self.as_of)
        self.assertEqual(r['status'],'AMBIGUOUS');self.assertIsNone(r['selected'])
    def test_correction_blocks(self):
        r=choose_candidate([filing(),filing(doc='S100ABCDEFH',dtype='130')],'7729',self.as_of)
        self.assertEqual(r['status'],'CORRECTION_REVIEW');self.assertIsNone(r['selected'])
    def test_correction_other_period_not_blocks(self):
        r=choose_candidate([filing(),filing(doc='S100ABCDEFH',dtype='130',end='2025-03-31')],'7729',self.as_of)
        self.assertEqual(r['status'],'DISCOVERED_UNVERIFIED')
    def test_invalid_docid_rejected(self):
        self.assertFalse(valid_annual(filing(doc='garbage'),'7729',self.as_of))
    def test_future_period_rejected(self):
        self.assertFalse(valid_annual(filing(end='2027-03-31'),'7729',self.as_of))
    def test_csv_missing_rejected(self):
        self.assertFalse(valid_annual(filing(csvFlag='0'),'7729',self.as_of))
    def test_xbrl_missing_rejected(self):
        self.assertFalse(valid_annual(filing(xbrlFlag='0'),'7729',self.as_of))
    def test_withdrawn_rejected(self):
        self.assertFalse(valid_annual(filing(withdrawalStatus='1'),'7729',self.as_of))
    def test_no_hit(self):
        r=choose_candidate([], '7729',self.as_of)
        self.assertEqual(r['status'],'NOT_FOUND')
    def test_api_key_not_in_metadata(self):
        self.assertNotIn('Subscription-Key',clean_entry(filing()))

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master=load_master(ROOT/'company-master-v316.json')
        cls.items=[c for c in cls.master['companies'] if c['stage']=='PUBLISHED']
        cls.approved='window.MCL_COMPANIES = '+json.dumps([
           {'id':c['ticker'],'name':c['name'],'sourceDocId':c['source_doc_id'],'sourceSha256':'x'*64}
           for c in cls.items],ensure_ascii=False)+';\nwindow.MCL_DEMOS=[];\n'
    def create_js(self,dir):
        path=Path(dir)/'company-data.js';path.write_text(self.approved);return path
    def test_publication_preserved_and_discovery_pending(self):
        with tempfile.TemporaryDirectory() as d:
            approved=self.create_js(d)
            day=date(2026,10,16)
            def fake_listing(on):return [filing()] if on==day else []
            result=run(ROOT/'company-master-v316.json',approved,Path(d)/'out',day,2,0,
                       key='test',list_reader=fake_listing)
            self.assertEqual(result['already_published'],10)
            self.assertEqual(result['found_unverified'],1)
            self.assertFalse(result['publication_approved_for_new_companies'])
            self.assertEqual(approved.read_text(),self.approved)
            data=json.loads((Path(d)/'out'/'filing-candidates-v316.json').read_text())
            self.assertEqual(len(data['companies']),20)
    def test_partial_scan_does_not_choose(self):
        with tempfile.TemporaryDirectory() as d:
            approved=self.create_js(d);day=date(2026,10,16)
            def scan(on):
                if on==day:return [filing()]
                raise DiscoveryError('mock-API-error')
            result=run(ROOT/'company-master-v316.json',approved,Path(d)/'out',day,2,0,
                       key='test',list_reader=scan)
            self.assertFalse(result['listing_complete'])
            data=json.loads((Path(d)/'out'/'filing-candidates-v316.json').read_text())
            row=next(r for r in data['companies'] if r['ticker']=='7729')
            self.assertEqual(row['status'],'PARTIAL_SCAN')
            self.assertIsNone(row['selected'])
    def test_bad_publication_data_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            f=Path(d)/'public.js';f.write_text('window.MCL_COMPANIES = [];')
            with self.assertRaises(DiscoveryError):assert_existing_publication(self.master,f)
    def test_all_twenty_candidates_discoverable_without_publishing(self):
        with tempfile.TemporaryDirectory() as d:
            approved=self.create_js(d);day=date(2026,10,16)
            tickers=[c['ticker'] for c in self.master['companies'] if c['stage']=='DISCOVERY_PENDING']
            def fake_listing(on):
                return [filing(ticker=t,doc='S100'+format(i+120000, '08X')) for i,t in enumerate(tickers)] if on==day else []
            result=run(ROOT/'company-master-v316.json',approved,Path(d)/'out',day,1,0,
                       key='test',list_reader=fake_listing)
            self.assertEqual(result['found_unverified'],20)
            self.assertEqual(result['already_published'],10)
            self.assertFalse(result['publication_approved_for_new_companies'])

    def test_original_zip_validation(self):
        buf=io.BytesIO()
        with zipfile.ZipFile(buf,'w') as z:z.writestr('XBRL/PublicDoc/example.xbrl',b'<xbrl/>')
        out=fetch_original('S100ABCDEFG','test',fetch=lambda u,**kw:buf.getvalue())
        self.assertEqual(out,buf.getvalue())
        with self.assertRaises(DiscoveryError):fetch_original('invalid','test',fetch=lambda u,**kw:buf.getvalue())
    def test_site_stage_keeps_approved_js(self):
        with tempfile.TemporaryDirectory() as d:
            approved=self.create_js(d)
            result=stage(ROOT/'company-master-v316.json',approved,ROOT/'site-update',Path(d)/'out')
            self.assertEqual(result['approved_companies'],10)
            self.assertEqual(result['new_companies_auto_published'],0)
            self.assertEqual((Path(d)/'out'/'site-preview'/'company-data.js').read_text(),self.approved)
    def test_missing_site_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            approved=self.create_js(d)
            with self.assertRaises(DiscoveryError):stage(ROOT/'company-master-v316.json',approved,Path(d)/'missing',Path(d)/'out')

if __name__=='__main__':unittest.main()
