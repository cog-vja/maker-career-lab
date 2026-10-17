#!/usr/bin/env python3
"""Research-only discovery of 25 unverified manufacturing candidates; never publish."""
from __future__ import annotations
import argparse,hashlib,io,json,os,time,zipfile
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import monthly_edinet_v321 as m

def run(master_path,output,days=400,download=True,delay=0.7,as_of=None,day_fetch=None,zip_fetch=None):
 if not 1<=days<=400 or not 0<=delay<=10:raise m.UpdateError('invalid discovery inputs')
 master=json.loads(Path(master_path).read_text(encoding='utf-8'))
 rows=master['companies']; ids=[x['ticker'] for x in rows]
 research=[x for x in rows if x['stage']=='ADDITIONAL_RESEARCH_UNVERIFIED']
 if len(rows)!=225 or len(set(ids))!=225 or len(research)!=25:raise m.UpdateError('wrong candidate master shape')
 known={x['ticker']:x for x in research}
 key=os.environ.get('EDINET_API_KEY','')
 if (day_fetch is None or (download and zip_fetch is None)) and not key:raise m.UpdateError('EDINET_API_KEY missing')
 day_fetch=day_fetch or (lambda d:m.request_json(d,key))
 zip_fetch=zip_fetch or (lambda d:m.get_zip(d,key))
 now=as_of or datetime.now(ZoneInfo('Asia/Tokyo')).date()
 gathered=defaultdict(list)
 for i in range(days):
  day=now-timedelta(days=i)
  for r in day_fetch(day):
   code=m.ticker(r)
   if code in known and str(r.get('docTypeCode')) in ('120','130'):gathered[code].append(r)
  if i<days-1 and delay:time.sleep(delay)
 dest=Path(output);dest.mkdir(parents=True,exist_ok=True)
 report=[]
 for index,item in enumerate(research):
  code=item['ticker'];choice=m.select(gathered[code],None,now)
  record={'ticker':code,'research_name_unverified':item['name'],'status':choice['status'],
   'issuer_identity_verified':False,'public_release_approved':False}
  if choice['status']=='NEW_FILING_UNVERIFIED':
   filing=choice['filing']
   record.update({k:filing[k] for k in ('docID','filerName','edinetCode','periodStart','periodEnd')})
   if download:
    try:
     raw=zip_fetch(filing['docID'])
     import edinet_v313 as audit
     audit.original_instance(raw,filing)
     d=dest/f'originals-batch-{index//10+1:02}'
     d.mkdir(exist_ok=True)
     (d/(code+'-'+filing['docID']+'.zip')).write_bytes(raw)
     record['original_zip_sha256']=hashlib.sha256(raw).hexdigest()
     record['status']='ORIGINAL_ACQUIRED_UNVERIFIED'
    except Exception as exc:
     record['status']='DOWNLOAD_FAILED';record['error_type']=type(exc).__name__
  report.append(record)
  print(f'[{index+1}/25] {code} {record["status"]}',flush=True)
 (dest/'discovery-summary-v322.json').write_text(json.dumps({'version':'3.22','candidates':25,'found':sum(x['status']=='ORIGINAL_ACQUIRED_UNVERIFIED' for x in report),
 'statuses':dict(Counter(x['status'] for x in report)), 'published':0},ensure_ascii=False,indent=2)+'\n')
 (dest/'discovery-details-v322.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 return report

def main():
 a=argparse.ArgumentParser();a.add_argument('--master',default='company-master-v322.json');a.add_argument('--output',default='v322-discovery-output')
 a.add_argument('--days',type=int,default=400);a.add_argument('--delay',type=float,default=0.7);a.add_argument('--no-download',action='store_true')
 v=a.parse_args();run(v.master,v.output,v.days,not v.no_download,v.delay)
if __name__=='__main__':main()
