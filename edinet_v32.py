#!/usr/bin/env python3
"""EDINET v3.2: extract diagnostic candidates from known doc IDs, never publish.
Standard library only. Requires EDINET_API_KEY environment variable.
"""
import argparse,csv,io,json,os,re,time,urllib.parse,urllib.request,urllib.error,zipfile
from collections import Counter
from decimal import Decimal,InvalidOperation
from pathlib import Path

BASE='https://api.edinet-fsa.go.jp/api/v2/documents/'
TAGS={
 'revenue_oku':{'Revenue','NetSales','SalesRevenue','OperatingRevenue','RevenueIFRS','NetSalesIFRS'},
 'operating_profit_oku':{'OperatingIncome','OperatingProfitLoss','OperatingProfitLossIFRS','OperatingIncomeLoss'},
 'prior_revenue_oku':{'Revenue','NetSales','SalesRevenue','OperatingRevenue','RevenueIFRS','NetSalesIFRS'},
 'operating_cf_oku':{'NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesIFRS'},
 'equity_ratio_pct':{'EquityToAssetRatio','RatioOfOwnersEquityToTotalAssets'},
 'average_salary_man':{'AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees'},
}
HEADERS={
 'element':['要素ID','要素ＩＤ','要素名','elementid','element','elementname'],
 'context':['コンテキストID','コンテキストＩＤ','コンテキスト','contextid','contextref','context'],
 'unit':['ユニットID','ユニットＩＤ','単位ID','単位','unitid','unit'],
 'value':['値','数値','value','factvalue'],
}
def normalize(s):return re.sub(r'[\s_\-　\ufeff]+','',s).lower()
def column_map(row):
 result={}
 for kind,alts in HEADERS.items():
  for i,s in enumerate(row):
   if normalize(s) in {normalize(a) for a in alts}:result[kind]=i;break
 return result if 'element' in result and 'value' in result else {}
def get(row,i):return row[i].strip() if isinstance(i,int) and i<len(row) else ''
def element_name(s):return re.split(r'[:}]',s)[-1]
def decode(raw):
 for encoding in ('utf-16','utf-8-sig','cp932'):
  try:return raw.decode(encoding),encoding
  except UnicodeError:pass
 raise ValueError('Unsupported CSV encoding')
def parse_file(raw,name):
 text,encoding=decode(raw)
 sample=text[:10000]
 delim='\t' if sample.count('\t')>=sample.count(',') else ','
 rows=csv.reader(io.StringIO(text),delimiter=delim)
 head=next(rows,[])
 mapping=column_map(head)
 # CSV from EDINET generally has an explicit header. Never silently assume column order.
 diagnostics={'file':name,'encoding':encoding,'delimiter':'TAB' if delim=='\t' else 'COMMA',
              'columns':len(head),'header':head[:20],'mapping':mapping,'rows':0,'matched_tags':0,
              'sample_elements':[],'sample_contexts':[]}
 samples_e=[];samples_c=[];facts=[]
 if not mapping:return diagnostics,facts
 for row in rows:
  diagnostics['rows']+=1
  element=element_name(get(row,mapping['element']))
  context=get(row,mapping.get('context'))
  unit=get(row,mapping.get('unit'))
  val=get(row,mapping['value']).replace(',','')
  if len(samples_e)<8 and element not in samples_e:samples_e.append(element)
  if len(samples_c)<8 and context not in samples_c:samples_c.append(context)
  if element in set().union(*TAGS.values()):
   diagnostics['matched_tags']+=1
   facts.append({'element':element,'context':context,'unit':unit,'value':val,'file':name})
 diagnostics['sample_elements']=samples_e;diagnostics['sample_contexts']=samples_c
 return diagnostics,facts

def label_period(context,metric):
 if 'Prior1YearDuration' in context:return 'prior'
 if 'CurrentYearDuration' in context:return 'current'
 if 'CurrentYearInstant' in context:return 'instant'
 return 'other'
def safe_candidate(fact,metric):
 ctx=fact['context'];period=label_period(ctx,metric)
 if any(x in ctx for x in ('NonConsolidated','Segment','Member','Axis')):return False,'excluded context'
 target=('prior' if metric=='prior_revenue_oku' else 'instant' if metric=='equity_ratio_pct' else 'current')
 if period!=target:return False,'period/context not matched'
 try:value=Decimal(fact['value'])
 except (InvalidOperation,ValueError):return False,'non numeric'
 if not value.is_finite():return False,'non finite'
 if metric=='equity_ratio_pct':return False,'ratio needs human unit verification'
 unit=fact['unit']
 if unit not in ('JPY','iso4217:JPY'):return False,'JPY unit not confirmed'
 divider=Decimal(10000 if metric=='average_salary_man' else 100000000)
 return True,str(value/divider)
def analyze(blob):
 report={'zip_entries':[],'csv_files':[],'candidate_facts':{},'selected_values':{},'issues':[]}
 with zipfile.ZipFile(io.BytesIO(blob)) as z:
  files=[x for x in z.infolist() if not x.is_dir() and x.filename.lower().endswith('.csv')]
  report['zip_entries']=[{'name':x.filename,'bytes':x.file_size} for x in z.infolist()[:60]]
  if not files:report['issues'].append('No CSV entries in ZIP')
  if len(files)>500:raise ValueError('Too many CSV entries')
  facts=[]
  for member in files:
   if member.file_size>50_000_000:raise ValueError('CSV too large')
   diag,found=parse_file(z.read(member),member.filename)
   report['csv_files'].append(diag);facts.extend(found)
  for metric,tags in TAGS.items():
   matches=[]
   for fact in facts:
    if fact['element'] not in tags:continue
    ok,result=safe_candidate(fact,metric)
    matches.append({**fact,'eligible':ok,'assessment':result})
   report['candidate_facts'][metric]=matches[:80]
   accepted={m['assessment'] for m in matches if m['eligible']}
   report['selected_values'][metric]=next(iter(accepted)) if len(accepted)==1 else None
   if len(accepted)>1:report['issues'].append(f'{metric}: conflicting values')
   if not matches:report['issues'].append(f'{metric}: no matching elements')
   if matches and not accepted:report['issues'].append(f'{metric}: found elements but no eligible values')
  if all(not x['mapping'] for x in report['csv_files']):report['issues'].append('No recognizable CSV headers')
 return report

def download(docid,key):
 if not re.fullmatch(r'[A-Z0-9]{8,16}',docid):raise ValueError('Invalid docID')
 url=BASE+docid+'?'+urllib.parse.urlencode({'type':5,'Subscription-Key':key})
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-v3.2-review'}),timeout=90) as r:blob=r.read()
 except urllib.error.HTTPError as e:raise RuntimeError(f'HTTP {e.code} for {docid}') from None
 if not blob.startswith(b'PK'):raise RuntimeError('Non-ZIP response from EDINET')
 return blob

def main():
 p=argparse.ArgumentParser();p.add_argument('--discovery',default='discovery-v31.json');p.add_argument('--output',default='edinet-v32-output');p.add_argument('--limit',type=int,default=10);p.add_argument('--delay',type=float,default=2.5)
 a=p.parse_args();key=os.environ.get('EDINET_API_KEY')
 if not key:raise RuntimeError('EDINET_API_KEY is missing')
 if not 1<=a.limit<=10 or not 0<=a.delay<=30:raise ValueError('invalid limit/delay')
 discovery=json.loads(Path(a.discovery).read_text(encoding='utf-8'))
 targets=[x for x in discovery['targets'] if x.get('selected')][:a.limit]
 out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
 summary=[]
 for i,item in enumerate(targets):
  doc=item['selected'];docid=doc['docID'];ticker=item['ticker']
  row={'ticker':ticker,'company':item['target_name'],'docID':docid,'periodEnd':doc.get('periodEnd'),'status':'error'}
  try:
   report=analyze(download(docid,key));row.update(status='diagnosed',csv_files=len(report['csv_files']),parsed_rows=sum(x['rows'] for x in report['csv_files']),candidate_counts={k:len(v) for k,v in report['candidate_facts'].items()},selected_values=report['selected_values'],issues=report['issues'])
   (out/f'{ticker}-{docid}-diagnostic.json').write_text(json.dumps({'filing':doc,'diagnostic':report,'publication_status':'UNVERIFIED'},ensure_ascii=False,indent=2),encoding='utf-8')
  except Exception as exc:
   row['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
  summary.append(row)
  print(ticker,docid,row['status'],'csv',row.get('csv_files','-'),flush=True)
  if i+1<len(targets):time.sleep(a.delay)
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 lines=['# EDINET v3.2 診断結果','', '**検証候補です。公開サイトのデータは変更していません。**','']
 for r in summary:lines.append(f"- {r['company']} ({r['ticker']}): {r['status']}, CSV={r.get('csv_files','?')}, rows={r.get('parsed_rows','?')}, candidates={r.get('candidate_counts','?')}, error={r.get('error','-')}")
 (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
 if any(x['status']=='error' for x in summary):raise RuntimeError('Some documents failed: review artifacts')
 if not any(any(v for v in x.get('candidate_counts',{}).values()) for x in summary):raise RuntimeError('No matching financial element in any report; review diagnostics')
if __name__=='__main__':
 try:main()
 except Exception as e:raise SystemExit('ERROR: '+str(e))
