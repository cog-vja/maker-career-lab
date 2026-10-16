#!/usr/bin/env python3
"""Manufacturer Career Lab v3.20 - 102-company manual-release staging and source re-verification.

Important: this tool NEVER commits/deploys. New companies require six original-XBRL
metrics and explicit manual upload of the staged site-ready files. The frozen
original-file fingerprints and values are checked again in live mode.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

VERSION='3.20'
BASELINE_SHA='2f4556d38bbb4e14b0d860fe41a84e2de8dee6b39865917aff607c6ccb0b222b'
MASTER_SHA='e9d4d3e5dbacc1304c721058f2b1ec0256c6d27f74e7ccf4578268558c050181'
AUDIT_SHA='52dd9ce0dd90ed24e751883c030da3d0d686b7ec527bd95c052708b06850eaf0'
METRICS=('revenue_oku','prior_revenue_oku','operating_profit_oku',
         'operating_cf_oku','equity_ratio_pct','average_salary_man')
PUBLIC_FIELDS=('revenue','revenuePrev','operatingProfit','operatingCashFlow','equityRatio','averageSalary')
SOURCE_TO_PUBLIC=dict(zip(METRICS,PUBLIC_FIELDS))
CATEGORIES={'PUBLISHED_BASELINE','RELEASE_READY_29','BLOCKED_METRIC_DEFINITION',
            'ORIGINAL_ACQUIRED_UNRECONCILED','DISCOVERY_PENDING'}
SAFE_AD_HOSTS={'px.a8.net','www.a8.net','a8.net'}

class GateError(ValueError):pass

def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def check_fixed(path,expected):
 if not Path(path).is_file() or sha(Path(path).read_bytes())!=expected:
  raise GateError('frozen historical input changed or missing: '+str(path))

def public_js_read(path):
 content=Path(path).read_text(encoding='utf-8')
 items=re.findall(r'window\.MCL_COMPANIES\s*=\s*(\[.*?\]);\s*window\.MCL_DATASET_META',content,re.S)
 if len(items)!=1:raise GateError('unrecognized baseline JS assignment')
 arr=json.loads(items[0]);return arr,content

def validate_frozen(master_file,baseline_file,audit_file):
 check_fixed(master_file,MASTER_SHA);check_fixed(baseline_file,BASELINE_SHA);check_fixed(audit_file,AUDIT_SHA)
 master=load(master_file)['companies']
 audit=load(audit_file)['companies']
 baseline,_=public_js_read(baseline_file)
 if len(master)!=110 or len(audit)!=79 or len(baseline)!=29:raise GateError('incorrect cohort counts')
 known={r['ticker']:r for r in master}
 if len(known)!=110 or any(not re.fullmatch(r'\d{4}',id) for id in known):raise GateError('duplicate/invalid master IDs')
 publ={str(r['id']):r for r in baseline}
 if len(publ)!=29 or any(str(id) not in known for id in publ):raise GateError('invalid baseline public IDs')
 expected_publ={'PUBLISHED_BASELINE','RELEASE_READY_29'}
 if {id for id,r in known.items() if r['stage'] in expected_publ}!=set(publ):
  raise GateError('29-company baseline differs from master')
 rec={r['ticker']:r for r in audit}
 if len(rec)!=79 or set(rec)!={id for id in known if id not in publ and id!='6501' and id!='6965'}:
  raise GateError('source audit missing or unexpected issuer')
 successes=0; blocked=[]
 for ticker,row in rec.items():
  if known[ticker].get('source_doc_id') and row['docID']!=known[ticker]['source_doc_id']:
   raise GateError('source document mismatch '+ticker)
  if not re.fullmatch(r'[a-f0-9]{64}',row['publicdoc_fingerprint']):raise GateError('invalid original fingerprint')
  if not re.fullmatch(r'[a-f0-9]{64}',row['original_zip_sha256']):raise GateError('invalid original ZIP hash')
  if row['filing']['secCode'][:4]!=ticker or row['filing']['docID']!=row['docID'] or row['filing']['docTypeCode']!='120' or row['filing']['withdrawalStatus']!='0':
   raise GateError('invalid filing scope '+ticker)
  if row['periodStart']!=row['filing']['periodStart'] or row['periodEnd']!=row['filing']['periodEnd'] or row['periodStart']>row['periodEnd']:
   raise GateError('invalid fiscal period '+ticker)
  if set(row['metrics'])!=set(METRICS):raise GateError('incomplete source audit metrics '+ticker)
  verified=0
  for k in METRICS:
   fact=row['metrics'][k]
   if fact['status']=='SOURCE_RECONCILED':
    verified+=1
    if 'evidence' not in fact or not isinstance(fact['evidence'],dict):raise GateError('missing fact proof: '+ticker+' '+k)
    try:num=Decimal(fact['value'])
    except (InvalidOperation,TypeError):raise GateError('invalid metric value')
    if not num.is_finite():raise GateError('nonfinite metric')
    if k in ('revenue_oku','prior_revenue_oku','average_salary_man') and num<=0:raise GateError('nonpositive metric')
    if k=='equity_ratio_pct' and not (Decimal('0')<=num<=Decimal('100')):raise GateError('equity ratio invalid')
   elif fact['status']!='BLOCKED':raise GateError('unrecognized verification status')
  if verified!=row['reconciled_count'] or 6-verified!=row['blocked_count']:raise GateError('incorrect metric count')
  if verified==6:successes+=1
  else:blocked.append(ticker)
 if successes!=73 or len(blocked)!=6 or set(blocked)!={'6301','7011','7012','7741','7751','5713'}:
  raise GateError('source quality count changed')
 return master,baseline,audit

def build_public(master,baseline,audit):
 by={r['ticker']:r for r in audit}
 ready=[]
 for r in master:
  ticker=r['ticker']
  if ticker in {str(x['id']) for x in baseline}:continue
  source=by.get(ticker)
  if not source or source['reconciled_count']!=6:continue
  vals={SOURCE_TO_PUBLIC[k]:float(Decimal(source['metrics'][k]['value'])) for k in METRICS}
  # All six inputs are consolidated facts except average salary (filing company only).
  row={'id':ticker,'name':r['name'],'aliases':r.get('aliases',[]),
       'period':source['periodStart']+'〜'+source['periodEnd'],
       'scope':'連結（給与のみ提出会社）','salaryScope':'提出会社単体',
       'accountingStandard':source['gaap'],
       'sourceLabel':'EDINET 有価証券報告書（書類ID: '+source['docID']+'）',
       'sourceUrl':'https://disclosure2.edinet-fsa.go.jp/',
       'sourceDocId':source['docID'],
       'sourceSha256':source['original_zip_sha256'],
       'sourcePayloadFingerprint':source['publicdoc_fingerprint'],
       'verifiedAt':'2026-10-16',
       **vals}
  ready.append(row)
 if len(ready)!=73:raise GateError('expected 73 audited new issuers')
 merged=baseline+ready
 if len(merged)!=102 or len({x['id'] for x in merged})!=102:raise GateError('public issuer count incorrect')
 if merged[:29]!=baseline:raise GateError('prior 29 source data changed')
 return merged

def generate_js(merged):
 demo=[
 {'id':'demo-a','name':'【架空】サンプル現職メーカー','demo':True,'period':'架空の2025年度','scope':'連結','salaryScope':'架空の単体','sourceLabel':'架空デモ','revenue':1000,'operatingProfit':80,'revenuePrev':950,'operatingCashFlow':90,'equityRatio':48,'averageSalary':680},
 {'id':'demo-b','name':'【架空】サンプル検討先メーカー','demo':True,'period':'架空の2025年度','scope':'連結','salaryScope':'架空の単体','sourceLabel':'架空デモ','revenue':1200,'operatingProfit':216,'revenuePrev':1050,'operatingCashFlow':130,'equityRatio':62,'averageSalary':820}
 ]
 meta={'version':VERSION,'status':'MANUAL_PUBLICATION_READY','count':len(merged),'priorApprovedCount':29,
       'newSourceAuditedCount':73,'publication':'manual root-file replacement only',
       'disclaimer':'Accounting dates and GAAP vary; salary is filing-company standalone.'}
 return ('/* v3.20: 102 original-XBRL audited company entries; manual publishing required. */\n'
         'window.MCL_COMPANIES = '+json.dumps(merged,ensure_ascii=False,separators=(',',':'))+';\n'
         'window.MCL_DATASET_META = '+json.dumps(meta,ensure_ascii=False,separators=(',',':'))+';\n'
         'window.MCL_DEMOS = '+json.dumps(demo,ensure_ascii=False,separators=(',',':'))+';\n')

def validate_ads(config):
 if set(config)-{'version','enabled','placements'}:raise GateError('unexpected advertising configuration keys')
 if config.get('version')!=VERSION or type(config.get('enabled')) is not bool:raise GateError('invalid ad config')
 placements=config.get('placements')
 if not isinstance(placements,list) or len(placements)>3:raise GateError('invalid ad count')
 slots=set()
 for ad in placements:
  if not isinstance(ad,dict) or set(ad)!={'slot','label','url','sponsor'}:raise GateError('invalid advertisement entry')
  if ad['slot'] not in ('compare-below-results',):raise GateError('unknown ad slot')
  if ad['slot'] in slots:raise GateError('duplicate ad slot')
  slots.add(ad['slot'])
  for field in ('label','sponsor'):
   t=ad[field]
   if not isinstance(t,str) or not (1<=len(t)<=100) or any(ord(c)<32 for c in t) or '<' in t or '>' in t:
    raise GateError('invalid ad field '+field)
  try:
   u=urlparse(ad['url'])
   allowed=(u.scheme=='https' and u.hostname in SAFE_AD_HOSTS and not u.username and not u.password and not u.port and u.path.startswith('/'))
  except (ValueError,TypeError):
   allowed=False
  if not allowed:raise GateError('unapproved A8 advertising URL')
 return True

def fingerprint_zip(raw):
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  if len(z.infolist())>1000:raise GateError('excessive archive members')
  if sum(m.file_size for m in z.infolist())>350_000_000:raise GateError('uncompressed ZIP too large')
  if z.testzip():raise GateError('ZIP corruption')
  names=[m.filename for m in z.infolist() if m.filename.lower().endswith('.xbrl') and '/publicdoc/' in ('/'+m.filename.lower())]
  if not names:raise GateError('PublicDoc XBRL missing')
  return sha(b''.join(sorted(hashlib.sha256(z.read(n)).digest() for n in names)))

def get_zip(doc_id,key):
 if not re.fullmatch(r'S[0-9A-Z]{7,15}',doc_id):raise GateError('invalid docID')
 qs=urllib.parse.urlencode({'type':1,'Subscription-Key':key})
 url='https://api.edinet-fsa.go.jp/api/v2/documents/'+doc_id+'?'+qs
 req=urllib.request.Request(url,headers={'User-Agent':'ManufacturerCareerLab-source-review/3.20'})
 with urllib.request.urlopen(req,timeout=110) as resp:
  if resp.status!=200:raise GateError('EDINET response is not 200')
  raw=resp.read(80_000_001)
 if len(raw)>80_000_000 or not zipfile.is_zipfile(io.BytesIO(raw)):raise GateError('EDINET source missing/bad ZIP')
 return raw

def live_reaudit(audit,out,delay=0.7,limit=79,source_fetcher=None):
 """Compare every fact value against frozen original XBRL, not its ZIP container SHA.

 When the EDINET service repackages a ZIP, the XBRL payload fingerprint
 is stable and the re-audit succeeds. A fact, context or filing change fails.
 """
 if limit!=79:raise GateError('live release qualification requires exactly 79 issuers')
 if not 0<=delay<=10:raise GateError('invalid request delay')
 key=os.environ.get('EDINET_API_KEY','')
 if source_fetcher is None:
  if not key:raise GateError('EDINET_API_KEY is missing')
  source_fetcher=lambda doc:get_zip(doc,key)
 import edinet_v313 as v313
 import edinet_v317 as v317
 seen=[];output=Path(out);output.mkdir(parents=True,exist_ok=True)
 for i,item in enumerate(audit[:limit]):
  ticker=item['ticker'];doc=item['docID'];report={'ticker':ticker,'docID':doc,'status':'FAILED'}
  try:
   raw=source_fetcher(doc)
   if fingerprint_zip(raw)!=item['publicdoc_fingerprint']:
    raise GateError('XBRL source content changed: '+ticker)
   facts,contexts,inst=v313.original_instance(raw,item['filing'])
   with zipfile.ZipFile(io.BytesIO(raw)) as z:root=ET.fromstring(z.read(inst))
   standards=[(el.text or '').strip() for el in root if v313.local(el.tag)=='AccountingStandardsDEI']
   gaap={'IFRS':'IFRS','Japan GAAP':'JP_GAAP','JapanGAAP':'JP_GAAP','Japanese GAAP':'JP_GAAP','US GAAP':'US_GAAP'}.get(standards[0]) if len(set(standards))==1 and standards else None
   if gaap!=item['gaap']:raise GateError('GAAP changed '+ticker)
   fresh={'metrics':{}}
   if gaap in ('JP_GAAP','IFRS'):
    v317.common_numeric(facts,item['filing'],gaap,fresh)
   else:
    for k in METRICS:v317.record_failure(fresh,k,'unsupported gaap '+str(gaap))
   for k in METRICS:
    old=item['metrics'][k];now=fresh['metrics'][k]
    if old['status']!=now['status'] or (old['status']=='SOURCE_RECONCILED' and Decimal(old['value'])!=Decimal(now['value'])):
     raise GateError('metric status/value changed '+ticker+' '+k)
   report={'ticker':ticker,'docID':doc,'status':'PASS','reconciled_count':item['reconciled_count'], 'archive_sha256_current':sha(raw),'payload_fingerprint':item['publicdoc_fingerprint']}
  except Exception as exc:
   report['reason']=str(exc)
  seen.append(report)
  print(f'[{i+1}/{limit}] {ticker} {report["status"]}',flush=True)
  save(output/'live-review-progress-v320.json',{'version':VERSION,'companies':seen})
  if report['status']!='PASS':raise GateError('live source re-audit failed: '+ticker+' '+report['reason'])
  if i<limit-1:time.sleep(delay)
 save(output/'live-review-summary-v320.json',{'version':VERSION,'result':'PASS','companies_verified':len(seen),
       'fully_reconciled':sum(x['reconciled_count']==6 for x in seen),
       'source_reconciled_metrics':sum(x['reconciled_count'] for x in seen),
       'new_companies_automatically_published':0,'frozen_audit_sha256':AUDIT_SHA})
 return seen

def stage(args):
 master,base,audit=validate_frozen(args.master,args.baseline,args.audit)
 ads=load(args.ads);validate_ads(ads)
 live=None
 if args.live_result:
  data=load(args.live_result)
  if data.get('version')!=VERSION or data.get('result')!='PASS' or data.get('companies_verified')!=79 or data.get('fully_reconciled')!=73 or data.get('source_reconciled_metrics')!=458 or data.get('frozen_audit_sha256')!=AUDIT_SHA:
   raise GateError('live source gate incomplete')
  progress=load(args.live_progress) if args.live_progress else None
  expected={r['ticker']:r['docID'] for r in audit}
  actual=progress.get('companies',[]) if isinstance(progress,dict) else []
  if len(actual)!=79 or {r['ticker']:r['docID'] for r in actual}!=expected or any(r.get('status')!='PASS' for r in actual):
   raise GateError('79 detailed live original rechecks not independently confirmed')
  live=True
 elif not args.allow_local_frozen:
  raise GateError('live re-audit result required for CI release staging')
 merged=build_public(master,base,audit)
 out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
 site=out/'site-ready';site.mkdir(exist_ok=True)
 (site/'company-data.js').write_text(generate_js(merged),encoding='utf-8')
 for source in ('company-check.html','company-compare.js','affiliate-render.js'):
  shutil.copyfile(Path(args.site_templates)/source,site/source)
 (site/'affiliate-config.js').write_text('/* v3.20: A8 advertising defaults to off until partnership approval. */\nwindow.MCL_ADS = '+json.dumps(ads,ensure_ascii=False,separators=(',',':'))+';\n',encoding='utf-8')
 report={'version':VERSION,'staged_public_count':102,'baseline_rows_unchanged':29,
         'new_source_reconciled':73,'source_metric_count':438,'all_79_source_metrics':458,
         'blocked_issuers':['6501','5713','6301','7011','7012','6965','7741','7751'],
         'publication_approved_by_automation':False,'deployed_to_pages':False,
         'requires_manual_root_file_replacement':True,'live_original_recheck':bool(live),
         'ads_enabled':ads['enabled'], 'company_data_sha256':sha((site/'company-data.js').read_bytes())}
 save(out/'release-summary-v320.json',report)
 print('STAGED 102 companies; automation does not publish; original 29 immutable.')
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__)
 sub=p.add_subparsers(dest='task',required=True)
 shared=lambda s: (s.add_argument('--master',default='company-master-v319.json'),
  s.add_argument('--baseline',default='baseline-29-v320.js'),
  s.add_argument('--audit',default='original-audit-v320.json'))
 s=sub.add_parser('stage');shared(s)
 s.add_argument('--ads',default='affiliate-v320.json');s.add_argument('--site-templates',default='site-update-v320')
 s.add_argument('--live-result');s.add_argument('--live-progress');s.add_argument('--allow-local-frozen',action='store_true')
 s.add_argument('--output',default='v320-output')
 s=sub.add_parser('live-audit');shared(s);s.add_argument('--delay',type=float,default=.7)
 s.add_argument('--limit',type=int,default=79);s.add_argument('--output',default='v320-output')
 s=sub.add_parser('check');shared(s);s.add_argument('--ads',default='affiliate-v320.json')
 args=p.parse_args()
 try:
  if args.task=='stage':stage(args)
  elif args.task=='live-audit':
   _,_,audit=validate_frozen(args.master,args.baseline,args.audit)
   live_reaudit(audit,args.output,args.delay,args.limit)
  else:
   validate_frozen(args.master,args.baseline,args.audit);validate_ads(load(args.ads))
   print('102-company frozen-source quality gate PASS')
 except (GateError,ValueError,OSError,KeyError,zipfile.BadZipFile) as exc:
  print('v3.20 GATE FAILURE:',exc,file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
