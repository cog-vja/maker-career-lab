#!/usr/bin/env python3
"""Read-only retrieval of earlier v3.25 GitHub Actions artifacts.

No git commit, git push, workflow modification, Pages deployment, or API write.
Artifacts are a temporary 90-day checkpoint; archive reviewed output separately.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

NAME_RE = re.compile(r'^mcl-v325-audit-b(\d+)-root(\d+)$')

class ArtifactError(ValueError): pass

def select_batches(pages, bootstrap_id):
    """Choose latest artifact for each offset of one explicit bootstrap run."""
    best = {}
    for page in pages:
        for a in page.get('artifacts', []):
            m = NAME_RE.fullmatch(str(a.get('name', '')))
            if not m or int(m.group(2)) != int(bootstrap_id) or a.get('expired'):
                continue
            offset = int(m.group(1))
            # Only 50-issuer-aligned batches belong to the v3.25 run.
            if offset < 0 or offset % 50:
                continue
            prior = best.get(offset)
            if prior is None or (a.get('created_at', ''), a.get('id', 0)) > (prior.get('created_at', ''),prior.get('id', 0)):
                best[offset] = a
    return best

def gh(*args):
    p = subprocess.run(['gh', *args], text=True, capture_output=True)
    if p.returncode:
        raise ArtifactError('GitHub artifact retrieval failed (no secrets shown): ' + p.stderr[:200])
    return p.stdout

def prepare(bootstrap_id, dest, public_path):
    if not os.environ.get('GH_TOKEN') or not os.environ.get('GITHUB_REPOSITORY'):
        raise ArtifactError('GH_TOKEN and GITHUB_REPOSITORY required; run in Actions')
    repo = os.environ['GITHUB_REPOSITORY']
    public_sha256 = hashlib.sha256(Path(public_path).read_bytes()).hexdigest()
    pages = json.loads(gh('api', f'repos/{repo}/actions/artifacts?per_page=100', '--paginate', '--slurp'))
    batches = select_batches(pages, bootstrap_id)
    if not batches:
        raise ArtifactError('No audited batches available for this bootstrap run')
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    company_seen = {}
    report = []
    offsets = sorted(batches)
    expected = list(range(0, offsets[-1] + 50, 50))
    if offsets != expected:
        raise ArtifactError('Missing audit offsets for this bootstrap: ' +
                            ', '.join(map(str, sorted(set(expected) - set(offsets)))))
    statuses = {}
    for offset in offsets:
        a = batches[offset]
        run = a.get('workflow_run') or {}
        runid = run.get('id')
        if not runid:
            raise ArtifactError('Missing workflow run id in artifact metadata')
        with tempfile.TemporaryDirectory() as t:
            gh('run', 'download', str(runid), '-R', repo, '-n', a['name'], '-D', t)
            summary_path = Path(t)/'batch-summary.json'
            if not summary_path.exists():
                raise ArtifactError('Batch summary absent at offset ' + str(offset))
            summary = json.loads(summary_path.read_text('utf-8'))
            if summary.get('offset') != offset or not 1 <= summary.get('attempted', 0) <= 50 or summary.get('limit') != 50:
                raise ArtifactError('Batch summary invalid at offset ' + str(offset))
            if summary.get('bootstrap_run_id') != int(bootstrap_id):
                raise ArtifactError('Batch bootstrap provenance mismatch at ' + str(offset))
            if summary.get('public_sha256') != public_sha256:
                raise ArtifactError('Published baseline changed since batch ' + str(offset) + '; start a new bootstrap')
            records = sorted(Path(t).glob('[0-9A-Z]*.json'))
            records = [p for p in records if p.name != 'batch-summary.json']
            if len(records) != summary['attempted']:
                raise ArtifactError('Batch audit count differs from claimed total: ' + str(offset))
            for p in records:
                item = json.loads(p.read_text('utf-8'))
                code = item.get('ticker')
                if not isinstance(code, str) or p.stem != code:
                    raise ArtifactError('Audit identity mismatch')
                if code in company_seen:
                    raise ArtifactError('Duplicated company across batches: '+code)
                company_seen[code] = (item,offset)
                status = str(item.get('status','UNKNOWN'))
                statuses[status] = statuses.get(status, 0) + 1
                shutil.copy2(p, dest/p.name)
            verified = sum(1 for p in records
                if json.loads(p.read_text('utf-8')).get('status') == 'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW')
            if verified != summary.get('fully_source_reconciled'):
                raise ArtifactError('Batch reconciled count mismatch: ' + str(offset))
            report.append({'offset':offset, 'run_id':runid, 'artifact':a['name'],
                           'attempted':len(records),'verified':verified})
    proposed = [code for code, (item,_) in sorted(company_seen.items())
                if item.get('status') == 'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW'
                and item.get('verifiedMetricCount') == 6]
    (dest.parent/'REVIEW-BATCHES.json').write_text(json.dumps({
        'bootstrap_run_id':int(bootstrap_id),'batches':report,'audited_total':len(company_seen),
        'six_metric_eligible_count':len(proposed),'eligible_tickers':proposed,
        'status_counts':statuses,'baseline_sha256':public_sha256,
        'note':'All six-metric source-reconciled issuers are staging candidates only. Output is NOT approved for publication or deployed.'
    },ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return proposed

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bootstrap-run', type=int, required=True)
    ap.add_argument('--audit-dir', default='out/reviews')
    ap.add_argument('--public', default='company-data.js')
    ap.add_argument('--candidate-csv', '--proposed-csv', dest='candidate_csv', default='out/staging-candidates.csv')
    a = ap.parse_args()
    eligible = prepare(a.bootstrap_run, a.audit_dir, a.public)
    p = Path(a.candidate_csv);p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        writer = csv.writer(f);writer.writerow(['ticker','include'])
        writer.writerows((s,'YES') for s in eligible)
    print('Audit evidence gathered:',len(eligible),'six-metric staging candidates; NOT APPROVED / NOT PUBLISHED')

if __name__=='__main__':main()
