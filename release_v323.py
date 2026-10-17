#!/usr/bin/env python3
"""v3.23 controlled release: frozen 185-company live-reviewed baseline + 24 newly reviewed issuers.

Staging does not modify or deploy the public website. Verify exact uncompressed XBRL contents
and all six current-period source metrics. NOT an independent EDINET CSV crosscheck.
"""
from __future__ import annotations
import argparse, hashlib, io, json, os, re, time, urllib.error, zipfile
from decimal import Decimal
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import release_v322 as v322

R=Path(__file__).resolve().parent
PUB=v322.METRIC_TO_PUBLIC
BASE_SHA='f079db5e6e4b208da4119209bf6929d14f2a0d9f22707c03db16d2eac1df060e'
EXCLUDED='7745'
FROZEN_SOURCE_SHA256={'audit-25-v323.json': 'ebd0f0e2ae546dce1be977f661c98ec8813d5664715e7cf6608364313fa6a65e', 'source-lock-25-v323.json': '5fdcb81136774aa7410f26b3b84a3d1398389fa13ee644488993a0cc486d1ba3', 'verification-83-live-v323.json': '8b6ab33d8e9d133baed0252fe03b1e9ea6ed68db8c5a6dfd5017ae7f202f31db'}
class ReleaseError(ValueError): pass

def sha(data):return hashlib.sha256(data).hexdigest()
def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def save(path,obj):v322.save(path,obj)
def rows(path):return v322.js_dataset(path)[0]

def prepare(root=R):
    for name,digest in FROZEN_SOURCE_SHA256.items():
        if sha((root/name).read_bytes())!=digest:
            raise ReleaseError('Frozen audit/proof file content modified: '+name)
    # Validate previously completed 83-company live source gate, not just claimed counts.
    v322.validate_inputs(root)
    prior=root/'baseline-185-v323.js'
    raw=prior.read_bytes()
    if sha(raw)!=BASE_SHA:raise ReleaseError('frozen 185-company dataset SHA256 differs from v3.22 live release')
    previous,metadata,demos=v322.js_dataset(prior)
    frozen_102,_,_=v322.js_dataset(root/'baseline-102-v322.js')
    if len(previous)!=185 or previous[:102]!=frozen_102:raise ReleaseError('previously published 102-company baseline changed')
    if metadata.get('count')!=185 or metadata.get('independent_EDINET_CSV_crosscheck') is not False:
        raise ReleaseError('unexpected v3.22 baseline metadata')
    proof=read_json(root/'verification-83-live-v323.json')
    if proof.get('pass') is not True or proof.get('passed_count')!=83 or proof.get('failed_count')!=0 or len(proof.get('rows',[]))!=83:
        raise ReleaseError('83-company live proof missing or failed')
    prior_locks={r['ticker']:r for r in read_json(root/'source-lock-87-v322.json')['records']}
    prior_audits={r['ticker']:r for r in read_json(root/'audit-87-v322.json')}
    prior_added={r['id']:r for r in previous[102:]}
    if len(prior_added)!=83 or len(prior_locks)!=87 or len(prior_audits)!=87:raise ReleaseError('bad prior release coverage')
    for p in proof['rows']:
        code=p['ticker']; lock=prior_locks.get(code); actual=prior_added.get(code); audit=prior_audits.get(code)
        if not lock or not actual or not audit or audit['reconciled_count']!=6 or p.get('verified_metrics')!=6:
            raise ReleaseError('prior evidence missing: '+code)
        if any(str(p.get(key))!=str(lock.get(key)) for key in ('docID','periodEnd','xbrl_sha256')):
            raise ReleaseError('prior evidence conflicts: '+code)
        if actual['sourceDocId']!=p['docID'] or actual['sourceXbrlSha256']!=p['xbrl_sha256']:
            raise ReleaseError('185 dataset contradicts prior live review: '+code)
        for metric,field in PUB.items():
            if Decimal(str(actual[field]))!=Decimal(str(audit['metrics'][metric]['value'])):
                raise ReleaseError('prior public value contradicted by audit: '+code+'/'+metric)
    audit=read_json(root/'audit-25-v323.json')
    locks=read_json(root/'source-lock-25-v323.json')['records']
    master=read_json(root/'company-master-v322.json')['companies']
    if len(audit)!=25 or len(locks)!=25 or len(master)!=225:raise ReleaseError('25 audit / lock or 225 master incomplete')
    by_audit={x['ticker']:x for x in audit};by_lock={x['ticker']:x for x in locks}
    by_master={x['ticker']:x for x in master}
    new_master=read_json(root/'company-master-v323.json')['companies']
    if len(new_master)!=225 or [r['ticker'] for r in new_master]!=[r['ticker'] for r in master]:
        raise ReleaseError('v3.23 master is not a 225-code extension of v3.22 master')
    new_stages={r['ticker']:r['stage'] for r in new_master}
    if new_stages.get(EXCLUDED)!='ADDITIONAL_RESEARCH_UNVERIFIED':raise ReleaseError('7745 must remain excluded')
    if any(new_stages[x]!='V323_XBRL_VERIFIED_RELEASE_CANDIDATE' for x in set(by_audit)-{EXCLUDED}):
        raise ReleaseError('v3.23 release-candidate stage conflict')
    if len(by_audit)!=25 or len(by_lock)!=25 or len(by_master)!=225 or set(by_lock)!=set(by_audit):
        raise ReleaseError('duplicate or missing new target')
    if set(by_lock)&{x['id'] for x in previous}:raise ReleaseError('new target overlaps 185-company baseline')
    if not set(by_lock)<=set(by_master):raise ReleaseError('unknown new target in master')
    for code,record in by_audit.items():
        lock=by_lock[code]
        if any(str(record[k])!=str(lock[k]) for k in ('docID','periodStart','periodEnd','edinetCode','gaap')):
            raise ReleaseError('25-source identity mismatch: '+code)
        if record['identity_verified'] is not True or record['original_sha256_matches'] is not True or not record['original_present']:
            raise ReleaseError('frozen issuer/source not verified: '+code)
        if record['reconciled_count']+record['blocked_count']!=6:raise ReleaseError('metric statuses incomplete: '+code)
        if code==EXCLUDED:
            if record['reconciled_count']!=5 or record['blocked_count']!=1:raise ReleaseError('expected 7745 salary exclusion')
            if record['metrics']['average_salary_man']['status']!='BLOCKED':raise ReleaseError('salary block changed')
        else:
            if record['reconciled_count']!=6 or record['blocked_count']!=0:raise ReleaseError('noneligible source '+code)
            if lock['reconciled_metrics']!=6:raise ReleaseError('frozen lock not complete: '+code)
            for metric in PUB:
                m=record['metrics'][metric]
                if m['status']!='SOURCE_RECONCILED' or m['value'] is None or not Decimal(str(m['value'])).is_finite():
                    raise ReleaseError('unverified metric: '+code+'/'+metric)
    return previous,demos,by_audit,by_lock,by_master

def offline_fetcher(directory):
    paths=sorted(Path(directory).glob('edinet-v322-originals-*.zip'))
    if len(paths)!=3:raise ReleaseError('exactly three v3.22 original batches required')
    files={}
    for path in paths:
        with zipfile.ZipFile(path) as z:
            if z.testzip() is not None:raise ReleaseError('damaged outer ZIP '+path.name)
            for name in z.namelist():
                if not re.fullmatch(r'[0-9]{4}-S[A-Z0-9]{7,15}\.zip',name):raise ReleaseError('unexpected file '+name)
                doc=name.split('-',1)[1][:-4]
                if doc in files:raise ReleaseError('duplicate EDINET original '+doc)
                files[doc]=(path,name)
    def get(doc):
        if doc not in files:raise ReleaseError('missing original '+doc)
        path,name=files[doc]
        with zipfile.ZipFile(path) as z:return z.read(name)
    return get

def live_fetcher():
    import monthly_edinet_v321 as m
    key=os.environ.get('EDINET_API_KEY','')
    if not key:raise ReleaseError('EDINET_API_KEY is not configured')
    def get(doc):
        for attempt in range(3):
            try:return m.get_zip(doc,key)
            except urllib.error.HTTPError as err:
                if err.code not in (429,500,502,503,504) or attempt==2:
                    raise ReleaseError('EDINET HTTP '+str(err.code)) from None
                time.sleep(3*(attempt+1))
        raise ReleaseError('download failed')
    return get

def verify(fetch,out,delay=0.7,root=R,mode="OFFLINE"):
    previous,demos,audit,locks,master=prepare(root)
    if not 0<=delay<=10:raise ReleaseError('invalid request delay')
    eligible=[r for r in audit.values() if r['reconciled_count']==6]
    if len(eligible)!=24:raise ReleaseError('expected exactly 24 eligible issuers')
    passed=[];failures=[]
    for i,a in enumerate(sorted(eligible,key=lambda x:x['ticker'])):
        code=a['ticker']
        try:
            raw=fetch(a['docID'])
            rec=v322.verify_one(raw,a,locks[code])
            passed.append(rec)
            print(f'[{i+1}/24] {code} PASS',flush=True)
        except Exception as exc:
            msg=('EDINET HTTP failure' if isinstance(exc,urllib.error.HTTPError) else type(exc).__name__+': '+str(exc)[:190])
            failures.append({'ticker':code,'docID':a['docID'],'reason':msg})
            print(f'[{i+1}/24] {code} BLOCKED: {type(exc).__name__}',flush=True)
        if delay and i<len(eligible)-1:time.sleep(delay)
    obj={'schema':'3.23','source':'EDINET_XBRL','verification_kind':'24 frozen XBRL instances and six metrics re-extracted',
        'independent_EDINET_CSV_crosscheck':False,'verification_mode':mode,'eligible_company_count':24,'passed_count':len(passed),
        'failed_count':len(failures),'pass':len(passed)==24 and not failures,'rows':passed,'failures':failures,
        'published':False,'previous_185_company_live_gate_still_required':True}
    save(Path(out)/'verification-24-v323.json',obj)
    if not obj['pass']:raise ReleaseError('24-company source gate failed; check diagnostic artifact')
    return obj

def render_js(public,demos):
    meta={'version':'3.23','status':'MANUAL_RELEASE_CANDIDATE_XBRL_VERIFIED','count':209,
          'priorApprovedCount':185,'newSourceAuditedCount':24,'original_XBRL_checked':True,
          'independent_EDINET_CSV_crosscheck':False,
          'publication':'manual root-file replacement only after review',
          'disclaimer':'Accounting periods, standards and salary scope differ; figures are not guaranteed to predict compensation.'}
    return ('/* v3.23: 209 companies; original-XBRL re-extracted; independent EDINET CSV not crosschecked. MANUAL RELEASE. */\n'
            +'window.MCL_COMPANIES = '+json.dumps(public,ensure_ascii=False,separators=(',',':'))+';\n'
            +'window.MCL_DATASET_META = '+json.dumps(meta,ensure_ascii=False,separators=(',',':'))+';\n'
            +'window.MCL_DEMOS = '+json.dumps(demos,ensure_ascii=False,separators=(',',':'))+';\n')

def stage(verification_file,current_js,out,root=R,require_live=True):
    previous,demos,audit,locks,master=prepare(root)
    proof=read_json(verification_file)
    if require_live and proof.get('verification_mode')!='LIVE':raise ReleaseError('publishable staging requires live re-download verification')
    if proof.get('schema')!='3.23' or proof.get('pass') is not True or proof.get('passed_count')!=24 or proof.get('failed_count')!=0 or len(proof.get('rows',[]))!=24:
        raise ReleaseError('24-company live/offline gate must pass entirely')
    seen={r['ticker']:r for r in proof['rows']}
    if len(seen)!=24:raise ReleaseError('duplicated proof issuer')
    added=[]
    for code in sorted(audit):
        a=audit[code]
        if code==EXCLUDED:continue
        lock=locks[code];ver=seen.get(code)
        if not ver or ver.get('verified_metrics')!=6 or any(str(ver.get(k))!=str(lock.get(k)) for k in ('docID','xbrl_sha256','periodEnd','gaap')):
            raise ReleaseError('24-source proof does not match frozen audit '+code)
        filing=lock['filerName'].strip().replace('　',' ')
        label=master[code]['name']
        aliases=([label] if label!=filing else [])+ [x for x in master[code].get('aliases',[]) if x not in (label,filing)]
        row={'id':code,'name':filing or label,'aliases':aliases,'period':lock['periodStart']+'〜'+lock['periodEnd'],
             'scope':'連結（給与のみ提出会社）','salaryScope':'提出会社単体','accountingStandard':a['gaap'],
             'sourceLabel':'EDINET 有価証券報告書（書類ID: '+lock['docID']+'）','sourceUrl':'https://disclosure2.edinet-fsa.go.jp/',
             'sourceDocId':lock['docID'],'sourceSha256':ver['observed_zip_sha256'],'sourceXbrlSha256':ver['xbrl_sha256']}
        for metric,field in PUB.items():row[field]=float(Decimal(str(a['metrics'][metric]['value'])))
        added.append(row)
    if len(added)!=24:raise ReleaseError('24 new records not generated')
    combined=previous+added
    ids=[str(x['id']) for x in combined]
    if len(combined)!=209 or len(set(ids))!=209:raise ReleaseError('209-company uniqueness check failed')
    new_js=render_js(combined,demos)
    new_rows,meta,_=parse_js(new_js)
    current,_,_=v322.js_dataset(current_js)
    if len(current)==102:
        if current!=previous[:102]:raise ReleaseError('current 102-company site has changed; must reconcile before replacement')
    elif len(current)==185:
        if current!=previous:raise ReleaseError('current 185-company site differs from frozen baseline')
    elif len(current)==209:
        if current!=combined:raise ReleaseError('209-company site differs from candidate; do not overwrite')
    else:raise ReleaseError('current public company count is not 102/185/209')
    output=Path(out);ready=output/'site-ready';ready.mkdir(parents=True,exist_ok=True)
    (ready/'company-data.js').write_text(new_js,encoding='utf-8')
    templates=root/'site-ready'
    for name in ('index.html','company-check.html','company-compare.js','affiliate-config.js','affiliate-render.js'):
        txt=(templates/name).read_text(encoding='utf-8')
        if name=='index.html':
            # Keep initial 102-company historical statistical cohort unchanged.
            txt=txt.replace('185社','209社')
        elif name=='company-check.html':
            txt=txt.replace('企業比較ツール v3.22','企業比較ツール v3.23').replace('company-data.js?v=322','company-data.js?v=323').replace('company-compare.js?v=322','company-compare.js?v=323')
            txt=txt.replace('affiliate-config.js" defer','affiliate-config.js?v=323" defer').replace('affiliate-render.js" defer','affiliate-render.js?v=323" defer')
        (ready/name).write_text(txt,encoding='utf-8')
    summary={'schema':'3.23','timestamp_jst':datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(timespec='seconds'),
            'current_site_rows_checked':len(current),'published_site_modified':False,'staged_public_count':209,
            'source_verified_new_count':24,'new_source_metric_count':144,'frozen_prior_count':185,
            'previous_83_source_live_gate':True,'24_source_gate':True,
            'independent_EDINET_CSV_crosscheck':False,'requires_manual_publication':True,'a8_ads_enabled':False,
            'site_ready_files':6,'company_data_sha256':sha(new_js.encode('utf-8'))}
    save(output/'release-summary-v323.json',summary)
    save(output/'release-roster-v323.json',[{'ticker':r['id'],'name':r['name'],'docID':r['sourceDocId']} for r in combined])
    print(json.dumps(summary,ensure_ascii=False))
    return summary

def parse_js(text):
    import tempfile
    # no code execution; strict capture of JSON arrays/objects in controlled source
    m=re.search(r'window\.MCL_COMPANIES\s*=\s*(\[.*?\]);\s*window\.MCL_DATASET_META\s*=\s*(\{.*?\});\s*window\.MCL_DEMOS\s*=\s*(\[.*?\]);',text,re.S)
    if not m:raise ReleaseError('generated JS does not match required structure')
    return json.loads(m.group(1)),json.loads(m.group(2)),json.loads(m.group(3))

def check(root=R):
    prepare(root)
    print('PASS: frozen 185 baseline + live evidence + 24 sources + excluded 7745')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('check')
    v=sub.add_parser('verify');g=v.add_mutually_exclusive_group(required=True);g.add_argument('--live',action='store_true');g.add_argument('--offline-batch-dir');v.add_argument('--delay',type=float,default=.7);v.add_argument('--output',default='v323-output')
    s=sub.add_parser('stage');s.add_argument('--verification',required=True);s.add_argument('--current-js',default='company-data.js');s.add_argument('--output',default='v323-output')
    args=p.parse_args()
    try:
        if args.command=='check':check()
        elif args.command=='verify':verify(live_fetcher() if args.live else offline_fetcher(args.offline_batch_dir),args.output,args.delay,mode='LIVE' if args.live else 'OFFLINE')
        elif args.command=='stage':stage(args.verification,args.current_js,args.output)
    except Exception as exc:
        print('v3.23 gate BLOCKED:',type(exc).__name__,str(exc)[:240],flush=True)
        raise SystemExit(1)
if __name__=='__main__':main()
