#!/usr/bin/env python3
"""EDINET v3.13: GAAP-specific metric contracts and fail-closed filing reconciliation.

Modes:
  offline: reconcile stored v3.11 reports against the type=1 EDINET originals;
  live: download each selected filing (type=5 plus type=1) once and reconcile.

This module never emits publish-ready company data. 'SOURCE_RECONCILED' signifies
an independent parser matched the uploaded filing, not public-release approval.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import io
import json
import os
import re
import time
import zipfile
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from xml.etree import ElementTree as ET

import edinet_v32 as v32
import edinet_v36 as v36
import edinet_v38 as v38
import edinet_v310 as v310
import edinet_v311 as v311

XBRLI='http://www.xbrl.org/2003/instance'
D=Decimal
MONEY=D('100000000')
SALARY=D('10000')
ONE_PERCENT=D('0.01')
METRICS=('revenue_oku','prior_revenue_oku','operating_profit_oku',
         'operating_cf_oku','equity_ratio_pct','average_salary_man')

# Declarative family mapping; never special-case a security code/company name.
DEFINITIONS={
 'JP_GAAP':{
  'revenue':('NetSales',),
  'operating_profit':('OperatingIncome',),
  'operating_cf':('NetCashProvidedByUsedInOperatingActivities',),
  'assets':('Assets',),
  'parent_equity':('ShareholdersEquity',),
  'valuation':('ValuationAndTranslationAdjustments',),
  'disclosed_ratio':('EquityToAssetRatioSummaryOfBusinessResults',),
  'equity_formula':'(ShareholdersEquity + ValuationAndTranslationAdjustments) / Assets * 100',
 },
 'IFRS':{
  'revenue':('NetSalesIFRS','RevenueIFRS'),
  'operating_profit':('OperatingProfitLossIFRS',),
  'operating_cf':('NetCashProvidedByUsedInOperatingActivitiesIFRS',),
  'assets':('AssetsIFRS',),
  'parent_equity':('EquityAttributableToOwnersOfParentIFRS',),
  'disclosed_ratio':('RatioOfOwnersEquityToGrossAssetsIFRSSummaryOfBusinessResults',),
  'equity_formula':'EquityAttributableToOwnersOfParentIFRS / AssetsIFRS * 100',
 },
 'US_GAAP':{
  'financials':'ConsolidatedStatementOfIncomeUSGAAPTextBlock, ConsolidatedBalanceSheetUSGAAPTextBlock, ConsolidatedStatementOfCashFlowsUSGAAPTextBlock',
  'equity_formula':'parent common shareholders equity / total assets * 100',
  'operating_profit_policy':'Use issuer-published definition and reconcile all cost components, never infer generic US GAAP EBIT',
 },
}
SALARY_ELEMENT='AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees'


def local(tag):return tag.rsplit('}',1)[-1]
def dec(value):
 try:
  n=D(str(value))
  if n.is_finite():return n
 except (InvalidOperation,ValueError,TypeError):pass
 return None

def percent(num,den):
 if den is None or num is None or den<=0 or num<0 or num>den:return None
 return (num/den*100).quantize(ONE_PERCENT,rounding=ROUND_HALF_UP)

def check_zip(data,limit=80_000_000):
 if len(data)>limit or not zipfile.is_zipfile(io.BytesIO(data)):
  raise ValueError('original ZIP absent or oversized')
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  if len(z.infolist())>3000:raise ValueError('too many ZIP entries')
  if sum(x.file_size for x in z.infolist())>250_000_000:
   raise ValueError('ZIP uncompressed content exceeds safety limit')
  if any(x.file_size>30_000_000 for x in z.infolist()):
   raise ValueError('oversized original ZIP member')
  bad=z.testzip()
  if bad:raise ValueError('ZIP checksum failed')
  if not any('/publicdoc/' in ('/'+n.lower()) and n.lower().endswith('.xbrl') for n in z.namelist()):
   raise ValueError('no PublicDoc XBRL instance')
 return hashlib.sha256(data).hexdigest()


def original_instance(data,filing):
 """Parse only actual PublicDoc XBRL instance and validate identity of filing."""
 check_zip(data)
 with zipfile.ZipFile(io.BytesIO(data)) as z:
  names=[info for info in z.infolist() if '/publicdoc/' in ('/'+info.filename.lower())
         and info.filename.lower().endswith('.xbrl') and not info.is_dir()]
  if len(names)!=1:raise ValueError('not exactly one PublicDoc XBRL instance')
  member=names[0]
  if member.file_size>30_000_000:raise ValueError('oversized XBRL')
  # Filename is metadata *inside* original submission, not a ticker-based rule.
  fn=member.filename
  edinet=filing.get('edinetCode')
  end=filing['periodEnd']
  if not edinet or edinet not in fn or end not in fn:
   raise ValueError('XBRL filename identity/period mismatch')
  root=ET.fromstring(z.read(member))
 contexts={}; units={}; facts=defaultdict(list)
 for el in root:
  name=local(el.tag)
  if name=='context':
   ident=el.get('id')
   entity=el.find('{%s}entity'%XBRLI)
   period=el.find('{%s}period'%XBRLI)
   if not ident or entity is None or period is None:continue
   identifier=entity.find('{%s}identifier'%XBRLI)
   contexts[ident]={
    'entity':identifier.text if identifier is not None else None,
    'start':period.findtext('{%s}startDate'%XBRLI),
    'end':period.findtext('{%s}endDate'%XBRLI),
    'instant':period.findtext('{%s}instant'%XBRLI),
    'dimensions':[x.text for x in el.iter() if local(x.tag) in ('explicitMember','typedMember')],
   }
  elif name=='unit':
   measures=[(x.text or '').strip() for x in el.iter() if local(x.tag)=='measure']
   units[el.get('id')]=measures if len(measures)==1 else []
  elif el.get('contextRef') and el.get('unitRef'):
   value=dec(el.text)
   if value is None or el.get('{http://www.w3.org/2001/XMLSchema-instance}nil')=='true':continue
   facts[(name,el.get('contextRef'))].append({
    'element':name,'namespace':el.tag.split('}',1)[0][1:] if el.tag.startswith('{') else '',
    'contextRef':el.get('contextRef'),'unitRef':el.get('unitRef'),
    'unit':units.get(el.get('unitRef')), # units might be defined later; normalized below
    'value':str(value),'decimals':el.get('decimals'),
    'file':member.filename,
   })
 # Resolve unitRef after all units: XBRL does not mandate document ordering.
 for entries in facts.values():
  for e in entries:e['unit']=units.get(e['unitRef'],[])
 for ctx in ('CurrentYearDuration','Prior1YearDuration','CurrentYearInstant',
             'CurrentYearInstant_NonConsolidatedMember'):
  if ctx not in contexts:raise ValueError('required context missing: '+ctx)
 current=contexts['CurrentYearDuration'];previous=contexts['Prior1YearDuration']
 instant=contexts['CurrentYearInstant'];salary=contexts['CurrentYearInstant_NonConsolidatedMember']
 if current['start']!=filing['periodStart'] or current['end']!=end:
  raise ValueError('current fiscal-period mismatch')
 if instant['instant']!=end or salary['instant']!=end:
  raise ValueError('instant period mismatch')
 try:
  if date.fromisoformat(previous['end'])+timedelta(days=1)!=date.fromisoformat(current['start']):
   raise ValueError('prior fiscal period not contiguous')
  delta=(date.fromisoformat(previous['end'])-date.fromisoformat(previous['start'])).days
  if not 350<=delta<=380:raise ValueError('prior duration not approximately 12 months')
 except (TypeError,KeyError) as e:raise ValueError('missing prior fiscal dates') from e
 if any(contexts[c]['dimensions'] for c in ('CurrentYearDuration','Prior1YearDuration','CurrentYearInstant')):
  raise ValueError('unexpected dimensions in consolidated context')
 if len(salary['dimensions'])!=1 or 'NonConsolidatedMember' not in salary['dimensions'][0]:
  raise ValueError('salary context is not clearly nonconsolidated')
 # Verify actual entity, not only the file name.
 if any(edinet not in (contexts[c]['entity'] or '') for c in ('CurrentYearDuration','Prior1YearDuration','CurrentYearInstant','CurrentYearInstant_NonConsolidatedMember')):
  raise ValueError('XBRL context entity mismatches filing EDINET code')
 return facts,contexts,member.filename


def pick(facts,aliases,context,unit,taxonomy):
 hits=[]
 for name in aliases:
  for e in facts.get((name,context),[]):
   if e['unit']!=[unit] or not e['namespace'].endswith('/'+taxonomy):continue
   hits.append(e)
 if not hits:raise ValueError('missing permitted fact '+str(aliases)+' @ '+context+' '+unit)
 vals={D(e['value']) for e in hits}
 if len(vals)!=1:raise ValueError('conflicting candidates '+str(aliases)+' @ '+context)
 return next(iter(vals)),{'element_names':sorted({x['element'] for x in hits}),
   'context':context,'unit':unit,'taxonomy':taxonomy,'value':str(next(iter(vals))),
   'instances':[x['file'] for x in hits[:3]],'duplicate_count':len(hits),
   'decimals':sorted(set(str(x['decimals']) for x in hits))}


def audit_numeric_original(data,filing,gaap):
 """Re-derive every metric from an independently parsed XBRL, no CSV reuse."""
 if gaap not in ('JP_GAAP','IFRS'):raise ValueError('numeric facts unsupported for '+str(gaap))
 f=DEFINITIONS[gaap]
 facts,contexts,instance=original_instance(data,filing)
 references={};evidence={}
 for metric,concept,ctx,scale in (
   ('revenue_oku','revenue','CurrentYearDuration',MONEY),
   ('prior_revenue_oku','revenue','Prior1YearDuration',MONEY),
   ('operating_profit_oku','operating_profit','CurrentYearDuration',MONEY),
   ('operating_cf_oku','operating_cf','CurrentYearDuration',MONEY)):
  n,e=pick(facts,f[concept],ctx,'iso4217:JPY','jppfs_cor' if gaap=='JP_GAAP' else 'jpigp_cor')
  references[metric]=str(n/scale);evidence[metric]=e
 salary,salary_e=pick(facts,(SALARY_ELEMENT,), 'CurrentYearInstant_NonConsolidatedMember','iso4217:JPY','jpcrp_cor')
 if salary<0:raise ValueError('negative salary')
 references['average_salary_man']=str(salary/SALARY)
 evidence['average_salary_man']={**salary_e,'scope':'filing company, nonconsolidated'}
 assets,ae=pick(facts,f['assets'],'CurrentYearInstant','iso4217:JPY','jppfs_cor' if gaap=='JP_GAAP' else 'jpigp_cor')
 equity,ee=pick(facts,f['parent_equity'],'CurrentYearInstant','iso4217:JPY','jppfs_cor' if gaap=='JP_GAAP' else 'jpigp_cor')
 ratio_evidence={'assets':ae,'parent_equity':ee}
 if gaap=='JP_GAAP':
  valuation,ve=pick(facts,f['valuation'],'CurrentYearInstant','iso4217:JPY','jppfs_cor')
  equity+=valuation;ratio_evidence['valuation_and_translation']=ve
 ratio=percent(equity,assets)
 if ratio is None:raise ValueError('invalid parent equity or assets')
 references['equity_ratio_pct']=str(ratio)
 published,pe=pick(facts,f['disclosed_ratio'],'CurrentYearInstant','xbrli:pure','jpcrp_cor')
 # Published filings use different displayed precisions (e.g. 71.5% vs 71.52%).
 reported_pct=published*100
 if abs(reported_pct-ratio)>D('0.051'):
  raise ValueError('ratio formula conflicts with issuer disclosed ratio')
 evidence['equity_ratio_pct']={**ratio_evidence,'formula':f['equity_formula'],
  'parent_equity_jpy':str(equity),'assets_jpy':str(assets),
  'disclosed_ratio_pct':str(reported_pct),'disclosed_ratio_source':pe,
  'disclosed_ratio_abs_delta_pp':str(abs(reported_pct-ratio))}
 return {'values':references,'evidence':evidence,'gaap':gaap,'instance':instance,
         'original_sha256':hashlib.sha256(data).hexdigest(),
         'period_start':filing['periodStart'],'period_end':filing['periodEnd'],
         'definition_version':'3.13'}


def audit_us_gaap_original(data,filing):
 """Independently extract statement-local HTML with issuer's operating-profit rule."""
 # First check original ZIP's XBRL identity, context and salary scope. Even
 # when consolidated figures are HTML TextBlocks the instance identifies filing.
 _,_,instance=original_instance(data,filing)
 extraction=v310.extract_original_type1(data,filing['docID'])
 valid,reason=v311.validate_original(filing,extraction)
 if not valid:raise ValueError('US GAAP source evidence rejected: '+reason)
 if extraction.get('issues') and any(x.get('error') in (
       'conflicting_exact_table_candidates','consolidated_balance_sheet_identity_mismatch') for x in extraction['issues']):
  raise ValueError('conflicting US GAAP original')
 values=extraction['candidate_values']
 evidence={k:{'source':'US GAAP consolidated iXBRL TextBlock',
              'source_elements':v310.STATEMENT_ELEMENTS,
              'source_filing':filing['docID'],'proof':str(extraction['provenance'].get(k,[]))[:1200]}
           for k in METRICS}
 evidence['operating_profit_oku']['formula']='revenue - cost_of_sales - selling_general_admin - research_development; issuer-defined'
 evidence['equity_ratio_pct']['formula']=DEFINITIONS['US_GAAP']['equity_formula']
 evidence['average_salary_man']['scope']='nonconsolidated reporting company'
 return {'values':values,'evidence':evidence,'gaap':'US_GAAP','instance':instance,
         'original_sha256':hashlib.sha256(data).hexdigest(),
         'period_start':filing['periodStart'],'period_end':filing['periodEnd'],
         'definition_version':'3.13'}


def reconcile(candidate,filing,original_data,external_sha=None):
 """Fail-closed metric review; never silently replace a non-ratio disagreement."""
 out=json.loads(json.dumps(candidate))
 out['pipeline_version']='3.13'
 out['publication_status']='UNVERIFIED'
 out['approved_for_publication']=False
 out.setdefault('quality_gate',{})['ready_for_publication']=False
 out['quality_gate']['status']='BLOCKED'
 result={'status':'BLOCKED','publication_approved':False,'metrics':{},'corrections':{},
         'errors':[],'original_sha256':None,'definition_version':'3.13'}
 gaap=candidate['accounting_standard']['standard']
 try:
  if filing['docID']!=candidate['filing']['docID'] or filing['periodEnd']!=candidate['filing']['periodEnd']:
   raise ValueError('candidate vs source filing ID/period mismatch')
  actual_hash=check_zip(original_data)
  result['original_sha256']=actual_hash
  if external_sha and external_sha!=actual_hash:raise ValueError('manifest SHA-256 mismatch')
  reference=(audit_us_gaap_original(original_data,filing) if gaap=='US_GAAP'
             else audit_numeric_original(original_data,filing,gaap))
  result['gaap']=gaap;result['source_instance']=reference['instance']
  for metric in METRICS:
   old=out['selected_values'].get(metric);ind=reference['values'].get(metric)
   status='SOURCE_RECONCILED'
   if ind is None:
    status='BLOCKED_NO_ORIGINAL';out['selected_values'][metric]=None
   elif dec(old) is None:
    status='BLOCKED_MISSING_CANDIDATE';out['selected_values'][metric]=None
   elif dec(old)!=dec(ind):
    if metric=='equity_ratio_pct' and gaap=='JP_GAAP':
     # This is the precise GAAP definition defect in v3.11.
     out['selected_values'][metric]=ind
     status='CORRECTED_SOURCE_RECONCILED'
     result['corrections'][metric]={'previous_value':old,'source_value':ind,
                                    'reason':'JP_GAAP_parent_equity_not_total_net_assets'}
    else:
     out['selected_values'][metric]=None
     status='BLOCKED_DISAGREEMENT'
   result['metrics'][metric]={'status':status,'candidate_v311':old,
     'original_value':ind,'selected_v313':out['selected_values'].get(metric),
     'provenance':reference['evidence'].get(metric),
     'approved_for_publication':False}
   out.setdefault('provenance',{})[metric]={'verification':status,
     'source_docID':filing['docID'],'source_sha256':actual_hash,
     'method':'independent_original_filing_reconciliation',
     'details':reference['evidence'].get(metric)}
 except Exception as exc:
  result['errors'].append(type(exc).__name__+': '+str(exc)[:220])
  # A failure to validate original identity, period, units, contexts or semantics
  # voids all six proofs. Never retain values as though checked.
  for metric in METRICS:
   result['metrics'][metric]={'status':'BLOCKED_SOURCE_ERROR',
     'candidate_v311':candidate.get('selected_values',{}).get(metric),
     'original_value':None,'selected_v313':None,'approved_for_publication':False}
   out['selected_values'][metric]=None
   out.setdefault('provenance',{})[metric]={'verification':'BLOCKED_SOURCE_ERROR'}
 result['reconciled_count']=sum(m['status'] in ('SOURCE_RECONCILED','CORRECTED_SOURCE_RECONCILED') for m in result['metrics'].values())
 result['blocked_metric_count']=len(METRICS)-result['reconciled_count']
 result['correction_count']=len(result['corrections'])
 result['status']='SOURCE_RECONCILED_PUBLICATION_BLOCKED' if result['reconciled_count']==len(METRICS) else 'BLOCKED'
 out['quality_gate']['independent_original_filing_verified']=result['blocked_metric_count']==0
 out['quality_gate']['reason']='original data reconciled; publication approval and site quality review remain required'
 out['quality_gate']['metrics']={k:r['status'] for k,r in result['metrics'].items()}
 out['quality_gate']['errors']=result['errors']
 out['derived_values']=v311.v33.calculate(out['selected_values'])
 out['source_reconciliation']=result
 return out


def load_offline_sources(nine_path,omron_path):
 """Recover original ZIPs, validating the nine-company artifact's SHA manifests."""
 data={}
 with zipfile.ZipFile(nine_path) as z:
  if z.testzip():raise ValueError('nine-source artifact damaged')
  manifest=json.loads(z.read('manifest.json'))
  if manifest.get('completed_count')!=9 or manifest.get('failed_count')!=0:
   raise ValueError('nine-company collection incomplete')
  if len(manifest['companies'])!=9:raise ValueError('nine-company manifest incomplete')
  for rec in manifest['companies']:
   if rec['status']!='verified':raise ValueError('unverified original download')
   b=z.read(rec['file'])
   if len(b)!=rec['bytes'] or hashlib.sha256(b).hexdigest()!=rec['sha256']:
    raise ValueError('original ZIP manifest mismatch: '+rec['ticker'])
   if rec['ticker'] in data:raise ValueError('duplicate company')
   data[rec['ticker']]={'original':b,'docID':rec['docID'],
     'sha256':rec['sha256'],'filing':{'docID':rec['docID'],
     'edinetCode':rec['edinetCode'],'periodStart':rec['periodStart'],'periodEnd':rec['periodEnd']}}
 with zipfile.ZipFile(omron_path) as z:
  if z.testzip():raise ValueError('US GAAP original artifact damaged')
  manifest=json.loads(z.read('manifest.json'))
  matched=[n for n in z.namelist() if n.lower().endswith('-type1-original.zip')]
  if len(matched)!=1:raise ValueError('US GAAP original source missing')
  data_bytes=z.read(matched[0]);sha=hashlib.sha256(data_bytes).hexdigest()
  if sha!=manifest['sha256'] or len(data_bytes)!=manifest['archive_size_bytes']:
   raise ValueError('US GAAP original artifact manifest mismatch')
  if '6645' in data:raise ValueError('duplicated US GAAP company')
  data['6645']={'original':data_bytes,'docID':manifest['docID'],'sha256':sha,'filing':None}
 return data


def load_candidate_reports(report_zip):
 reports={}
 with zipfile.ZipFile(report_zip) as z:
  if z.testzip():raise ValueError('candidate artifact damaged')
  for name in z.namelist():
   if name.endswith('-v311.json'):
    ticker=name.split('-',1)[0]
    if ticker in reports:raise ValueError('duplicate v311 report')
    reports[ticker]=json.loads(z.read(name))
 return reports


def build_summary(ticker,report):
 rec=report['source_reconciliation'];return {
  'ticker':ticker,'company':report['filing'].get('filerName'),
  'docID':report['filing']['docID'],
  'accounting_standard':report['accounting_standard']['standard'],
  **{metric:report['selected_values'].get(metric) for metric in METRICS},
  'reconciled_count':rec['reconciled_count'],
  'blocked_metric_count':rec['blocked_metric_count'],
  'correction_count':rec['correction_count'],
  'quality_status':'BLOCKED','publication_status':'UNVERIFIED',
  'original_sha256':rec['original_sha256'],
  'review_errors':'; '.join(rec['errors'])}


def write_results(results,output):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 summary=[];audits=[]
 for ticker,report in sorted(results.items()):
  docid=report['filing']['docID']
  (out/f'{ticker}-{docid}-v313.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
  summary.append(build_summary(ticker,report))
  for metric,r in report['source_reconciliation']['metrics'].items():
   audits.append({'ticker':ticker,'docID':docid,'metric':metric,
    'candidate_v311':r.get('candidate_v311'),'original_value':r.get('original_value'),
    'selected_v313':r.get('selected_v313'),'verification_status':r['status'],
    'source_docID':docid,'source_sha256':report['source_reconciliation']['original_sha256'],
    'public_release_approved':False})
 (out/'summary.json').write_text(json.dumps({'companies':summary,
  'company_count':len(summary),'total_reconciled_metrics':sum(s['reconciled_count'] for s in summary),
  'total_corrected_metrics':sum(s['correction_count'] for s in summary),
  'total_blocked_metrics':sum(s['blocked_metric_count'] for s in summary),
  'all_companies_publication_status':'UNVERIFIED',
  'public_release_approved':False},ensure_ascii=False,indent=2),encoding='utf-8')
 cols=['ticker','company','docID','accounting_standard',*METRICS,
       'reconciled_count','blocked_metric_count','correction_count',
       'quality_status','publication_status','original_sha256','review_errors']
 with (out/'company-candidates-v313.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r.get(k) for k in cols} for r in summary)
 with (out/'metric-audit-v313.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(audits[0]) if audits else ['ticker','metric']);w.writeheader();w.writerows(audits)
 (out/'metric-contract-v313.json').write_text(json.dumps({'definitions':DEFINITIONS,
  'salary':{'element':SALARY_ELEMENT,'scope':'nonconsolidated reporting company',
   'context':'CurrentYearInstant_NonConsolidatedMember','unit':'iso4217:JPY',
   'conversion':'JPY / 10000 = 10k JPY'},
  'duration':{'current':'CurrentYearDuration','prior':'Prior1YearDuration'},
  'currency':'JPY','ratio_display':'percent, ROUND_HALF_UP to 0.01 percent point',
  'source_approval':'independent type1 parse is required; no site publication before explicit approval'},ensure_ascii=False,indent=2),encoding='utf-8')
 return summary


def run_offline(v311_zip,nine_originals,omron_original,output):
 originals=load_offline_sources(nine_originals,omron_original)
 candidates=load_candidate_reports(v311_zip)
 if set(candidates)!=set(originals) or len(candidates)!=10:
  raise ValueError('original company set differs from the ten candidates')
 results={}
 for ticker,base in candidates.items():
  source=originals[ticker];filing=base['filing']
  if filing['docID']!=source['docID']:
   raise ValueError('docID mismatch for '+ticker)
  results[ticker]=reconcile(base,filing,source['original'],source['sha256'])
  print(ticker,results[ticker]['source_reconciliation']['reconciled_count'],'/6',flush=True)
 return write_results(results,output)


def run_live(discovery,output,limit,delay):
 key=os.environ.get('EDINET_API_KEY')
 if not key:raise ValueError('EDINET_API_KEY missing')
 targets=[x for x in json.loads(Path(discovery).read_text(encoding='utf-8'))['targets'] if x.get('selected')][:limit]
 results={}
 for i,t in enumerate(targets):
  ticker=t['ticker'];filing=t['selected']
  try:
   type5=v32.download(filing['docID'],key)
   type1=v38.fetch_original(filing['docID'],key)
   # Run original v3.11 rules; type1 is fetched regardless of accounting standard
   # so all six facts can be reconciled independently for every company.
   report=v311.process(type5,filing,type1)
   results[ticker]=reconcile(report,filing,type1)
  except Exception as exc:
   # Preserve an auditable row, not an approved value; no silent skip.
   report={'filing':filing,'accounting_standard':{'standard':'UNKNOWN'},
    'selected_values':{m:None for m in METRICS},'quality_gate':{},'provenance':{}}
   results[ticker]=reconcile(report,filing,b'')
   results[ticker]['source_reconciliation']['errors'].append('download_or_parse: '+type(exc).__name__+': '+str(exc)[:180])
  print(ticker,results[ticker]['source_reconciliation']['reconciled_count'],'/6',flush=True)
  if i+1<len(targets):time.sleep(delay)
 return write_results(results,output)


def main():
 p=argparse.ArgumentParser(description='v3.13 source reconciliation, never publish')
 p.add_argument('--mode',choices=('offline','live'),default='live')
 p.add_argument('--v311-zip',default='edinet-v311-review.zip')
 p.add_argument('--nine-originals',default='edinet-v312-nine-originals.zip')
 p.add_argument('--omron-original',default='omron-S100YG81-original.zip')
 p.add_argument('--discovery',default='discovery-v31.json')
 p.add_argument('--limit',type=int,default=10)
 p.add_argument('--delay',type=float,default=2)
 p.add_argument('--output',default='edinet-v313-output')
 a=p.parse_args()
 if not 1<=a.limit<=100 or not 0<=a.delay<=30:p.error('limit 1-100; delay 0-30')
 if a.mode=='offline':rows=run_offline(a.v311_zip,a.nine_originals,a.omron_original,a.output)
 else:rows=run_live(a.discovery,a.output,a.limit,a.delay)
 if any(r['reconciled_count']!=6 for r in rows) or (a.mode=='offline' and len(rows)!=10):
  raise SystemExit('Source reconciliation incomplete; see artifact (publication BLOCKED)')
 print('Source-reconciled:',sum(r['reconciled_count'] for r in rows),'metrics; corrections:',sum(r['correction_count'] for r in rows))
 print('PUBLICATION STILL BLOCKED')

if __name__=='__main__':main()
