#!/usr/bin/env python3
"""EDINET v3.11: ten-company, standards-aware integration, fail-closed.

Type=5 CSV is the primary existing filing processor (v3.6). For US GAAP,
only incomplete metrics are filled with v3.10 source-scoped, type=1 HTML
candidates. Existing non-null values are never silently overwritten.
Outputs are diagnostic only; no files for public site are produced.
"""
import argparse
import csv
import json
import os
import time
from copy import deepcopy
from decimal import Decimal, InvalidOperation
from pathlib import Path
import edinet_v32 as v32
import edinet_v33 as v33
import edinet_v35 as v35
import edinet_v36 as v36
import edinet_v38 as v38
import edinet_v310 as v310

METRICS=tuple(v32.TAGS)
METRIC_REQUIRED_CHECKS={
    'equity_ratio_pct': ('assets_equal_liabilities_plus_net_assets',
                         'net_assets_equal_parent_equity_plus_noncontrolling'),
}

def decimal_equal(a,b):
    try:
        x,y=Decimal(str(a)),Decimal(str(b))
        return x.is_finite() and y.is_finite() and x==y
    except (ValueError,TypeError,InvalidOperation):return False

def validate_original(filing, original):
    """Require filing-year match and recorded source evidence; no ticker rules."""
    current_year=int(filing['periodEnd'][:4])
    parts=original.get('components_jpy',{})
    for key in ('revenue','operating_cash_flow','total_assets','parent_equity'):
        item=parts.get(key)
        if not item or item.get('current_year')!=current_year:
            return False, 'missing_or_incorrect_year_'+key
    # Operating-profit components and issuer-defined formula must be present.
    for key in ('cost_of_sales','selling_general_admin','research_development'):
        item=parts.get(key)
        if not item or item.get('current_year')!=current_year:
            return False,'missing_operating_profit_component_'+key
    if not original.get('operating_profit_definition'):
        return False,'missing_issuer_profit_definition'
    if not original.get('provenance',{}).get('average_salary_man'):
        return False,'missing_salary_source'
    checks=original.get('accounting_cross_checks',{})
    if not checks or any(checks.get(k) is not True for k in METRIC_REQUIRED_CHECKS['equity_ratio_pct']):
        return False,'balance_sheet_identity_unconfirmed'
    vals=original.get('candidate_values',{})
    if any(vals.get(k) is None for k in METRICS):
        return False,'incomplete_original_six_metrics'
    return True,'source_structure_and_arithmetic_checked'

def integrate(base,filing,original=None,source_error=None):
    """Integration may add only missing, admissible US GAAP values.

    `original` must come from the actual type=1 ZIP of the SAME docID.
    Even after a successful merge, publication remains BLOCKED.
    """
    result=deepcopy(base)
    result['pipeline_version']='3.11'
    result['source_review']={'type1_attempted':bool(original is not None or source_error),
        'type1_error':source_error,'merges':{},'conflicts':{},'original_checked':False}
    gaap=result['accounting_standard']['standard']
    if gaap=='US_GAAP' and original is not None:
        if original.get('docID')!=filing.get('docID'):
            result['source_review']['type1_error']='docid_mismatch'
        else:
            valid,reason=validate_original(filing,original)
            result['source_review']['original_checked']=valid
            result['source_review']['original_check_reason']=reason
            if valid:
                for metric in METRICS:
                    incoming=original['candidate_values'][metric]
                    existing=result['selected_values'].get(metric)
                    if existing is None:
                        result['selected_values'][metric]=incoming
                        result['provenance'][metric]={
                            'method':'type1_consolidated_html_v310',
                            'source_docID':filing['docID'],
                            'source_metric':metric,
                            'verification':'SOURCE_CHECKED_PUBLICATION_PENDING',
                            'detail':original['provenance'].get({
                                'revenue_oku':'revenue',
                                'prior_revenue_oku':'revenue',
                                'operating_profit_oku':'revenue',
                                'operating_cf_oku':'operating_cash_flow',
                                'equity_ratio_pct':'parent_equity',
                                'average_salary_man':'average_salary_man',
                            }[metric],[])[:10]}
                        result['source_review']['merges'][metric]=incoming
                    elif not decimal_equal(existing,incoming):
                        result['source_review']['conflicts'][metric]={'csv':existing,'original':incoming}
                        # Conflicting value remains blocked (not silently published).
                        result['selected_values'][metric]=None
                        result['provenance'][metric]={'method':'type5_type1_disagreement',
                            'verification':'BLOCKED','csv_value':existing,'original_value':incoming}
    result['derived_values']=v33.calculate(result['selected_values'])
    result['quality_gate']=v35.crosscheck(result['selected_values'],result['provenance'],result['accounting_standard'])
    result['quality_gate']['status']='BLOCKED'
    result['quality_gate']['independent_original_filing_verified']=False
    result['publication_status']='UNVERIFIED'
    result['approved_for_publication']=False
    return result

def process(blob,filing,original_zip=None,type1_error=None):
    base=v36.review(blob,filing)
    gaap=base['accounting_standard']['standard']
    original=None
    if gaap=='US_GAAP' and original_zip is not None:
        try:original=v310.extract_original_type1(original_zip,filing['docID'])
        except Exception as exc:type1_error=type(exc).__name__+': '+str(exc)[:180]
    return integrate(base,filing,original,type1_error)

def build_summary(target,report):
    return {'ticker':target['ticker'],'company':target['target_name'],
            'docID':target['selected']['docID'],
            'accounting_standard':report['accounting_standard']['standard'],
            **{k:report['selected_values'].get(k) for k in METRICS},
            **report['derived_values'],
            'metric_count':sum(report['selected_values'].get(k) is not None for k in METRICS),
            'source_checked':report['source_review']['original_checked'],
            'type1_merges':len(report['source_review']['merges']),
            'type1_conflicts':len(report['source_review']['conflicts']),
            'quality_status':'BLOCKED','publication_status':'UNVERIFIED'}

def run(targets,key,output,limit=10,delay=2):
    out=Path(output);out.mkdir(parents=True,exist_ok=True)
    records=[]
    for i,t in enumerate(targets[:limit]):
        docid=t['selected']['docID'];ticker=t['ticker']
        row={'ticker':ticker,'company':t['target_name'],'docID':docid,
             'status':'error','publication_status':'UNVERIFIED'}
        try:
            csv_zip=v32.download(docid,key)
            # Determine GAAP from the existing filing-level standards before
            # fetching additional data. Non-US GAAP never requires type=1.
            base=v36.review(csv_zip,t['selected'])
            original=None;source_error=None
            if base['accounting_standard']['standard']=='US_GAAP' and any(
                    base['selected_values'].get(m) is None for m in METRICS):
                try:original=v38.fetch_original(docid,key)
                except Exception as exc:source_error=type(exc).__name__+': '+str(exc)[:160]
            if original is not None:
                report=process(csv_zip,t['selected'],original)
            else:
                report=integrate(base,t['selected'],source_error=source_error)
            (out/f'{ticker}-{docid}-v311.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            row.update(status='diagnosed',**build_summary(t,report))
            if source_error:row['source_error']=source_error
        except Exception as exc:
            row['error']=type(exc).__name__+': '+str(exc)[:180]
        records.append(row)
        print(ticker,row['status'],row.get('metric_count',0),flush=True)
        if i+1<len(targets[:limit]):time.sleep(delay)
    (out/'summary.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    cols=['ticker','company','docID','status','accounting_standard',*METRICS,
          'operating_margin_pct','revenue_growth_pct','operating_cf_to_revenue_pct',
          'metric_count','source_checked','type1_merges','type1_conflicts',
          'quality_status','publication_status','source_error','error']
    with (out/'company-candidates-v311.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
        w.writerows({k:r.get(k) for k in cols} for r in records)
    (out/'README.txt').write_text('v3.11 ten-company review only. None of the outputs are approved for publication.\n',encoding='utf-8')
    return records

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--discovery',default='discovery-v31.json')
    p.add_argument('--output',default='edinet-v311-output')
    p.add_argument('--limit',type=int,default=10)
    p.add_argument('--delay',type=float,default=2)
    a=p.parse_args()
    if not 1<=a.limit<=10 or not 0<=a.delay<=30:p.error('limit 1-10; delay 0-30')
    key=os.environ.get('EDINET_API_KEY')
    if not key:p.error('EDINET_API_KEY missing')
    targets=[t for t in json.loads(Path(a.discovery).read_text(encoding='utf-8'))['targets'] if t.get('selected')]
    records=run(targets,key,a.output,a.limit,a.delay)
    if any(r.get('status')!='diagnosed' for r in records):raise SystemExit('Some companies failed; inspect artifact')

if __name__=='__main__':main()
