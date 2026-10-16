#!/usr/bin/env python3
"""v3.16: stage *manual* site UI update with the ten already-approved records.

Never writes to repository root company-data.js or approves pending companies.
"""
from __future__ import annotations
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
from discover_edinet_v316 import load_master,assert_existing_publication,DiscoveryError

FILES=('company-check.html','company-compare.js')

def stage(master_path,approved_js,site_update,output,style_path=None):
    master=load_master(master_path)
    existing=assert_existing_publication(master,approved_js)
    site_update=Path(site_update);output=Path(output);output.mkdir(parents=True,exist_ok=True)
    dest=output/'site-preview';dest.mkdir(parents=True,exist_ok=True)
    for name in FILES:
        source=site_update/name
        if not source.is_file():raise DiscoveryError('missing staged site reference: '+name)
        shutil.copy2(source,dest/name)
    shutil.copy2(approved_js,dest/'company-data.js')
    if style_path and Path(style_path).is_file():
        shutil.copy2(style_path,dest/'style.css')
    markup=(dest/'company-check.html').read_text(encoding='utf-8')
    js=(dest/'company-compare.js').read_text(encoding='utf-8')
    for required in ('company-data.js','company-compare.js','id="compare-form"',
                     'id="results"','id="sources"','id="metrics-body"',
                     'id="dataset-status"'):
        if required not in markup:raise DiscoveryError('missing UI contract: '+required)
    for required in ('window.MCL_COMPANIES','sourceDocId','navigator.clipboard',
                     '同じ会社が選択されています','実施日未記録','mcl-metric-delta'):
        if required not in js:raise DiscoveryError('missing new behavior: '+required)
    if shutil.which('node'):
        for name in ('company-compare.js','company-data.js'):
            p=subprocess.run(['node','--check',str(dest/name)],capture_output=True,text=True)
            if p.returncode:raise DiscoveryError('invalid JavaScript: '+name)
    if 'EDINET原本との照合と公開承認を完了' not in markup:
        raise DiscoveryError('stale public-data description')
    file_digests={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in dest.iterdir() if p.is_file()}
    manifest={'version':'3.16','approved_companies':10,'pending_companies':20,
              'new_companies_auto_published':0,
              'live_deployment':'NOT_PERFORMED','approval_of_new_companies':False,
              'published_data_sha256_unchanged':existing['data_sha256'],
              'file_sha256':file_digests,
              'notes':'Use only company-check.html and company-compare.js to update site root; preserve root company-data.js.'}
    (output/'site-staging-manifest-v316.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return manifest

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--master',default='company-master-v316.json')
    p.add_argument('--approved-js',default='company-data.js')
    p.add_argument('--site-update',default='site-update')
    p.add_argument('--output',default='v316-site-review')
    p.add_argument('--style',default='style.css')
    args=p.parse_args()
    try:print(json.dumps(stage(args.master,args.approved_js,args.site_update,args.output,args.style),ensure_ascii=False,indent=2))
    except DiscoveryError as e:raise SystemExit('BLOCKED: '+str(e))

if __name__=='__main__':main()
