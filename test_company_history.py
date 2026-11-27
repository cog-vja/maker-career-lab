"""Offline checks for the review boundary and reproducible EDINET history."""
from datetime import date
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from company_history import ARCHIVE, EDINET_PDF, History, atomic_create, dataset, record_monthly, record_reviewed
from expand_manufacturers_v325 import GateError, METRICS, parse_public
from monthly_edinet_v325 import analyze


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "company-data.js"
PRODUCTION_SHA = "c862b96a08df3a039b865aa127a0b255367b5df3615045fc51006a93af9096c4"


class CompanyHistoryTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.archive = self.root / "history"
        shutil.copytree(ROOT / ARCHIVE, self.archive)
        self.history = History(self.archive)
        self.baseline = self.history.render()
        self.source = self.root / "original.js"
        self.source.write_text(self.baseline, encoding="utf-8")
        self.latest_path = self.root / "candidate.js"
        self.proof_path = self.root / "review.json"

    def candidate(self, **changes):
        raw, match, rows, _ = parse_public(self.source)
        first = rows[0]
        first.update(changes)
        payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
        self.latest_path.write_text(raw[:match.start(2)] + payload + raw[match.end(2):], encoding="utf-8")
        return first

    def test_restoration_and_historical_facts(self):
        initial = History(self.archive, through=1)
        self.assertEqual(initial.head, PRODUCTION_SHA)
        self.assertEqual(len(initial.latest), 1089)
        self.assertEqual(len(initial.records), 1095)
        historic = [item for item in initial.records.values() if item["kind"] == "historical"]
        self.assertEqual(len(historic), 6)
        self.assertTrue(all(item["acquired_at"] is None for item in historic))
        self.assertEqual(self.history.head, dataset(SOURCE)[0])
        self.assertEqual(self.baseline.encode(), SOURCE.read_bytes())

    def test_real_monthly_validation_then_archive_only_good_filings(self):
        chosen = [
            {**row, "edinet": self.history.registry[code]["edinet_code"]}
            for code, row in self.history.latest.items() if row["period"].endswith("2026-03-31")
        ][:2]
        self.assertEqual(len(chosen), 2)
        valid, mismatched = chosen
        ticker = str(valid["id"])
        doc = "S100ZZ10"
        def filing(row, number, issuer):
            return {"secCode": str(row["id"]) + "0", "docID": number,
                    "edinetCode": issuer, "docTypeCode": "120", "withdrawalStatus": "0",
                    "xbrlFlag": "1", "csvFlag": "1", "periodStart": "2026-04-01",
                    "periodEnd": "2026-09-30", "submitDateTime": "2026-10-01 12:00:00"}
        submissions = [filing(valid, doc, valid["edinet"]), filing(mismatched, "S100ZZ20", "E99999")]
        audit = {
            "ticker": ticker, "status": "SOURCE_RECONCILED_6_OF_6_REQUIRES_REVIEW",
            "verifiedMetricCount": 6, "gaap": valid["accountingStandard"],
            "financialScope": "提出会社単体" if valid["scope"].startswith("提出会社単体") else "連結",
            "periodStart": "2026-04-01", "periodEnd": "2026-09-30", "docID": doc,
            "sourceOriginalSha256": "a" * 64, "sourceXbrlSha256": "b" * 64,
            "sourcePayloadFingerprint": "c" * 64, "verifiedAt": "2026-10-22",
            "metrics": {key: {"status": "SOURCE_RECONCILED", "value": valid[field]}
                        for key, field in METRICS.items()},
        }
        with patch("monthly_edinet_v325._audit_one", return_value=audit) as auditor:
            report = analyze(self.source, self.root, days=1, delay=0, asof=date(2026, 10, 22),
                             day_fetcher=lambda _: submissions, zip_fetcher=lambda _: b"fixture",
                             issuer_registry=self.archive / "issuer-registry.json")
        self.assertEqual((report["verified_updates"], report["review_required"]), (1, 1))
        self.assertEqual(auditor.call_count, 1)
        candidate = self.root / "company-data-VERIFIED-REVIEW.js"
        summary = self.root / "monthly-summary-v325.json"
        details = self.root / "monthly-details-v325.json"
        args = (self.source, candidate, summary, details, "a" * 40, 123)
        past_files = list((self.archive / "releases").glob("*.jsonl"))
        past = {path: path.read_bytes() for path in past_files}
        self.assertEqual(record_monthly(History(self.archive), *args, dry_run=True), {"new_period": 1})
        self.assertEqual(list((self.archive / "releases").glob("*.jsonl")), past_files)
        self.assertEqual(record_monthly(self.history, *args), {"new_period": 1})
        reloaded = History(self.archive)
        self.assertEqual(reloaded.render().encode(), candidate.read_bytes())
        self.assertEqual(reloaded.latest[str(mismatched["id"])],
                         History(self.archive, through=self.history.version - 1).latest[str(mismatched["id"])])
        self.assertEqual(record_monthly(reloaded, *args), {})
        self.assertEqual({path: path.read_bytes() for path in past_files}, past)

    def test_same_fiscal_period_amendment_and_unchanged_original_processing_revision(self):
        old = next(iter(self.history.latest.values()))
        changed = self.candidate(sourceDocId="S100ZZA1", sourceSha256="3"*64,
                                 averageSalary=old["averageSalary"] + 1)
        ticker = str(old["id"])
        issuer = self.history.registry[ticker]["edinet_code"]
        proof = {"kind": "amendment", "edinet_code": issuer, "document_type": "130",
                 "document": changed["sourceDocId"], "supersedes_document": old["sourceDocId"],
                 "source": EDINET_PDF + changed["sourceDocId"] + ".pdf"}
        self.proof_path.write_text(json.dumps({ticker: proof}), encoding="utf-8")
        self.assertEqual(record_reviewed(self.history, self.latest_path, self.proof_path, "a" * 40),
                         {"amendment": 1})
        self.source.write_bytes(self.latest_path.read_bytes())
        self.candidate(averageSalary=old["averageSalary"] + 2)
        proof = {"kind": "processing_revision", "edinet_code": issuer,
                 "source_sha256": changed["sourceSha256"],
                 "review": "https://github.com/cog-vja/maker-career-lab/pull/1"}
        self.proof_path.write_text(json.dumps({ticker: proof}), encoding="utf-8")
        self.assertEqual(record_reviewed(History(self.archive), self.latest_path, self.proof_path, "a" * 40),
                         {"processing_revision": 1})
        self.assertEqual(History(self.archive).render().encode(), self.latest_path.read_bytes())
        self.assertEqual(History(self.archive, through=1).head, PRODUCTION_SHA)

    def test_missing_optional_field_stays_missing_and_timestamps_do_not_duplicate_facts(self):
        count = len(self.history.records)
        self.candidate(averageAge=None, verifiedAt="2026-11-26")
        self.proof_path.write_text("{}", encoding="utf-8")
        self.assertEqual(record_reviewed(self.history, self.latest_path, self.proof_path, "a" * 40),
                         {"metadata": 1})
        final = History(self.archive)
        self.assertEqual(len(final.records), count)
        self.assertIsNone(next(iter(final.latest.values()))["averageAge"])
        self.assertEqual(final.render().encode(), self.latest_path.read_bytes())

    def test_failed_stage_and_concurrent_write_leave_archive_intact(self):
        existing = {path: path.read_bytes() for path in (self.archive / "releases").glob("*.jsonl")}
        self.candidate(sourceDocId="UNREVIEWED", averageSalary=90000)
        self.proof_path.write_text("{}", encoding="utf-8")
        with self.assertRaises(GateError):
            record_reviewed(self.history, self.latest_path, self.proof_path, "a" * 40)
        target = next(iter(existing))
        with self.assertRaises(FileExistsError):
            atomic_create(target, "not a valid release")
        self.assertEqual({path: path.read_bytes() for path in existing}, existing)

    def test_dry_run_no_update_preserves_full_archive(self):
        self.proof_path.write_text("{}", encoding="utf-8")
        self.latest_path.write_bytes(self.source.read_bytes())
        count = self.history.version
        self.assertEqual(record_reviewed(self.history, self.latest_path, self.proof_path, "a" * 40), {})
        self.assertEqual(History(self.archive).version, count)
        self.assertEqual(dataset(self.latest_path)[0], self.history.head)
