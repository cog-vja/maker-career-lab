#!/usr/bin/env python3
"""v3.25 conservative 209+ company monthly update (only six-source-verified changes).
Outputs REVIEW state and staged company-data.js; public file is never overwritten by Python.
Workflow may copy/commit staged file only if AUTO_PUBLISH_VERIFIED=true.
"""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
from datetime import timedelta,date
from decimal import Decimal
import json
from pathlib import Path
import time
from zoneinfo import ZoneInfo
from datetime import datetime
from expand_manufacturers_v325 import (
    parse_public,emit,day_docs,choose,original_zip,_audit_one,edinet_ticker,
    METRICS,GateError,safe_sha,now_jst)

MAX_COMPANIES=2500

def proposed(raw,matcher,existing,meta,changes):
    if not changes:return None
    ids={str(c['id']) for c in existing}
    if not set(changes).issubset(ids):raise GateError('attempt to insert unknown ticker during update')
    data=[changes.get(str(c['id']),c) for c in existing]
    if [str(x['id']) for x in data]!=[str(x['id']) for x in existing]:raise GateError('company order or membership changed')
    meta=dict(meta);meta.update({'count':len(data),'lastMonthlyReviewJST':now_jst().date().isoformat(),
                'lastMonthlyVerifiedUpdateCount':len(changes)})
    return (raw[:matcher.start(2)]+json.dumps(data,ensure_ascii=False,separators=(',',':'))+
            raw[matcher.end(2):matcher.start(4)]+json.dumps(meta,ensure_ascii=False,separators=(',',':'))+raw[matcher.end(4):])

def six_metric_update(old,audit):
    if audit.get('status')!='SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW' or audit.get('verifiedMetricCount')!=6:
        raise GateError('not 6/6 source reconciled')
    if audit['gaap']!=old.get('accountingStandard'):raise GateError('GAAP changed (manual)')
    if audit['ticker']!=str(old['id']):raise GateError('ticker mismatch')
    old_end=old['period'].split('〜')[-1]
    if audit['periodEnd']<=old_end:raise GateError('not newer annual period')
    if audit['periodEnd']>now_jst().date().isoformat():raise GateError('future annual period')
    fresh=dict(old)
    for metric,field in METRICS.items():
        node=audit['metrics'].get(metric)
        if not node or node.get('status')!='SOURCE_RECONCILED':raise GateError('unreconciled metric')
        value=Decimal(str(node['value']))
        if not value.is_finite():raise GateError('nonfinite metric')
        if field in ('revenue','revenuePrev','averageSalary') and value<=0:raise GateError('nonpositive key metric')
        if field=='averageSalary' and Decimal('100')>value:raise GateError('unusually low salary')
        if field=='averageSalary' and Decimal('10000')<value:raise GateError('unusually high salary')
        prior=Decimal(str(old[field]))
        if field=='averageSalary' and prior>0 and abs(value/prior-1)>Decimal('0.40'):
            raise GateError('salary moved >40%; manual review')
        if field=='revenue' and prior>0 and abs(value/prior-1)>Decimal('2.00'):
            raise GateError('revenue moved >200%; manual review')
        if field=='equityRatio' and (value<Decimal('-100') or value>Decimal('100')):
            raise GateError('equity ratio outside cautious range')
        fresh[field]=float(value)
    fresh.update({'period':audit['periodStart']+'〜'+audit['periodEnd'],
      'sourceLabel':'EDINET 有価証券報告書（書類ID: '+audit['docID']+'）',
      'sourceDocId':audit['docID'],'sourceSha256':audit['sourceOriginalSha256'],
      'sourceXbrlSha256':audit['sourceXbrlSha256'],
      'sourcePayloadFingerprint':audit['sourcePayloadFingerprint'],
      'verifiedAt':audit['verifiedAt']})
    return fresh

def analyze(public_path,output_dir,days=55,delay=1,asof=None,day_fetcher=None,zip_fetcher=None):
    if not 1<=days<=90:raise GateError('monthly scan must be 1..90 days')
    raw,match,existing,meta=parse_public(public_path)
    if not 1<=len(existing)<=MAX_COMPANIES:raise GateError('unexpected public company count')
    asof=asof or now_jst().date()
    known={str(x['id']):x for x in existing}
    if day_fetcher is None or zip_fetcher is None:
        import os
        key=os.environ.get('EDINET_API_KEY','')
        if not key:raise GateError('EDINET_API_KEY required')
        day_fetcher=day_fetcher or (lambda day:day_docs(day,key))
        zip_fetcher=zip_fetcher or (lambda doc:original_zip(doc,key))
    entries=defaultdict(list); scanned=[]
    for i in range(days):
        d=asof-timedelta(days=i)
        batch=day_fetcher(d)
        for r in batch:
            code=edinet_ticker(r.get('secCode'))
            if code in known and str(r.get('docTypeCode')) in ('120','130'):
                entries[code].append(r)
        scanned.append(d.isoformat())
        if i<days-1:time.sleep(max(0,delay))
    updates={};review=[];report=[]
    for code,filings in sorted(entries.items()):
        old=known[code]
        amend=[r for r in filings if str(r.get('docTypeCode'))=='130']
        if amend:
            report.append({'ticker':code,'status':'CORRECTION_REQUIRES_REVIEW','docIDs':[r.get('docID') for r in amend]});review.append(code);continue
        status,filing=choose(filings,asof)
        if status!='SELECTED':
            report.append({'ticker':code,'status':status});review.append(code);continue
        if filing['docID']==old.get('sourceDocId'):
            report.append({'ticker':code,'status':'UNCHANGED'});continue
        if filing['periodEnd']<=old.get('period','').split('〜')[-1]:
            report.append({'ticker':code,'status':'OLD_FILING_REQUIRES_REVIEW','docID':filing['docID']});review.append(code);continue
        try:
            raw_zip=zip_fetcher(filing['docID'])
            audit=_audit_one(filing,old['name'],old.get('industry',''),raw_zip)
            candidate=six_metric_update(old,audit)
            updates[code]=candidate
            report.append({'ticker':code,'status':'VERIFIED_NEW_PERIOD','previous_docID':old.get('sourceDocId'),
                           'new_docID':filing['docID'],'new_period':candidate['period']})
        except Exception as ex:
            report.append({'ticker':code,'status':'SOURCE_REVIEW_REQUIRED','reason':type(ex).__name__+': '+str(ex)[:140]})
            review.append(code)
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    js=proposed(raw,match,existing,meta,updates)
    if js:
        (out/'company-data-VERIFIED-REVIEW.js').write_text(js,encoding='utf-8')
    summary={'version':'3.25','as_of_jst':asof.isoformat(),'scan_days':days,'published':len(existing),
      'verified_updates':len(updates),'review_required':len(set(review)),
      'site_file_created':bool(js),'site_auto_deployed_by_script':False,'statuses':dict(Counter(x['status'] for x in report)),
      'notes':'Only fully verified changed issuers in site candidate. Amendment/new GAAP/large changes held.'}
    emit(out/'monthly-summary-v325.json',summary)
    emit(out/'monthly-details-v325.json',report)
    print(json.dumps(summary,ensure_ascii=False))
    return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--public',default='company-data.js')
    ap.add_argument('--output',default='out/monthly');ap.add_argument('--days',type=int,default=55)
    ap.add_argument('--delay',type=float,default=1)
    a=ap.parse_args()
    analyze(a.public,a.output,a.days,a.delay)
