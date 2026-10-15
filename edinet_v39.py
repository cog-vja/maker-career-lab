#!/usr/bin/env python3
"""v3.9: original EDINET HTML + CSV TextBlock consolidated US GAAP diagnostics.
Candidate amounts are never merged into published or selected metrics.
"""
import argparse,csv,html,io,json,os,re,time,zipfile
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path
import edinet_v32 as v32
import edinet_v35 as v35
import edinet_v36 as v36
import edinet_v38 as v38

STATEMENTS={'income':'ConsolidatedStatementOfIncomeUSGAAPTextBlock',
'balance':'ConsolidatedBalanceSheetUSGAAPTextBlock',
'cashflow':'ConsolidatedStatementOfCashFlowsUSGAAPTextBlock'}
METRICS={
'revenue_oku':('income',('売上高','純売上高','売上収益')),
'prior_revenue_oku':('income',('売上高','純売上高','売上収益')),
'operating_profit_oku':('income',('営業利益','営業損益')),
'operating_cf_oku':('cashflow',('営業活動によるキャッシュフロー','営業活動によるキャッシュ・フロー')),
'assets':('balance',('資産合計','資産の部合計','総資産')),
'equity':('balance',('株主資本合計','当社株主資本合計','親会社株主持分合計'))}
def clean(s):return re.sub(r'\s+',' ',html.unescape(s).replace('\u3000',' ')).strip()
def label_key(s):return re.sub(r'[\s\u3000（）()・:：\-‐－]','',clean(s))
def number(s):
 s=clean(s).replace(',','').replace('△','-').replace('▲','-').replace('−','-').replace('－','-')
 if s.startswith('(') and s.endswith(')'):s='-'+s[1:-1]
 return Decimal(s) if re.fullmatch(r'-?\d+(?:\.\d+)?',s) else None
def multiplier(text):
 found=[m for u,m in [('百万円',10**6),('千円',10**3),('億円',10**8)] if u in text]
 return found[0] if len(found)==1 else None
def years(text):return sorted(set(re.findall(r'20\d{2}(?:年|/\d{1,2})?|前連結会計年度|当連結会計年度|前期|当期',text)))
def matches(s,labels):
 k=label_key(s)
 return any(k==label_key(l) or k.startswith(label_key(l)+'注記') for l in labels)
class Tables(HTMLParser):
 def __init__(self):
  super().__init__(convert_charrefs=True)
  self.tables=[];self.table=None;self.row=None;self.cell=None;self.stack=[];self.text=[];self.inline=0
 def handle_starttag(self,tag,attrs):
  if tag.startswith('ix:'):self.inline+=1
  if tag=='table':
   self.stack.append((self.table,self.row,self.cell));self.table=[];self.row=None;self.cell=None
  elif tag=='tr' and self.table is not None:self.row=[]
  elif tag in ('td','th') and self.row is not None:
   a=dict(attrs)
   try:span=(int(a.get('colspan','1')),int(a.get('rowspan','1')))
   except ValueError:span=(0,0)
   self.cell={'text':'','span':span}
 def handle_data(self,data):
  self.text.append(data)
  if self.cell is not None:self.cell['text']+=data
 def handle_endtag(self,tag):
  if tag in ('td','th') and self.cell is not None and self.row is not None:
   self.cell['text']=clean(self.cell['text']);self.row.append(self.cell);self.cell=None
  elif tag=='tr' and self.row is not None and self.table is not None:
   if self.row:self.table.append(self.row)
   self.row=None
  elif tag=='table' and self.stack:
   if self.table:self.tables.append(self.table)
   self.table,self.row,self.cell=self.stack.pop()
def statement_hints(text):
 head=clean(re.sub(r'<[^>]+>',' ',text[:30000]))[:1500]
 return [k for k,p in {'income':r'連結損益計算書|連結損益及び包括利益計算書',
 'balance':r'連結貸借対照表','cashflow':r'連結キャッシュ[・\s]?フロー計算書'}.items() if re.search(p,head)]
def analyze(content,source,hint=None):
 parser=Tables();parser.feed(content)
 visible=' '.join(parser.text);unit=multiplier(visible);periods=years(visible)
 stmts=[hint] if hint else statement_hints(content)
 result={'source':source,'statements':stmts,'table_count':len(parser.tables),
 'inline_xbrl_tag_count':parser.inline,'unit_multiplier':unit,'period_evidence':periods[:12],
 'candidates':{},'rejections':{}}
 for metric,(stmt,labels) in METRICS.items():
  if stmt not in stmts:continue
  found=[];reject=[]
  for ti,table in enumerate(parser.tables):
   # Require two period markers and explicit unit. No guess on ambiguous rows.
   for ri,row in enumerate(table):
    hits=[j for j,c in enumerate(row[:3]) if matches(c['text'],labels)]
    for j in hits:
     if unit is None or len(periods)<2:
      reject.append({'table':ti,'row':ri,'reason':'missing_unit_or_period'});continue
     if any(c['span']!=(1,1) for c in row):
      reject.append({'table':ti,'row':ri,'reason':'merged_cells'});continue
     nums=[number(c['text']) for c in row[j+1:]]
     nums=[n for n in nums if n is not None]
     if len(nums)!=2:
      reject.append({'table':ti,'row':ri,'reason':'not_two_numeric_columns','count':len(nums)});continue
     n=nums[0 if metric=='prior_revenue_oku' else 1]
     found.append({'metric':metric,'value_jpy':str(n*unit),'source':source,
      'table_index':ti,'row_index':ri,'label':row[j]['text'],
      'row_preview':[c['text'][:55] for c in row[:8]],
      'period_rule':'left_prior_right_current_not_yet_verified'})
  result['candidates'][metric]=found[:30];result['rejections'][metric]=reject[:20]
 return result
def inspect(original,blocks):
 output=[];warnings=[]
 for b in blocks:
  for stmt,element in STATEMENTS.items():
   if b['element']==element:
    output.append(analyze(b['html'],'CSV:'+b['file']+':'+element,stmt))
 if original:
  with zipfile.ZipFile(io.BytesIO(original)) as z:
   files=[m for m in z.infolist() if m.filename.lower().endswith(('.htm','.html','.xhtml'))
          and '/publicdoc/' in ('/'+m.filename.lower()) and not m.is_dir()]
   for m in files[:40]:
    if m.file_size>8_000_000:
     warnings.append({'file':m.filename,'reason':'oversized'});continue
    try:
     raw=z.read(m);content=None
     for enc in ('utf-8-sig','cp932','utf-16'):
      try:content=raw.decode(enc);break
      except UnicodeError:continue
     if content is None:raise ValueError('encoding')
     d=analyze(content,'HTML:'+m.filename)
     if d['statements'] or d['table_count'] or d['inline_xbrl_tag_count']:output.append(d)
    except Exception as exc:warnings.append({'file':m.filename,'reason':type(exc).__name__})
 return output,warnings
def propose(diagnostics):
 output={}
 for metric in METRICS:
  evidence=[c for d in diagnostics for c in d['candidates'].get(metric,[])]
  distinct=sorted({c['value_jpy'] for c in evidence},key=Decimal)
  output[metric]={'status':'CANDIDATE_UNVERIFIED' if len(distinct)==1 else ('CONFLICT' if distinct else 'NOT_FOUND'),
   'distinct_jpy_values':distinct[:20],'candidate_count':len(evidence),
   'evidence':evidence[:20],'approved_for_publication':False}
 a=output['assets']['distinct_jpy_values'];e=output['equity']['distinct_jpy_values']
 if len(a)==len(e)==1 and Decimal(a[0])>0 and 0<=Decimal(e[0])<=Decimal(a[0]):
  output['equity_ratio_pct']={'status':'CANDIDATE_UNVERIFIED',
   'value':str((Decimal(e[0])/Decimal(a[0])*100).quantize(Decimal('.01'))),
   'approved_for_publication':False}
 else:output['equity_ratio_pct']={'status':'NOT_RESOLVED','approved_for_publication':False}
 return output
def main():
 p=argparse.ArgumentParser()
 p.add_argument('--discovery',default='discovery-v31.json')
 p.add_argument('--output',default='edinet-v39-output')
 p.add_argument('--limit',type=int,default=10)
 p.add_argument('--delay',type=float,default=3)
 p.add_argument('--skip-type1',action='store_true')
 a=p.parse_args()
 if not 1<=a.limit<=10 or not 0<=a.delay<=30:p.error('limit 1-10; delay 0-30')
 key=os.environ.get('EDINET_API_KEY')
 if not key:raise RuntimeError('EDINET_API_KEY missing')
 targets=[t for t in json.loads(Path(a.discovery).read_text(encoding='utf-8'))['targets'] if t.get('selected')][:a.limit]
 out=Path(a.output);out.mkdir(parents=True,exist_ok=True);summary=[]
 for i,t in enumerate(targets):
  filing=t['selected'];docid=filing['docID'];ticker=t['ticker']
  r={'ticker':ticker,'company':t['target_name'],'docID':docid,'status':'error','publication_status':'UNVERIFIED'}
  try:
   blob=v32.download(docid,key);base=v36.review(blob,filing)
   diag={'source_docID':docid,'accounting_standard':base['accounting_standard']['standard'],
    'selected_values_v36':base['selected_values'],'publication_status':'UNVERIFIED',
    'quality_status':'BLOCKED','provenance_policy':'proposals_not_merged'}
   if base['accounting_standard']['standard']=='US_GAAP':
    original=None
    if not a.skip_type1:
     try:original=v38.fetch_original(docid,key)
     except Exception as exc:diag['type1_error']=type(exc).__name__+': '+str(exc)[:120]
    d,w=inspect(original,v35.textblock_records(blob))
    diag.update(source_diagnostics=d,warnings=w,proposals=propose(d))
    r['candidate_count']=sum(v['candidate_count'] for v in diag['proposals'].values() if 'candidate_count' in v)
   else:diag['source_diagnostics']=[];diag['proposals']={}
   (out/f'{ticker}-{docid}-v39.json').write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding='utf-8')
   r.update(status='diagnosed',accounting_standard=base['accounting_standard']['standard'],
    quality_status='BLOCKED',**base['selected_values'])
  except Exception as exc:r['error']=type(exc).__name__+': '+str(exc)[:200]
  summary.append(r);print(ticker,r['status'],flush=True)
  if i+1<len(targets):time.sleep(a.delay)
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 cols=['ticker','company','docID','status','accounting_standard','quality_status',*v32.TAGS.keys(),
 'candidate_count','publication_status','error']
 with (out/'company-candidates-v39.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r.get(k) for k in cols} for r in summary)
 (out/'README.txt').write_text('v3.9 ORIGINAL HTML + CSV TEXTBLOCK REVIEW ONLY. Proposals never adopted; all data UNVERIFIED and BLOCKED.\n',encoding='utf-8')
 if any(r['status']=='error' for r in summary):raise RuntimeError('Some filings failed; see summary')
if __name__=='__main__':main()
