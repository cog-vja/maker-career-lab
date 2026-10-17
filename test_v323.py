"""Fast offline release gates; no EDINET network access in unit tests."""
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import release_v323 as v
import monthly_edinet_v323 as monthly

ROOT=Path(__file__).resolve().parent
FIXTURE=ROOT/'fixtures'/'verification-offline-v323.json'

class V323ReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prior,cls.demos,cls.audit,cls.locks,cls.master=v.prepare()
        cls.fixture=json.loads(FIXTURE.read_text(encoding='utf-8'))

    def test_185_baseline_has_102_unchanged_and_83_verified(self):
        self.assertEqual(len(self.prior),185)
        base,_,_=v.v322.js_dataset(ROOT/'baseline-102-v322.js')
        self.assertEqual(self.prior[:102],base)
        self.assertEqual(len({r['id'] for r in self.prior}),185)

    def test_25_lock_reconciles_with_audit(self):
        self.assertEqual(len(self.audit),25)
        for ticker,r in self.audit.items():
            for key in ('docID','edinetCode','periodStart','periodEnd','gaap'):
                self.assertEqual(r[key],self.locks[ticker][key])

    def test_exactly_24_eligible_and_salary_blocked_for_7745(self):
        self.assertEqual(sum(r['reconciled_count']==6 for r in self.audit.values()),24)
        self.assertEqual(self.audit[v.EXCLUDED]['metrics']['average_salary_man']['status'],'BLOCKED')

    def test_offline_evidence_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(v.ReleaseError,'live re-download'):
                v.stage(FIXTURE,ROOT/'baseline-102-v322.js',d)

    def test_staging_209_from_102_and_idempotent_from_209(self):
        with tempfile.TemporaryDirectory() as d:
            s=v.stage(FIXTURE,ROOT/'baseline-102-v322.js',d,require_live=False)
            self.assertEqual(s['staged_public_count'],209)
            candidate=Path(d)/'site-ready'/'company-data.js'
            all_rows,meta,_=v.v322.js_dataset(candidate)
            self.assertEqual(len(all_rows),209)
            self.assertEqual(meta['count'],209)
            self.assertEqual(all_rows[:185],self.prior)
            self.assertEqual(len({r['id'] for r in all_rows}),209)
            self.assertNotIn(v.EXCLUDED,{r['id'] for r in all_rows})
            self.assertEqual(len({r['id'] for r in all_rows[185:]}),24)
            self.assertEqual(v.stage(FIXTURE,candidate,d,require_live=False)['staged_public_count'],209)
            self.assertIn('209社', (Path(d)/'site-ready'/'index.html').read_text())
            self.assertIn('v=323',(Path(d)/'site-ready'/'company-check.html').read_text())
            self.assertNotIn('.slice(0,110)',(Path(d)/'site-ready'/'company-compare.js').read_text())
            self.assertIn('false',(Path(d)/'site-ready'/'affiliate-config.js').read_text())

    def test_any_mutation_of_frozen_25_audit_is_blocked(self):
        import shutil
        needed=['audit-25-v323.json','source-lock-25-v323.json','verification-83-live-v323.json',
                'baseline-185-v323.js','baseline-102-v322.js','company-master-v322.json',
                'company-master-v323.json','audit-87-v322.json','source-lock-87-v322.json',
                'discovery-90-v322.json']
        with tempfile.TemporaryDirectory() as d:
            tmp=Path(d)
            for name in needed:shutil.copy(ROOT/name,tmp/name)
            (tmp/'audit-25-v323.json').write_bytes((tmp/'audit-25-v323.json').read_bytes()+b'\n')
            with self.assertRaisesRegex(v.ReleaseError,'Frozen audit/proof file'):
                v.prepare(tmp)

    def test_missing_or_tampered_proof_is_rejected(self):
        for edit in ('missing','bad_count','tampered_hash'):
            proof=json.loads(json.dumps(self.fixture))
            if edit=='missing':proof['rows'].pop()
            elif edit=='bad_count':proof['passed_count']=23
            else:proof['rows'][0]['xbrl_sha256']='0'*64
            with tempfile.TemporaryDirectory() as d:
                f=Path(d)/'bad-proof.json';f.write_text(json.dumps(proof))
                with self.assertRaises(v.ReleaseError):v.stage(f,ROOT/'baseline-102-v322.js',d,require_live=False)

    def test_altered_existing_company_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            text=(ROOT/'baseline-102-v322.js').read_text()
            text=text.replace('"revenue":', '"revenue":9999999, "originalRevenue":',1)
            path=Path(d)/'company-data.js';path.write_text(text)
            with self.assertRaises(v.ReleaseError):v.stage(FIXTURE,path,d,require_live=False)

    def test_mismatched_185_baseline_blocks_release(self):
        with tempfile.TemporaryDirectory() as d:
            text=(ROOT/'baseline-185-v323.js').read_text().replace('"revenue":','"revenue":1, "oldRevenue":',1)
            path=Path(d)/'company-data.js';path.write_text(text)
            with self.assertRaises(v.ReleaseError):v.stage(FIXTURE,path,d,require_live=False)

    def test_monthly_209_and_102_readers(self):
        with tempfile.TemporaryDirectory() as d:
            v.stage(FIXTURE,ROOT/'baseline-102-v322.js',d,require_live=False)
            self.assertEqual(len(monthly.read_public(Path(d)/'site-ready'/'company-data.js')[0]),209)
            self.assertEqual(len(monthly.read_public(ROOT/'baseline-102-v322.js')[0]),102)
            self.assertEqual(len(monthly.read_master(ROOT/'company-master-v323.json')),225)

    def test_monthly_209_mock_no_changes_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            v.stage(FIXTURE,ROOT/'baseline-102-v322.js',d,require_live=False)
            out=Path(d)/'month'
            s=monthly.run(ROOT/'company-master-v323.json',Path(d)/'site-ready'/'company-data.js',out,days=1,delay=0,
                          day_fetcher=lambda date:[],zip_fetcher=lambda doc: b'')
            self.assertEqual(s['published_count'],209)
            self.assertEqual(s['published_updates_fully_reconciled'],0)
            self.assertFalse(s['deployed_to_pages'])
            self.assertFalse((out/'company-data-v323-REVIEW-ONLY.js').exists())

if __name__=='__main__':unittest.main()
