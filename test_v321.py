import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import date
import json
import re
import monthly_edinet_v321 as m

ROOT=Path(__file__).parent
TEST_PUBLIC=ROOT/'company-data.js' if (ROOT/'company-data.js').exists() else ROOT/'test-fixtures/company-data-v320.js'

class TestMasterAndBaseline(unittest.TestCase):
    def test_master_has_200_nonduplicate(self):
        master=m.read_master(ROOT/'company-master-v321.json')
        self.assertEqual(len(master),200)
        self.assertEqual(sum(r['stage']=='RESEARCH_UNVERIFIED' for r in master),90)
    def test_real_public_dataset_frozen_102(self):
        p=TEST_PUBLIC
        self.assertEqual(len(m.read_public(p)[0]),102)
    def test_choose_single_original(self):
        r=self.doc('S1001234','2026-06-30')
        selected=m.select([r],None,date(2026,10,20))
        self.assertEqual(selected['status'],'NEW_FILING_UNVERIFIED')
    def test_duplicates_blocked(self):
        a=self.doc('S1001234','2026-06-30')
        b=self.doc('S1001235','2026-06-30')
        self.assertEqual(m.select([a,b],None,date(2026,10,20))['status'],'AMBIGUOUS')
    def test_amendments_blocked(self):
        a=self.doc('S1001234','2026-06-30')
        b=self.doc('S1001235','2026-06-30');b['docTypeCode']='130'
        self.assertEqual(m.select([a,b],None,date(2026,10,20))['status'],'CORRECTION_REVIEW')
    def test_amendment_only_blocked(self):
        b=self.doc('S1001235','2026-06-30');b['docTypeCode']='130'
        self.assertEqual(m.select([b],None,date(2026,10,20))['status'],'CORRECTION_REVIEW')
    def test_existing_same_doc_unchanged(self):
        a=self.doc('S1001234','2026-06-30')
        old={'period':'2025-07-01〜2026-06-30','sourceDocId':'S1001234'}
        self.assertEqual(m.select([a],old,date(2026,10,20))['status'],'UNCHANGED')
    def test_existing_same_period_changed_blocked(self):
        a=self.doc('S1001234','2026-06-30')
        old={'period':'2025-07-01〜2026-06-30','sourceDocId':'S100XXXX'}
        self.assertEqual(m.select([a],old,date(2026,10,20))['status'],'OLD_OR_RESTATED_REVIEW')
    def test_no_filing_no_publish(self):
        master=ROOT/'company-master-v321.json'
        pub=TEST_PUBLIC
        with TemporaryDirectory() as temp:
            result=m.run(master,pub,temp,days=1,delay=0,as_of=date(2026,10,20),day_fetcher=lambda _:[],zip_fetcher=lambda _:self.fail('zip should not be fetched'))
            self.assertEqual(result['published_updates_fully_reconciled'],0)
            self.assertFalse((Path(temp)/'company-data-v321-REVIEW-ONLY.js').exists())
            self.assertEqual(len(json.loads((Path(temp)/'monthly-candidates-v321.json').read_text())),200)
    def test_90_candidate_discovery_empty_safe(self):
        from discover_90_v321 import discover
        with TemporaryDirectory() as temp:
            result=discover(ROOT/'company-master-v321.json',temp,days=1,download=False,delay=0,as_of=date(2026,10,20),day_fetch=lambda _:[])
            self.assertEqual(len(result),90)
            self.assertTrue(all(x['status']=='NOT_FOUND' for x in result))
            self.assertFalse(list(Path(temp).rglob('*.zip')))
    def test_proposed_keeps_102_and_other_rows(self):
        rows,original=m.read_public(TEST_PUBLIC)
        r=dict(rows[0]);r['averageSalary']+=1
        changed=m.proposed_js(original,{r['id']:r})
        with TemporaryDirectory() as temp:
            p=Path(temp)/'company-data.js';p.write_text(changed)
            c=m.read_public(p)[0]
            self.assertEqual(len(c),102)
            self.assertEqual(c[1:],rows[1:])
    @staticmethod
    def doc(docid,period):
        return {'docID':docid,'docTypeCode':'120','periodStart':'2025-07-01','periodEnd':period,'submitDateTime':'2026-09-20 09:00:00',
                'withdrawalStatus':'0','xbrlFlag':'1','csvFlag':'1','secCode':'68570','edinetCode':'E00000','filerName':'試験会社'}

if __name__=='__main__':unittest.main()
