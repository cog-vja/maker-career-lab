#!/usr/bin/env python3
"""EDINET API v2 -> review CSV candidates (never automatically publishes).
Python stdlib only. Usage: python edinet_pipeline.py discover --days 14 --names "東京エレクトロン,アドバンテスト"
                   python edinet_pipeline.py extract --doc-id S1234567 --company-name "..." --edinet-code E00000
                   python edinet_pipeline.py extract --zip-file saved.zip --doc-id S1234567 --company-name "..." --edinet-code E00000
Requires EDINET_API_KEY for network. Output candidates to local CSV, not approved.
"""
import argparse, csv, datetime as dt, io, json, os, re, sys, time, urllib.parse, urllib.request, zipfile
from pathlib import Path
from decimal import Decimal, InvalidOperation

BASE=Path(__file__).resolve().parent
API='https://api.edinet-fsa.go.jp/api/v2/'
FIELDS=['company_id','company_name','aliases','edinet_code','fiscal_period','accounting_standard','scope','salary_scope','revenue_oku','operating_profit_oku','prior_revenue_oku','operating_cf_oku','equity_ratio_pct','average_salary_man','source_document_id','source_url','verified_at','reviewer','review_status']
# Only explicit, consolidated contexts; fail closed when ambiguity arises.
METRICS={
 'revenue_oku': {'Revenue','NetSales','SalesRevenue','OperatingRevenue','RevenueIFRS'},
 'operating_profit_oku': {'OperatingIncome','OperatingProfitLoss','OperatingProfitLossIFRS'},
 'prior_revenue_oku': {'Revenue','NetSales','SalesRevenue','OperatingRevenue','RevenueIFRS'},
 'operating_cf_oku': {'NetCashProvidedByUsedInOperatingActivities','CashFlowsFromUsedInOperatingActivities','NetCashProvidedByUsedInOperatingActivitiesIFRS'},
 'equity_ratio_pct': {'EquityToAssetRatio','RatioOfOwnersEquityToTotalAssets'},
 'average_salary_man': {'AverageAnnualSalaryInformationAboutReportingCompanyInformationAboutEmployees'},
}
DURATION={'revenue_oku':'CurrentYearDuration','operating_profit_oku':'CurrentYearDuration','prior_revenue_oku':'Prior1YearDuration','operating_cf_oku':'CurrentYearDuration','equity_ratio_pct':'CurrentYearInstant','average_salary_man':'CurrentYearDuration'}

def request(url, key):
 if not key: raise ValueError('EDINET_API_KEYが未設定です。')
 req=urllib.request.Request(url,headers={'User-Agent':'MakerCareerLabValidation/0.3 (research)'})
 with urllib.request.urlopen(req,timeout=45) as resp: return resp.read()

def api_url(path, params, key):
 return API+path+'?'+urllib.parse.urlencode(dict(params,**{'Subscription-Key':key}))

def discover(args):
 key=os.environ.get('EDINET_API_KEY'); names=[n.strip() for n in args.names.split(',') if n.strip()]
 if not names: raise ValueError('--names に企業名を指定してください')
 rows=[]; today=dt.date.today(); start=dt.date.fromisoformat(args.start) if args.start else today-dt.timedelta(days=args.days-1)
 if (today-start).days>366 or start>today: raise ValueError('検索範囲は過去366日以内')
 day=start
 while day<=today:
  payload=json.loads(request(api_url('documents.json',{'date':day.isoformat(),'type':2},key),key))
  for x in payload.get('results',[]):
   if any(n in (x.get('filerName') or '') for n in names) and '有価証券報告書' in (x.get('docDescription') or ''):
    rows.append({k:x.get(k) for k in ['docID','edinetCode','filerName','docDescription','submitDateTime','periodStart','periodEnd','csvFlag','legalStatus']})
  day+=dt.timedelta(days=1)
  if day<=today: time.sleep(args.delay)
 print(json.dumps({'searched_days':(today-start).days+1,'matches':rows},ensure_ascii=False,indent=2))

def load_csv_zip(blob):
 with zipfile.ZipFile(io.BytesIO(blob)) as z:
  names=[n for n in z.namelist() if n.lower().endswith('.csv') and not n.startswith('__MACOSX/')]
  if not names: raise ValueError('CSVがZIPにありません。type=5を確認')
  if len(names)>500: raise ValueError('CSVファイル数が過大です')
  for name in names:
   if z.getinfo(name).file_size>50_000_000: raise ValueError('CSVファイルが大きすぎます')
   raw=z.read(name)
   try: content=raw.decode('utf-16')
   except UnicodeError: content=raw.decode('utf-8-sig')
   reader=csv.reader(io.StringIO(content),delimiter='\t')
   for row in reader:
    if len(row)<3: continue
    yield name,row

def tag_name(s):
 s=s.rsplit(':',1)[-1].split('}',1)[-1]
 return s

def context_ok(context, metric):
 # Strictly disallow dimensions and nonconsolidated contexts. Salary is a reporting-company metric.
 if 'NonConsolidated' in context or 'Segment' in context or 'Member' in context or 'Axis' in context: return False
 expected=DURATION[metric]
 return context==expected

def extract_metrics(blob):
 found={k:[] for k in METRICS}; trace={k:[] for k in METRICS}
 for filename,row in load_csv_zip(blob):
  tag=tag_name(row[0].strip()); context=row[1].strip(); raw=row[2].strip().replace(',','')
  for key,tags in METRICS.items():
   if tag not in tags or not context_ok(context,key): continue
   try: val=Decimal(raw)
   except InvalidOperation: continue
   if not val.is_finite(): continue
   # Japanese XBRL monetary values typically JPY, percentages may be fractions or percentages.
   unit=row[3].strip() if len(row)>3 else ''
   if key in ('equity_ratio_pct',) and not unit:
    trace[key].append({'tag':tag,'context':context,'value':raw,'issue':'ratio unit needs review'});continue
   if key in ('revenue_oku','operating_profit_oku','prior_revenue_oku','operating_cf_oku'):
    if unit not in ('JPY','iso4217:JPY'):
     trace[key].append({'tag':tag,'context':context,'value':raw,'issue':'unknown unit '+unit});continue
    val=val/Decimal(100_000_000)
   elif key=='average_salary_man':
    if unit not in ('JPY','iso4217:JPY'):continue
    val=val/Decimal(10_000)
   elif key=='equity_ratio_pct':
    # Do not guess whether XBRL is stored as fraction or percent; manual review.
    trace[key].append({'tag':tag,'context':context,'value':raw,'unit':unit,'issue':'manual ratio conversion required'});continue
   found[key].append((str(val),tag,context,filename))
 values={};
 for key,records in found.items():
  unique={r[0] for r in records}
  values[key]=next(iter(unique)) if len(unique)==1 else ''
  if len(unique)>1:trace[key].append({'issue':'conflicting candidates; left blank','candidates':records[:10]})
  elif records:trace[key].append({'selected':records[0]})
 return values,trace

def extract(args):
 key=os.environ.get('EDINET_API_KEY')
 if args.zip_file: blob=Path(args.zip_file).read_bytes()
 else: blob=request(api_url('documents/'+args.doc_id,{'type':5},key),key)
 values,trace=extract_metrics(blob)
 row={k:'' for k in FIELDS}
 row.update(company_id=args.edinet_code,company_name=args.company_name,edinet_code=args.edinet_code,
            source_document_id=args.doc_id,source_url='https://disclosure2.edinet-fsa.go.jp/',
            scope='連結（候補、要照合）',salary_scope='提出会社単体（要照合）',review_status='draft')
 row.update(values)
 out=Path(args.output)
 if out.exists():
  with out.open(encoding='utf-8-sig',newline='') as f: existing=list(csv.DictReader(f))
 else: existing=[]
 if any(x['source_document_id']==args.doc_id for x in existing):raise ValueError('同じdocIDが既に候補CSVにあります')
 with out.open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(existing+[row])
 report=out.with_suffix('.review.json')
 report.write_text(json.dumps({'docID':args.doc_id,'company':args.company_name,'candidate':row,'extraction_trace':trace,'warnings':['未承認。決算期、会計基準、連結範囲、前期数値、給与対象、訂正書類の有無を有価証券報告書と照合すること','ROE/ROIC/PER/PBRは本バージョンの比較対象外','同一タグでも文脈・企業拡張タクソノミで意味が異なる可能性があります']},ensure_ascii=False,indent=2),encoding='utf-8')
 print(f'候補を保存: {out}\n照合用レポート: {report}\n公開用データは変更していません。')

def main():
 p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
 d=sub.add_parser('discover');d.add_argument('--names',required=True);d.add_argument('--days',type=int,default=14);d.add_argument('--start');d.add_argument('--delay',type=float,default=3.0);d.set_defaults(func=discover)
 e=sub.add_parser('extract');e.add_argument('--doc-id',required=True);e.add_argument('--company-name',required=True);e.add_argument('--edinet-code',required=True);e.add_argument('--zip-file');e.add_argument('--output',default='company-candidates.csv');e.set_defaults(func=extract)
 a=p.parse_args();a.func(a)
if __name__=='__main__':
 try:main()
 except (ValueError, OSError, zipfile.BadZipFile) as e:sys.exit('エラー: '+str(e))
