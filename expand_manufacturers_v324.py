#!/usr/bin/env python3
"""Manufacturer coverage expansion, v3.24 (RESEARCH/REVIEW ONLY).

Inputs: public company-data.js (209 verified), JPX CSV export, EDINET API key.
Outputs are never deployed or written to the public site automatically.
All new published rows require live original XBRL 6/6 and manual approval.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date, datetime, timedelta
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
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo

MFG = frozenset('食料品 繊維製品 パルプ・紙 化学 医薬品 石油・石炭製品 ゴム製品 ガラス・土石製品 鉄鋼 非鉄金属 金属製品 機械 電気機器 輸送用機器 精密機器 その他製品'.split())
# The sector list above is intentionally strict: a nonmanufacturing 33-sector issuer
# with a manufacturing segment requires a separately documented manual decision.
ENDPOINT = 'https://api.edinet-fsa.go.jp/api/v2'
METRICS = {'revenue_oku':'revenue','prior_revenue_oku':'revenuePrev','operating_profit_oku':'operatingProfit',
           'operating_cf_oku':'operatingCashFlow','equity_ratio_pct':'equityRatio','average_salary_man':'averageSalary'}
DOC_CODE = re.compile(r'^S[A-Z0-9]{7,15}$')
TICKER = re.compile(r'^(?:[0-9]{4}|[0-9]{3}[A-Z])$')

class GateError(ValueError): pass

def emit(path, payload):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def safe_sha(x):return hashlib.sha256(x).hexdigest()

def now_jst():return datetime.now(ZoneInfo('Asia/Tokyo'))

def norm(s):return re.sub(r'\s+','',str(s).replace('（','(').replace('）',')').replace('・',''))

def parse_public(path):
    data=Path(path).read_text('utf-8')
    m=re.search(r'(window\.MCL_COMPANIES\s*=\s*)(\[.*?\])(\s*;\s*window\.MCL_DATASET_META\s*=\s*)(\{.*?\})(\s*;\s*window\.MCL_DEMOS\s*=)',data,re.S)
    if not m:raise GateError('company-data.js is not a compatible MCL dataset')
    rows=json.loads(m.group(2));meta=json.loads(m.group(4))
    ids=[str(r['id']) for r in rows]
    if len(ids)!=len(set(ids)):raise GateError('duplicate existing ticker')
    return data,m,rows,meta

def _column(cols,aliases):
    exact={norm(k).lower():k for k in cols if k}
    for name in aliases:
        if norm(name).lower() in exact:return exact[norm(name).lower()]
    raise GateError('JPX CSV missing column '+str(aliases)+'; actual columns='+str(cols))

def normalize_ticker(value):
    s=str(value).strip().upper()
    if s.endswith('.0'):s=s[:-2]
    if not TICKER.fullmatch(s):raise GateError('unsupported ticker '+repr(value))
    return s

def parse_jpx(csvfile,public_file):
    _,_,existing,_=parse_public(public_file)
    public={str(x['id']) for x in existing}
    with open(csvfile,encoding='utf-8-sig',newline='') as f:
        # Strict 33-sector category; don't confuse 17-sector with it.
        rd=csv.DictReader(f)
        if not rd.fieldnames:raise GateError('empty CSV or missing header')
        code=_column(rd.fieldnames,('コード','銘柄コード','証券コード','証券コード（4桁）','Code','Local Code'))
        name=_column(rd.fieldnames,('銘柄名','会社名','企業名','銘柄名称','Company Name','Name'))
        sector=_column(rd.fieldnames,('33業種区分','33業種名','33業種','業種（33業種）','業種区分（33業種）','33 Sector Name'))
        market=None
        for alias in ('市場区分','市場・商品区分','市場','Market/Products'):
            if norm(alias).lower() in {norm(s).lower() for s in rd.fieldnames}:
                market=_column(rd.fieldnames,(alias,));break
        out=[];rejected=[];seen={}
        for n,row in enumerate(rd,2):
            ind=str(row.get(sector) or '').strip();nm=str(row.get(name) or '').strip()
            if ind not in MFG:continue
            try:code4=normalize_ticker(row.get(code,''))
            except GateError as e:rejected.append({'line':n,'reason':str(e),'company':nm});continue
            # JPX sometimes has multiple securities for an issuer. First exact unique identity wins;
            # conflicting duplicate issuer metadata goes to review, not a silent overwrite.
            if code4 in seen:
                if seen[code4]['name']!=nm or seen[code4]['industry']!=ind:
                    rejected.append({'line':n,'reason':'conflicting duplicate code','ticker':code4,'company':nm})
                continue
            r={'ticker':code4,'name':nm,'industry':ind,'market':str(row.get(market) or '') if market else '',
               'stage':'ALREADY_PUBLISHED' if code4 in public else 'RESEARCH_UNVERIFIED',
               'source':'JPX CSV; 33-sector manufacturer'}
            seen[code4]=r;out.append(r)
    if len(out)!=len(seen):raise GateError('universe duplicate identifiers')
    return sorted(out,key=lambda r:r['ticker']),rejected,public

def universe(args):
    rows,rejected,public=parse_jpx(args.jpx,args.public)
    # Existing 209 are mandatory even if JPX classifies some as non-manufacturing
    # or issuer was newly delisted; don't silently delete existing controlled rows.
    overlap=sum(x['stage']=='ALREADY_PUBLISHED' for x in rows)
    info={'version':'3.24','as_of_jst':now_jst().date().isoformat(),
          'source_csv_name':Path(args.jpx).name,'source_csv_sha256':safe_sha(Path(args.jpx).read_bytes()),
          'definition':'16 manufacturing sectors in JPX 33-sector classification',
          'universe_count':len(rows),'current_published_count':len(public),
          'existing_issuer_overlap':overlap,'new_research_only':len(rows)-overlap,
          'rejected_rows':rejected,'companies':rows}
    emit(args.output,info)
    print(json.dumps({k:v for k,v in info.items() if k not in ('companies','rejected_rows')},ensure_ascii=False))
    if len(rows)<1001:print('WARNING: strict-sector universe under 1001; widen scope only with documented rule')

def edinet_ticker(s):
    s=str(s or '').strip().upper()
    if (len(s) in (5,6)) and s.endswith('0') and TICKER.fullmatch(s[:4]):return s[:4]
    if TICKER.fullmatch(s):return s
    return None

def _open(url,max_bytes=18_000_000):
    req=urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-v324-source-review'})
    # The URL embeds a secret. Never expose exception URLs (including tracebacks).
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=105) as x:data=x.read(max_bytes+1)
            if len(data)>max_bytes:raise GateError('oversized EDINET response')
            return data
        except urllib.error.HTTPError as e:
            if e.code in (429,500,502,503,504) and attempt<2:
                time.sleep(4*(attempt+1));continue
            raise GateError('EDINET HTTP error: '+str(e.code)) from None
        except urllib.error.URLError:
            if attempt<2:time.sleep(3*(attempt+1));continue
            raise GateError('EDINET network error (no secret logged)') from None
    raise GateError('unreachable EDINET retry state')

def day_docs(d,key):
    params=urllib.parse.urlencode({'date':d.isoformat(),'type':'2','Subscription-Key':key})
    p=json.loads(_open(ENDPOINT+'/documents.json?'+params))
    if str(p.get('metadata',{}).get('status','200')) not in ('200','200.0'):
        raise GateError('EDINET daily API status unsuccessful')
    if not isinstance(p.get('results'),list):raise GateError('invalid EDINET daily list')
    return p['results']

def original_zip(doc,key):
    if not DOC_CODE.fullmatch(doc):raise GateError('unexpected document ID')
    p=urllib.parse.urlencode({'type':1,'Subscription-Key':key})
    raw=_open(ENDPOINT+'/documents/'+doc+'?'+p,80_000_000)
    if not zipfile.is_zipfile(io.BytesIO(raw)):raise GateError('EDINET original is not ZIP')
    return raw

def index(args):
    key=os.environ.get('EDINET_API_KEY')
    if not key:raise GateError('GitHub Actions secret EDINET_API_KEY required')
    catalog=load(args.universe);codes={x['ticker'] for x in catalog['companies']}
    if not codes:raise GateError('empty universe')
    days=args.days
    if not 1<=days<=450:raise GateError('days must be 1..450')
    stop=date.fromisoformat(args.end) if args.end else now_jst().date()
    keep={};scanned={}
    if Path(args.output).exists():
        prev=load(args.output)
        if prev.get('universe_sha256')!=safe_sha(Path(args.universe).read_bytes()):raise GateError('universe changed since prior checkpoint')
        keep={s['docID']:s for s in prev['filings']}
        scanned={s['day']:s for s in prev['scanned_days']}
    for i in range(days):
        d=stop-timedelta(days=i)
        if d.isoformat() in scanned:continue
        if i and args.delay:time.sleep(args.delay)
        # No silent skip on failed EDINET day; checkpoint permits safe retry.
        rows=day_docs(d,key)
        hits=0
        for r in rows:
            code=edinet_ticker(r.get('secCode'))
            if code not in codes or str(r.get('docTypeCode')) not in ('120','130'):continue
            doc=str(r.get('docID',''))
            if not DOC_CODE.fullmatch(doc):continue
            hits+=1
            keep[doc]={k:r.get(k) for k in ('docID','secCode','edinetCode','filerName','docTypeCode','withdrawalStatus',
              'periodStart','periodEnd','submitDateTime','xbrlFlag','csvFlag')}
        scanned[d.isoformat()]={'day':d.isoformat(),'matched_filings':hits}
        if i%15==0 or i==days-1:
            emit(args.output,{'version':'3.24','universe_sha256':safe_sha(Path(args.universe).read_bytes()),
                 'filings':sorted(keep.values(),key=lambda x:x['docID']),
                 'scanned_days':sorted(scanned.values(),key=lambda x:x['day'])})
        print(f'day {i+1}/{days} {d.isoformat()} matched {hits}',flush=True)
    print('EDINET annual report and correction entries:',len(keep),'scanned days:',len(scanned))

def choose(rows,asof):
    def proper(r):
        try:return (r.get('docTypeCode')=='120' and str(r.get('withdrawalStatus','0'))=='0'
         and str(r.get('xbrlFlag'))=='1' and str(r.get('csvFlag'))=='1'
         and date.fromisoformat(str(r['periodStart']))<date.fromisoformat(str(r['periodEnd']))<=asof
         and date.fromisoformat(str(r['submitDateTime'])[:10])<=asof)
        except (KeyError,ValueError,TypeError):return False
    valid=[r for r in rows if proper(r)]
    if not valid:return 'NO_VALID_ANNUAL_REPORT',None
    latest=max(r['periodEnd'] for r in valid)
    if any(str(x.get('docTypeCode'))=='130' and x.get('periodEnd')==latest for x in rows):
        return 'CORRECTED_FILING_REVIEW',None
    recent={r['docID']:r for r in valid if r['periodEnd']==latest}
    if len(recent)!=1:return 'MULTIPLE_ANNUAL_REPORTS_REVIEW',None
    return 'SELECTED',next(iter(recent.values()))

def _audit_one(filing,name,sector,raw):
    import edinet_v313 as v313
    import edinet_v317 as v317
    from edinet_v320 import fingerprint_zip
    code=edinet_ticker(filing['secCode'])
    if not code or not DOC_CODE.fullmatch(filing['docID']):raise GateError('invalid filing identity')
    facts,contexts,instance=v313.original_instance(raw,filing)
    with zipfile.ZipFile(io.BytesIO(raw)) as z:root=ET.fromstring(z.read(instance))
    vals={(x.text or '').strip() for x in root if v313.local(x.tag)=='AccountingStandardsDEI'}
    if len(vals)!=1:raise GateError('AccountingStandardsDEI missing or conflicting')
    gaap={'IFRS':'IFRS','Japan GAAP':'JP_GAAP','JapanGAAP':'JP_GAAP','Japanese GAAP':'JP_GAAP'}.get(next(iter(vals)))
    if gaap is None:raise GateError('unrecognized / not-yet-supported GAAP')
    o={'metrics':{}};v317.common_numeric(facts,filing,gaap,o)
    verified=sum(o['metrics'][m]['status']=='SOURCE_RECONCILED' for m in METRICS)
    eligible=verified==6 and all(Decimal(str(o['metrics'][m]['value'])).is_finite() for m in METRICS)
    raw_xbrl=None
    with zipfile.ZipFile(io.BytesIO(raw)) as z:raw_xbrl=safe_sha(z.read(instance))
    record={'ticker':code,'name':str(filing.get('filerName') or name),'jpx_name':name,'industry':sector,
       'docID':filing['docID'],'edinetCode':filing['edinetCode'],
       'periodStart':filing['periodStart'],'periodEnd':filing['periodEnd'],
       'gaap':gaap,'verifiedAt':now_jst().date().isoformat(),
       'sourceOriginalSha256':safe_sha(raw),'sourceXbrlSha256':raw_xbrl,
       'sourcePayloadFingerprint':fingerprint_zip(raw),'sourceInstance':instance,
       'metrics':o['metrics'],'verifiedMetricCount':verified,
       'status':'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW' if eligible else 'BLOCKED_INCOMPLETE',
       'approved_for_publication':False,'independent_EDINET_CSV_crosscheck':False}
    return record

def audit(args):
    cat=load(args.universe); index_obj=load(args.index)
    if index_obj.get('universe_sha256')!=safe_sha(Path(args.universe).read_bytes()):raise GateError('index/universe hash mismatch')
    _,_,public,_=parse_public(args.public)
    published={str(x['id']) for x in public}
    all_new=[c for c in cat['companies'] if c['ticker'] not in published]
    if args.offset<0 or args.limit<1 or args.limit>80:raise GateError('offset or limit invalid')
    selected=all_new[args.offset:args.offset+args.limit]
    if not selected:raise GateError('empty batch')
    code_filings={}
    for r in index_obj['filings']:
        code=edinet_ticker(r.get('secCode'))
        if code:code_filings.setdefault(code,[]).append(r)
    key=os.environ.get('EDINET_API_KEY')
    if not key:raise GateError('EDINET_API_KEY is required')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    results=[]
    for i,c in enumerate(selected):
        code=c['ticker'];state,filing=choose(code_filings.get(code,[]),now_jst().date())
        r={'ticker':code,'name':c['name'],'industry':c['industry'],
           'status':state,'approved_for_publication':False}
        if filing:
            try:
                raw=original_zip(filing['docID'],key)
                r=_audit_one(filing,c['name'],c['industry'],raw)
                r['market']=c.get('market','')
            except Exception as e:
                r.update({'docID':filing['docID'],'status':'BLOCKED_SOURCE_AUDIT','failure':type(e).__name__+': '+str(e)[:240]})
        results.append(r)
        emit(output/(code+'.json'),r)
        print(f'{i+1}/{len(selected)} {code} {r["status"]}',flush=True)
        if i+1<len(selected):time.sleep(args.delay)
    emit(output/'batch-summary.json',{'version':'3.24','offset':args.offset,'limit':args.limit,
      'attempted':len(results),'fully_source_reconciled':sum(r['status'].startswith('SOURCE_RECONCILED') for r in results),
      'published':0,'rejected_or_blocked':sum(not r['status'].startswith('SOURCE_RECONCILED') for r in results)})

def stage(args):
    raw,m,existing,meta=parse_public(args.public)
    previously={str(r['id']) for r in existing}
    with open(args.approvals,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    approved=[normalize_ticker(r['ticker']) for r in rows if str(r.get('approved','')).strip().upper()=='YES']
    if len(approved)!=len(set(approved)):raise GateError('duplicated human approval')
    if not approved:raise GateError('no human-approved tickers; publishing prohibited')
    additional=[];seen_ids=set()
    for c in approved:
        if c in previously:raise GateError('existing company cannot be replaced: '+c)
        p=Path(args.audit_dir)/(c+'.json')
        if not p.is_file():raise GateError('audit proof absent: '+c)
        audit=load(p)
        if audit.get('ticker')!=c or audit.get('status')!='SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW':
            raise GateError('six-metric approval gate failed: '+c)
        if len(audit['metrics'])!=6 or audit['verifiedMetricCount']!=6:raise GateError('audit metadata incomplete: '+c)
        if not DOC_CODE.fullmatch(audit['docID']):raise GateError('EDINET document ID invalid: '+c)
        if not all(re.fullmatch('[a-f0-9]{64}',str(audit.get(k,''))) for k in ('sourceOriginalSha256','sourceXbrlSha256','sourcePayloadFingerprint')):
            raise GateError('source fingerprints missing: '+c)
        if c in seen_ids:raise GateError('duplicate approval')
        seen_ids.add(c)
        record={'id':c,'name':audit['name'],'aliases':[],'industry':audit['industry'],'market':audit.get('market',''),
          'period':audit['periodStart']+'〜'+audit['periodEnd'],
          'scope':'連結（給与のみ提出会社）','salaryScope':'提出会社単体',
          'accountingStandard':audit['gaap'],'sourceLabel':'EDINET 有価証券報告書（書類ID: '+audit['docID']+'）',
          'sourceUrl':'https://disclosure2.edinet-fsa.go.jp/','sourceDocId':audit['docID'],
          'sourceSha256':audit['sourceOriginalSha256'],'sourcePayloadFingerprint':audit['sourcePayloadFingerprint'],
          'sourceXbrlSha256':audit['sourceXbrlSha256'],'verifiedAt':audit['verifiedAt']}
        for metric,field in METRICS.items():
            obj=audit['metrics'][metric]
            if obj['status']!='SOURCE_RECONCILED':raise GateError('non-reconciled metric '+metric+'/'+c)
            record[field]=float(Decimal(str(obj['value'])))
        additional.append(record)
    total=len(existing)+len(additional)
    if total<args.require_count:raise GateError(f'only {total} verified / human-approved companies; require {args.require_count}; no release')
    data=existing+sorted(additional,key=lambda x:x['id'])
    meta.update({'version':'3.24','status':'STAGED_NOT_DEPLOYED','count':total,
     'priorApprovedCount':len(existing),'newSourceAuditedCount':len(additional),
     'independent_EDINET_CSV_crosscheck':False,
     'publication':'manual review only; never auto-deployed'})
    result=raw[:m.start(2)]+json.dumps(data,ensure_ascii=False,separators=(',',':'))+raw[m.end(2):m.start(4)]+json.dumps(meta,ensure_ascii=False,separators=(',',':'))+raw[m.end(4):]
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    (out/'company-data.js').write_text(result,encoding='utf-8')
    emit(out/'MANUAL-RELEASE-SUMMARY.json',{'version':'3.24','prior':len(existing),'additional':len(additional),
     'staged_total':total,'manual_approval_required':True,'deployed':False,
     'source_sha256':safe_sha(result.encode('utf-8'))})
    print('Staged '+str(total)+' companies. NOT DEPLOYED.')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('universe');p.add_argument('--jpx',required=True);p.add_argument('--public',default='company-data.js');p.add_argument('--output',default='manufacturing-universe-v324.json');p.set_defaults(func=universe)
    p=sub.add_parser('index');p.add_argument('--universe',default='manufacturing-universe-v324.json');p.add_argument('--days',type=int,default=400);p.add_argument('--end');p.add_argument('--delay',type=float,default=1.0);p.add_argument('--output',default='edinet-index-v324.json');p.set_defaults(func=index)
    p=sub.add_parser('audit');p.add_argument('--universe',default='manufacturing-universe-v324.json');p.add_argument('--index',default='edinet-index-v324.json');p.add_argument('--public',default='company-data.js');p.add_argument('--offset',type=int,default=0);p.add_argument('--limit',type=int,default=50);p.add_argument('--delay',type=float,default=1.0);p.add_argument('--output',default='review-v324');p.set_defaults(func=audit)
    p=sub.add_parser('stage');p.add_argument('--public',default='company-data.js');p.add_argument('--audit-dir',default='review-v324');p.add_argument('--approvals',default='approved-v324.csv');p.add_argument('--require-count',type=int,default=1001);p.add_argument('--output',default='staged-v324');p.set_defaults(func=stage)
    args=parser.parse_args();args.func(args)

if __name__=='__main__':main()
