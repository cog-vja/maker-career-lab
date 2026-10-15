#!/usr/bin/env python3
"""v3.8: EDINET original XBRL numeric-fact investigation; no automatic publication.

For US GAAP filings, fetch type=1, enumerate instance facts and contexts, and
identify candidate facts by taxonomy-local-name families. Never assume that
the presence of a tag proves a financial metric is comparable.
"""
import argparse, csv, io, json, os, re, time, urllib.parse, urllib.request, zipfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree as ET
import edinet_v32 as v32
import edinet_v36 as v36

XBRLI='http://www.xbrl.org/2003/instance'
XSI='http://www.w3.org/2001/XMLSchema-instance'
METRIC_PATTERNS={
 'revenue_oku': [r'^(?:NetSales|SalesRevenue|Revenues|Revenue|NetSalesRevenue|Sales|RevenueFromContractWithCustomerExcludingAssessedTax)$'],
 'operating_profit_oku':[r'^(?:OperatingIncomeLoss|OperatingProfitLoss|OperatingIncome|IncomeLossFromOperations)$'],
 'operating_cf_oku':[r'^(?:NetCashProvidedByUsedInOperatingActivities|NetCashProvidedByUsedInOperatingActivitiesContinuingOperations)$'],
 'assets':[r'^(?:Assets|TotalAssets)$'],
 'equity':[r'^(?:StockholdersEquity|StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest|EquityAttributableToOwnersOfParent|ShareholdersEquity)$']
}
def local(tag):return tag.rsplit('}',1)[-1].rsplit(':',1)[-1]
def match_metric(name):
    return [metric for metric,patterns in METRIC_PATTERNS.items() if any(re.fullmatch(p,name,re.I) for p in patterns)]
def safe_decimal(s):
    try:
        d=Decimal((s or '').strip().replace(',',''))
        return d if d.is_finite() else None
    except InvalidOperation:return None
def inspect_instance(raw,source,max_facts=250000):
    """Stream XML facts; preserve only candidate metadata, not filing text."""
    if len(raw)>30_000_000:raise ValueError('instance exceeds 30MB')
    root=ET.fromstring(raw)
    contexts={};units={}
    for e in root:
        tag=local(e.tag)
        if tag=='context':
            cid=e.get('id','')
            period=e.find('{%s}period'%XBRLI)
            if period is None:continue
            start=period.findtext('{%s}startDate'%XBRLI)
            end=period.findtext('{%s}endDate'%XBRLI)
            instant=period.findtext('{%s}instant'%XBRLI)
            has_segment=any(local(x.tag) in ('segment','scenario','explicitMember','typedMember') for x in e.iter())
            contexts[cid]={'start':start,'end':end,'instant':instant,'dimensional':has_segment}
        elif tag=='unit':
            units[e.get('id','')]=' '.join((x.text or '').strip() for x in e.iter() if local(x.tag)=='measure')
    candidates=[]; counts=Counter(); total=0
    for e in root:
        total+=1
        if total>max_facts:raise ValueError('too many root elements')
        name=local(e.tag)
        metrics=match_metric(name)
        if not metrics:continue
        ctx=e.get('contextRef',''); unit=e.get('unitRef','')
        value=safe_decimal(e.text)
        if value is None:continue
        namespace=e.tag.split('}',1)[0][1:] if e.tag.startswith('{') else ''
        entry={'element':name,'namespace':namespace,'contextRef':ctx,'context':contexts.get(ctx),
               'unitRef':unit,'unit':units.get(unit,''),'value':str(value),
               'decimals':e.get('decimals'),'source':source,'metrics':metrics}
        candidates.append(entry)
        for metric in metrics:counts[metric]+=1
    return {'source':source,'context_count':len(contexts),'unit_count':len(units),
            'candidate_count':len(candidates),'candidate_metric_counts':dict(counts),
            'candidates':candidates[:1000],'truncated':len(candidates)>1000}
def fetch_original(docid,key):
    if not re.fullmatch(r'[A-Z0-9]{8,16}',docid):raise ValueError('invalid docid')
    url=v32.BASE+docid+'?'+urllib.parse.urlencode({'type':1,'Subscription-Key':key})
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-v3.8'}),timeout=90) as r:
        data=r.read(80_000_001)
    if len(data)>80_000_000 or not zipfile.is_zipfile(io.BytesIO(data)):raise ValueError('type1 invalid/too large')
    return data
def inspect_original(blob):
    results=[]; errors=[]
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        members=[m for m in z.infolist() if m.filename.lower().endswith('.xbrl') and not m.is_dir()]
        # Only actual PublicDoc filing instance(s); skip AuditDoc and unrelated instances.
        public=[m for m in members if '/publicdoc/' in ('/'+m.filename.lower())]
        for m in public[:10]:
            try:
                if m.file_size>30_000_000:raise ValueError('oversized instance')
                results.append(inspect_instance(z.read(m),m.filename))
            except Exception as exc:errors.append({'file':m.filename,'error':type(exc).__name__+': '+str(exc)[:120]})
    return {'instances':results,'errors':errors,'instance_count':len(results),
            'selection_policy':'diagnostic_only_no_automatic_adoption',
            'reconciliation':'PENDING','publication_status':'UNVERIFIED'}
def review(blob,filing,key,inspect_type1=True):
    base=v36.review(blob,filing)
    diagnostic={'accounting_standard':base['accounting_standard']['standard'],
                'source_docID':filing['docID'],'publication_status':'UNVERIFIED'}
    if inspect_type1 and base['accounting_standard']['standard']=='US_GAAP':
        try:diagnostic['original_xbrl']=inspect_original(fetch_original(filing['docID'],key))
        except Exception as exc:diagnostic['original_xbrl_error']=type(exc).__name__+': '+str(exc)[:160]
    else:diagnostic['original_xbrl']={'status':'not_requested_or_not_us_gaap'}
    return base,diagnostic
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--discovery',default='discovery-v31.json')
    p.add_argument('--output',default='edinet-v38-output')
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
            base,diag=review(v32.download(docid,key),filing,key,not a.skip_type1)
            (out/f'{ticker}-{docid}-v38-xbrl.json').write_text(json.dumps(diag,ensure_ascii=False,indent=2),encoding='utf-8')
            r.update(status='diagnosed',accounting_standard=base['accounting_standard']['standard'],
                     quality_status=base['quality_gate']['status'],**base['selected_values'])
            if diag.get('original_xbrl_error') or diag.get('original_xbrl',{}).get('errors'):
                r['xbrl_warning']=diag.get('original_xbrl_error') or str(diag['original_xbrl']['errors'])[:250]
            else:r['xbrl_warning']=''
        except Exception as exc:r['error']=type(exc).__name__+': '+str(exc)[:250]
        summary.append(r);print(ticker,r['status'],flush=True)
        if i+1<len(targets):time.sleep(a.delay)
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['ticker','company','docID','status','accounting_standard','quality_status',*v32.TAGS.keys(),'publication_status','xbrl_warning','error']
    with (out/'company-candidates-v38.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows({k:r.get(k) for k in cols} for r in summary)
    (out/'README.txt').write_text('v3.8 XBRL DIAGNOSTIC ONLY. No US GAAP XBRL candidates automatically adopted. All values UNVERIFIED.\n',encoding='utf-8')
    if any(r['status']=='error' for r in summary):raise RuntimeError('Some filings failed; see diagnostics')
if __name__=='__main__':main()
