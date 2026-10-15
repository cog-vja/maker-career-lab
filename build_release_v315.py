#!/usr/bin/env python3
"""v3.15: stage site release. No automatic publication."""
import argparse,hashlib,json,re,shutil,subprocess
from pathlib import Path
from build_release_v314 import build,ReleaseError

def stage(review,output,mode,approval=None,site_dir=None):
 out=Path(output);out.mkdir(parents=True,exist_ok=True)
 result=build(review,out/'quality-gate',mode,approval)
 dest=out/'site-ready';dest.mkdir(exist_ok=True)
 ref=Path(site_dir) if site_dir else Path(__file__).with_name('site-reference')
 for name in ('company-check.html','company-compare.js'):
  if not (ref/name).is_file():raise ReleaseError('site reference file absent: '+name)
  shutil.copy2(ref/name,dest/name)
 shutil.copy2(out/'quality-gate/company-data.js',dest/'company-data.js')
 page=(dest/'company-check.html').read_text();data=(dest/'company-data.js').read_text();logic=(dest/'company-compare.js').read_text()
 for key in ('company-data.js','company-compare.js','id="compare-form"','id="sources"','id="metrics-body"'):
  if key not in page:raise ReleaseError('missing HTML component: '+key)
 for key in ('window.MCL_COMPANIES','window.MCL_DATASET_META','window.MCL_DEMOS'):
  if key not in data:raise ReleaseError('missing data field: '+key)
 for key in ('operatingProfit','revenuePrev','equityRatio','averageSalary','sourceLabel'):
  if key not in logic:raise ReleaseError('missing compare field: '+key)
 if shutil.which('node'):
  for name in ('company-data.js','company-compare.js'):
   test=subprocess.run(['node','--check',str(dest/name)],capture_output=True)
   if test.returncode:raise ReleaseError('invalid JavaScript: '+name)
 if mode=='preview' and not re.search(r'window\.MCL_COMPANIES\s*=\s*\[\s*\]',data):raise ReleaseError('unsafe preview')
 if mode=='publish' and data.count('"sourceDocId"')!=10:raise ReleaseError('incorrect company count')
 manifest={'version':'3.15','mode':mode,'actual_companies':10 if mode=='publish' else 0,
  'source_artifact_sha256':result['artifact_sha256'],
  'file_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in dest.iterdir()},
  'auto_deploy':False,'live_browser_validation':'PENDING'}
 (out/'manifest-v315.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
 (out/'DEPLOY-NOTE.txt').write_text('Manual review and manual GitHub commit required. Replace ONLY company-data.js after publish approval; compare live site JS and HTML before changing those files.\n')
 return manifest

def main():
 p=argparse.ArgumentParser();p.add_argument('--review',default='fixtures-v314.zip');p.add_argument('--output',default='v315-output')
 p.add_argument('--mode',choices=['preview','publish'],default='preview');p.add_argument('--approval');p.add_argument('--site-dir')
 a=p.parse_args();print(json.dumps(stage(a.review,a.output,a.mode,a.approval,a.site_dir),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
