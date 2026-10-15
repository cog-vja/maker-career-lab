#!/usr/bin/env python3
"""MCL v3.14: fail-closed publication builder for source-reconciled v3.13 artifact.

Preview produces no public real-company JS; publish requires an explicit human
approval bound to the exact artifact SHA256 and 10 document IDs. No Git push.
"""
import argparse, csv, hashlib, json, re, zipfile
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

EXPECTED_TICKERS=('6146','6506','6645','6841','6857','6861','6920','6954','7735','8035')
METRICS=('revenue_oku','prior_revenue_oku','operating_profit_oku','operating_cf_oku','equity_ratio_pct','average_salary_man')
MAP={'revenue_oku':'revenue','prior_revenue_oku':'revenuePrev','operating_profit_oku':'operatingProfit',
     'operating_cf_oku':'operatingCashFlow','equity_ratio_pct':'equityRatio','average_salary_man':'averageSalary'}
ALIASES={'6146':['ディスコ'],'6506':['安川電機'],'6645':['オムロン'],'6841':['横河電機'],
 '6857':['アドバンテスト'],'6861':['キーエンス'],'6920':['レーザーテック'],
 '6954':['ファナック'],'7735':['SCREENホールディングス','SCREEN HD'],'8035':['東京エレクトロン']}
ALLOWED_VERIFICATIONS={'SOURCE_RECONCILED','CORRECTED_SOURCE_RECONCILED'}
class ReleaseError(ValueError):pass

def exact_decimal(v):
 if v is None or isinstance(v,bool):raise ReleaseError('missing / invalid numeric value')
 try:x=Decimal(str(v))
 except InvalidOperation:raise ReleaseError('invalid number')
 if not x.is_finite():raise ReleaseError('non-finite numeric value')
 return x

def load_review(path):
 raw=Path(path).read_bytes(); digest=hashlib.sha256(raw).hexdigest()
 if len(raw)>10_000_000:raise ReleaseError('v3.13 result exceeds size cap')
 with zipfile.ZipFile(path) as z:
  if z.testzip() is not None:raise ReleaseError('corrupted artifact zip')
  summary=json.loads(z.read('summary.json'))['companies']
  by_ticker={str(x['ticker']):x for x in summary}
  if len(summary)!=10 or len(by_ticker)!=10 or set(by_ticker)!=set(EXPECTED_TICKERS):
   raise ReleaseError('expected exactly the approved 10-company scope')
  details={}
  for n in z.namelist():
   if re.fullmatch(r'\d{4}-S[A-Z0-9]+-v313\.json',n):
    obj=json.loads(z.read(n));t=n[:4]
    if t in details:raise ReleaseError('duplicate company details')
    details[t]=obj
  if set(details)!=set(EXPECTED_TICKERS):raise ReleaseError('missing or extra company detail')
 return digest,by_ticker,details

def inspect_review(path):
 digest,summary,details=load_review(path); companies=[]; checks=[];errors=[]
 for ticker in EXPECTED_TICKERS:
  s=summary[ticker];d=details[ticker];filing=d.get('filing',{})
  docid=s.get('docID');prov=d.get('provenance') or {};rec=d.get('source_reconciliation') or {}
  reasons=[]
  if not re.fullmatch(r'S[A-Z0-9]{7,15}',str(docid)):reasons.append('invalid_docID')
  if filing.get('docID')!=docid:reasons.append('docID_mismatch')
  if s.get('accounting_standard')!=d.get('accounting_standard',{}).get('standard'):reasons.append('gaap_mismatch')
  if s.get('reconciled_count')!=6 or s.get('blocked_metric_count')!=0:reasons.append('incomplete_reconciliation')
  if s.get('review_errors'):reasons.append('review_errors')
  if s.get('quality_status')!='BLOCKED' or s.get('publication_status')!='UNVERIFIED':
   reasons.append('unexpected_previous_quality_state')
  if rec.get('status')!='SOURCE_RECONCILED_PUBLICATION_BLOCKED':reasons.append('bad_source_review_state')
  origsha=s.get('original_sha256')
  if not re.fullmatch(r'[a-f0-9]{64}',str(origsha)):reasons.append('invalid_source_sha256')
  vals={}
  for metric in METRICS:
   m=rec.get('metrics',{}).get(metric) or {};p=prov.get(metric) or {}
   bad=[]
   if m.get('status') not in ALLOWED_VERIFICATIONS or p.get('verification') not in ALLOWED_VERIFICATIONS:
    bad.append('not_source_reconciled')
   if m.get('approved_for_publication') is not False:bad.append('source_approval_state_changed')
   if p.get('source_docID')!=docid or p.get('source_sha256')!=origsha:bad.append('provenance_source_mismatch')
   try:
    selected=exact_decimal(d.get('selected_values',{}).get(metric))
    summ=exact_decimal(s.get(metric));original=exact_decimal(m.get('original_value'))
    if selected!=summ or selected!=original:bad.append('value_mismatch')
    if metric in ('revenue_oku','prior_revenue_oku','average_salary_man') and selected<=0:bad.append('nonpositive_value')
    if metric=='equity_ratio_pct' and not (0<=selected<=100):bad.append('ratio_out_of_range')
    vals[MAP[metric]]=float(selected)
   except ReleaseError:bad.append('bad_numeric_value')
   if bad:reasons.append(metric+':'+','.join(bad))
   checks.append({'ticker':ticker,'docID':docid,'metric':metric,'result':'PASS' if not bad else 'BLOCKED',
                  'issues':';'.join(bad),'value':str(s.get(metric))})
  period_start=filing.get('periodStart');period_end=filing.get('periodEnd')
  try:
   start=date.fromisoformat(period_start);end=date.fromisoformat(period_end)
   if not start<end:raise ValueError()
  except (TypeError,ValueError):reasons.append('invalid_period')
  if reasons:errors.extend(f'{ticker}: {r}' for r in reasons)
  company={'id':ticker,'name':s['company'],'aliases':ALIASES[ticker],
   'period':f'{period_start}〜{period_end}', 'scope':'連結（給与のみ提出会社）',
   'salaryScope':'提出会社単体','accountingStandard':s['accounting_standard'],
   'sourceLabel':f'EDINET 有価証券報告書（書類ID: {docid}）',
   'sourceUrl':'https://disclosure2.edinet-fsa.go.jp/',
   'sourceDocId':docid,'sourceSha256':origsha,
   **vals}
  companies.append(company)
 if errors:raise ReleaseError('QUALITY GATE FAILED:\n'+'\n'.join(errors))
 return {'artifact_sha256':digest,'companies':companies,'checks':checks,
         'document_ids':{c['id']:c['sourceDocId'] for c in companies},'metrics_verified':len(checks)}

def make_js(companies,sha,mode):
 # Serialize using JSON to prevent string interpolation and JS injection.
 payload=json.dumps(companies,ensure_ascii=False,separators=(',',':'))
 meta=json.dumps({'version':'3.14','sourceArtifactSha256':sha,'status':mode,
                  'count':len(companies),'verification':'EDINET原本照合済み・公開審査済み' if mode=='PUBLISHED' else '社内確認用プレビュー'},ensure_ascii=False)
 return ('/* Auto-generated by build_release_v314.py; do not hand-edit. */\n'
   'window.MCL_COMPANIES = '+payload+';\nwindow.MCL_DATASET_META = '+meta+';\n'
   'window.MCL_DEMOS = [{"id":"demo-a","name":"【架空】サンプル現職メーカー","demo":true,"period":"架空の2025年度","scope":"連結","salaryScope":"架空の単体","sourceLabel":"架空デモ","revenue":1000,"operatingProfit":80,"revenuePrev":950,"operatingCashFlow":90,"equityRatio":48,"averageSalary":680},'
   '{"id":"demo-b","name":"【架空】サンプル検討先メーカー","demo":true,"period":"架空の2025年度","scope":"連結","salaryScope":"架空の単体","sourceLabel":"架空デモ","revenue":1200,"operatingProfit":216,"revenuePrev":1050,"operatingCashFlow":130,"equityRatio":62,"averageSalary":820}];\n')

def verify_approval(path,report):
 obj=json.loads(Path(path).read_text(encoding='utf-8'))
 if obj.get('approved') is not True or obj.get('release_version')!='3.14':raise ReleaseError('explicit release approval missing')
 if obj.get('artifact_sha256')!=report['artifact_sha256']:raise ReleaseError('approval digest mismatch')
 if obj.get('document_ids')!=report['document_ids']:raise ReleaseError('approval docIDs mismatch')
 if obj.get('reviewer_confirmation')!='I reviewed and approve the ten companies and sixty metrics for public release':
  raise ReleaseError('human reviewer confirmation not supplied')

def build(review,output,mode,approval=None):
 report=inspect_review(review);out=Path(output);out.mkdir(parents=True,exist_ok=True)
 with (out/'metric-audit-v314.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=['ticker','docID','metric','result','issues','value']);w.writeheader();w.writerows(report['checks'])
 approval_template={'release_version':'3.14','approved':False,'artifact_sha256':report['artifact_sha256'],
  'document_ids':report['document_ids'], 'reviewer_confirmation':''}
 (out/'release-approval-template-v314.json').write_text(json.dumps(approval_template,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'validation-v314.json').write_text(json.dumps({'artifact_sha256':report['artifact_sha256'],
  'company_count':10,'metric_count':60,'all_metrics_source_reconciled':True,
  'publish_approved':mode=='publish','company_docIDs':report['document_ids']},ensure_ascii=False,indent=2),encoding='utf-8')
 # Preview JS contains no actual companies. The audit CSV contains reconciled numbers,
 # but is never linked from live site.
 if mode=='preview':
  (out/'company-data.js').write_text(make_js([],report['artifact_sha256'],'PREVIEW_BLOCKED'),encoding='utf-8')
  (out/'PREVIEW-NOT-FOR-PUBLICATION.txt').write_text('10 companies / 60 metrics reviewed. Actual-company JS blocked pending explicit approval.\n',encoding='utf-8')
 elif mode=='publish':
  if not approval:raise ReleaseError('approval file required to publish')
  verify_approval(approval,report)
  (out/'company-data.js').write_text(make_js(report['companies'],report['artifact_sha256'],'PUBLISHED'),encoding='utf-8')
 else:raise ReleaseError('invalid mode')
 return report

def main():
 p=argparse.ArgumentParser();p.add_argument('--review',required=True);p.add_argument('--output',default='v314-output')
 p.add_argument('--mode',choices=['preview','publish'],default='preview');p.add_argument('--approval')
 args=p.parse_args()
 report=build(args.review,args.output,args.mode,args.approval)
 print('v3.14 quality gate PASS: 10 companies, 60 metrics. mode=',args.mode)
 print('Input artifact SHA256:',report['artifact_sha256'])
 if args.mode=='preview':print('PUBLICATION BLOCKED. Explicit approval required.')
if __name__=='__main__':main()
