#!/usr/bin/env python3
"""EDINET API v2で提出書類一覧を確認する調査用スクリプト（数値抽出は行わない）。
EDINET_API_KEYを環境変数に設定。書類一覧は検証候補であり、そのまま公開しない。
"""
import os,sys,json,urllib.request,urllib.parse,datetime,time
key=os.environ.get('EDINET_API_KEY')
if not key:sys.exit('EDINET_API_KEY が未設定です。APIキーを公開ファイルに書かないでください。')
day=sys.argv[1] if len(sys.argv)>1 else str(datetime.date.today()-datetime.timedelta(days=1))
try:datetime.date.fromisoformat(day)
except ValueError:sys.exit('日付はYYYY-MM-DD形式で指定')
params=urllib.parse.urlencode({'date':day,'type':2,'Subscription-Key':key})
url='https://api.edinet-fsa.go.jp/api/v2/documents.json?'+params
try:
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MakerCareerLabResearch/0.2'}),timeout=30) as r: data=json.load(r)
except Exception as exc:sys.exit('API取得に失敗しました: '+str(exc))
results=data.get('results') or []
selected=[{'docID':x.get('docID'),'edinetCode':x.get('edinetCode'),'filerName':x.get('filerName'),'docDescription':x.get('docDescription'),'submitDateTime':x.get('submitDateTime')} for x in results if ('有価証券報告書' in str(x.get('docDescription','')))]
print(json.dumps({'date':day,'count':len(selected),'documents':selected},ensure_ascii=False,indent=2))
