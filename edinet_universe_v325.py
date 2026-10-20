#!/usr/bin/env python3
"""Create manufacturing candidate CSV from the FSA's official EDINET filer code list.
Unlike JPX's market download, the FSA dataset is the permitted public-data source.
Actual current CSV is downloaded/generated at GitHub Actions runtime, not fabricated.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import zipfile
from expand_manufacturers_v325 import MFG,normalize_ticker

SOURCE='https://disclosure2dl.edinet-fsa.go.jp/searchdocument/codelist/Edinetcode.zip'
class FilerListError(ValueError):pass

def fetch():
    for n in range(3):
        try:
            req=urllib.request.Request(SOURCE,headers={'User-Agent':'MakerCareerLab-v325-open-data-review'})
            with urllib.request.urlopen(req,timeout=65) as r:content=r.read(15_000_001)
            if len(content)>15_000_000 or not zipfile.is_zipfile(io.BytesIO(content)):
                raise FilerListError('FSA EDINET filer code list is not a valid ZIP')
            return content
        except (urllib.error.URLError,TimeoutError):
            if n==2:raise FilerListError('FSA code-list download unavailable') from None
            time.sleep(3*(n+1))
    raise FilerListError('EDINET download exhausted')

def parse(raw):
    if not zipfile.is_zipfile(io.BytesIO(raw)):raise FilerListError('not zip')
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        files=[x for x in z.namelist() if x.lower().endswith('.csv')]
        if len(files)!=1:raise FilerListError('EDINET code list must have exactly one CSV')
        content=z.read(files[0])
        if len(content)>30_000_000:raise FilerListError('oversized CSV')
    # Official EDINET code list is CSV in CP932 / Shift_JIS (first row is metadata).
    data=content.decode('cp932').lstrip('\ufeff')
    lines=data.splitlines()
    header_row=next((i for i,r in enumerate(lines[:15]) if ('証券コード' in r and '提出者業種' in r and '上場区分' in r)),None)
    if header_row is None:raise FilerListError('EDINET CSV header changed')
    rd=csv.DictReader(io.StringIO('\n'.join(lines[header_row:])))
    result=[];seen={};bad=[];listing_values=set()
    for line,r in enumerate(rd,header_row+2):
        row={re.sub(r'[\s\u3000]','',str(k or '').replace('ＥＤＩＮＥＴ','EDINET')):str(v or '').strip() for k,v in r.items() if k}
        industry=row.get('提出者業種','')
        if industry not in MFG:continue
        listing=row.get('上場区分','');listing_values.add(listing)
        # EDINET list marks non-listed as 非上場; do not use them even with stale sec code.
        if not (listing == '1' or (listing.startswith('上場') and not any(x in listing for x in ('廃止','予定','解除')))):
            continue
        code=row.get('証券コード','').upper()
        if len(code)==5 and code.endswith('0'):code=code[:4]
        try:code=normalize_ticker(code)
        except ValueError:
            bad.append({'line':line,'code':code,'reason':'invalid securities code'});continue
        name=row.get('提出者名','')
        edcode=row.get('EDINETコード','')
        if not name or not re.fullmatch(r'E\d{5}',edcode):
            bad.append({'line':line,'code':code,'reason':'missing name or edinet code'});continue
        row={'コード':code,'銘柄名':name,'33業種区分':industry,'市場・商品区分':listing,'EDINETコード':edcode}
        if code in seen:
            if seen[code]['EDINETコード']!=edcode:
                bad.append({'line':line,'code':code,'reason':'duplicate securities code; first kept'})
            continue
        seen[code]=row;result.append(row)
    if len(result)<200:raise FilerListError('Too few listed manufacturing issuers; verify EDINET schema/filter')
    return sorted(result,key=lambda x:x['コード']),listing_values,bad,len(lines)-header_row-1

def run(output,meta,raw=None):
    content=raw if raw is not None else fetch()
    rows,listing,rejections,scanned=parse(content)
    out=Path(output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['コード','銘柄名','33業種区分','市場・商品区分','EDINETコード']);w.writeheader();w.writerows(rows)
    summary={'version':'3.25','source':SOURCE,'source_type':'FSA EDINET public filer code list',
             'total_records_scanned':scanned,'manufacturing_candidate_count':len(rows),
             'list_values':sorted(listing),'rejected':rejections[:30],
             'source_sha256':hashlib.sha256(content).hexdigest(),
             'generated_at_utc':datetime.utcnow().isoformat()+'Z',
             'note':'EDINET listed industry data may differ from JPX TSE 33-sector membership. Requires reconciliation. No company is published by this step.'}
    mp=Path(meta);mp.parent.mkdir(parents=True,exist_ok=True)
    mp.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k!='rejected'},ensure_ascii=False))
    return summary

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--output',default='state/v325/edinet-issues.csv')
    ap.add_argument('--meta',default='state/v325/edinet-source.json');ap.add_argument('--zip',default='')
    a=ap.parse_args();run(a.output,a.meta,Path(a.zip).read_bytes() if a.zip else None)
