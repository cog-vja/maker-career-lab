#!/usr/bin/env python3
"""EDINET v3.6 diagnostic extractor: GAAP-neutral, evidence-first, never auto-publish.
US GAAP tables are parsed with expanded spans, column metadata, and ambiguity blocking.
"""
import argparse,csv,json,os,re,time
from pathlib import Path
from decimal import Decimal
from html.parser import HTMLParser
import edinet_v32 as v32
import edinet_v33 as v33
import edinet_v35 as v35

class GridParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables=[];self.stack=[];self.row=None;self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':self.stack.append([])
        elif tag=='tr' and self.stack:self.row=[]
        elif tag in ('td','th') and self.stack and self.row is not None:
            a=dict(attrs)
            try: cs=min(30,max(1,int(a.get('colspan','1'))));rs=min(100,max(1,int(a.get('rowspan','1'))))
            except ValueError:cs=rs=1
            self.cell={'text':'','colspan':cs,'rowspan':rs,'header':tag=='th'}
        elif tag=='br' and self.cell is not None:self.cell['text']+=' '
    def handle_data(self,data):
        if self.cell is not None:self.cell['text']+=data
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None and self.row is not None:
            self.cell['text']=' '.join(self.cell['text'].split());self.row.append(self.cell);self.cell=None
        elif tag=='tr' and self.row is not None and self.stack:
            if self.row:self.stack[-1].append(self.row)
            self.row=None
        elif tag=='table' and self.stack:
            table=self.stack.pop()
            if table:self.tables.append(table)

def expand(table):
    grid=[];pending={}
    for row in table[:400]:
        out=[];idx=0
        def fill():
            nonlocal idx
            while idx in pending:
                c,left=pending[idx];out.append(c);left-=1
                if left:pending[idx]=(c,left)
                else:del pending[idx]
                idx+=1
        for cell in row:
            fill()
            for _ in range(cell['colspan']):
                out.append(cell)
                if cell['rowspan']>1:pending[idx]=(cell,cell['rowspan']-1)
                idx+=1
        fill()
        grid.append(out[:40])
    return grid

def norm(s):return re.sub(r'[\s\u3000（）()・:：\-‐－]','',s)
def number(s):
    s=s.strip().replace(',','').replace('△','-').replace('▲','-').replace('−','-').replace('－','-')
    if re.fullmatch(r'-?\d+(?:\.\d+)?',s):return Decimal(s)
    return None

def unit_multiplier(html):
    # Unit must be explicit; mixed currencies/units are blocked.
    found=set()
    for unit,m in [('百万円',10**6),('千円',10**3),('億円',10**8)]:
        if unit in html:found.add(m)
    return next(iter(found)) if len(found)==1 else None

def statement_candidates(block,metric):
    labels={
        'revenue_oku':['売上高','売上収益','純売上高'],
        'prior_revenue_oku':['売上高','売上収益','純売上高'],
        'operating_profit_oku':['営業利益','営業損益'],
        'operating_cf_oku':['営業活動によるキャッシュフロー','営業活動によるキャッシュ・フロー'],
        'assets':['資産合計','資産の部合計','総資産'],
        'equity':['株主資本合計','当社株主資本合計','親会社株主持分合計'],
    }[metric]
    parser=GridParser();parser.feed(block['html'])
    mult=unit_multiplier(block['html'])
    found=[];diagnostics=[]
    for ti,raw in enumerate(parser.tables):
        grid=expand(raw)
        # Collect rows with exact financial labels and numbers, without inferring year order blindly.
        for ri,row in enumerate(grid):
            if not row:continue
            label=norm(row[0]['text'])
            if not any(label==norm(x) or label.startswith(norm(x)+'注記') for x in labels):continue
            vals=[];seen=set()
            for ci,c in enumerate(row[1:],1):
                if id(c) in seen:continue
                seen.add(id(c));n=number(c['text'])
                if n is not None:vals.append((ci,n))
            header=' '.join(c['text'] for r in grid[:min(10,ri)] for c in r)
            year_markers=re.findall(r'(?:20\d{2}|第\d+期|前連結|当連結)',header)
            item={'metric':metric,'element':block['element'],'file':block['file'],'table_index':ti,'row_index':ri,
                  'label':row[0]['text'],'numeric_cells':[(i,str(n)) for i,n in vals],
                  'header_excerpt':header[:450],'unit_multiplier':mult,'year_markers':year_markers[:20]}
            diagnostics.append(item)
            # Safe extraction: exactly two monetary cells, clear two-period heading and one explicit unit.
            # Financial statements with percentage columns must be manually reviewed until column typing is proven.
            if mult is None or len(vals)!=2 or len(year_markers)<2:continue
            if vals[0][1]==vals[1][1] and len(year_markers)<2:continue
            chosen=vals[0 if metric=='prior_revenue_oku' else 1][1]
            found.append({**item,'value_jpy':str(chosen*mult),'selection':'two_numeric_columns_prior_current'})
    return found,diagnostics

ELEMENTS={
 'revenue_oku':'ConsolidatedStatementOfIncomeUSGAAPTextBlock',
 'prior_revenue_oku':'ConsolidatedStatementOfIncomeUSGAAPTextBlock',
 'operating_profit_oku':'ConsolidatedStatementOfIncomeUSGAAPTextBlock',
 'operating_cf_oku':'ConsolidatedStatementOfCashFlowsUSGAAPTextBlock',
 'assets':'ConsolidatedBalanceSheetUSGAAPTextBlock',
 'equity':'ConsolidatedBalanceSheetUSGAAPTextBlock',
}

def us_extract(blocks):
    values={};proof={};debug=[]
    for metric,element in ELEMENTS.items():
        candidates=[]
        for b in blocks:
            if b['element']!=element:continue
            got,diag=statement_candidates(b,metric);candidates.extend(got);debug.extend(diag)
        distinct={x['value_jpy'] for x in candidates}
        if len(distinct)==1:
            value=Decimal(next(iter(distinct)))
            values[metric]=value
            proof[metric]={'method':'two_period_us_gaap_table','verification':'PENDING','candidates':candidates}
        else:
            proof[metric]={'method':'us_gaap_ambiguous_or_missing','verification':'BLOCKED','candidate_count':len(candidates),'candidate_values':sorted(distinct)}
    final={}
    for metric in ('revenue_oku','prior_revenue_oku','operating_profit_oku','operating_cf_oku'):
        final[metric]=str(values[metric]/Decimal(10**8)) if metric in values else None
    if 'assets' in values and 'equity' in values and values['assets']>0 and 0<=values['equity']<=values['assets']:
        final['equity_ratio_pct']=str((values['equity']/values['assets']*100).quantize(Decimal('.01')))
        proof['equity_ratio_pct']={'method':'us_gaap_balance_sheet_equity_over_assets','verification':'PENDING','assets':proof['assets'],'equity':proof['equity']}
    else:
        final['equity_ratio_pct']=None
        proof['equity_ratio_pct']={'method':'us_gaap_balance_sheet_unresolved','verification':'BLOCKED','assets':proof['assets'],'equity':proof['equity']}
    return final,proof,debug

def review(blob,filing):
    result=v35.review(blob,filing)
    result['pipeline_version']='3.6'
    if result['accounting_standard']['standard']=='US_GAAP':
        blocks=v35.textblock_records(blob)
        vals,proof,debug=us_extract(blocks)
        result['selected_values'].update(vals)
        result['provenance'].update(proof)
        result['table_diagnostics']=debug[:250]
        result['us_gaap_block_metadata']=[{'element':b['element'],'length':len(b['html']),'file':b['file']} for b in blocks if 'USGAAP' in b['element']]
    result['derived_values']=v33.calculate(result['selected_values'])
    result['quality_gate']=v35.crosscheck(result['selected_values'],result['provenance'],result['accounting_standard'])
    result['quality_gate']['independent_original_filing_verified']=False
    result['publication_status']='UNVERIFIED'
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--discovery',default='discovery-v31.json');p.add_argument('--output',default='edinet-v36-output')
    p.add_argument('--limit',type=int,default=10);p.add_argument('--delay',type=float,default=3)
    a=p.parse_args()
    if not 1<=a.limit<=10 or not 0<=a.delay<=30:p.error('limit must be 1-10; delay 0-30')
    key=os.environ.get('EDINET_API_KEY')
    if not key:raise RuntimeError('EDINET_API_KEY missing')
    targets=[t for t in json.loads(Path(a.discovery).read_text(encoding='utf-8'))['targets'] if t.get('selected')][:a.limit]
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);summary=[]
    for i,t in enumerate(targets):
        filing=t['selected'];ticker=t['ticker'];docid=filing['docID'];r={'ticker':ticker,'company':t['target_name'],'docID':docid,'status':'error','publication_status':'UNVERIFIED'}
        try:
            result=review(v32.download(docid,key),filing)
            (out/f'{ticker}-{docid}-v36.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            r.update(status='diagnosed',accounting_standard=result['accounting_standard']['standard'],gaap_confidence=result['accounting_standard']['confidence'],**result['selected_values'],**result['derived_values'],quality_status=result['quality_gate']['status'])
        except Exception as exc:r['error']=f'{type(exc).__name__}: {str(exc)[:250]}'
        summary.append(r);print(ticker,r['status'],r.get('accounting_standard',''),flush=True)
        if i+1<len(targets):time.sleep(a.delay)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['ticker','company','docID','status','accounting_standard','gaap_confidence',*v32.TAGS.keys(),'operating_margin_pct','revenue_growth_pct','operating_cf_to_revenue_pct','quality_status','publication_status','error']
    with (out/'company-candidates-v36.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r.get(k) for k in cols} for r in summary)
    (out/'README.txt').write_text('v3.6 REVIEW ONLY. All outputs UNVERIFIED; independent filing reconciliation is NOT complete. Do not publish.\n',encoding='utf-8')
    if any(r['status']=='error' for r in summary):raise RuntimeError('Some downloads failed; inspect artifacts')
if __name__=='__main__':main()
