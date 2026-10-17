#!/usr/bin/env python3
"""Initial 400-day discovery for 90 unverified candidate tickers.

No company is published or approved. Originals are separated into 9 artifact batches.
"""
from __future__ import annotations
import argparse
from collections import defaultdict,Counter
from datetime import datetime,timedelta
import hashlib
import io
import json
from pathlib import Path
import time
import zipfile
from zoneinfo import ZoneInfo
import os
import monthly_edinet_v321 as src

def discover(master_file,out,days=400,download=True,delay=0.7,day_fetch=None,zip_fetch=None,as_of=None):
    if not 1<=days<=400 or not 0<=delay<=10:raise src.UpdateError('unsafe discovery arguments')
    master=src.read_master(master_file)
    research=[r for r in master if r['stage']=='RESEARCH_UNVERIFIED']
    assert len(research)==90
    known={r['ticker']:r for r in research}
    key=os.environ.get('EDINET_API_KEY','')
    if (not day_fetch or (download and not zip_fetch)) and not key:raise src.UpdateError('EDINET_API_KEY missing')
    day_fetch=day_fetch or (lambda d:src.request_json(d,key))
    zip_fetch=zip_fetch or (lambda doc:src.get_zip(doc,key))
    now=as_of or datetime.now(ZoneInfo('Asia/Tokyo')).date()
    group=defaultdict(list)
    for i in range(days):
        day=now-timedelta(days=i)
        for row in day_fetch(day):
            ticker=src.ticker(row)
            if ticker in known and str(row.get('docTypeCode')) in ('120','130'):group[ticker].append(row)
        if i<days-1:time.sleep(delay)
    output=Path(out);output.mkdir(parents=True,exist_ok=True)
    rows=[]
    for index,r in enumerate(research):
        id=r['ticker'];choice=src.select(group[id],None,now)
        record={'ticker':id,'research_name_unverified':r['name'],'status':choice['status'],'published':False,'issuer_identity_verified':False}
        if choice['status']=='NEW_FILING_UNVERIFIED':
            file=choice['filing']
            record.update({'docID':file['docID'],'filerName':file['filerName'],'periodStart':file['periodStart'],'periodEnd':file['periodEnd'],'edinetCode':file['edinetCode']})
            if download:
                try:
                    raw=zip_fetch(file['docID'])
                    with zipfile.ZipFile(io.BytesIO(raw)) as z:
                        if z.testzip():raise src.UpdateError('source corrupt')
                        members=z.namelist()
                        if not any(x.endswith('.xbrl') and '/publicdoc/' in ('/'+x.lower()) for x in members):raise src.UpdateError('PublicDoc XBRL missing')
                    target=output/f'originals-batch-{index//10+1:02}'
                    target.mkdir(exist_ok=True)
                    (target/(id+'-'+file['docID']+'.zip')).write_bytes(raw)
                    record['original_zip_sha256']=hashlib.sha256(raw).hexdigest()
                    record['status']='ORIGINAL_ACQUIRED_UNVERIFIED'
                except Exception as exc:
                    record['status']='DOWNLOAD_FAILED';record['reason']=type(exc).__name__
        rows.append(record)
        print(f'[{index+1}/90] {id} {record["status"]}',flush=True)
    src.save(output/'discovery-90-summary-v321.json',{'version':'3.21','research_candidates':90,'download_enabled':download,'scan_days':days,
        'statuses':dict(Counter(r['status'] for r in rows)),'automatically_published':0})
    src.save(output/'discovery-90-details-v321.json',rows)
    return rows

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--master',default='company-master-v321.json')
    parser.add_argument('--output',default='v321-discovery-90');parser.add_argument('--days',type=int,default=400)
    parser.add_argument('--delay',type=float,default=0.7);parser.add_argument('--no-download',action='store_true')
    a=parser.parse_args();discover(a.master,a.output,a.days,not a.no_download,a.delay)
if __name__=='__main__':main()
