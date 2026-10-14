#!/usr/bin/env python3
"""v3.3: financial review candidates, never automatically publish."""
import argparse,csv,json,os,time
from pathlib import Path
from decimal import Decimal,InvalidOperation
import edinet_v32 as v32

v32.TAGS['equity_ratio_pct'].update({'EquityToAssetRatioIFRSSummaryOfBusinessResults','EquityToAssetRatioSummaryOfBusinessResults'})
old_candidate=v32.safe_candidate

def safe_candidate(fact,metric):
    ctx=fact['context']
    if metric=='average_salary_man':
        if ctx!='CurrentYearInstant_NonConsolidatedMember':return False,'salary: parent-company context required'
        try:n=Decimal(fact['value'])
        except (InvalidOperation,ValueError):return False,'non-numeric salary'
        if not n.is_finite() or fact['unit'].split(':')[-1]!='JPY':return False,'invalid salary unit'
        return True,str(n/Decimal(10000))
    if metric=='equity_ratio_pct':
        if ctx!='CurrentYearInstant':return False,'ratio: consolidated instant context required'
        try:n=Decimal(fact['value'])
        except (InvalidOperation,ValueError):return False,'non-numeric ratio'
        if not n.is_finite():return False,'non-finite ratio'
        unit=fact['unit'].split(':')[-1].lower()
        if unit=='pure' and 0<=n<=1:return True,str(n*100)
        if unit=='percent' and 0<=n<=100:return True,str(n)
        return False,'ratio scale/unit ambiguous; do not guess'
    return old_candidate(fact,metric)

v32.safe_candidate=safe_candidate

def calculate(values):
    def d(k):
        try:return Decimal(values[k]) if values[k] is not None else None
        except (InvalidOperation,ValueError,KeyError):return None
    revenue,prior,profit,cf=map(d,['revenue_oku','prior_revenue_oku','operating_profit_oku','operating_cf_oku'])
    def percent(n,den):return str((n/den*100).quantize(Decimal('0.01'))) if n is not None and den is not None and den!=0 else None
    return {'operating_margin_pct':percent(profit,revenue),'revenue_growth_pct':percent(revenue-prior,prior) if revenue is not None and prior is not None else None,'operating_cf_to_revenue_pct':percent(cf,revenue)}

def main():
    p=argparse.ArgumentParser();p.add_argument('--discovery',default='discovery-v31.json');p.add_argument('--output',default='edinet-v33-output');p.add_argument('--limit',type=int,default=1);p.add_argument('--delay',type=float,default=2.5)
    a=p.parse_args()
    if not 1<=a.limit<=10 or not 0<=a.delay<=30:p.error('limit 1-10, delay 0-30')
    key=os.environ.get('EDINET_API_KEY')
    if not key:raise RuntimeError('EDINET_API_KEY missing')
    targets=[x for x in json.loads(Path(a.discovery).read_text(encoding='utf-8'))['targets'] if x.get('selected')][:a.limit]
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);summary=[]
    for i,item in enumerate(targets):
        doc=item['selected'];ticker=item['ticker'];docid=doc['docID']
        row={'ticker':ticker,'company':item['target_name'],'docID':docid,'periodEnd':doc.get('periodEnd'),'status':'error','publication_status':'UNVERIFIED'}
        try:
            report=v32.analyze(v32.download(docid,key));values=report['selected_values'];derived=calculate(values)
            row.update(status='diagnosed',selected_values=values,derived_values=derived,issues=report['issues'],csv_files=len(report['csv_files']))
            (out/f'{ticker}-{docid}-v33.json').write_text(json.dumps({'filing':doc,'diagnostic':report,'derived_values':derived,'publication_status':'UNVERIFIED'},ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception as e:row['error']=f'{type(e).__name__}: {str(e)[:250]}'
        summary.append(row);print(ticker,row['status'],flush=True)
        if i+1<len(targets):time.sleep(a.delay)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['ticker','company','docID','periodEnd','status',*v32.TAGS.keys(),'operating_margin_pct','revenue_growth_pct','operating_cf_to_revenue_pct','publication_status']
    with (out/'company-candidates-v33.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
        for row in summary:w.writerow({**row,**row.get('selected_values',{}),**row.get('derived_values',{})})
    (out/'README.txt').write_text('UNVERIFIED: compare all candidate values against original annual reports before publication.\n',encoding='utf-8')
    if any(r['status']=='error' for r in summary):raise RuntimeError('Download errors; inspect artifact')
    if not any(any(v is not None for v in r.get('selected_values',{}).values()) for r in summary):raise RuntimeError('No values extracted; inspect artifact')

if __name__=='__main__':main()
