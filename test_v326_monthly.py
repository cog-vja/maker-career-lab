"""Offline regression for v3.26 1000+ monthly workflow; no EDINET network calls."""
import json
from datetime import date
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from expand_manufacturers_v325 import GateError, parse_public, METRICS
from monthly_edinet_v325 import analyze, proposed
from monthly_publish_v326 import validate_monthly

ROOT = Path(__file__).resolve().parent


def baseline_row():
    return parse_public(ROOT/'company-data.js')[2][0]


class MonthlyV326Tests(unittest.TestCase):
    def test_real_1089_input(self):
        _,_,rows,meta=parse_public(ROOT/'company-data.js')
        self.assertEqual(len(rows),1089)
        self.assertEqual(meta['count'],len(rows))
        self.assertNotIn('6390',{str(r['id']) for r in rows})
        self.assertEqual(len(set(str(r['id']) for r in rows)),len(rows))

    def test_live_page_claims_and_209_historical_statistics(self):
        for p in ('index.html','company-check.html','articles/it-scm-career.html','articles/salary-market.html'):
            html=(ROOT/p).read_text(encoding='utf-8')
            self.assertNotIn('200社以上',html,p)
            self.assertIn('1,000社以上',html,p)
        self.assertIn('過去', (ROOT/'articles/salary-market.html').read_text(encoding='utf8'))
        self.assertIn('集計対象：比較ツール掲載209社', (ROOT/'index.html').read_text(encoding='utf8'))

    def test_no_filing_keeps_published_file_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);src=ROOT/'company-data.js'
            original=src.read_bytes()
            with patch('monthly_edinet_v325.time.sleep'):
                report=analyze(src,p/'monthly',days=1,delay=0,asof=date(2026,10,22),
                      day_fetcher=lambda _:[],zip_fetcher=lambda _:b'')
            self.assertEqual(report['verified_updates'],0)
            self.assertEqual(original,src.read_bytes())
            plan=validate_monthly(src,p/'monthly'/'company-data-VERIFIED-REVIEW.js',
                p/'monthly'/'monthly-summary-v325.json',p/'monthly'/'monthly-details-v325.json')
            self.assertEqual(plan['release'],'NO_CHANGES')

    def test_new_report_success_and_strict_validation(self):
        src=ROOT/'company-data.js'
        old=baseline_row()
        ticker=str(old['id']);doc='S100AA11'
        filing={'secCode':ticker+'0','docID':doc,'docTypeCode':'120',
            'withdrawalStatus':'0','xbrlFlag':'1','csvFlag':'1',
            'periodStart':'2026-04-01','periodEnd':'2026-09-30',
            'submitDateTime':'2026-10-01 12:00:00'}
        audit={'ticker':ticker,'status':'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW',
            'verifiedMetricCount':6,'gaap':old['accountingStandard'],
            'periodStart':'2026-04-01','periodEnd':'2026-09-30',
            'docID':doc,'sourceOriginalSha256':'a'*64,'sourceXbrlSha256':'b'*64,
            'sourcePayloadFingerprint':'c'*64,'verifiedAt':'2026-10-22',
            'metrics':{k:{'status':'SOURCE_RECONCILED','value':old[v]} for k,v in METRICS.items()}}
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)
            with patch('monthly_edinet_v325._audit_one',return_value=audit):
                result=analyze(src,out,days=1,delay=0,asof=date(2026,10,22),
                    day_fetcher=lambda _:[filing],zip_fetcher=lambda _:b'fake-original')
            self.assertEqual(result['verified_updates'],1)
            cand=out/'company-data-VERIFIED-REVIEW.js'
            summary=out/'monthly-summary-v325.json'
            details=out/'monthly-details-v325.json'
            plan=validate_monthly(src,cand,summary,details)
            self.assertEqual(plan['release'],'READY_FOR_AUTOMATED_COMMIT')
            self.assertEqual(plan['updated_tickers'],[ticker])
            raw,m,rows,meta=parse_public(cand)
            self.assertEqual(len(rows),1089)
            self.assertEqual(rows[0]['sourceDocId'],doc)
            self.assertEqual(rows[1],parse_public(src)[2][1])
            # Tampered row: no unrelated firm may be silently updated.
            rows[1]['averageSalary']=2000
            cand.write_text(raw[:m.start(2)]+json.dumps(rows,ensure_ascii=False)+raw[m.end(2):],encoding='utf-8')
            with self.assertRaisesRegex(GateError,'Unverified company'):
                validate_monthly(src,cand,summary,details)

    def test_corrections_are_held_and_never_auto_published(self):
        old=baseline_row();ticker=str(old['id'])
        correction={'secCode':ticker+'0','docID':'S100ZZZZ',
            'docTypeCode':'130','withdrawalStatus':'0','submitDateTime':'2026-10-21 12:00:00'}
        with tempfile.TemporaryDirectory() as tmp:
            src=ROOT/'company-data.js';p=Path(tmp)
            result=analyze(src,p,days=1,delay=0,asof=date(2026,10,22),
                day_fetcher=lambda _:[correction],zip_fetcher=lambda _:b'')
            self.assertEqual(result['review_required'],1)
            self.assertEqual(result['verified_updates'],0)
            plan=validate_monthly(src,p/'company-data-VERIFIED-REVIEW.js',
                p/'monthly-summary-v325.json',p/'monthly-details-v325.json')
            self.assertEqual(plan['held_for_review'],1)
            self.assertEqual(plan['release'],'NO_CHANGES')

    def test_legacy_monthly_schedules_removed(self):
        d=ROOT/'.github/workflows'
        for v in ('v321','v322','v323'):
            y=(d/f'edinet-{v}-monthly-review.yml').read_text(encoding='utf8')
            self.assertNotIn('  schedule:',y)
            self.assertIn('  workflow_dispatch:',y)
        current=(d/'edinet-v325-monthly-review.yml').read_text(encoding='utf8')
        self.assertIn("cron: '23 12 5 * *'",current)
        self.assertIn('timezone: \'Asia/Tokyo\'',current)
        self.assertIn('monthly_publish_v326.py',current)
        self.assertIn('MCL_PAGES_PUBLISH_PAT',current)

if __name__=='__main__':unittest.main()
