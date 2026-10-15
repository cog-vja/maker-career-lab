#!/usr/bin/env python3
"""Download nine other EDINET filing-original ZIPs as verification fixtures.

Never print EDINET key or the authenticated URL. No automatic data publishing.
"""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

EDINET_ENDPOINT = 'https://api.edinet-fsa.go.jp/api/v2/documents/'
OMRON_TICKER = '6645'
MAX_ZIP_BYTES = 80_000_000
MAX_TOTAL_BYTES = 600_000_000
MAX_MEMBER_COUNT = 20000


def load_targets(discovery_path, expected_count=9):
    data = json.loads(Path(discovery_path).read_text(encoding='utf-8'))
    targets = data['targets']
    if len(targets) != 10:
        raise ValueError(f'Expected 10 discovery targets; got {len(targets)}')
    selected = []
    all_tickers = set()
    for t in targets:
        ticker = str(t['ticker'])
        filing = t.get('selected')
        if ticker in all_tickers:
            raise ValueError(f'Duplicate ticker: {ticker}')
        all_tickers.add(ticker)
        if ticker == OMRON_TICKER:
            continue
        if not filing:
            raise ValueError(f'Missing filing for ticker {ticker}')
        docid = filing.get('docID', '')
        if not re.fullmatch(r'S[0-9A-Z]{7,15}', docid):
            raise ValueError('Invalid filing ID')
        if not re.fullmatch(r'\d{4}', ticker):
            raise ValueError('Invalid ticker')
        if not filing.get('periodEnd'):
            raise ValueError('Missing filing period')
        selected.append({'ticker': ticker, 'company': t['target_name'],
                         'docID': docid, 'periodStart': filing.get('periodStart'),
                         'periodEnd': filing['periodEnd'], 'edinetCode': filing.get('edinetCode')})
    if OMRON_TICKER not in all_tickers:
        raise ValueError('Omron not present in discovery')
    if len(selected) != expected_count or len({x['docID'] for x in selected}) != expected_count:
        raise ValueError('Unexpected target count or duplicated docID')
    return selected


def verify_zip(data):
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError('Filing exceeds maximum download size')
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError('Response is not a ZIP')
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        items = z.infolist()
        if len(items) > MAX_MEMBER_COUNT:
            raise ValueError('Excessive ZIP entry count')
        if not any('/publicdoc/' in ('/' + i.filename.lower()) for i in items):
            raise ValueError('Expected PublicDoc folder not found')
        if not any(i.filename.lower().endswith('.xbrl') and '/publicdoc/' in ('/' + i.filename.lower()) for i in items):
            raise ValueError('Expected PublicDoc XBRL not found')
        if z.testzip() is not None:
            raise ValueError('Original ZIP failed CRC check')
        return {'file_count': len([i for i in items if not i.is_dir()]),
                'xbrl_count': sum(i.filename.lower().endswith('.xbrl') for i in items),
                'html_count': sum(i.filename.lower().endswith(('.htm','.html')) for i in items)}


def fetch(docid, api_key, attempts=3, opener=None, sleep=time.sleep):
    if not re.fullmatch(r'S[0-9A-Z]{7,15}', docid):
        raise ValueError('Invalid document ID')
    params = urllib.parse.urlencode({'type': '1', 'Subscription-Key': api_key})
    request = urllib.request.Request(EDINET_ENDPOINT + docid + '?' + params,
                                     headers={'User-Agent': 'maker-career-lab/source-verification-v3.12'})
    opener = opener or urllib.request.urlopen
    for attempt in range(attempts):
        try:
            with opener(request, timeout=90) as response:
                result = response.read(MAX_ZIP_BYTES + 1)
            if len(result) > MAX_ZIP_BYTES:
                raise ValueError('Original ZIP too large')
            verify_zip(result)
            return result
        except urllib.error.HTTPError as ex:
            if ex.code in (429, 500, 502, 503, 504) and attempt + 1 < attempts:
                sleep(2 ** attempt * 3)
                continue
            raise RuntimeError(f'EDINET HTTP {ex.code}') from None
        except urllib.error.URLError:
            if attempt + 1 < attempts:
                sleep(2 ** attempt * 3)
                continue
            raise RuntimeError('EDINET network failure') from None
    raise RuntimeError('Retry limit reached')


def download_all(targets, api_key, output, fetcher=fetch, delay=2):
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    files_dir = out / 'originals'
    files_dir.mkdir(exist_ok=True)
    manifest = {'version': '3.12', 'source': 'EDINET type=1 filing original ZIP',
                'created_utc': datetime.now(timezone.utc).isoformat(),
                'excluded_ticker': OMRON_TICKER,
                'company_count_expected': len(targets),
                'source_validation': 'ZIP CRC, PublicDoc XBRL, SHA-256',
                'publication_status': 'UNVERIFIED', 'quality_status': 'BLOCKED',
                'companies': [], 'completed_count': 0, 'failed_count': 0}
    total = 0
    for idx,t in enumerate(targets):
        record = dict(t)
        filename = f"{t['ticker']}-{t['docID']}-type1-original.zip"
        record.update({'file': 'originals/' + filename, 'status': 'failed'})
        try:
            data = fetcher(t['docID'], api_key)
            checks = verify_zip(data)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError('Total ZIP download exceeds safety limit')
            (files_dir / filename).write_bytes(data)
            record.update(status='verified', bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), **checks)
            manifest['completed_count'] += 1
        except Exception as ex:
            # Never print URL, request, or exception strings that could reveal API key.
            record.update(error_type=type(ex).__name__, error='Download or validation failed')
            manifest['failed_count'] += 1
        manifest['companies'].append(record)
        (out / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        print(f"{t['ticker']} {t['docID']}: {record['status']}",flush=True)
        if idx + 1 < len(targets) and delay:
            time.sleep(delay)
    (out / 'README.txt').write_text('Nine EDINET type=1 original filing ZIPs. Downloaded as independent verification fixtures. Do not commit originals to Git. No metrics have been approved for publication.\n',encoding='utf-8')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discovery',default='discovery-v31.json')
    parser.add_argument('--output',default='edinet-v312-originals')
    parser.add_argument('--dry-run',action='store_true')
    args=parser.parse_args()
    targets = load_targets(args.discovery)
    if args.dry_run:
        print(json.dumps(targets, ensure_ascii=False,indent=2))
        return
    key=os.environ.get('EDINET_API_KEY')
    if not key:
        raise SystemExit('GitHub Secret EDINET_API_KEY is missing')
    result=download_all(targets,key,args.output)
    if result['failed_count']:
        raise SystemExit(f"{result['failed_count']} filing(s) failed; see uploaded manifest")

if __name__ == '__main__':
    main()
