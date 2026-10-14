#!/usr/bin/env python3
"""EDINET v3.4: filing-level GAAP detection, provenance and conservative review.
No company-specific rules. No automatic publication.
"""
import argparse,csv,io,json,os,re,time,zipfile
from collections import Counter
from decimal import Decimal,InvalidOperation
from pathlib import Path
from html.parser import HTMLParser
import edinet_v33 as v33
import edinet_v32 as v32

class TextReader(HTMLParser):
    def __init__(self):super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)

def extract_csv(blob):
    facts=[];textblocks=[];diagnostics=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=[m for m in z.infolist() if not m.is_dir() and m.filename.lower().endswith('.csv')]
        if len(members)>500:raise ValueError('Too many CSV files')
        for m in members:
            if m.file_size>50_000_000:raise ValueError('Oversize CSV')
            raw=z.read(m);txt,encoding=v32.decode(raw)
            delim='\t' if txt[:10000].count('\t')>=txt[:10000].count(',') else ','
            reader=csv.reader(io.StringIO(txt),delimiter=delim)
            head=next(reader,[]);mp=v32.column_map(head)
            diagnostics.append({'file':m.filename,'encoding':encoding,'mapped':bool(mp)})
            if not mp:continue
            for row in reader:
                element=v32.element_name(v32.get(row,mp['element']))
                context=v32.get(row,mp.get('context'))
                unit=v32.get(row,mp.get('unit'))
                value=v32.get(row,mp['value']).replace(',','')
                fact={'element':element,'context':context,'unit':unit,'value':value,'file':m.filename}
                if element.endswith('TextBlock') and ('USGAAP' in element.upper() or 'US_GAAP' in element.upper() or 'FinancialStatements' in element):
                    reader2=TextReader()
                    try:reader2.feed(value)
                    except Exception:pass
                    plain=' '.join(' '.join(reader2.parts).split())
                    textblocks.append({'element':element,'context':context,'length':len(value),'preview':plain[:250], 'file':m.filename})
                if element.endswith('TextBlock'):continue
                facts.append(fact)
    return facts,textblocks,diagnostics

def detect_gaap(facts,textblocks):
    # Strong explicit evidence takes precedence. Tags alone only yield inferred status.
    for f in facts:
        if re.search(r'(AccountingStandard|AccountingStandards|BasisOfPreparation)',f['element'],re.I):
            v=f['value'].lower()
            if '米国' in v or 'us gaap' in v or 'u.s. gaap' in v:return {'standard':'US_GAAP','method':'explicit_filing_field','confidence':'high','evidence':f['element']}
            if '国際' in v or 'ifrs' in v:return {'standard':'IFRS','method':'explicit_filing_field','confidence':'high','evidence':f['element']}
            if '日本' in v or 'japan gaap' in v:return {'standard':'JP_GAAP','method':'explicit_filing_field','confidence':'high','evidence':f['element']}
    us=[t['element'] for t in textblocks if re.search(r'USGAAP|US_GAAP',t['element'],re.I)]
    if us:return {'standard':'US_GAAP','method':'us_gaap_financial_textblock','confidence':'high','evidence':us[:5]}
    names={f['element'] for f in facts if f['context'] in ('CurrentYearDuration','CurrentYearInstant')}
    if any('IFRS' in s for s in names):return {'standard':'IFRS','method':'numeric_taxonomy_inference','confidence':'medium','evidence':sorted(s for s in names if 'IFRS' in s)[:5]}
    if {'NetSales','OperatingIncome'} & names:return {'standard':'JP_GAAP','method':'numeric_taxonomy_inference','confidence':'low','evidence':sorted({'NetSales','OperatingIncome'} & names)}
    return {'standard':'UNKNOWN','method':'insufficient_evidence','confidence':'none','evidence':[]}

def exact_numeric(facts,tags,context):
    found=[]
    for f in facts:
        if f['element'] not in tags or f['context']!=context or f['unit'].split(':')[-1]!='JPY':continue
        try:n=Decimal(f['value'])
        except (InvalidOperation,ValueError):continue
        if n.is_finite():found.append((n,f))
    vals={n for n,f in found}
    return next(iter(vals)) if len(vals)==1 else None,found

ASSETS={'Assets','AssetsIFRS','TotalAssets','TotalAssetsIFRS','TotalAssetsIFRSSummaryOfBusinessResults'}
EQUITY={'EquityAttributableToOwnersOfParent','EquityAttributableToOwnersOfParentIFRS','EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults','Equity','EquityIFRS','NetAssets','NetAssetsSummaryOfBusinessResults'}

def equity_ratio(facts,gaap):
    if gaap['standard']=='US_GAAP':return None,{'status':'unsupported_us_gaap_textblock','reason':'US GAAP statement requires verified table extraction'}
    assets,af=exact_numeric(facts,ASSETS,'CurrentYearInstant')
    equity,ef=exact_numeric(facts,EQUITY,'CurrentYearInstant')
    if assets is None or equity is None or assets<=0 or not 0<=equity<=assets:
        return None,{'status':'unresolved','asset_candidates':len(af),'equity_candidates':len(ef),'reason':'missing/conflicting numerator or denominator'}
    ratio=(equity/assets*100).quantize(Decimal('0.01'))
    return str(ratio),{'status':'calculated_unverified','formula':'consolidated_equity / consolidated_assets * 100','assets_jpy':str(assets),'equity_jpy':str(equity),'assets_sources':[f['element'] for _,f in af], 'equity_sources':[f['element'] for _,f in ef]}

def review(blob,filing):
    facts,textblocks,diagnostics=extract_csv(blob)
    gaap=detect_gaap(facts,textblocks)
    legacy=v32.analyze(blob)
    values=dict(legacy['selected_values'])
    provenance={k:{'method':'v3.3_numeric_tag','verification':'pending'} for k in values}
    ratio,ratio_detail=equity_ratio(facts,gaap)
    if ratio is not None:
        values['equity_ratio_pct']=ratio
        provenance['equity_ratio_pct']={'method':'consolidated_balance_sheet_formula','verification':'pending','detail':ratio_detail}
    else:
        provenance['equity_ratio_pct']={'method':'unresolved','verification':'pending','detail':ratio_detail}
    if gaap['standard']=='US_GAAP':
        # Prevent silent adoption of standalone numbers or non-comparable values.
        for metric in ('revenue_oku','operating_profit_oku','prior_revenue_oku','operating_cf_oku','equity_ratio_pct'):
            values[metric]=None;provenance[metric]={'method':'us_gaap_textblock_pending_structured_validation','verification':'blocked'}
    derived=v33.calculate(values)
    return {'filing':filing,'accounting_standard':gaap,'selected_values':values,'derived_values':derived,
            'provenance':provenance,'textblock_inventory':textblocks[:100], 'csv_diagnostics':diagnostics,
            'legacy_issues':legacy['issues'], 'publication_status':'UNVERIFIED',
            'quality_gate':{'ready_for_publication':False,'reason':'original filing reconciliation is not automated'}}

def main():
    p=argparse.ArgumentParser();p.add_argument('--discovery',default='discovery-v31.json');p.add_argument('--output',default='edinet-v34-output');p.add_argument('--limit',type=int,default=1);p.add_argument('--delay',type=float,default=3)
    a=p.parse_args()
    if not 1<=a.limit<=10 or not 0<=a.delay<=30:p.error('limit 1-10 and delay 0-30 required')
    key=os.environ.get('EDINET_API_KEY')
    if not key:raise RuntimeError('EDINET_API_KEY missing')
    targets=[t for t in json.loads(Path(a.discovery).read_text(encoding='utf-8'))['targets'] if t.get('selected')][:a.limit]
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);summary=[]
    for i,t in enumerate(targets):
        filing=t['selected'];ticker=t['ticker'];docid=filing['docID'];r={'ticker':ticker,'company':t['target_name'],'docID':docid,'status':'error','publication_status':'UNVERIFIED'}
        try:
            data=review(v32.download(docid,key),filing)
            (out/f'{ticker}-{docid}-v34.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            r.update(status='diagnosed',accounting_standard=data['accounting_standard']['standard'],gaap_confidence=data['accounting_standard']['confidence'],**data['selected_values'],**data['derived_values'])
        except Exception as exc:r['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
        summary.append(r);print(ticker,r['status'],r.get('accounting_standard',''),flush=True)
        if i+1<len(targets):time.sleep(a.delay)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['ticker','company','docID','status','accounting_standard','gaap_confidence',*v32.TAGS.keys(),'operating_margin_pct','revenue_growth_pct','operating_cf_to_revenue_pct','publication_status','error']
    with (out/'company-candidates-v34.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r.get(k) for k in cols} for r in summary)
    (out/'README.txt').write_text('All outputs UNVERIFIED. US GAAP financial statement TextBlocks are inventoried, not automatically converted into numeric facts. Do not publish.\n',encoding='utf-8')
    if any(r['status']=='error' for r in summary):raise RuntimeError('Some downloads failed; inspect artifacts')
if __name__=='__main__':main()
