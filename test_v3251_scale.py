"""v3.25.1 regression for expanding the existing 209-company site to 1,000+.
All data in these tests is synthetic; no EDINET requests and no release.
"""
import csv
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from expand_manufacturers_v325 import METRICS, GateError, stage, parse_public
from v325_artifacts import select_batches


class ExpansionScaleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.public = self.root/'company-data.js'
        self.existing = [{'id':str(1000+i),'name':f'Existing {i}'} for i in range(209)]
        self.public.write_text('window.MCL_COMPANIES = '+json.dumps(self.existing)+'; '\
            'window.MCL_DATASET_META = {"count":209}; window.MCL_DEMOS = [];',encoding='utf-8')
        self.audit = self.root/'audits'
        self.audit.mkdir()
        self.candidates = self.root/'staging-candidates.csv'

    def audit_row(self,ticker):
        return {'ticker':ticker,'name':'New '+ticker,'industry':'機械','market':'プライム',
          'status':'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW','verifiedMetricCount':6,
          'financialScope':'連結','gaap':'JP_GAAP','docID':'S100ABCD',
          'periodStart':'2025-04-01','periodEnd':'2026-03-31','verifiedAt':'2026-10-20',
          'sourceOriginalSha256':'a'*64,'sourceXbrlSha256':'b'*64,
          'sourcePayloadFingerprint':'c'*64,
          'metrics':{m:{'status':'SOURCE_RECONCILED','value':'30'} for m in METRICS}}

    def fixture(self,number):
        with self.candidates.open('w',newline='',encoding='utf-8') as f:
            w=csv.writer(f);w.writerow(['ticker','include'])
            for i in range(number):
                ticker=str(2000+i)
                (self.audit/(ticker+'.json')).write_text(json.dumps(self.audit_row(ticker)),encoding='utf-8')
                w.writerow([ticker,'YES'])

    def params(self,limit=1000):
        return SimpleNamespace(public=str(self.public),audit_dir=str(self.audit),
           approvals=None,candidates=str(self.candidates),require_count=limit,
           output=str(self.root/'stage'))

    def test_1000_staging_without_replacing_209(self):
        self.fixture(791)
        stage(self.params())
        _,_,rows,meta=parse_public(self.root/'stage'/'company-data.js')
        self.assertEqual(len(rows),1000)
        self.assertEqual(rows[:209],self.existing)
        self.assertEqual(meta['status'],'STAGED_NOT_DEPLOYED')
        self.assertEqual(meta['stageInput'],'six-metric-candidates')
        self.assertEqual(json.loads((self.root/'stage'/'MANUAL-RELEASE-SUMMARY.json').read_text())['deployed'],False)

    def test_1001_and_gate(self):
        self.fixture(792)
        stage(self.params(1001))
        _,_,rows,_=parse_public(self.root/'stage'/'company-data.js')
        self.assertEqual(len(rows),1001)
        with self.assertRaisesRegex(GateError,'only 1001'):stage(self.params(1002))

    def test_blocked_is_not_staged(self):
        self.fixture(1)
        row=self.audit_row('2000')
        row['status']='BLOCKED_INCOMPLETE'
        (self.audit/'2000.json').write_text(json.dumps(row))
        with self.assertRaisesRegex(GateError,'six-metric approval gate failed'):
            stage(self.params(210))

    def test_non_finite_value_rejected(self):
        self.fixture(1)
        row=self.audit_row('2000')
        row['metrics']['equity_ratio_pct']['value']='NaN'
        (self.audit/'2000.json').write_text(json.dumps(row))
        with self.assertRaisesRegex(GateError,'non-finite metric'):
            stage(self.params(210))

    def test_candidate_csv_rejects_unknown_flag(self):
        self.fixture(1)
        self.candidates.write_text('ticker,include\n2000,MAYBE\n')
        with self.assertRaisesRegex(GateError,'YES or NO'):stage(self.params(210))

    def test_artifact_offsets_only_in_50_steps(self):
        arts=[{'name':f'mcl-v325-audit-b{i}-root123','created_at':'2026-10-22','id':i,
               'expired':False} for i in (0,50,600,650,700,750,800,850,900,925)]
        got=select_batches([{'artifacts':arts}],123)
        self.assertEqual(sorted(got),[0,50,600,650,700,750,800,850,900])

if __name__ == '__main__':
    unittest.main()
