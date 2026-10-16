#!/usr/bin/env python3
"""Manufacturer Career Lab v3.19: safely stage 29 verified issuers + discover 50 new ones.

Never commits or deploys to GitHub Pages. The 29-company file is staged for
manual publication only. Previously unapproved companies are never exposed.
"""
from __future__ import annotations
import argparse
import csv
from datetime import date,datetime,timedelta
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import time
import zipfile
from zoneinfo import ZoneInfo

import edinet_v318 as prior
from discover_edinet_v316 import choose_candidate,daily_list,fetch_original

VERSION='3.19'
V318_FROZEN_MANIFEST_SHA256='dc6963c0a1e4165d6260264c115c62c3cf60cb5400ada5226b319b7766286d05'
STAGES={'PUBLISHED_BASELINE':10,'RELEASE_READY_29':19,'BLOCKED_METRIC_DEFINITION':1,
        'ORIGINAL_ACQUIRED_UNRECONCILED':30,'DISCOVERY_PENDING':50}
REQUIRED_FIELDS=('revenue','revenuePrev','operatingProfit','operatingCashFlow','equityRatio','averageSalary')

class GateError(ValueError):pass

def load_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def dump_json(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def canonical(obj):return json.dumps(obj,ensure_ascii=False,separators=(',', ':'),sort_keys=True).encode()

def master_validate(master_file, prior_master_file, frozen_file):
 m=load_json(master_file)
 if m.get('schema_version')!=VERSION or len(m.get('companies',[]))!=110:
  raise GateError('v3.19 master requires exactly 110 controlled issuers')
 rows=m['companies'];by={x['ticker']:x for x in rows}
 if len(by)!=110 or any(not re.fullmatch(r'[0-9]{4}',x.get('ticker','')) for x in rows):
  raise GateError('duplicate/invalid security code')
 counts={stage:sum(r.get('stage')==stage for r in rows) for stage in STAGES}
 if counts!=STAGES or any(r.get('stage') not in STAGES or r.get('expected_metrics')!=6 for r in rows):
  raise GateError('issuer stage/count mismatch: '+str(counts))
 original=prior.load_master(prior_master_file)
 for row in original['companies']:
  ticker=row['ticker'];actual=by.get(ticker)
  if not actual or any(actual.get(k)!=row.get(k) for k in ('ticker','name','industry','aliases','expected_metrics')):
   raise GateError('previous master identity altered: '+ticker)
  stage=row['stage']
  expected=('PUBLISHED_BASELINE' if stage=='PUBLISHED' else
            ('BLOCKED_METRIC_DEFINITION' if ticker=='6501' else 'RELEASE_READY_29') if stage=='SOURCE_RECONCILED_PENDING_APPROVAL' else
            'ORIGINAL_ACQUIRED_UNRECONCILED')
  if actual['stage']!=expected:raise GateError('invalid stage transition: '+ticker)
  if stage!='DISCOVERY_PENDING':
   for key in ('source_doc_id','edinet_code','source_payload_sha256'):
    if key in row and actual.get(key)!=row[key]:raise GateError('previous source identity changed: '+ticker)
 if digest(Path(frozen_file).read_bytes())!=V318_FROZEN_MANIFEST_SHA256:
  raise GateError('v3.18 original-source manifest SHA256 mismatch')
 manifest=load_json(frozen_file)
 if manifest.get('schema_version')!=VERSION or manifest.get('company_count')!=30 or len(manifest.get('companies',[]))!=30:
  raise GateError('v3.18 original-source manifest malformed')
 frozen={x['ticker']:x for x in manifest['companies']}
 if len(frozen)!=30 or set(frozen)!={r['ticker'] for r in rows if r['stage']=='ORIGINAL_ACQUIRED_UNRECONCILED'}:
  raise GateError('acquired-original issuer roster changed')
 for ticker,freeze in frozen.items():
  r=by[ticker]
  for key,col in [('docID','source_doc_id'),('edinetCode','edinet_code'),('source_zip_sha256','source_zip_sha256'),('source_payload_fingerprint','source_payload_fingerprint')]:
   if freeze[key]!=r.get(col):raise GateError('acquired original identity altered: '+ticker)
  if not re.fullmatch(r'[a-f0-9]{64}',freeze['source_zip_sha256']):raise GateError('invalid source digest')
 return m

def parse_public_js(path):
 raw=Path(path).read_text(encoding='utf-8')
 matches=re.findall(r'window\.MCL_COMPANIES\s*=\s*(\[.*?\]);\s*window\.MCL_DATASET_META',raw,re.S)
 if len(matches)!=1:raise GateError('unexpected company-data.js layout')
 arr=json.loads(matches[0]);ids=[x.get('id') for x in arr]
 if len(ids)!=len(set(ids)):raise GateError('duplicate public IDs')
 return arr

def review_and_stage(master,baseline_js,old_public,old_master,selections,baseline_json,source_zip,dest):
 # v3.18 independently validates the full frozen source metrics and baseline.
 summary,candidates,approval,old=prior.review_source(source_zip,old_master,selections,baseline_js,baseline_json,Path(dest)/'reconciliation')
 proposed=old+candidates
 if len(proposed)!=29 or len({x['id'] for x in proposed})!=29:
  raise GateError('unexpected final release roster')
 ids={x['id'] for x in proposed}
 m={r['ticker']:r for r in master['companies']}
 if ids!={k for k,r in m.items() if r['stage'] in ('PUBLISHED_BASELINE','RELEASE_READY_29')}:
  raise GateError('29-company staged roster not identical to verified master')
 for x in proposed:
  for f in REQUIRED_FIELDS:
   if type(x.get(f)) not in (int,float):raise GateError('incomplete public metric: '+x['id']+'/'+f)
  if x['sourceDocId']!=m[x['id']]['source_doc_id']:
   raise GateError('staged issuer provenance mismatch: '+x['id'])
 current=parse_public_js(old_public)
 if current!=old and current!=proposed:
  raise GateError('current live site contains unexpected values/companies; manual review required')
 # Guard a previously published 29-company site against the same 10-company baseline regression.
 if len(current)==29 and current[:10]!=old:raise GateError('original ten changed')
 payload=prior.js_for(proposed,summary['review_artifact_sha256'])
 payload=payload.replace('Generated by EDINET v3.18','Generated by EDINET v3.19').replace('window.MCL_DATASET_META = {"version":"3.18"','window.MCL_DATASET_META = {"version":"3.19"')
 output=Path(dest)/'site-ready';output.mkdir(parents=True,exist_ok=True)
 (output/'company-data.js').write_text(payload,encoding='utf-8')
 publish_summary={'version':VERSION,'previous_live_count':len(current),'staged_public_count':29,
  'new_verified_company_count':19,'verified_metric_count':114,'blocked_companies':['6501'],
  'staged_js_sha256':digest(payload.encode()),'source_review_sha256':summary['review_artifact_sha256'],
  'deployed_to_github_pages':False,'requires_manual_root_file_replacement':True,
  'additional_80_companies_auto_published':False}
 dump_json(Path(dest)/'release-summary-v319.json',publish_summary)
 print('RELEASE PREPARED: 29 reconciled companies; live repo not modified.',flush=True)
 return publish_summary

def discover(master,dest,as_of,lookback,delay,download_originals,key=None,listing=None,originals=None):
 if not 1<=lookback<=400 or not 0<=delay<=20:raise GateError('invalid scan window/delay')
 if as_of>datetime.now(ZoneInfo('Asia/Tokyo')).date():raise GateError('future scan date')
 waiting={r['ticker']:r for r in master['companies'] if r['stage']=='DISCOVERY_PENDING'}
 if len(waiting)!=50:raise GateError('not exactly 50 pending firms')
 if listing is None:
  if not key:raise GateError('EDINET_API_KEY missing')
  listing=lambda day:daily_list(day,key)
 if download_originals and originals is None:
  if not key:raise GateError('EDINET_API_KEY missing')
  originals=lambda docid:fetch_original(docid,key)
 report=Path(dest)/'discovery-report';report.mkdir(parents=True,exist_ok=True)
 rows=[];failed=[];ok=0
 for i in range(lookback):
  day=as_of-timedelta(days=i)
  try:
   entries=listing(day)
   if not isinstance(entries,list):raise ValueError('EDINET results not a list')
   ok+=1
   rows.extend(x for x in entries if isinstance(x,dict) and str(x.get('secCode',''))[:4] in waiting and str(x.get('docTypeCode')) in ('120','130'))
  except Exception as exc:
   failed.append({'day':day.isoformat(),'error_type':type(exc).__name__})
  if (i+1)%25==0:print('EDINET scanning day',i+1,'/',lookback,flush=True)
  if delay and i+1<lookback:time.sleep(delay)
 choices=[];manifest=[];docids=set()
 for pos,(ticker,item) in enumerate(waiting.items()):
  selection=choose_candidate(rows,ticker,as_of)
  selection['company']=item['name'];selection['industry']=item['industry']
  if failed and selection['status']=='DISCOVERED_UNVERIFIED':
   selection.update(status='PARTIAL_SCAN',selected=None,reason='daily_list_failure_blocks_latest_report_selection')
  chosen=selection.get('selected')
  if chosen and (chosen['docID'] in docids or str(chosen.get('secCode',''))[:4]!=ticker):
   selection.update(status='AMBIGUOUS',selected=None,reason='conflicting_filing_identity');chosen=None
  if chosen:docids.add(chosen['docID'])
  choices.append(selection)
  if chosen and selection['status']=='DISCOVERED_UNVERIFIED' and download_originals:
   try:
    raw=originals(chosen['docID'])
    if len(raw)>80_000_000:raise GateError('oversize downloaded original')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
     if z.testzip() is not None:raise GateError('corrupt original ZIP')
     members=[x for x in z.infolist() if '/publicdoc/' in ('/'+x.filename.lower()) and x.filename.lower().endswith('.xbrl')]
     if not members:raise GateError('original XBRL absent')
     file_digest=digest(b''.join(sorted(hashlib.sha256(z.read(x)).digest() for x in members)))
    group=pos//10+1
    batch=Path(dest)/f'originals-batch-{group:02d}';batch.mkdir(parents=True,exist_ok=True)
    filename=f'{ticker}-{chosen["docID"]}-type1.zip';(batch/filename).write_bytes(raw)
    manifest.append({'ticker':ticker,'company':item['name'],'docID':chosen['docID'],
        'edinetCode':chosen.get('edinetCode'),'archive':filename,'batch':group,
        'status':'DOWNLOADED_UNRECONCILED','archive_sha256':digest(raw),
        'xbrl_fingerprint':file_digest,'size_bytes':len(raw)})
   except Exception as exc:
    manifest.append({'ticker':ticker,'company':item['name'],'docID':chosen['docID'],
        'status':'DOWNLOAD_ERROR','reason':type(exc).__name__})
 summary={'version':VERSION,'target_companies':110,'eligible_release':29,'new_discovery_targets':50,
  'days_requested':lookback,'days_succeeded':ok,'days_failed':len(failed),'daily_scan_complete':not failed,
  'found_unverified':sum(r['status']=='DISCOVERED_UNVERIFIED' for r in choices),
  'needs_review':sum(r['status'] not in ('DISCOVERED_UNVERIFIED','NOT_FOUND') for r in choices),
  'not_found':sum(r['status']=='NOT_FOUND' for r in choices),
  'originals_downloaded':sum(x['status']=='DOWNLOADED_UNRECONCILED' for x in manifest),
  'originals_failed':sum(x['status']=='DOWNLOAD_ERROR' for x in manifest),
  'new_companies_published':0,'live_site_modified':False,'fail_closed':True,'days_failed_detail':failed}
 dump_json(report/'discovery-summary-v319.json',summary)
 dump_json(report/'discovery-candidates-v319.json',{'companies':choices})
 dump_json(report/'originals-manifest-v319.json',{'companies':manifest})
 with (report/'discovery-v319.csv').open('w',encoding='utf-8-sig',newline='') as file:
  writer=csv.DictWriter(file,fieldnames=['ticker','name','industry','status','docID','edinetCode','reason'])
  writer.writeheader()
  for c in choices:
   selected=c.get('selected') or {}
   writer.writerow({'ticker':c['ticker'],'name':c['company'],'industry':c['industry'],'status':c['status'],
                    'docID':selected.get('docID',''),'edinetCode':selected.get('edinetCode',''),'reason':c['reason']})
 print('DISCOVERY',summary['found_unverified'],'/50; originals',summary['originals_downloaded'],'; scan errors',len(failed),flush=True)
 return summary

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('command',choices=['stage-release','discover','validate'])
 parser.add_argument('--master',default='company-master-v319.json')
 parser.add_argument('--old-master',default='company-master-v318.json')
 parser.add_argument('--frozen-originals',default='v318-originals-manifest-v319.json')
 parser.add_argument('--baseline-js',default='approved-ten-company-data-v319.js')
 parser.add_argument('--current-js',default='company-data.js')
 parser.add_argument('--baseline',default='approved-ten-baseline-v318.json')
 parser.add_argument('--selections',default='filing-selections-v317.json')
 parser.add_argument('--review',default='v317-review-v318.zip')
 parser.add_argument('--output',default='v319-output')
 parser.add_argument('--lookback-days',type=int,default=220)
 parser.add_argument('--delay',type=float,default=1.0)
 parser.add_argument('--download-originals',action='store_true')
 parser.add_argument('--as-of',default=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat())
 args=parser.parse_args()
 try:
  master=master_validate(args.master,args.old_master,args.frozen_originals)
  if args.command=='stage-release':
   review_and_stage(master,args.baseline_js,args.current_js,args.old_master,args.selections,args.baseline,args.review,args.output)
  elif args.command=='discover':
   # Validate existing 10/29 before external fetching.
   review_and_stage(master,args.baseline_js,args.current_js,args.old_master,args.selections,args.baseline,args.review,args.output)
   result=discover(master,args.output,date.fromisoformat(args.as_of),args.lookback_days,args.delay,
                   args.download_originals,os.environ.get('EDINET_API_KEY'))
   if result['days_failed'] or result['originals_failed']:
    raise GateError('partial discovery / download; inspect uploaded reports')
  else:
   print('MASTER VALID: 10+19+1+30+50',flush=True)
 except (GateError,prior.GateError,ValueError,KeyError,zipfile.BadZipFile,FileNotFoundError) as exc:
  print('BLOCKED:',type(exc).__name__,str(exc)[:250],file=sys.stderr)
  raise SystemExit(1)
if __name__=='__main__':main()
