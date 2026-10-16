#!/usr/bin/env python3
"""v3.17 original-filing 20-company extension diagnostics.

This tool NEVER approves publishing. Any ambiguous or unrecognized element is
BLOCKED, with evidence, even when a plausible-looking number is present.
Use --artifact to reproduce against the uploaded v3.16 Actions artifact ZIP.
Use --mode live with EDINET_API_KEY to redownload frozen filings in GitHub Actions.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, re, time, urllib.error, zipfile
from datetime import date
from decimal import Decimal as D
from pathlib import Path

import edinet_v313 as v313
import edinet_v38 as v38

METRICS=v313.METRICS
EXTENSION_REVENUE=('TotalNetRevenuesIFRS','OperatingRevenuesIFRSKeyFinancialData','SalesRevenuesIFRS')


def issuer_namespace(namespace,filing):
    """Never take custom facts from a different filing's issuer extension."""
    return (namespace.startswith('http://') or namespace.startswith('https://')) and (
        '/'+filing['edinetCode']+'-' in namespace and
        '/'+filing['periodEnd']+'/' in namespace and '/asr/' in namespace)


def extension_revenue(facts,filing,context):
    """Only three explicit revenue-total aliases, two independent tag names required.

    SalesOfProductsIFRS and generic segment sales are intentionally excluded.
    """
    proof=[]
    for name in EXTENSION_REVENUE:
        items=facts.get((name,context),[])
        for entry in items:
            if entry['unit']!=['iso4217:JPY'] or not issuer_namespace(entry['namespace'],filing):
                raise ValueError('incorrect extension namespace or unit: '+name)
            proof.append(entry)
    names={e['element'] for e in proof}
    if 'TotalNetRevenuesIFRS' not in names or len(names)<2:
        raise ValueError('missing independent issuer total revenue aliases')
    amounts={D(x['value']) for x in proof}
    if len(amounts)!=1:raise ValueError('conflicting issuer extension revenue totals')
    amount=amounts.pop()
    if amount<0:raise ValueError('negative issuer revenue')
    return amount,{'basis':'issuer_defined_total_revenue','unit':'iso4217:JPY',
                   'context':context,'element_names':sorted(names),
                   'element_sources':[{'element':e['element'],'namespace':e['namespace'],
                    'context':e['contextRef'],'value_jpy':e['value']} for e in proof[:20]],
                   'verification':'multiple_allowed_fact_names_same_value'}


def record_success(result,metric,value,evidence,method='standard_taxonomy'):
    result['metrics'][metric]={'status':'SOURCE_RECONCILED','value':str(value),
       'method':method,'evidence':evidence,'approved_for_publication':False}


def record_failure(result,metric,reason):
    result['metrics'][metric]={'status':'BLOCKED','value':None,
       'reason':str(reason)[:240],'approved_for_publication':False}


def common_numeric(facts,filing,gaap,result):
    """Per-metric safe extraction; allow other metrics to pass if one definition fails."""
    cfg=v313.DEFINITIONS[gaap]
    taxonomy='jppfs_cor' if gaap=='JP_GAAP' else 'jpigp_cor'
    for metric,concept,ctx in [('revenue_oku','revenue','CurrentYearDuration'),
                               ('prior_revenue_oku','revenue','Prior1YearDuration'),
                               ('operating_profit_oku','operating_profit','CurrentYearDuration'),
                               ('operating_cf_oku','operating_cf','CurrentYearDuration')]:
        try:
            try:
                amount,evidence=v313.pick(facts,cfg[concept],ctx,'iso4217:JPY',taxonomy)
                if amount<0 and concept=='revenue':raise ValueError('negative revenue')
                method='standard_taxonomy'
            except ValueError as exc:
                # Only a genuinely ABSENT allowed-tag family activates fallback.
                if (gaap!='IFRS' or concept!='revenue' or
                    not str(exc).startswith('missing permitted fact')):
                    raise
                amount,evidence=extension_revenue(facts,filing,ctx)
                method='issuer_extension_correlated'
            record_success(result,metric,amount/v313.MONEY,evidence,method)
        except Exception as exc:record_failure(result,metric,exc)
    try:
        salary,se=v313.pick(facts,(v313.SALARY_ELEMENT,),
                  'CurrentYearInstant_NonConsolidatedMember','iso4217:JPY','jpcrp_cor')
        if salary<0:raise ValueError('negative salary')
        record_success(result,'average_salary_man',salary/v313.SALARY,
                       {**se,'scope':'nonconsolidated reporting company'})
    except Exception as exc:record_failure(result,'average_salary_man',exc)
    try:
        asset,ae=v313.pick(facts,cfg['assets'],'CurrentYearInstant','iso4217:JPY',taxonomy)
        equity,ee=v313.pick(facts,cfg['parent_equity'],'CurrentYearInstant','iso4217:JPY',taxonomy)
        proofs={'assets':ae,'parent_equity':ee}
        if gaap=='JP_GAAP':
            val,ve=v313.pick(facts,cfg['valuation'],'CurrentYearInstant','iso4217:JPY',taxonomy)
            equity+=val;proofs['valuation_and_translation']=ve
        ratio=v313.percent(equity,asset)
        if ratio is None:raise ValueError('invalid consolidated equity ratio')
        disclosed,de=v313.pick(facts,cfg['disclosed_ratio'],
                                    'CurrentYearInstant','xbrli:pure','jpcrp_cor')
        if abs(disclosed*100-ratio)>D('.051'):
            raise ValueError('disclosed ratio conflicts with recomputation')
        record_success(result,'equity_ratio_pct',ratio,
           {**proofs,'formula':cfg['equity_formula'],
            'disclosed_ratio':de,'disclosed_pct':str(disclosed*100)})
    except Exception as exc:record_failure(result,'equity_ratio_pct',exc)


def adjusted_operating_profit_supplemental(original,facts,result):
    """Evidence for disclosure only; NEVER map to operating_profit_oku."""
    if result['metrics'].get('operating_profit_oku',{}).get('status')!='BLOCKED':return
    try:
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            matches=[]
            for member in z.infolist():
                if not member.filename.lower().endswith(('.htm','.html')) or '/publicdoc/' not in ('/'+member.filename.lower()):continue
                if member.file_size>8_000_000:continue
                raw=z.read(member)
                text=None
                for enc in ('utf-8-sig','cp932'):
                    try:text=raw.decode(enc);break
                    except UnicodeError:continue
                if not text:continue
                import html
                simple=html.unescape(re.sub(r'<[^>]*>','',text))
                # Require issuer's written definition in same sentence vicinity.
                for m in re.finditer('調整後営業利益',simple):
                    snippet=simple[max(0,m.start()-45):m.start()+190]
                    if all(k in snippet for k in ('売上収益','売上原価','販売費及び一般管理費')):
                        matches.append(member.filename)
                        break
            if not matches:return
        tags=('RevenueIFRS','CostOfSalesIFRS','SellingGeneralAndAdministrativeExpensesIFRS')
        vals=[];proof=[]
        for tag in tags:
            n,e=v313.pick(facts,(tag,),'CurrentYearDuration','iso4217:JPY','jpigp_cor')
            vals.append(n);proof.append(e)
        adjusted=vals[0]-vals[1]-vals[2]
        if adjusted<0:return
        result['supplemental']={'name':'調整後営業利益','value_oku':str(adjusted/v313.MONEY),
          'formula':'RevenueIFRS - CostOfSalesIFRS - SellingGeneralAndAdministrativeExpensesIFRS',
          'definition_evidence_html':matches[:4],'fact_proofs':proof,
          'status':'DISPLAY_ONLY_NOT_COMPARABLE','mapped_to_operating_profit':False}
    except (ValueError,zipfile.BadZipFile):return


def audit_one(original,entry):
    ticker=entry['ticker'];filing=entry['filing'];docid=filing['docID']
    result={'ticker':ticker,'company':entry['name'],'docID':docid,
      'edinetCode':filing['edinetCode'],'periodStart':filing['periodStart'],
      'periodEnd':filing['periodEnd'],'gaap':None,'metrics':{},'supplemental':None,
      'quality_status':'BLOCKED','publication_status':'UNVERIFIED',
      'public_release_approved':False,'source_sha256':hashlib.sha256(original).hexdigest(),
      'source_bytes':len(original),'issues':[]}
    try:
        if result['source_sha256']!=entry['source_original_sha256']:
            raise ValueError('v3.16 original SHA256 mismatch')
        if len(original)!=entry['source_original_bytes']:
            raise ValueError('v3.16 original length mismatch')
        if filing['secCode'][:4]!=ticker:raise ValueError('security code mismatch')
        if filing['docTypeCode']!='120' or filing.get('withdrawalStatus')!='0':
            raise ValueError('not original periodic report')
        facts,contexts,instance=v313.original_instance(original,filing)
        result['source_instance']=instance
        # Accounting standard is a filing-level DEI tag, never inferred by ticker.
        standards=[]
        with zipfile.ZipFile(io.BytesIO(original)) as z:
            from xml.etree import ElementTree as ET
            root=ET.fromstring(z.read(instance))
            standards=[(el.text or '').strip() for el in root if v313.local(el.tag)=='AccountingStandardsDEI']
        if len(set(standards))!=1:raise ValueError('missing or conflicting accounting standard DEI')
        gaap={'IFRS':'IFRS','Japan GAAP':'JP_GAAP','JapanGAAP':'JP_GAAP',
              'Japanese GAAP':'JP_GAAP','US GAAP':'US_GAAP'}.get(standards[0])
        if gaap not in ('IFRS','JP_GAAP'):
            raise ValueError('accounting standard not yet supported: '+standards[0])
        result['gaap']=gaap
        common_numeric(facts,filing,gaap,result)
        if gaap=='IFRS':adjusted_operating_profit_supplemental(original,facts,result)
    except Exception as exc:
        result['issues'].append(type(exc).__name__+': '+str(exc)[:240])
        for metric in METRICS:record_failure(result,metric,'source identity/structure failed: '+str(exc))
    result['reconciled_count']=sum(result['metrics'][m]['status']=='SOURCE_RECONCILED' for m in METRICS)
    result['blocked_count']=6-result['reconciled_count']
    # Fail closed: even 6/6 merely source reconciled, never publication approved.
    result['source_reconciliation']='PASS' if result['blocked_count']==0 else 'PARTIAL_BLOCKED'
    return result


def validate_selection(data):
    if data.get('schema_version')!='3.17':raise ValueError('wrong selection schema')
    entries=data.get('companies',[])
    if len(entries)==0 or len(entries)>200:raise ValueError('company selection outside 1..200')
    tickers=set();ids=set()
    for e in entries:
        ticker=e['ticker'];filing=e['filing']
        if not re.fullmatch(r'[0-9A-Z]{4}',ticker) or ticker in tickers:raise ValueError('ticker duplicate/invalid')
        tickers.add(ticker)
        if e.get('publish_approved') is not False:raise ValueError('unexpected publication approval')
        if not re.fullmatch(r'[a-f0-9]{64}',e['source_original_sha256']):raise ValueError('missing source hash')
        if filing['docID'] in ids:raise ValueError('duplicate filing ID')
        ids.add(filing['docID'])
        if filing['secCode'][:4]!=ticker:raise ValueError('ticker and secCode differ')
        if filing.get('xbrlFlag')!='1' or filing.get('docTypeCode')!='120':raise ValueError('wrong filing kind')
        if date.fromisoformat(filing['periodEnd']) < date.fromisoformat(filing['periodStart']):
            raise ValueError('reverse fiscal period')
    return entries


def obtain_source(entry,mode,artifact,timeout=90):
    f=entry['filing'];ticker=entry['ticker'];docid=f['docID']
    if mode=='offline':
        if artifact is None:raise ValueError('offline artifact path required')
        data=artifact.read(f'originals/{ticker}-{docid}-type1.zip')
    elif mode=='live':
        key=os.environ.get('EDINET_API_KEY')
        if not key:raise ValueError('EDINET_API_KEY missing')
        data=v38.fetch_original(docid,key)
    else:raise ValueError('bad mode')
    return data


def run(select_path,output,mode='offline',artifact_path=None,start=0,limit=200,delay=0.5):
    spec=json.loads(Path(select_path).read_text(encoding='utf-8'))
    all_entries=validate_selection(spec)
    if not (0<=start<len(all_entries) and 1<=limit<=200 and 0<=delay<=15):
        raise ValueError('invalid pagination/delay')
    selected=all_entries[start:start+limit]
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    artifact=None
    if mode=='offline':
        artifact=zipfile.ZipFile(artifact_path)
        if artifact.testzip():raise ValueError('v3.16 artifact ZIP corrupted')
    records=[]
    try:
        for i,entry in enumerate(selected):
            try:
                source=obtain_source(entry,mode,artifact)
                result=audit_one(source,entry)
            except Exception as exc:
                result={'ticker':entry['ticker'],'company':entry['name'],
                  'docID':entry['filing']['docID'],'metrics':{m:{'status':'BLOCKED','value':None,
                  'reason':type(exc).__name__+': '+str(exc)[:180]} for m in METRICS},
                  'reconciled_count':0,'blocked_count':6,'issues':[str(exc)[:180]],
                  'quality_status':'BLOCKED','publication_status':'UNVERIFIED',
                  'public_release_approved':False,'source_reconciliation':'BLOCKED'}
            records.append(result)
            (out/(entry['ticker']+'-'+entry['filing']['docID']+'-v317.json')).write_text(
                json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(entry['ticker'],result['reconciled_count'],'/6',flush=True)
            if mode=='live' and i+1<len(selected):time.sleep(delay)
    finally:
        if artifact is not None:artifact.close()
    summary={'version':'3.17','companies_processed':len(records),
      'reconciled_metrics':sum(r['reconciled_count'] for r in records),
      'blocked_metrics':sum(r['blocked_count'] for r in records),
      'fully_reconciled_companies':sum(r['reconciled_count']==6 for r in records),
      'public_release_approved':False,'existing_ten_unmodified':True,
      'quality_status':'BLOCKED','records':[{'ticker':r['ticker'],'company':r['company'],
       'docID':r['docID'],'reconciled':r['reconciled_count'],'blocked':r['blocked_count'],
       'issues':r.get('issues',[])} for r in records]}
    (out/'summary-v317.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    with (out/'metric-audit-v317.csv').open('w',encoding='utf-8-sig',newline='') as f:
        fields=['ticker','company','docID','gaap','metric','status','value','method',
                'source_sha256','reason','publish_approved']
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in records:
            for metric,d in r['metrics'].items():
                writer.writerow({'ticker':r['ticker'],'company':r['company'],'docID':r['docID'],
                  'gaap':r.get('gaap'),'metric':metric,'status':d['status'],'value':d.get('value'),
                  'method':d.get('method'),'source_sha256':r.get('source_sha256'),
                  'reason':d.get('reason'),'publish_approved':False})
    (out/'README.txt').write_text('v3.17 diagnostics only. Never replace site company-data.js. Source reconciliation is not publication approval.\n',encoding='utf-8')
    return summary


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--selections',default='filing-selections-v317.json')
    p.add_argument('--output',default='v317-output')
    p.add_argument('--mode',choices=['offline','live'],default='offline')
    p.add_argument('--artifact',help='v3.16 GitHub Actions artifact ZIP for offline mode')
    p.add_argument('--start',type=int,default=0)
    p.add_argument('--limit',type=int,default=200)
    p.add_argument('--delay',type=float,default=0.5)
    a=p.parse_args()
    report=run(a.selections,a.output,a.mode,a.artifact,a.start,a.limit,a.delay)
    # 1 means infrastructure/identity error or no useful result; per-metric exceptions are
    # a normal BLOCKED result, not a reason to hide the completed review artifact.
    if report['reconciled_metrics']==0:raise SystemExit('No metrics reconciled; inspect v317 output')

if __name__=='__main__':main()
