import hashlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from download_edinet_originals_v312 import load_targets, verify_zip, download_all


def valid_zip():
    output=io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('XBRL/PublicDoc/sample.xbrl','<xbrl/>')
        z.writestr('XBRL/PublicDoc/sample.htm','<html/>')
    return output.getvalue()

class Tests(unittest.TestCase):
    def test_target_set(self):
        targets=load_targets('discovery-v31.json')
        self.assertEqual(len(targets),9)
        self.assertNotIn('6645',{t['ticker'] for t in targets})
        self.assertEqual(len({t['docID'] for t in targets}),9)
    def test_valid_zip(self):
        meta=verify_zip(valid_zip())
        self.assertEqual(meta['xbrl_count'],1)
        self.assertEqual(meta['html_count'],1)
    def test_nonzip_rejected(self):
        with self.assertRaises(ValueError):verify_zip(b'not a zip')
    def test_no_publicdoc_rejected(self):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:z.writestr('other/file.xbrl','x')
        with self.assertRaises(ValueError):verify_zip(out.getvalue())
    def test_manifest_and_download(self):
        targets=load_targets('discovery-v31.json')
        with tempfile.TemporaryDirectory() as tmp:
            archive=valid_zip()
            m=download_all(targets,'fake',tmp,fetcher=lambda docid,key:archive,delay=0)
            self.assertEqual(m['completed_count'],9)
            self.assertEqual(m['failed_count'],0)
            self.assertEqual(len(list((Path(tmp)/'originals').glob('*.zip'))),9)
            for x in m['companies']:
                self.assertEqual(x['sha256'],hashlib.sha256(archive).hexdigest())
                self.assertEqual(x['status'],'verified')
            self.assertEqual(json.loads((Path(tmp)/'manifest.json').read_text())['quality_status'],'BLOCKED')
    def test_partial_failure_persisted(self):
        targets=load_targets('discovery-v31.json')
        def failing(docid,key):
            if docid==targets[0]['docID']:raise ValueError('error')
            return valid_zip()
        with tempfile.TemporaryDirectory() as tmp:
            m=download_all(targets,'fake',tmp,fetcher=failing,delay=0)
            self.assertEqual(m['failed_count'],1)
            self.assertEqual(m['completed_count'],8)
            self.assertTrue((Path(tmp)/'manifest.json').exists())

if __name__ == '__main__':unittest.main()
