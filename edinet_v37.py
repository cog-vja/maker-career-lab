#!/usr/bin/env python3
"""EDINET v3.7: source-structure diagnostics for US GAAP, review-only.
No company-specific rules, no automatic publishing, no full raw TextBlock dumps.
"""
import argparse, csv, html, io, json, os, re, time, zipfile, urllib.parse, urllib.request
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
import edinet_v32 as v32
import edinet_v35 as v35
import edinet_v36 as v36

class Shape(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags=Counter(); self.tables=0; self.rows=0; self.cells=0
    def handle_starttag(self, tag, attrs):
        self.tags[tag]+=1
        if tag=='table':self.tables+=1
        if tag=='tr':self.rows+=1
        if tag in ('td','th'):self.cells+=1

def structural_view(value):
    """Compare original, once-unescaped, twice-unescaped without persisting contents."""
    views=[]; current=value
    for depth in range(3):
        shape=Shape()
        try:shape.feed(current)
        except Exception as exc: parse_error=type(exc).__name__
        else:parse_error=None
        grid=v36.GridParser()
        try:grid.feed(current); parsed=len(grid.tables)
        except Exception:parsed=0
        views.append({'unescape_depth':depth,'length':len(current),
            'literal_table_tags':len(re.findall(r'<\s*table\b',current,re.I)),
            'escaped_table_tags':len(re.findall(r'&lt;\s*table\b',current,re.I)),
            'table_tags':shape.tables,'tr_tags':shape.rows,'cell_tags':shape.cells,
            'grid_tables':parsed,'parse_error':parse_error,
            'contains_xml_declaration':'<?xml' in current[:300],
            'contains_xbrl_tags':bool(re.search(r'<(?:ix:|xbrli:|xbrl)',current,re.I))})
        nxt=html.unescape(current)
        if nxt==current:break
        current=nxt
    return views

def csv_inspection(blob):
    output={'zip_entry_count':0,'csv_entries':[],'textblocks':[],'issues':[]}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=z.infolist();output['zip_entry_count']=len(members)
        for m in members:
            if m.is_dir() or not m.filename.lower().endswith('.csv'):continue
            if m.file_size>50_000_000:output['issues'].append('oversized_csv_skipped');continue
            raw=z.read(m);text,encoding=v32.decode(raw)
            delimiter='\t' if text[:10000].count('\t')>=text[:10000].count(',') else ','
            rows=csv.reader(io.StringIO(text),delimiter=delimiter)
            mapping=v32.column_map(next(rows,[]))
            info={'file':m.filename,'encoding':encoding,'delimiter':'TAB' if delimiter=='\t' else 'COMMA',
                  'mapping':mapping,'rows':0,'textblock_rows':0,'context_counts':{},'element_suffix_counts':{}}
            contexts=Counter();suffixes=Counter()
            if mapping:
                for row in rows:
                    info['rows']+=1
                    element=v32.element_name(v32.get(row,mapping['element']))
                    if not element.endswith('TextBlock'):continue
                    info['textblock_rows']+=1
                    context=v32.get(row,mapping.get('context'));contexts[context]+=1
                    suffixes['USGAAP' if 'USGAAP' in element else 'OTHER']+=1
                    if 'USGAAP' not in element:continue
                    value=v32.get(row,mapping['value'])
                    output['textblocks'].append({'file':m.filename,'element':element,'context':context,
                        'length':len(value),'structure':structural_view(value),
                        'year_token_count':len(re.findall(r'20\d{2}|第\d+期|前連結|当連結',value)),
                        'unit_markers':[u for u in ('百万円','千円','億円') if u in value],
                        'financial_label_presence':{label:label in value for label in ('売上高','営業利益','営業活動によるキャッシュ・フロー','資産合計','株主資本')},
                        'current_duration':context=='CurrentYearDuration'})
            info['context_counts']=dict(contexts.most_common(12));info['element_suffix_counts']=dict(suffixes)
            output['csv_entries'].append(info)
    return output

def original_package_structure(docid,key):
    """Optional type=1 package inventory; never stores original content or key."""
    if not re.fullmatch(r'[A-Z0-9]{8,16}',docid):raise ValueError('Invalid docID')
    url=v32.BASE+docid+'?'+urllib.parse.urlencode({'type':1,'Subscription-Key':key})
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-v3.7-diagnostic'}),timeout=90) as r:
        data=r.read(80_000_001)
    if len(data)>80_000_000:raise ValueError('type1 ZIP exceeds 80 MB cap')
    if not zipfile.is_zipfile(io.BytesIO(data)):raise ValueError('type1 response not ZIP')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        entries=z.infolist()
        return {'entry_count':len(entries),'file_types':dict(Counter(Path(m.filename).suffix.lower() for m in entries if not m.is_dir())),
                'candidate_xbrl_files':[{'path':m.filename,'bytes':m.file_size} for m in entries if not m.is_dir() and Path(m.filename).suffix.lower() in ('.xbrl','.xml','.htm','.html')][:120]}

def review(blob,filing,include_type1=False,key=None):
    baseline=v36.review(blob,filing)
    diagnostics=csv_inspection(blob)
    diagnostics['baseline_us_gaap_block_count']=len(baseline.get('us_gaap_block_metadata',[]))
    diagnostics['baseline_table_diagnostic_count']=len(baseline.get('table_diagnostics',[]))
    diagnostics['baseline_accounting_standard']=baseline['accounting_standard']['standard']
    if include_type1:
        try:diagnostics['original_type1_package']=original_package_structure(filing['docID'],key)
        except Exception as exc:diagnostics['original_type1_error']=type(exc).__name__+': '+str(exc)[:120]
    return baseline,diagnostics

def main():
    p=argparse.ArgumentParser();p.add_argument('--discovery',default='discovery-v31.json');p.add_argument('--output',default='edinet-v37-output')
    p.add_argument('--limit',type=int,default=10);p.add_argument('--delay',type=float,default=3)
    p.add_argument('--inspect-type1',action='store_true',help='Inventory type=1 original ZIP for US GAAP filings (additional API call)')
    a=p.parse_args()
    if not 1<=a.limit<=10 or not 0<=a.delay<=30:p.error('limit 1-10, delay 0-30')
    key=os.environ.get('EDINET_API_KEY')
    if not key:raise RuntimeError('EDINET_API_KEY missing')
    targets=[t for t in json.loads(Path(a.discovery).read_text(encoding='utf-8'))['targets'] if t.get('selected')][:a.limit]
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True);summary=[]
    for i,t in enumerate(targets):
        filing=t['selected'];ticker=t['ticker'];docid=filing['docID']
        record={'ticker':ticker,'company':t['target_name'],'docID':docid,'status':'error','publication_status':'UNVERIFIED'}
        try:
            blob=v32.download(docid,key)
            baseline,diag=review(blob,filing)
            if a.inspect_type1 and baseline['accounting_standard']['standard']=='US_GAAP':
                try:diag['original_type1_package']=original_package_structure(docid,key)
                except Exception as exc:diag['original_type1_error']=type(exc).__name__+': '+str(exc)[:120]
            (out/f'{ticker}-{docid}-v37-structure.json').write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding='utf-8')
            record.update(status='diagnosed',accounting_standard=baseline['accounting_standard']['standard'],
                quality_status=baseline['quality_gate']['status'],textblock_count=len(diag['textblocks']),
                **baseline['selected_values'])
        except Exception as exc:record['error']=type(exc).__name__+': '+str(exc)[:200]
        summary.append(record);print(ticker,record['status'],flush=True)
        if i+1<len(targets):time.sleep(a.delay)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'company-candidates-v37.csv').open('w',encoding='utf-8-sig',newline='') as f:
        columns=['ticker','company','docID','status','accounting_standard','quality_status',*v32.TAGS.keys(),'publication_status','textblock_count','error']
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader();writer.writerows({k:r.get(k) for k in columns} for r in summary)
    (out/'README.txt').write_text('v3.7 STRUCTURAL DIAGNOSTICS ONLY. All values UNVERIFIED. No raw TextBlocks saved. No auto-publication.\n',encoding='utf-8')
    if any(x['status']=='error' for x in summary):raise RuntimeError('Some filings failed; inspect uploaded diagnostics')
if __name__=='__main__':main()
