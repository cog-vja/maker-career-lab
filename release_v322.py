#!/usr/bin/env python3
"""v3.22: pinned 83-company original XBRL recheck and manual-only 185-company release staging.

Safety design:
 * All 102 publicly available rows are copied byte-for-byte at the JSON-object level.
 * Every new issuer is derived from a frozen v3.21 EDINET filing and its raw XBRL SHA256.
 * Re-extract six metrics from the original XBRL (same permitted taxonomy with different run).
 * Repackaged ZIP container is allowed ONLY when raw PublicDoc XBRL is unchanged.
 * No source update or GitHub Pages deployment is performed by this module.
 * These checks are XBRL-vs-XBRL checks, NOT an independent EDINET CSV crosscheck.
"""
from __future__ import annotations
import argparse,csv,hashlib,io,json,os,re,time,urllib.error,zipfile
from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo
import edinet_v313 as v313
import edinet_v317 as v317

R=Path(__file__).resolve().parent
METRIC_TO_PUBLIC={'revenue_oku':'revenue','prior_revenue_oku':'revenuePrev','operating_profit_oku':'operatingProfit',
 'operating_cf_oku':'operatingCashFlow','equity_ratio_pct':'equityRatio','average_salary_man':'averageSalary'}
REQUIRED=("period", "scope", "accountingStandard", "sourceDocId", "sourceSha256",*METRIC_TO_PUBLIC.values())
class GateError(ValueError):pass

def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,obj):
 p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(data):return hashlib.sha256(data).hexdigest()
def js_dataset(path):
 raw=Path(path).read_text(encoding='utf-8')
 m=re.search(r'(window\.MCL_COMPANIES\s*=\s*)(\[.*?\])(\s*;\s*window\.MCL_DATASET_META\s*=\s*)(\{.*?\})(\s*;\s*window\.MCL_DEMOS\s*=\s*)(\[.*?\])(\s*;)',raw,re.S)
 if not m:raise GateError('company-data.js structure unrecognized')
 rows=json.loads(m.group(2));meta=json.loads(m.group(4));demos=json.loads(m.group(6))
 ids=[str(x['id']) for x in rows]
 if len(ids)!=len(set(ids)) or any(not re.fullmatch(r'\d{4}',id) for id in ids):raise GateError('duplicate or invalid identifiers')
 if any(set(REQUIRED)-set(x) for x in rows):raise GateError('public data missing expected keys')
 return rows,meta,demos

def validate_inputs(root=R):
 master=read_json(root/'company-master-v322.json')
 audit=read_json(root/'audit-87-v322.json')
 locks=read_json(root/'source-lock-87-v322.json')['records']
 discovery=read_json(root/'discovery-90-v322.json')
 base,meta,demos=js_dataset(root/'baseline-102-v322.js')
 mid=[x['ticker'] for x in master['companies']];bid=[r['id'] for r in base]
 aid=[r['ticker'] for r in audit];lid=[x['ticker'] for x in locks]
 assert len(master['companies'])==225 and len(set(mid))==225, '225 unique target codes required'
 assert len(base)==102 and meta.get('count')==102, 'frozen baseline must have 102 rows'
 assert len(audit)==87 and len(set(aid))==87, '87 audit rows required'
 assert len(locks)==87 and len(set(lid))==87, '87 XBRL hashes required'
 assert len(discovery)==90, '90 discovery rows required'
 if not (set(bid)|set(aid)).issubset(set(mid)):raise GateError('missing published or audited company in master')
 if set(bid)&set(aid):raise GateError('published / new source overlap')
 adict={r['ticker']:r for r in audit};ldict={r['ticker']:r for r in locks}
 if set(adict)!=set(ldict):raise GateError('audit / XBRL lock mismatch')
 for code,row in adict.items():
  lock=ldict[code]
  if any(str(row[k])!=str(lock[k]) for k in ('docID','periodEnd')):raise GateError('audit / locked filing conflict: '+code)
  if not row['identity_verified'] or not row['sha256_matches_report']:raise GateError('historical source integrity failed: '+code)
  if row['reconciled_count']+row['blocked_count']!=6:raise GateError('incomplete metric status: '+code)
  for key in METRIC_TO_PUBLIC:
   met=row['metrics'][key]
   if met['status']=='SOURCE_RECONCILED':
    if met['value'] is None or not Decimal(str(met['value'])).is_finite():raise GateError('invalid numeric metric')
   elif met['status']!='BLOCKED':raise GateError('unrecognized metric status')
 count=sum(r['reconciled_count']==6 for r in audit)
 if count!=83:raise GateError('expected exactly 83 complete reviewed candidates')
 return master,base,audit,ldict

def uncompressed_xbrl(raw):
 v313.check_zip(raw)
 with zipfile.ZipFile(io.BytesIO(raw)) as z:
  matches=[n for n in z.namelist() if '/publicdoc/' in ('/'+n.lower()) and n.lower().endswith('.xbrl')]
  if len(matches)!=1:raise GateError('XBRL filename count != 1')
  return matches[0],z.read(matches[0])

def verify_one(raw,audit,lock):
 if len(raw)>80_000_000:raise GateError('original too large')
 path,data=uncompressed_xbrl(raw)
 if path!=lock['xbrl_path'] or sha(data)!=lock['xbrl_sha256']:
  raise GateError('frozen XBRL contents changed: '+audit['ticker'])
 filing={'docID':lock['docID'],'edinetCode':lock['edinetCode'],'periodStart':lock['periodStart'],'periodEnd':lock['periodEnd']}
 facts,ctx,filename=v313.original_instance(raw,filing)
 if filename!=path:raise GateError('XBRL path mismatch')
 # Read documented GAAP with independently parsed DEI (not company-master guess).
 from xml.etree import ElementTree as ET
 root=ET.fromstring(data)
 standards=set((e.text or '').strip() for e in root if v313.local(e.tag)=='AccountingStandardsDEI')
 gaap={'Japan GAAP':'JP_GAAP','JapanGAAP':'JP_GAAP','Japanese GAAP':'JP_GAAP','IFRS':'IFRS','US GAAP':'US_GAAP'}.get(next(iter(standards)) if len(standards)==1 else '')
 if gaap!=audit['gaap'] or gaap not in ('JP_GAAP','IFRS'):raise GateError('GAAP unsupported/changed')
 result={'metrics':{}}
 v317.common_numeric(facts,filing,gaap,result)
 for m in METRIC_TO_PUBLIC:
  frozen=audit['metrics'][m]
  fresh=result['metrics'][m]
  if frozen['status']!='SOURCE_RECONCILED' or fresh['status']!='SOURCE_RECONCILED':
   raise GateError('6 metrics not complete for '+audit['ticker']+': '+m)
  if Decimal(str(frozen['value']))!=Decimal(str(fresh['value'])):
   raise GateError('different source metric '+audit['ticker']+': '+m)
 return {'ticker':audit['ticker'],'docID':lock['docID'],'filerName':lock['filerName'],
   'periodStart':lock['periodStart'],'periodEnd':lock['periodEnd'],'gaap':gaap,'xbrl_sha256':lock['xbrl_sha256'],
   'observed_zip_sha256':sha(raw),'verified_metrics':6}

def offline_fetcher(batch_dir):
 paths=sorted(Path(batch_dir).glob('edinet-v321-originals-batch-*.zip'))
 if len(paths)!=9:raise GateError('9 original batch ZIPs required')
 index={}
 for batch in paths:
  with zipfile.ZipFile(batch) as z:
   if z.testzip():raise GateError('corrupted batch ZIP')
   for name in z.namelist():
    if not re.fullmatch(r'\d{4}-S[A-Z0-9]+\.zip',name):raise GateError('unexpected source filename '+name)
    doc=name.split('-')[1][:-4]
    if doc in index:raise GateError('repeated EDINET doc '+doc)
    index[doc]=(batch,name)
 def fetch(doc):
  if doc not in index:raise GateError('missing original '+doc)
  batch,member=index[doc]
  with zipfile.ZipFile(batch) as z:return z.read(member)
 return fetch

def live_fetcher():
 import monthly_edinet_v321 as m
 key=os.environ.get('EDINET_API_KEY','')
 if not key:raise GateError('EDINET_API_KEY secret not configured')
 def fetch(doc):
  for attempt in range(3):
   try:return m.get_zip(doc,key)
   except urllib.error.HTTPError as e:
    if e.code not in (429,500,502,503,504) or attempt==2:raise GateError('EDINET HTTP '+str(e.code)) from None
    time.sleep(3*(attempt+1))
  raise GateError('download failed')
 return fetch

def verify(out,fetch,delay=0,root=R):
 master,base,audit,locks=validate_inputs(root)
 if not 0<=delay<=10:raise GateError('invalid request delay')
 target=sorted([a for a in audit if a['reconciled_count']==6],key=lambda x:x['ticker'])
 rows=[];failures=[]
 for i,a in enumerate(target):
  try:
   raw=fetch(a['docID'])
   r=verify_one(raw,a,locks[a['ticker']]);rows.append(r)
   print(f"[{i+1}/83] {a['ticker']} OK",flush=True)
  except Exception as e:
   # No raw secrets or API URLs in diagnostics.
   failures.append({'ticker':a['ticker'],'docID':a['docID'],'error':type(e).__name__+': '+str(e)[:180]})
   print(f"[{i+1}/83] {a['ticker']} BLOCKED {type(e).__name__}",flush=True)
  if i<len(target)-1 and delay:time.sleep(delay)
 obj={'schema':'3.22','source':'EDINET_XBRL','review_type':'re-download_and_re-extract_against_frozen_XBRL',
  'crosschecked_against_independent_EDINET_CSV':False,'eligible_count':len(target),'passed_count':len(rows),
  'failed_count':len(failures),'pass':len(rows)==83 and not failures,
  'rows':rows,'failures':failures,'automatic_publication':False}
 save(Path(out)/'verification-v322.json',obj)
 if failures:raise GateError('83-company source gate failed; inspect verification-v322.json')
 return obj

def stage(result_file,out,root=R,current_js=None):
 master,base,audit,locks=validate_inputs(root)
 if current_js is not None:
  current,_,_=js_dataset(current_js)
  if len(current) not in (102,185) or current[:102]!=base:
   raise GateError('current site baseline changed; reconcile prior 102 before staging')
 result=read_json(result_file)
 if not result.get('pass') or result.get('passed_count')!=83 or result.get('failed_count')!=0 or len(result.get('rows',[]))!=83:
  raise GateError('live/offline source gate must pass all 83 companies')
 verified={r['ticker']:r for r in result['rows']}
 if len(verified)!=83:raise GateError('duplicate verified row')
 available={r['ticker']:r for r in master['companies']}
 new=[]
 for item in sorted(audit,key=lambda r:r['ticker']):
  if item['reconciled_count']!=6:continue
  code=item['ticker'];proof=verified.get(code);frozen=locks[code]
  if not proof or any(str(proof[k])!=str(frozen[k]) for k in ('docID','xbrl_sha256','periodEnd')) or proof['verified_metrics']!=6 or proof['gaap']!=item['gaap']:
   raise GateError('release evidence conflict '+code)
  if available[code]['stage']!='V322_SOURCE_RECHECK_PENDING_RELEASE':raise GateError('unapproved stage '+code)
  issuer=frozen['filerName'].strip().replace('　',' ')
  label=available[code]['name']
  # Use current legal issuer name, preserving original candidate name as searchable alias.
  display=issuer or label
  aliases=[label] if label!=display else []
  aliases.extend(x for x in available[code].get('aliases',[]) if x not in aliases and x!=display)
  row={'id':code,'name':display,'aliases':aliases,'period':frozen['periodStart']+'〜'+frozen['periodEnd'],
    'scope':'連結（給与のみ提出会社）','salaryScope':'提出会社単体','accountingStandard':item['gaap'],
    'sourceLabel':'EDINET 有価証券報告書（書類ID: '+frozen['docID']+'）',
    'sourceUrl':'https://disclosure2.edinet-fsa.go.jp/','sourceDocId':frozen['docID'],
    'sourceSha256':proof['observed_zip_sha256'],'sourceXbrlSha256':proof['xbrl_sha256']}
  for k,public in METRIC_TO_PUBLIC.items():row[public]=float(Decimal(item['metrics'][k]['value']))
  new.append(row)
 if len(new)!=83:raise GateError('not exactly 83 new records')
 merged=base+new
 ids=[str(x['id']) for x in merged]
 if len(merged)!=185 or len(set(ids))!=185:raise GateError('expected 185 unique companies')
 prior_text=(root/'baseline-102-v322.js').read_text(encoding='utf-8')
 _,oldmeta,demos=js_dataset(root/'baseline-102-v322.js')
 meta={'version':'3.22','status':'MANUAL_RELEASE_CANDIDATE_XBRL_VERIFIED','count':185,
   'priorApprovedCount':102,'newSourceAuditedCount':83,'original_XBRL_checked':True,
   'independent_EDINET_CSV_crosscheck':False,
   'publication':'manual root-file replacement ONLY after review',
   'disclaimer':'Accounting dates and standards vary; salary is filing-company standalone.'}
 js='/* v3.22: 185 EDINET original XBRL reviewed; MANUAL RELEASE; independent CSV crosscheck pending. */\n'
 js+='window.MCL_COMPANIES = '+json.dumps(merged,ensure_ascii=False,separators=(',',':'))+';\n'
 js+='window.MCL_DATASET_META = '+json.dumps(meta,ensure_ascii=False,separators=(',',':'))+';\n'
 js+='window.MCL_DEMOS = '+json.dumps(demos,ensure_ascii=False,separators=(',',':'))+';\n'
 out=Path(out);ready=out/'site-ready';ready.mkdir(parents=True,exist_ok=True)
 (ready/'company-data.js').write_text(js,encoding='utf-8')
 for name in ('index.html','company-check.html','company-compare.js','affiliate-config.js','affiliate-render.js'):
  data=(root/'site-ready'/name).read_text(encoding='utf-8')
  if name=='index.html':
   data=data.replace('102社の財務データと実践的なキャリア記事', '185社の財務データと実践的なキャリア記事')
   data=data.replace('102社の企業を比較する', '185社の企業を比較する')
   data=data.replace('掲載102社を単純に集計すると', 'v3.20公開時点の102社を単純に集計すると')
   data=data.replace('現在102社掲載。約200社への拡張対象は照合・承認前のため未掲載です。',
     '現在185社の比較データを掲載。未照合の調査候補は掲載していません。')
   data=data.replace('102社の実データを読み、利益と給与の関係を考える。',
     '初期102社のデータを手がかりに、利益と給与の関係を考える。')
  if name=='company-check.html':
   data=data.replace('企業比較ツール v3.21','企業比較ツール v3.22').replace('企業比較ツール v3.20','企業比較ツール v3.22')
   data=data.replace('company-data.js" defer','company-data.js?v=322" defer').replace('company-compare.js" defer','company-compare.js?v=322" defer')
  (ready/name).write_text(data,encoding='utf-8')
 now=datetime.now(ZoneInfo('Asia/Tokyo')).date().isoformat()
 summary={'version':'3.22','as_of_jst':now,'original_baseline_count':102,'new_reviewed_source_count':83,
   'staged_public_count':185,'new_metric_count':498,'blocked_prior_and_new':15,
   'new_research_targets':25,'xbrl_source_gate':True,'independent_EDINET_CSV_crosscheck':False,
   'requires_manual_publication_review':True,'automatically_deployed':False,
   'site_ready_file_count':6,'company_data_sha256':sha(js.encode())}
 save(out/'release-summary-v322.json',summary)
 save(out/'release-roster-v322.json',[{'ticker':x['id'],'name':x['name'],'docID':x['sourceDocId']} for x in merged])
 print(json.dumps(summary,ensure_ascii=False))
 return summary

def main():
 parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='cmd',required=True)
 v=sub.add_parser('verify');v.add_argument('--offline-batch-dir');v.add_argument('--live',action='store_true');v.add_argument('--delay',type=float,default=0.7);v.add_argument('--output',default='v322-output')
 s=sub.add_parser('stage');s.add_argument('--verification',required=True);s.add_argument('--output',default='v322-output');s.add_argument('--current-js',default=None)
 c=sub.add_parser('check')
 args=parser.parse_args()
 if args.cmd=='check':
  validate_inputs();print('v3.22 input/baseline gate PASS')
 elif args.cmd=='verify':
  if bool(args.offline_batch_dir)==bool(args.live):parser.error('choose one source: --offline-batch-dir or --live')
  verify(args.output,offline_fetcher(args.offline_batch_dir) if args.offline_batch_dir else live_fetcher(),args.delay)
 else:stage(args.verification,args.output,current_js=args.current_js)
if __name__=='__main__':main()
