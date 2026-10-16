#!/usr/bin/env python3
"""v3.16: 30-company master and fail-closed EDINET annual-report discovery.

Public companies are fixed at the ten independently approved in v3.15.
Twenty new companies are *candidates* only. This program neither extracts
financial metrics for them nor writes into company-data.js.

No guessed EDINET codes or invented docIDs. Matching uses the official secCode
from the EDINET documents.json (type=2) daily filing list.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date, datetime, timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from zoneinfo import ZoneInfo

API='https://api.edinet-fsa.go.jp/api/v2'
ANNUAL='120'
AMENDED='130'
DOCID_PATTERN=re.compile(r'S[A-Z0-9]{7,15}$')

class DiscoveryError(ValueError):pass


def load_master(path):
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    items=obj.get('companies')
    if not isinstance(items,list) or len(items)!=30:
        raise DiscoveryError('expected a 30-company master')
    seen=set();count={'PUBLISHED':0,'DISCOVERY_PENDING':0}
    for item in items:
        ticker=item.get('ticker')
        if not isinstance(ticker,str) or not re.fullmatch(r'[0-9]{4}',ticker) or ticker in seen:
            raise DiscoveryError('invalid or duplicated four-digit ticker')
        seen.add(ticker)
        if not item.get('name') or item.get('stage') not in count:
            raise DiscoveryError('invalid name or company stage')
        count[item['stage']]+=1
        if item.get('expected_metrics')!=6:raise DiscoveryError('expected six metrics per company')
        if item['stage']=='PUBLISHED' and not DOCID_PATTERN.fullmatch(str(item.get('source_doc_id'))):
            raise DiscoveryError('published company must have approved document ID')
        if item['stage']=='DISCOVERY_PENDING' and item.get('source_doc_id') is not None:
            raise DiscoveryError('pending company cannot carry an approved document ID')
    if count!={'PUBLISHED':10,'DISCOVERY_PENDING':20}:
        raise DiscoveryError('expected exactly ten published and twenty pending')
    return obj


def assert_existing_publication(master,approved_js):
    """Bind master publication scope to currently approved static JS; never edit it."""
    raw=Path(approved_js).read_text(encoding='utf-8')
    match=re.search(r'window\.MCL_COMPANIES\s*=\s*(\[[\s\S]*?\]);',raw)
    if match is None:raise DiscoveryError('approved company-data.js not found')
    try: data=json.loads(match.group(1))
    except json.JSONDecodeError as exc:raise DiscoveryError('company-data.js is not JSON-formatted') from exc
    expected={x['ticker']:x for x in master['companies'] if x['stage']=='PUBLISHED'}
    actual={str(x.get('id')):x for x in data}
    if len(data)!=10 or len(actual)!=10 or set(actual)!=set(expected):
        raise DiscoveryError('the already-published ten must remain unchanged')
    for ticker,pub in expected.items():
        actual_company=actual[ticker]
        if (actual_company.get('sourceDocId')!=pub['source_doc_id'] or
            actual_company.get('name')!=pub['name'] or
            not actual_company.get('sourceSha256')):
            raise DiscoveryError('approved company metadata changed: '+ticker)
    return {'published_tickers':sorted(actual),'data_sha256':hashlib.sha256(raw.encode('utf-8')).hexdigest()}


def sec_ticker(sec_code):
    s=str(sec_code or '').strip()
    if re.fullmatch(r'\d{4}(?:0|00)?',s):return s[:4]
    return None


def clean_entry(row):
    """Preserve only metadata needed for selection and audit. No secret/token."""
    fields=('docID','edinetCode','secCode','filerName','docDescription','docTypeCode',
            'submitDateTime','periodStart','periodEnd','csvFlag','xbrlFlag',
            'withdrawalStatus','formCode')
    return {key:row.get(key) for key in fields}


def valid_annual(row,ticker,as_of):
    if not isinstance(row,dict):return False
    if sec_ticker(row.get('secCode'))!=ticker:return False
    if str(row.get('docTypeCode'))!=ANNUAL:return False
    if str(row.get('withdrawalStatus','0')) not in ('0','None',''):
        return False
    if str(row.get('csvFlag'))!='1':return False
    if str(row.get('xbrlFlag','1'))=='0':return False
    if not DOCID_PATTERN.fullmatch(str(row.get('docID'))):return False
    try:
        start=date.fromisoformat(str(row['periodStart']))
        end=date.fromisoformat(str(row['periodEnd']))
        filing_date=date.fromisoformat(str(row['submitDateTime'])[:10])
    except (ValueError,KeyError):return False
    return start<end<=as_of and filing_date<=as_of


def choose_candidate(rows,ticker,as_of):
    """Never silently pick a correction, duplicate report, or conflicting issuer."""
    eligible=[r for r in rows if valid_annual(r,ticker,as_of)]
    corrections=[r for r in rows if isinstance(r,dict) and
                 sec_ticker(r.get('secCode'))==ticker and
                 str(r.get('docTypeCode'))==AMENDED and
                 str(r.get('withdrawalStatus','0')) in ('0','','None')]
    if not eligible:
        return {'ticker':ticker,'status':'NOT_FOUND','selected':None,'candidates':[],
                'correction_count':len(corrections),'reason':'no_valid_annual_report_in_window'}
    top_period=max(str(r['periodEnd']) for r in eligible)
    most_recent={str(r['docID']):r for r in eligible if r['periodEnd']==top_period}
    candidate_list=[clean_entry(r) for r in sorted(most_recent.values(),key=lambda r:r['docID'])]
    relevant_corrections=[r for r in corrections if str(r.get('periodEnd'))==top_period]
    if relevant_corrections:
        status='CORRECTION_REVIEW';reason='amended_annual_report_exists_for_latest_period';selected=None
    elif len(most_recent)!=1:
        status='AMBIGUOUS';reason='multiple_original_reports_same_latest_period';selected=None
    else:
        status='DISCOVERED_UNVERIFIED';reason='await_original_source_reconciliation_and_approval'
        selected=candidate_list[0]
    return {'ticker':ticker,'status':status,'selected':selected,
            'period_end':top_period,'candidates':candidate_list,
            'correction_count':len(relevant_corrections),'reason':reason}


def api_get(url,limit=15_000_000,retries=3,timeout=40):
    for i in range(retries):
        try:
            request=urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-v3.16-discovery'})
            with urllib.request.urlopen(request,timeout=timeout) as response:
                data=response.read(limit+1)
                if len(data)>limit:raise DiscoveryError('EDINET response exceeds safety limit')
                return data
        except urllib.error.HTTPError as exc:
            # No API key in exception strings or logs.
            if exc.code not in (429,500,502,503,504) or i+1==retries:
                raise DiscoveryError('EDINET HTTP status '+str(exc.code)) from None
        except urllib.error.URLError:
            if i+1==retries:raise DiscoveryError('EDINET network failure') from None
        time.sleep(min(15,2**(i+1)))
    raise DiscoveryError('EDINET request failed')


def daily_list(day,key,fetch=api_get):
    qs=urllib.parse.urlencode({'date':day.isoformat(),'type':2,'Subscription-Key':key})
    raw=fetch(API+'/documents.json?'+qs)
    try:payload=json.loads(raw)
    except (UnicodeDecodeError,json.JSONDecodeError) as exc:raise DiscoveryError('invalid EDINET listing JSON') from exc
    if str(payload.get('metadata',{}).get('status','200')) not in ('200','200.0'):
        raise DiscoveryError('non-200 EDINET metadata status')
    rows=payload.get('results',[])
    if not isinstance(rows,list):raise DiscoveryError('invalid EDINET listing rows')
    return rows


def fetch_original(docid,key,fetch=api_get):
    if not DOCID_PATTERN.fullmatch(docid):raise DiscoveryError('invalid document ID')
    qs=urllib.parse.urlencode({'type':1,'Subscription-Key':key})
    raw=fetch(API+'/documents/'+docid+'?'+qs,limit=80_000_000,timeout=90)
    if not zipfile.is_zipfile(io.BytesIO(raw)):
        raise DiscoveryError('original is not ZIP')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        if z.testzip() is not None:raise DiscoveryError('corrupted original ZIP')
        filenames=[i.filename.lower() for i in z.infolist() if not i.is_dir()]
        if not any('/publicdoc/' in ('/'+name) and name.endswith('.xbrl') for name in filenames):
            raise DiscoveryError('filing lacks PublicDoc XBRL')
        if sum(x.file_size for x in z.infolist())>350_000_000:
            raise DiscoveryError('unsafe uncompressed ZIP size')
    return raw


def run(master_path,approved_js,output,as_of,lookback_days,delay,download_originals=False,
        key=None,list_reader=None,original_fetcher=None):
    if not 1<=lookback_days<=400:raise DiscoveryError('lookback_days must be 1-400')
    if not 0<=delay<=30:raise DiscoveryError('delay must be 0-30')
    master=load_master(master_path)
    publication=assert_existing_publication(master,approved_js)
    pending={x['ticker']:x for x in master['companies'] if x['stage']=='DISCOVERY_PENDING'}
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    if key is None and list_reader is None:raise DiscoveryError('EDINET_API_KEY missing')
    if list_reader is None:list_reader=lambda day:daily_list(day,key)
    if original_fetcher is None and download_originals:
        original_fetcher=lambda docid:fetch_original(docid,key)
    days_error=[];all_rows=[];successful=0
    for offset in range(lookback_days):
        day=as_of-timedelta(days=offset)
        try:
            entries=list_reader(day)
            if not isinstance(entries,list):raise DiscoveryError('invalid daily listing')
            successful+=1
            for e in entries:
                if isinstance(e,dict) and sec_ticker(e.get('secCode')) in pending and str(e.get('docTypeCode')) in (ANNUAL,AMENDED):
                    all_rows.append(e)
        except (Exception) as exc:
            days_error.append({'date':day.isoformat(),'error':type(exc).__name__+': '+str(exc)[:90]})
        if offset and offset%30==0:print('Scanned',offset,'/',lookback_days,'days; pending issuer filings',len(all_rows),flush=True)
        if delay and offset+1<lookback_days:time.sleep(delay)
    rows=[];original_status={}
    complete=not days_error
    for ticker,item in pending.items():
        r=choose_candidate(all_rows,ticker,as_of)
        r['company']=item['name'];r['industry']=item['industry']
        # A partial scan cannot justify an authoritative latest-filing selection.
        if not complete and r['status']=='DISCOVERED_UNVERIFIED':
            r['status']='PARTIAL_SCAN';r['reason']='some_dates_failed; filing_selection_not_reliable';r['selected']=None
        rows.append(r)
        if download_originals and r['status']=='DISCOVERED_UNVERIFIED':
            docid=r['selected']['docID']
            try:
                raw=original_fetcher(docid)
                directory=output/'originals';directory.mkdir(exist_ok=True)
                (directory/f'{ticker}-{docid}-type1.zip').write_bytes(raw)
                original_status[ticker]={'docID':docid,'status':'DOWNLOADED_UNVERIFIED',
                                         'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
            except Exception as exc:
                original_status[ticker]={'docID':docid,'status':'DOWNLOAD_ERROR',
                                         'reason':type(exc).__name__+': '+str(exc)[:120]}
            if delay:time.sleep(delay)
    summary={'version':'3.16','as_of':as_of.isoformat(),
        'master_companies':30,'already_published':10,'pending_discovery':20,
        'reused_published_data_sha256':publication['data_sha256'],
        'daily_scan_requested':lookback_days,'daily_scan_succeeded':successful,
        'daily_scan_errors':days_error,'listing_complete':complete,
        'found_unverified':sum(r['status']=='DISCOVERED_UNVERIFIED' for r in rows),
        'awaiting_review':sum(r['status'] in ('AMBIGUOUS','CORRECTION_REVIEW','PARTIAL_SCAN') for r in rows),
        'not_found':sum(r['status']=='NOT_FOUND' for r in rows),
        'originals':original_status,
        'publication_approved_for_new_companies':False,
        'publication_status':'BLOCKED_NEW_COMPANIES',
        'note':'No new company is automatically included in public company-data.js.'}
    (output/'summary-v316.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output/'filing-candidates-v316.json').write_text(json.dumps({'summary':summary,'companies':rows},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    fields=('ticker','company','industry','status','docID','periodEnd','edinetCode','secCode','submitDateTime','correction_count','reason')
    with (output/'discovery-v316.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:
            doc=r.get('selected') or (r['candidates'][0] if r.get('candidates') else {})
            writer.writerow({'ticker':r['ticker'],'company':r['company'],'industry':r['industry'],
              'status':r['status'],'docID':doc.get('docID'),'periodEnd':r.get('period_end'),
              'edinetCode':doc.get('edinetCode'),'secCode':doc.get('secCode'),
              'submitDateTime':doc.get('submitDateTime'),'correction_count':r['correction_count'],
              'reason':r['reason']})
    print('Master 30: published 10 (untouched), pending 20; discovered',summary['found_unverified'],
          'days',successful,'/',lookback_days,'errors',len(days_error),flush=True)
    return summary


def main():
    p=argparse.ArgumentParser(description='v3.16 20-company source discovery; NO AUTO-PUBLICATION')
    p.add_argument('--master',default='company-master-v316.json')
    p.add_argument('--approved-js',default='company-data.js')
    p.add_argument('--output',default='v316-output')
    p.add_argument('--as-of',default=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat())
    p.add_argument('--lookback-days',type=int,default=220)
    p.add_argument('--delay',type=float,default=1.0)
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--download-originals',action='store_true')
    args=p.parse_args()
    try:
        as_of=date.fromisoformat(args.as_of)
        if as_of>datetime.now(ZoneInfo('Asia/Tokyo')).date():raise DiscoveryError('future date prohibited')
        if args.dry_run:
            master=load_master(args.master)
            pmeta=assert_existing_publication(master,args.approved_js)
            Path(args.output).mkdir(parents=True,exist_ok=True)
            result={'status':'MASTER_VALIDATED','companies':30,'published':10,'pending':20,
                    'approved_js_sha256':pmeta['data_sha256'],'auto_publication':False}
            (Path(args.output)/'master-check-v316.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
            print(json.dumps(result,ensure_ascii=False,indent=2))
        else:
            key=os.environ.get('EDINET_API_KEY')
            if not key:raise DiscoveryError('EDINET_API_KEY missing')
            summary=run(args.master,args.approved_js,args.output,as_of,args.lookback_days,args.delay,args.download_originals,key)
            if summary['daily_scan_errors']:raise SystemExit('EDINET listing scan incomplete; see artifact; nothing published')
    except (DiscoveryError,ValueError) as exc:
        print('BLOCKED:',exc,file=sys.stderr);raise SystemExit(1)

if __name__=='__main__':main()
