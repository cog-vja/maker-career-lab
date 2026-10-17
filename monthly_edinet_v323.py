#!/usr/bin/env python3
"""v3.23 monthly EDINET monitoring and *manual review* staging.

Scheduled execution checks 200 target codes, but only stages updates for previously
published 102, 185 or 209 issuers. Never commits, creates PRs, or deploys on its own.
Corrections, duplicates, fiscal-period anomalies and unfamiliar accounting
standards are always held for manual review.
"""
from __future__ import annotations
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timedelta,date
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET

EDINET='https://api.edinet-fsa.go.jp/api/v2'
VALID_FIELDS={'revenue_oku':'revenue','prior_revenue_oku':'revenuePrev','operating_profit_oku':'operatingProfit','operating_cf_oku':'operatingCashFlow','equity_ratio_pct':'equityRatio','average_salary_man':'averageSalary'}

class UpdateError(ValueError):pass

def read_public(path):
    raw=Path(path).read_text(encoding='utf-8')
    m=re.search(r'window\.MCL_COMPANIES\s*=\s*(\[.*?\]);\s*window\.MCL_DATASET_META',raw,re.S)
    if not m:raise UpdateError('unrecognized company-data.js')
    rows=json.loads(m.group(1))
    ids=[str(r['id']) for r in rows]
    if len(rows) not in (102,185,209) or len(ids)!=len(set(ids)):raise UpdateError('expected published 102, 185 or 209 unique companies')
    if any(set(VALID_FIELDS.values())-set(x) or not re.fullmatch(r'\d{4}',str(x['id'])) for x in rows):raise UpdateError('invalid public rows')
    return rows,raw

def read_master(path):
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    rows=obj['companies'];ids=[r['ticker'] for r in rows]
    if len(rows)!=225 or len(ids)!=len(set(ids)) or any(not re.fullmatch(r'\d{4}',i) for i in ids):raise UpdateError('master must contain 225 unique 4-digit codes')
    if sum(x['stage']=='ADDITIONAL_RESEARCH_UNVERIFIED' for x in rows)!=1 or sum(x['stage']=='V323_XBRL_VERIFIED_RELEASE_CANDIDATE' for x in rows)!=24:
        raise UpdateError('master must mark 24 ready for review, 1 blocked, and 225 unique issuers')
    return rows

def request_json(day,key):
    args=urllib.parse.urlencode({'date':day.isoformat(),'type':'2','Subscription-Key':key})
    url=EDINET+'/documents.json?'+args
    req=urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-v321-monthly'})
    with urllib.request.urlopen(req,timeout=60) as r:raw=r.read(18_000_001)
    if len(raw)>18_000_000:raise UpdateError('EDINET daily-list response too large')
    payload=json.loads(raw)
    if str(payload.get('metadata',{}).get('status','200')) not in ('200','200.0'):raise UpdateError('EDINET API status is not 200')
    rows=payload.get('results',[])
    if not isinstance(rows,list):raise UpdateError('EDINET results not list')
    return rows

def get_zip(doc_id,key):
    if not re.fullmatch(r'S[A-Z0-9]{7,15}',doc_id):raise UpdateError('invalid docID')
    args=urllib.parse.urlencode({'type':1,'Subscription-Key':key})
    req=urllib.request.Request(EDINET+'/documents/'+doc_id+'?'+args,headers={'User-Agent':'MakerCareerLab-v321-monthly'})
    with urllib.request.urlopen(req,timeout=100) as r:raw=r.read(80_000_001)
    if len(raw)>80_000_000 or not zipfile.is_zipfile(io.BytesIO(raw)):raise UpdateError('invalid EDINET source ZIP')
    return raw

def ticker(row):
    s=str(row.get('secCode') or '')
    return s[:4] if re.fullmatch(r'\d{4}(0|00)?',s) else None

def valid_original(r,as_of):
    if str(r.get('docTypeCode'))!='120' or str(r.get('withdrawalStatus','0'))!='0':return False
    if str(r.get('xbrlFlag'))!='1' or str(r.get('csvFlag'))!='1':return False
    if not re.fullmatch(r'S[A-Z0-9]{7,15}',str(r.get('docID',''))):return False
    try:
        end=date.fromisoformat(str(r['periodEnd']))
        start=date.fromisoformat(str(r['periodStart']))
        submitted=date.fromisoformat(str(r['submitDateTime'])[:10])
        return start<end<=as_of and submitted<=as_of
    except (KeyError,ValueError):return False

def select(rows,existing,as_of):
    """Select unambiguous latest annual report, never corrected filing."""
    originals=[r for r in rows if valid_original(r,as_of)]
    if not originals:
        amendments=[r for r in rows if str(r.get('docTypeCode'))=='130']
        if amendments:return {'status':'CORRECTION_REVIEW','periodEnd':max(str(r.get('periodEnd','')) for r in amendments)}
        return {'status':'NOT_FOUND'}
    top=max(r['periodEnd'] for r in originals)
    latest={r['docID']:r for r in originals if r['periodEnd']==top}
    amendments=[r for r in rows if str(r.get('docTypeCode'))=='130' and str(r.get('periodEnd'))==top]
    if amendments:return {'status':'CORRECTION_REVIEW','periodEnd':top,'amendments':[r.get('docID') for r in amendments]}
    if len(latest)!=1:return {'status':'AMBIGUOUS','periodEnd':top,'document_count':len(latest)}
    chosen=list(latest.values())[0]
    if existing:
        old_end=str(existing.get('period','')).split('〜')[-1]
        if chosen['docID']==existing.get('sourceDocId'):return {'status':'UNCHANGED','periodEnd':top}
        if top<=old_end:return {'status':'OLD_OR_RESTATED_REVIEW','periodEnd':top,'docID':chosen['docID']}
    return {'status':'NEW_FILING_UNVERIFIED','periodEnd':top,'filing':{k:chosen.get(k) for k in ('docID','secCode','edinetCode','filerName','docTypeCode','withdrawalStatus','periodStart','periodEnd','submitDateTime','csvFlag','xbrlFlag')}}

def reconcile_zip(raw,filing,prior):
    """Previous published issuer, full six allowed XBRL facts, same GAAP."""
    import edinet_v313 as v313
    import edinet_v317 as v317
    from edinet_v320 import fingerprint_zip
    if ticker(filing)!=str(prior['id']):raise UpdateError('issuer ticker mismatch')
    facts,contexts,filename=v313.original_instance(raw,filing)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root=ET.fromstring(z.read(filename))
    standards=[(el.text or '').strip() for el in root if v313.local(el.tag)=='AccountingStandardsDEI']
    if len(set(standards))!=1:raise UpdateError('ambiguous accounting standard')
    gaap={'IFRS':'IFRS','Japan GAAP':'JP_GAAP','JapanGAAP':'JP_GAAP','Japanese GAAP':'JP_GAAP','US GAAP':'US_GAAP'}.get(standards[0])
    if gaap not in ('JP_GAAP','IFRS') or gaap!=prior.get('accountingStandard'):raise UpdateError('GAAP change or unsupported GAAP')
    result={'metrics':{}}
    v317.common_numeric(facts,filing,gaap,result)
    bad=[k for k in VALID_FIELDS if result['metrics'][k]['status']!='SOURCE_RECONCILED']
    if bad:raise UpdateError('blocked metric definitions: '+','.join(bad))
    fresh=dict(prior)
    for k,field in VALID_FIELDS.items():fresh[field]=float(Decimal(result['metrics'][k]['value']))
    fresh.update({'period':filing['periodStart']+'〜'+filing['periodEnd'],
                  'sourceLabel':'EDINET 有価証券報告書（書類ID: '+filing['docID']+'）',
                  'sourceDocId':filing['docID'],'sourceSha256':hashlib.sha256(raw).hexdigest(),
                  'sourcePayloadFingerprint':fingerprint_zip(raw),
                  'verifiedAt':datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()})
    return fresh

def save(path,data):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def proposed_js(original,changes):
    m=re.search(r'(window\.MCL_COMPANIES\s*=\s*)(\[.*?\])(\s*;\s*window\.MCL_DATASET_META)',original,re.S)
    if not m:raise UpdateError('invalid data JS')
    rows=json.loads(m.group(2));new=[changes.get(str(r['id']),r) for r in rows]
    assert len(new) in (102,185,209) and [r['id'] for r in new]==[r['id'] for r in rows]
    return original[:m.start(2)]+json.dumps(new,ensure_ascii=False,separators=(',',':'))+original[m.end(2):]

def run(master_file,public_file,output_dir,days=45,delay=0.7,as_of=None,day_fetcher=None,zip_fetcher=None):
    if not 1<=days<=400:raise UpdateError('days must be 1..400')
    if not 0<=delay<=10:raise UpdateError('delay must be 0..10 seconds')
    now=as_of or datetime.now(ZoneInfo('Asia/Tokyo')).date()
    master=read_master(master_file);public,original=read_public(public_file)
    known={r['ticker']:r for r in master};published={str(r['id']):r for r in public}
    if not set(published).issubset(set(known)):raise UpdateError('published issuer outside target master')
    key=os.environ.get('EDINET_API_KEY','')
    if (not day_fetcher or not zip_fetcher) and not key:raise UpdateError('EDINET_API_KEY not configured')
    day_fetcher=day_fetcher or (lambda d:request_json(d,key))
    zip_fetcher=zip_fetcher or (lambda d:get_zip(d,key))
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    grouped=defaultdict(list);total=0
    for n in range(days):
        d=now-timedelta(days=n)
        for row in day_fetcher(d):
            code=ticker(row)
            if code in known and str(row.get('docTypeCode')) in ('120','130'):
                grouped[code].append(row);total+=1
        if n<days-1:time.sleep(delay)
    report=[];updates={};review=[]
    for code,row in sorted(known.items()):
        choice=select(grouped[code],published.get(code),now)
        status=choice['status']
        entry={'ticker':code,'name':row['name'],'was_published':code in published,'status':status}
        if choice.get('filing'):
            filing=choice['filing'];entry.update({'docID':filing['docID'],'periodEnd':filing['periodEnd']})
            if code in published:
                try:
                    raw=zip_fetcher(filing['docID'])
                    updates[code]=reconcile_zip(raw,filing,published[code])
                    entry['status']='VERIFIED_UPDATE_STAGED'
                    entry['source_payload_fingerprint']=updates[code]['sourcePayloadFingerprint']
                except Exception as exc:
                    # Never propagate external HTTP error response, which might include API key URL.
                    entry['status']='REVIEW_REQUIRED';entry['reason']=type(exc).__name__+': '+str(exc)[:200] if not isinstance(exc,urllib.error.HTTPError) else 'EDINET HTTP error'
                    review.append(code)
        if status in ('CORRECTION_REVIEW','AMBIGUOUS','OLD_OR_RESTATED_REVIEW'):review.append(code)
        report.append(entry)
    published_review=[x['ticker'] for x in report if x['was_published'] and x['status'] in ('REVIEW_REQUIRED','CORRECTION_REVIEW','AMBIGUOUS','OLD_OR_RESTATED_REVIEW')]
    summary={'version':'3.23','as_of_jst':now.isoformat(),'scan_days':days,'controlled_target_count':225,'published_count':len(public),
             'new_research_targets_unverified':sum(1 for x in master if x['stage']=='ADDITIONAL_RESEARCH_UNVERIFIED' and x['ticker'] not in published),'published_updates_fully_reconciled':len(updates),
             'manual_review_required':len(set(review)),'published_manual_review_required':len(published_review),
             'all_new_issuers_automatically_published':0,
             'deployed_to_pages':False,'source_list_records_matched':total,
             'statuses':dict(Counter(x['status'] for x in report))}
    save(output/'monthly-summary-v323.json',summary)
    save(output/'monthly-candidates-v323.json',report)
    if updates:
        staged=proposed_js(original,updates)
        (output/'company-data-v323-REVIEW-ONLY.js').write_text(staged,encoding='utf-8')
        save(output/'review-changes-v323.json',[{'ticker':t,'old_doc':published[t]['sourceDocId'],'new_doc':x['sourceDocId'],
             'old_period':published[t]['period'],'new_period':x['period']} for t,x in sorted(updates.items())])
    print(json.dumps(summary,ensure_ascii=False))
    return summary

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--master',default='company-master-v323.json');ap.add_argument('--public',default='company-data.js')
    ap.add_argument('--output',default='v323-monthly-output');ap.add_argument('--days',type=int,default=45)
    ap.add_argument('--delay',type=float,default=0.7)
    args=ap.parse_args();run(args.master,args.public,args.output,args.days,args.delay)
if __name__=='__main__':main()
