#!/usr/bin/env python3
"""EDINET v3.5: filing-based GAAP, conservative reconciliation and US GAAP HTML table extraction.
No company-specific branches; never publishes unverified financial information.
"""
import argparse,csv,io,json,os,re,time,zipfile
from collections import defaultdict
from decimal import Decimal,InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
import edinet_v32 as v32
import edinet_v33 as v33
import edinet_v34 as v34

class TableReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.tables=[];self.table=None;self.row=None;self.cell=None;self.depth=0
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.depth+=1
            if self.depth==1:self.table=[]
        elif self.depth==1 and tag=='tr':self.row=[]
        elif self.depth==1 and tag in ('td','th') and self.row is not None:
            a=dict(attrs);self.cell={'text':'','colspan':int(a.get('colspan','1') or 1),'rowspan':int(a.get('rowspan','1') or 1)}
    def handle_data(self,data):
        if self.cell is not None:self.cell['text']+=data
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None and self.row is not None:
            self.cell['text']=' '.join(self.cell['text'].split());self.row.append(self.cell);self.cell=None
        elif tag=='tr' and self.row is not None and self.table is not None:
            if self.row:self.table.append(self.row)
            self.row=None
        elif tag=='table' and self.depth:
            if self.depth==1 and self.table:self.tables.append(self.table);self.table=None
            self.depth-=1

def textblock_records(blob):
    result=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        for member in z.infolist():
            if member.is_dir() or not member.filename.lower().endswith('.csv'):continue
            if member.file_size>50_000_000:raise ValueError('Oversize CSV')
            text,_=v32.decode(z.read(member));delimiter='\t' if text[:10000].count('\t')>=text[:10000].count(',') else ','
            rows=csv.reader(io.StringIO(text),delimiter=delimiter);mapping=v32.column_map(next(rows,[]))
            if not mapping:continue
            for row in rows:
                element=v32.element_name(v32.get(row,mapping['element']))
                if not element.endswith('TextBlock'):continue
                context=v32.get(row,mapping.get('context'))
                if context!='CurrentYearDuration':continue
                value=v32.get(row,mapping['value'])
                if not value:continue
                result.append({'element':element,'context':context,'html':value,'file':member.filename})
    return result

def numeric(s):
    s=s.replace(',','').replace('△','-').replace('▲','-').replace('−','-').strip()
    if not re.fullmatch(r'-?\d+(?:\.\d+)?',s):return None
    try:return Decimal(s)
    except InvalidOperation:return None

# Consolidated statements only. Use full element names, not company names.
US_STATEMENTS={
 'revenue_oku':('ConsolidatedStatementOfIncomeUSGAAPTextBlock',('売上高','売上収益','純売上高')),
 'operating_profit_oku':('ConsolidatedStatementOfIncomeUSGAAPTextBlock',('営業利益','営業損益')),
 'prior_revenue_oku':('ConsolidatedStatementOfIncomeUSGAAPTextBlock',('売上高','売上収益','純売上高')),
 'operating_cf_oku':('ConsolidatedStatementOfCashFlowsUSGAAPTextBlock',('営業活動によるキャッシュ・フロー','営業活動によるキャッシュフロー')),
}

def table_candidates(html,labels,prior=False):
    """Return candidates only from simple, explicitly year-ordered 2-period tables.
    Multi-column tables (percentages/notes), spanning cells, and ambiguous rows are rejected.
    """
    parser=TableReader();parser.feed(html)
    candidates=[];rejections=[]
    for ti,table in enumerate(parser.tables):
        headers=' '.join(c['text'] for row in table[:8] for c in row)
        if not (re.search(r'202[0-9]',headers) or ('前連結' in headers and '当連結' in headers)):
            rejections.append('year headings absent');continue
        if not ('百万円' in html or '千円' in html or '円' in html):
            rejections.append('unit missing');continue
        if '百万円' in html:multiplier=Decimal(1000000)
        elif '千円' in html:multiplier=Decimal(1000)
        else:multiplier=Decimal(1)
        for ri,row in enumerate(table):
            if not row:continue
            label=row[0]['text']
            if not any(label==x or label.startswith(x+'（') or label.startswith(x+'(') for x in labels):continue
            if any(c['colspan']!=1 or c['rowspan']!=1 for c in row):rejections.append('merged cells');continue
            # only one label cell and two numeric cells, in prior/current order
            if len(row)!=3:rejections.append('row not exactly two fiscal numeric columns');continue
            left,right=numeric(row[1]['text']),numeric(row[2]['text'])
            if left is None or right is None:rejections.append('non numeric columns');continue
            value=left if prior else right
            candidates.append({'value_jpy':str(value*multiplier),'table_index':ti,'row_index':ri,'label':label,'unit_multiplier':str(multiplier),'row':[c['text'] for c in row]})
    return candidates,rejections[:10]

def us_gaap_extract(blocks):
    values={};provenance={};issues=[]
    for metric,(element,labels) in US_STATEMENTS.items():
        matches=[b for b in blocks if b['element']==element]
        candidates=[];reasons=[]
        for b in matches:
            rows,rejected=table_candidates(b['html'],labels,metric=='prior_revenue_oku')
            for r in rows:candidates.append({**r,'element':element,'file':b['file']})
            reasons+=rejected
        distinct={c['value_jpy'] for c in candidates}
        if len(distinct)==1:
            amount=Decimal(next(iter(distinct)))/Decimal(100000000)
            values[metric]=str(amount)
            provenance[metric]={'method':'us_gaap_structured_table','verification':'pending','candidates':candidates}
        else:
            values[metric]=None
            provenance[metric]={'method':'us_gaap_table_unresolved','verification':'blocked','candidate_count':len(candidates),'reasons':reasons[:10]}
            issues.append(f'{metric}: structured table not uniquely extractable')
    return values,provenance,issues

# Tag-specific ranking is GAAP-dependent; this is a reusable rule, not a ticker override.
ASSET_PRIORITY={
 'IFRS':[['AssetsIFRS','TotalAssetsIFRS'],['TotalAssetsIFRSSummaryOfBusinessResults'],['Assets','TotalAssets']],
 'JP_GAAP':[['Assets','TotalAssets'],['TotalAssetsIFRSSummaryOfBusinessResults']],
}
EQUITY_PRIORITY={
 'IFRS':[['EquityAttributableToOwnersOfParentIFRS','EquityAttributableToOwnersOfParent'],['EquityAttributableToOwnersOfParentIFRSSummaryOfBusinessResults'],['EquityIFRS','Equity']],
 'JP_GAAP':[['NetAssets','NetAssetsSummaryOfBusinessResults'],['Equity','EquityIFRS']],
}

def choose_ranked(facts,tiers):
    for tier,tagset in enumerate(tiers):
        hits=[]
        for f in facts:
            if f['element'] not in tagset or f['context']!='CurrentYearInstant' or f['unit'].split(':')[-1]!='JPY':continue
            n=numeric(f['value'])
            if n is not None:hits.append((n,f))
        if not hits:continue
        distinct={n for n,_ in hits}
        if len(distinct)!=1:return None,{'status':'conflict','tier':tier,'values':[str(n) for n in sorted(distinct)],'sources':hits[:8]}
        return next(iter(distinct)),{'status':'selected','tier':tier,'sources':[f for _,f in hits[:8]]}
    return None,{'status':'missing'}

def ranked_equity_ratio(facts,gaap):
    standard=gaap['standard']
    if standard not in ASSET_PRIORITY:return None,{'status':'unsupported_gaap'}
    assets,ap=choose_ranked(facts,ASSET_PRIORITY[standard]);equity,ep=choose_ranked(facts,EQUITY_PRIORITY[standard])
    evidence={'assets':ap,'equity':ep,'formula':('parent_attributable_equity / total_assets' if standard=='IFRS' else 'net_assets / total_assets')}
    if assets is None or equity is None:return None,{'status':'unresolved',**evidence}
    if assets<=0 or equity<0 or equity>assets:return None,{'status':'invalid_amounts',**evidence}
    return str((equity/assets*100).quantize(Decimal('0.01'))),{'status':'calculated_unverified','assets_jpy':str(assets),'equity_jpy':str(equity),**evidence}

def crosscheck(values,provenance,gaap):
    checks=[]
    if gaap['standard']=='UNKNOWN':checks.append({'check':'accounting_standard','status':'BLOCK','detail':'unknown'})
    for metric in v32.TAGS:
        if values.get(metric) is None:checks.append({'check':metric,'status':'BLOCK','detail':'missing or ambiguous'})
        else:checks.append({'check':metric,'status':'PENDING','detail':'original filing not independently reconciled'})
    try:
        revenue=Decimal(values['revenue_oku']) if values.get('revenue_oku') else None
        op=Decimal(values['operating_profit_oku']) if values.get('operating_profit_oku') else None
        ratio=Decimal(values['equity_ratio_pct']) if values.get('equity_ratio_pct') else None
        if revenue is not None and revenue<=0:checks.append({'check':'revenue_positive','status':'BLOCK'})
        if ratio is not None and not 0<=ratio<=100:checks.append({'check':'equity_ratio_range','status':'BLOCK'})
        if op is not None and revenue is not None and abs(op)>revenue*3:checks.append({'check':'operating_profit_outlier','status':'BLOCK'})
    except (InvalidOperation,KeyError):checks.append({'check':'numeric_validation','status':'BLOCK'})
    return {'ready_for_publication':False,'status':'BLOCKED','checks':checks,'reason':'independent original-filing reconciliation and approval required'}

def review(blob,filing):
    base=v34.review(blob,filing)
    gaap=base['accounting_standard'];values=dict(base['selected_values']);provenance=dict(base['provenance']);issues=[]
    facts,_,_=v34.extract_csv(blob)
    if gaap['standard']=='US_GAAP':
        blocks=textblock_records(blob)
        extracted,prov,issues=us_gaap_extract(blocks)
        values.update(extracted);provenance.update(prov)
        # US GAAP balance-sheet and CF fields stay blocked if the structure is not validated.
    else:
        ratio,detail=ranked_equity_ratio(facts,gaap)
        if ratio is not None:
            values['equity_ratio_pct']=ratio
            provenance['equity_ratio_pct']={'method':'gaap_ranked_equity_formula','verification':'pending','detail':detail}
        elif values.get('equity_ratio_pct') is None:
            provenance['equity_ratio_pct']={'method':'gaap_ranked_equity_unresolved','verification':'blocked','detail':detail}
        else:
            # Existing v3.4 ratio is not replaced if new rule cannot resolve it; flag discrepancy.
            issues.append('ranked equity formula unresolved; retained v3.4 unverified candidate')
    base['selected_values']=values;base['provenance']=provenance
    base['derived_values']=v33.calculate(values)
    base['extraction_issues']=issues
    base['quality_gate']=crosscheck(values,provenance,gaap)
    base['publication_status']='UNVERIFIED'
    base['pipeline_version']='3.5'
    return base

def main():
    p=argparse.ArgumentParser();p.add_argument('--discovery',default='discovery-v31.json');p.add_argument('--output',default='edinet-v35-output');p.add_argument('--limit',type=int,default=1);p.add_argument('--delay',type=float,default=3)
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
            (out/f'{ticker}-{docid}-v35.json').write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
            r.update(status='diagnosed',accounting_standard=data['accounting_standard']['standard'],gaap_confidence=data['accounting_standard']['confidence'],**data['selected_values'],**data['derived_values'],quality_status=data['quality_gate']['status'])
        except Exception as exc:r['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
        summary.append(r);print(ticker,r['status'],r.get('accounting_standard',''),flush=True)
        if i+1<len(targets):time.sleep(a.delay)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['ticker','company','docID','status','accounting_standard','gaap_confidence',*v32.TAGS.keys(),'operating_margin_pct','revenue_growth_pct','operating_cf_to_revenue_pct','quality_status','publication_status','error']
    with (out/'company-candidates-v35.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r.get(k) for k in cols} for r in summary)
    (out/'README.txt').write_text('v3.5 REVIEW ONLY. All data UNVERIFIED and publication BLOCKED. Check source filing and provenance before publication.\n',encoding='utf-8')
    if any(r['status']=='error' for r in summary):raise RuntimeError('Some downloads failed; inspect artifacts')
if __name__=='__main__':main()
