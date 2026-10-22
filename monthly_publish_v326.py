#!/usr/bin/env python3
"""Fail-closed, offline pre-publication gate for v3.26 monthly EDINET changes.

This script NEVER fetches EDINET, edits the baseline or pushes GitHub. It validates
monthly_edinet_v325.py outputs and writes an auditable plan. GitHub Actions may
commit the existing-issuer candidate only after this gate passes.
"""
from __future__ import annotations

import argparse
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import re

from expand_manufacturers_v325 import GateError, parse_public, METRICS

UPDATE_FIELDS = frozenset({
    'revenue', 'revenuePrev', 'operatingProfit', 'operatingCashFlow',
    'equityRatio', 'averageSalary', 'period', 'sourceLabel', 'sourceDocId',
    'sourceSha256', 'sourceXbrlSha256', 'sourcePayloadFingerprint', 'verifiedAt',
})
DOC_ID = re.compile(r'^S[A-Z0-9]{7,15}$')


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate_monthly(baseline, candidate, summary_file, details_file, minimum_count=1000):
    base_raw, _, base, base_meta = parse_public(baseline)
    if len(base) < minimum_count or len(base) > 2500:
        raise GateError('Monthly auto-publish requires 1000+ existing, approved companies (<=2500)')
    if base_meta.get('count') != len(base):
        raise GateError('Existing dataset count metadata mismatch')
    if any(str(r['id']) == '6390' for r in base):
        raise GateError('Previously withheld ticker 6390 must not be auto-published')
    summary = _read_json(summary_file)
    details = _read_json(details_file)
    if not isinstance(details, list) or not isinstance(summary, dict):
        raise GateError('Invalid monthly report structure')
    if summary.get('published') != len(base) or summary.get('site_auto_deployed_by_script') is not False:
        raise GateError('Monthly report baseline mismatch')
    if not isinstance(summary.get('verified_updates'), int) or summary['verified_updates'] < 0:
        raise GateError('Monthly summary verified_updates invalid')
    if not isinstance(summary.get('review_required'), int) or summary['review_required'] < 0:
        raise GateError('Monthly summary review count invalid')
    if not 1 <= int(summary.get('scan_days', -1)) <= 90:
        raise GateError('Monthly scan was not completed correctly')
    changed_report = [x for x in details if x.get('status') == 'VERIFIED_NEW_PERIOD']
    expected_codes = [str(x.get('ticker')) for x in changed_report]
    if len(set(expected_codes)) != len(expected_codes):
        raise GateError('Duplicate verified update entries')
    if len(expected_codes) != summary['verified_updates']:
        raise GateError('Summary and verified changes disagree')
    if len(details) != len({str(x.get('ticker')) for x in details}):
        raise GateError('Duplicate ticker in monthly report')
    review_codes = {str(x.get('ticker')) for x in details if x.get('status') not in ('VERIFIED_NEW_PERIOD', 'UNCHANGED')}
    if len(review_codes) != summary['review_required']:
        raise GateError('Summary and held-for-review companies disagree')
    base_codes = [str(x['id']) for x in base]
    if set(expected_codes) - set(base_codes):
        raise GateError('New ticker insertion is forbidden in a monthly update')
    if not expected_codes:
        if Path(candidate).exists():
            raise GateError('Candidate file exists despite zero verified changes')
        return {'release':'NO_CHANGES','baseline_count':len(base),'updated':0,
                'held_for_review':len(review_codes),'updated_tickers':[]}
    if not Path(candidate).is_file():
        raise GateError('Verified changes exist but candidate JS is missing')
    cand_raw, _, next_rows, meta = parse_public(candidate)
    if [str(x['id']) for x in next_rows] != base_codes:
        raise GateError('Candidate changed published company identity or ordering')
    if meta.get('count') != len(base) or meta.get('lastMonthlyVerifiedUpdateCount') != len(expected_codes):
        raise GateError('Candidate count metadata mismatch')
    if any(meta.get(k) != v for k, v in base_meta.items()):
        raise GateError('Candidate overwrote established publication metadata')
    # No manipulation of archived demos or site runtime code.
    if base_raw.split('window.MCL_DEMOS =', 1)[-1] != cand_raw.split('window.MCL_DEMOS =', 1)[-1]:
        raise GateError('Candidate edited demo data')
    updates = {str(x['ticker']):x for x in changed_report}
    observed = []
    for before, after in zip(base, next_rows):
        ticker = str(before['id'])
        if ticker not in updates:
            if after != before:raise GateError('Unverified company row modified: '+ticker)
            continue
        if before == after:raise GateError('Verified filing has no changed row: '+ticker)
        mutated = {k for k in (set(before) | set(after)) if before.get(k) != after.get(k)}
        if not mutated.issubset(UPDATE_FIELDS):
            raise GateError('Protected company field modified: '+ticker+' '+','.join(sorted(mutated-UPDATE_FIELDS)))
        doc = str(updates[ticker].get('new_docID') or '')
        if not DOC_ID.fullmatch(doc) or after.get('sourceDocId') != doc:
            raise GateError('EDINET source document mismatch: '+ticker)
        if before.get('sourceDocId') == doc:
            raise GateError('New filing ID equals old document: '+ticker)
        try:
            start,end = str(after['period']).split('〜')
            if date.fromisoformat(end) <= date.fromisoformat(str(before['period']).split('〜')[-1]):
                raise GateError('Candidate period is not newer: '+ticker)
            if date.fromisoformat(start) >= date.fromisoformat(end):
                raise GateError('Malformed candidate period: '+ticker)
        except (KeyError, ValueError) as e:
            raise GateError('Invalid updated fiscal period: '+ticker) from e
        for field in METRICS.values():
            try: v=Decimal(str(after[field]))
            except (KeyError, TypeError, ValueError, InvalidOperation) as e:
                raise GateError('Invalid financial metric: '+ticker+' '+field) from e
            if not v.is_finite():raise GateError('Nonfinite updated metric: '+ticker+' '+field)
        if not Decimal('100') <= Decimal(str(after['averageSalary'])) <= Decimal('10000'):
            raise GateError('Candidate salary out of bounds: '+ticker)
        if not 0 <= Decimal(str(after['equityRatio'])) <= 100:
            raise GateError('Candidate equity ratio out of normal bounds: '+ticker)
        observed.append(ticker)
    if set(observed) != set(expected_codes):
        raise GateError('Verified tickers and changed rows disagree')
    return {'release':'READY_FOR_AUTOMATED_COMMIT','baseline_count':len(base),
            'updated':len(observed),'held_for_review':len(review_codes),
            'updated_tickers':sorted(observed)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--baseline',default='company-data.js')
    ap.add_argument('--candidate',default='out/monthly/company-data-VERIFIED-REVIEW.js')
    ap.add_argument('--summary',default='out/monthly/monthly-summary-v325.json')
    ap.add_argument('--details',default='out/monthly/monthly-details-v325.json')
    ap.add_argument('--plan',default='out/monthly/publish-plan-v326.json')
    ap.add_argument('--minimum-count',type=int,default=1000)
    args=ap.parse_args()
    result=validate_monthly(args.baseline,args.candidate,args.summary,args.details,args.minimum_count)
    p=Path(args.plan);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
    return result

if __name__=='__main__':main()
