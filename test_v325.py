"""Offline tests: no JPX or EDINET network requests, no site publication."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from test_expand_v325 import CheckExpansion, VerifyV3251Standalone  # full v3.25.1 regression suite
from edinet_universe_v325 import parse as parse_edinet,FilerListError
from expand_manufacturers_v325 import parse_public,GateError,METRICS
from monthly_edinet_v325 import six_metric_update,proposed
from v325_artifacts import select_batches


def tiny_fsa_edinet_zip():
    head=['ＥＤＩＮＥＴコード','提出者種別','上場区分','連結の有無','資本金','決算日','提出者名','提出者名（英字）','提出者名（ヨミ）','所在地','提出者業種','証券コード','提出者法人番号']
    rows=[head]
    for i in range(250):
        rows.append([f'E{i:05}', '内国法人','上場','','','','製造会社'+str(i),'','','','機械',f'{1000+i}0',''])
    rows.append(['E99999','内国法人','非上場','','','','対象外','','','','機械','99990',''])
    text='20261020,251\n'+ '\n'.join(','.join(x) for x in rows)+'\n'
    stream=io.BytesIO()
    with zipfile.ZipFile(stream,'w') as z:z.writestr('EdinetcodeDlInfo.csv',text.encode('cp932'))
    return stream.getvalue()

class VerifyV325(unittest.TestCase):
    def test_official_edinet_zip_to_candidate_csv(self):
        rows,listing,bad,total=parse_edinet(tiny_fsa_edinet_zip())
        self.assertEqual(len(rows),250)
        self.assertEqual(rows[0]['コード'],'1000')
        self.assertEqual(rows[0]['EDINETコード'],'E00000')
        self.assertEqual(rows[-1]['コード'],'1249')
        self.assertEqual(len(bad),0)
        self.assertIn('上場',listing)
    def test_edinet_reject_corrupted(self):
        with self.assertRaises(FilerListError):parse_edinet(b'invalid')
    def test_monthly_update_six_metric_gate(self):
        old={'id':'1111','name':'Example','accountingStandard':'JP_GAAP','period':'2024-04-01〜2025-03-31',
         'revenue':100,'revenuePrev':95,'operatingProfit':10,'operatingCashFlow':4,'equityRatio':55,'averageSalary':650}
        aud={'ticker':'1111','status':'SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW','verifiedMetricCount':6,
          'gaap':'JP_GAAP','periodStart':'2025-04-01','periodEnd':'2026-03-31','docID':'S100AAAA',
          'sourceOriginalSha256':'a'*64,'sourceXbrlSha256':'b'*64,'sourcePayloadFingerprint':'c'*64,
          'verifiedAt':'2026-10-20','metrics':{k:{'status':'SOURCE_RECONCILED','value':str(old[v])} for k,v in METRICS.items()}}
        self.assertEqual(six_metric_update(old,aud)['period'],'2025-04-01〜2026-03-31')
        aud['metrics']['average_salary_man']['value']='1800'
        with self.assertRaises(GateError):six_metric_update(old,aud)
        aud['metrics']['average_salary_man']['value']='650';aud['metrics']['equity_ratio_pct']['status']='BLOCKED'
        with self.assertRaises(GateError):six_metric_update(old,aud)
    def test_209_and_more_supported_and_nothing_removed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'company-data.js'
            rows=[{'id':f'{1000+i}','name':str(i)} for i in range(1201)]
            p.write_text('window.MCL_COMPANIES = '+json.dumps(rows)+'; window.MCL_DATASET_META = {"count":1201}; window.MCL_DEMOS = [];')
            raw,m,original,meta=parse_public(p)
            self.assertEqual(len(original),1201)
            new=dict(original[0]);new['name']='new name'
            updated=proposed(raw,m,original,meta,{new['id']:new})
            p.write_text(updated)
            _,_,after,_=parse_public(p)
            self.assertEqual(len(after),1201);self.assertEqual(after[0]['name'],'new name')
            self.assertEqual(after[-1],original[-1])
    def test_artifacts_only_same_bootstrap_latest_offset(self):
        pages=[{'artifacts':[
            {'name':'mcl-v325-audit-b0-root111','created_at':'2026-10-20T12:00:00Z','id':1,'expired':False},
            {'name':'mcl-v325-audit-b0-root111','created_at':'2026-10-21T12:00:00Z','id':2,'expired':False},
            {'name':'mcl-v325-audit-b50-root222','created_at':'2026-10-21T12:00:00Z','id':3,'expired':False},
            {'name':'mcl-v325-audit-b50-root111','created_at':'2026-10-21T12:00:00Z','id':4,'expired':True},
        ]}]
        selected=select_batches(pages,111)
        self.assertEqual(list(selected),[0])
        self.assertEqual(selected[0]['id'],2)

if __name__=='__main__':unittest.main()
