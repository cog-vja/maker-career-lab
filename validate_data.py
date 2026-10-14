#!/usr/bin/env python3
"""CSVから検証済み企業のみcompany-data.jsを生成。Python標準ライブラリのみ。"""
import csv, json, math, sys, re
from pathlib import Path
base=Path(__file__).resolve().parent
source=Path(sys.argv[1]) if len(sys.argv)>1 else base/'company-review-template.csv'
required=['company_id','company_name','fiscal_period','scope','salary_scope','source_document_id','source_url','verified_at','reviewer','review_status']
metrics={'revenue_oku':'revenue','operating_profit_oku':'operatingProfit','prior_revenue_oku':'revenuePrev','operating_cf_oku':'operatingCashFlow','equity_ratio_pct':'equityRatio','average_salary_man':'averageSalary'}
result=[]; errors=[]; seen=set()
with source.open(encoding='utf-8-sig',newline='') as f:
 for line,row in enumerate(csv.DictReader(f),2):
  if not any((v or '').strip() for v in row.values()): continue
  if (row.get('review_status') or '').strip()!='approved': continue
  for key in required:
   if not (row.get(key) or '').strip(): errors.append(f'{line}: {key} が未入力')
  cid=(row.get('company_id') or '').strip()
  if cid in seen:errors.append(f'{line}: company_id 重複')
  seen.add(cid)
  url=(row.get('source_url') or '').strip()
  if not re.match(r'^https://',url): errors.append(f'{line}: 出典URLはhttps必須')
  item=dict(id=cid,name=(row.get('company_name') or '').strip(),aliases=[x.strip() for x in (row.get('aliases') or '').split('|') if x.strip()],edinetCode=(row.get('edinet_code') or '').strip(),period=(row.get('fiscal_period') or '').strip(),accountingStandard=(row.get('accounting_standard') or '').strip(),scope=(row.get('scope') or '').strip(),salaryScope=(row.get('salary_scope') or '').strip(),sourceLabel='EDINET等の一次資料（手動照合済み）／書類ID：'+(row.get('source_document_id') or '').strip(),sourceUrl=url,verifiedAt=(row.get('verified_at') or '').strip(),demo=False)
  for col,key in metrics.items():
   raw=(row.get(col) or '').strip()
   if not raw:item[key]=None;continue
   try:
    val=float(raw)
    if not math.isfinite(val):raise ValueError()
    item[key]=val
   except ValueError: errors.append(f'{line}: {col} は数値か空欄のみ')
  if not re.fullmatch(r'[A-Z][0-9]{7}',item['sourceLabel'].split('書類ID：')[-1]): errors.append(f'{line}: EDINET書類IDの形式を確認')
  if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',item['verifiedAt']): errors.append(f'{line}: 照合日はYYYY-MM-DD')
  if not item['accountingStandard']: errors.append(f'{line}: 会計基準が未入力')
  if not any(item.get(k) is not None for k in metrics.values()): errors.append(f'{line}: 公開できる指標がありません')
  if item['revenue'] is not None and item['revenue']<=0: errors.append(f'{line}: 売上高が0以下')
  if item['revenuePrev'] is not None and item['revenuePrev']<=0: errors.append(f'{line}: 前期売上高が0以下')
  if item['equityRatio'] is not None and not (-100<=item['equityRatio']<=100):errors.append(f'{line}: 自己資本比率の範囲要確認')
  if item['averageSalary'] is not None and item['averageSalary']<=0:errors.append(f'{line}: 給与の値が不正')
  result.append(item)
if errors:print('検証エラー：\n'+'\n'.join(errors));sys.exit(1)
if not result:print('approved の行が0件。実在企業データは変更しません。');sys.exit(0)
out=base/'company-data.js'
old=out.read_text(encoding='utf-8')
demos=old.split('window.MCL_DEMOS = ',1)[1] if 'window.MCL_DEMOS = ' in old else '[];'
text='/* 一次資料照合・承認済みデータ。CSVから生成 */\nwindow.MCL_COMPANIES = '+json.dumps(result,ensure_ascii=False,indent=2)+';\nwindow.MCL_DATASET_META = '+json.dumps({'version':'3.0','verification':'CSVでapprovedの行のみ'},ensure_ascii=False)+';\nwindow.MCL_DEMOS = '+demos
out.write_text(text,encoding='utf-8')
print(f'{len(result)}社を更新しました: {out}')
