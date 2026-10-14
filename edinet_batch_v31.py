#!/usr/bin/env python3
"""v3.1 EDINET annual report discovery + unapproved extraction; stdlib only.
No changes to company-data.js. Outputs are GitHub Actions artifacts only.
"""
import argparse, csv, datetime as dt, io, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request, zipfile
from pathlib import Path
from edinet_pipeline import extract_metrics, FIELDS

API='https://api.edinet-fsa.go.jp/api/v2/'
# Security codes identify listed issuer; check legal entity and EDINET code during review.
TARGETS={
 '6857':'アドバンテスト','8035':'東京エレクトロン','6146':'ディスコ',
 '7735':'SCREENホールディングス','6920':'レーザーテック',
 '6861':'キーエンス','6954':'ファナック','6506':'安川電機',
 '6645':'オムロン','6841':'横河電機'
}

def call(path, params, key, *, binary=False):
    query=urllib.parse.urlencode({**params,'Subscription-Key':key})
    url=API+path+'?'+query
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MakerCareerLab-Research/3.1'}),timeout=45) as r:
            blob=r.read()
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'EDINET HTTP error {exc.code} at {path}') from None
    except urllib.error.URLError as exc:
        raise RuntimeError(f'EDINET network error at {path}: {type(exc.reason).__name__}') from None
    if binary:
        if not blob.startswith(b'PK'):
            raise RuntimeError(f'EDINET returned non-ZIP content for {path}')
        return blob
    try: data=json.loads(blob)
    except (ValueError,UnicodeError): raise RuntimeError(f'EDINET returned invalid JSON for {path}') from None
    if str(data.get('metadata',{}).get('status'))!='200':
        raise RuntimeError(f'EDINET response not successful for {path} (status={data.get("metadata",{}).get("status")})')
    return data

def annual(doc):
    return str(doc.get('docTypeCode',''))=='120' and str(doc.get('csvFlag',''))=='1' and str(doc.get('withdrawalStatus','0')) in ('0','')

def match(doc):
    code=re.sub(r'\D','',str(doc.get('secCode') or ''))
    # EDINET secCode is often 5 digits, ending in zero.
    if len(code)==5 and code.endswith('0'): code=code[:4]
    return code if code in TARGETS else None

def run(days, delay, output, max_docs):
    key=os.environ.get('EDINET_API_KEY','')
    if not key: raise RuntimeError('GitHub Secret EDINET_API_KEY がありません')
    if not 1<=days<=200: raise ValueError('days must be between 1 and 200')
    if not 0<=max_docs<=10: raise ValueError('max-docs must be 0..10')
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    candidates={}; issues=[]; days_checked=0
    for offset in range(days):
        day=today-dt.timedelta(days=offset)
        try: payload=call('documents.json',{'date':day.isoformat(),'type':2},key)
        except RuntimeError as exc:
            issues.append({'date':day.isoformat(),'error':str(exc)}); continue
        days_checked+=1
        for doc in payload.get('results',[]):
            ticker=match(doc)
            if ticker and annual(doc) and doc.get('docID'):
                candidates.setdefault(ticker,[]).append({k:doc.get(k) for k in (
                    'docID','edinetCode','secCode','filerName','docDescription','docTypeCode',
                    'submitDateTime','periodStart','periodEnd','csvFlag','withdrawalStatus')})
        if offset+1<days: time.sleep(delay)
    selected={}
    for ticker, docs in candidates.items():
        docs.sort(key=lambda x:(x.get('periodEnd') or '',x.get('submitDateTime') or ''),reverse=True)
        selected[ticker]=docs[0]
    discovery={'status':'unverified','checked_days':days_checked,'requested_days':days,
               'found_count':len(selected),'target_count':len(TARGETS),'targets':[],
               'scan_errors':issues,'notice':'EDINET書類検索結果。訂正書類・対象会社・決算期は人手で要確認。'}
    for ticker,name in TARGETS.items():
        discovery['targets'].append({'ticker':ticker,'target_name':name,
             'selected':selected.get(ticker),'all_annual_reports':candidates.get(ticker,[])})
    (out/'discovery.json').write_text(json.dumps(discovery,ensure_ascii=False,indent=2),encoding='utf-8')
    extracted=[]; review_dir=out/'reviews';review_dir.mkdir(exist_ok=True)
    for idx,(ticker,doc) in enumerate(selected.items()):
        if idx>=max_docs: break
        docid=doc['docID']; row={k:'' for k in FIELDS}
        row.update(company_id=doc.get('edinetCode') or '',company_name=doc.get('filerName') or TARGETS[ticker],
                   edinet_code=doc.get('edinetCode') or '',fiscal_period=doc.get('periodEnd') or '',
                   source_document_id=docid,source_url='https://disclosure2.edinet-fsa.go.jp/',
                   scope='連結（未照合）',salary_scope='提出会社単体（未照合）',review_status='draft')
        try:
            blob=call('documents/'+urllib.parse.quote(docid,safe=''),{'type':5},key,binary=True)
            values,trace=extract_metrics(blob);row.update(values)
            review={'ticker':ticker,'filing':doc,'extraction_trace':trace,'status':'requires_manual_verification',
                    'warnings':['訂正報告書の有無を確認','会計基準・連結/単体・財務指標定義・前年値・給与範囲を原本照合',
                                '自己資本比率は自動採用しない','公開前に人手で承認する']}
        except (RuntimeError,ValueError,zipfile.BadZipFile) as exc:
            review={'ticker':ticker,'filing':doc,'error':str(exc),'status':'extraction_failed'}
        extracted.append(row)
        (review_dir/f'{ticker}-{docid}.json').write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding='utf-8')
        if idx+1<len(selected) and idx+1<max_docs: time.sleep(delay)
    with (out/'company-candidates.csv').open('w',newline='',encoding='utf-8-sig') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS);writer.writeheader();writer.writerows(extracted)
    lines=['# v3.1 検証結果','',f'- 対象企業：{len(TARGETS)}社',f'- 検索日数：{days_checked}/{days}日',
           f'- 有価証券報告書を検出：{len(selected)}社',f'- 抽出を試行：{len(extracted)}社',
           f'- 日次APIエラー：{len(issues)}件','','**候補は未承認で、サイトに公開していません。**',
           '','## 企業別の状況','']
    for ticker,name in TARGETS.items():
        doc=selected.get(ticker)
        lines.append(f'- {name}（{ticker}）：'+(f'{doc["docID"]}／{doc.get("periodEnd") or "期末不明"}' if doc else '対象期間内に有報が見つかりません'))
    (out/'SUMMARY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(f'EDINET batch finished: days={days_checked}/{days}, filings={len(selected)}/{len(TARGETS)}, extraction_attempts={len(extracted)}, errors={len(issues)}')
    print('Review artifacts only; company-data.js was NOT changed.')
    if days_checked==0: raise RuntimeError('All daily document requests failed. Check discovery.json in artifacts.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=150)
    p.add_argument('--delay',type=float,default=2.5);p.add_argument('--output',default='edinet-review-output')
    p.add_argument('--max-docs',type=int,default=10);args=p.parse_args()
    try:run(args.days,args.delay,args.output,args.max_docs)
    except (RuntimeError,ValueError) as exc:
        print('ERROR: '+str(exc),file=sys.stderr);sys.exit(1)
