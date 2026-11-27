#!/usr/bin/env python3
"""Maintain the review-only, offline history of source-verified public filings."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import math
import os
from pathlib import Path
import re
import subprocess
from tempfile import NamedTemporaryFile

from expand_manufacturers_v325 import GateError, METRICS, parse_public
from monthly_publish_v326 import validate_monthly


ARCHIVE = Path("data/company-history")
EDINET_PDF = "https://disclosure2dl.edinet-fsa.go.jp/searchdocument/pdf/"
TICKER = re.compile(r"[0-9A-Z]{4}")
FILER = re.compile(r"E[0-9]{5}")
DOC = re.compile(r"S[0-9A-Z]{7,15}")
SHA = re.compile(r"[0-9a-f]{64}")
BASE_FINANCIAL_FIELDS = {*METRICS.values(), "averageAge", "averageTenure", "employeeCount"}
FACT_FIELDS = BASE_FINANCIAL_FIELDS | {
    "period", "scope", "salaryScope", "accountingStandard", "sourceDocId", "sourceSha256",
}
KINDS = {"baseline", "historical", "new_period", "amendment", "processing_revision", "metadata"}


def need(condition, message):
    if not condition:
        raise GateError(message)


def json_text(value, *, sort_keys=False):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=sort_keys,
                      allow_nan=False)


def digest(text):
    return sha256(text.encode("utf-8")).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def fiscal_period(row):
    start, end = (date.fromisoformat(text) for text in row["period"].split("〜"))
    need(start < end, f"Invalid fiscal period: {row.get('id')}")
    return start, end


def scope_identity(row):
    return row["scope"], row["salaryScope"], row["accountingStandard"]


def check_row(row):
    ticker = str(row["id"])
    need(matches(TICKER, ticker) and row.get("name"), f"Missing issuer identity: {ticker}")
    need(matches(DOC, row.get("sourceDocId")) and matches(SHA, row.get("sourceSha256")),
         f"Missing matched EDINET document and original hash: {ticker}")
    need(row.get("sourceUrl") == "https://disclosure2.edinet-fsa.go.jp/",
         f"Unexpected public source URL: {ticker}")
    need(row.get("scope") in {"連結（給与のみ提出会社）", "提出会社単体（給与も同一法人）"}
         and row.get("salaryScope") == "提出会社単体"
         and row.get("accountingStandard") in {"JP_GAAP", "IFRS", "US_GAAP"},
         f"Unknown financial or payroll scope: {ticker}")
    fiscal_period(row)
    for field in BASE_FINANCIAL_FIELDS:
        value = row.get(field)
        if value is not None:
            need(type(value) in (int, float) and math.isfinite(value),
                 f"Nonfinite source value: {ticker} {field}")
    for field in ("sourceXbrlSha256", "sourcePayloadFingerprint"):
        if row.get(field) is not None:
            need(matches(SHA, row[field]), f"Invalid source digest: {ticker} {field}")
    if row.get("averageSalary") is not None:
        need(100 <= row["averageSalary"] <= 10_000, f"Out-of-range salary: {ticker}")
    for field in ("revenue", "revenuePrev", "employeeCount"):
        need(row.get(field) is None or row[field] >= 0, f"Negative nonnegative field: {ticker} {field}")


def archive_id(ticker, entry):
    need(entry is not None, f"Issuer {ticker} is missing from the reviewed registry")
    edinet = entry["edinet_code"]
    if edinet is None:
        return f"filing:{ticker}:{entry['anchor_document']}"
    need(matches(FILER, edinet), f"Invalid EDINET issuer code: {ticker}")
    return f"edinet:{edinet}"


def fact_hash(row, identity):
    return digest(json_text([identity, {k: row.get(k) for k in FACT_FIELDS}], sort_keys=True))


def operating_margin(row):
    revenue, profit = row.get("revenue"), row.get("operatingProfit")
    return 100 * profit / revenue if revenue and profit is not None else None


def review_evidence(row, prior, identity, evidence):
    ticker = str(row["id"])
    need(isinstance(evidence, dict) and evidence.get("edinet_code") == identity.removeprefix("edinet:")
         and identity.startswith("edinet:"), f"Reviewed change needs EDINET identity: {ticker}")
    kind = evidence.get("kind")
    if kind == "amendment":
        need(evidence.get("document_type") == "130"
             and evidence.get("document") == row["sourceDocId"]
             and evidence.get("supersedes_document") == prior["sourceDocId"]
             and row["sourceDocId"] != prior["sourceDocId"]
             and evidence.get("source") == EDINET_PDF + row["sourceDocId"] + ".pdf",
             f"Amendment proof does not identify the replacement filing: {ticker}")
    elif kind == "processing_revision":
        need(row["sourceDocId"] == prior["sourceDocId"] and row["sourceSha256"] == prior["sourceSha256"]
             and matches(SHA, evidence.get("source_sha256"))
             and evidence["source_sha256"] == row["sourceSha256"]
             and isinstance(evidence.get("review"), str)
             and re.fullmatch(r"https://github\.com/cog-vja/maker-career-lab/(?:pull/\d+|commit/[0-9a-f]{40})",
                              evidence["review"]),
             f"Processing revision needs unchanged original and a review reference: {ticker}")
    else:
        raise GateError(f"Unknown correction type: {ticker}")
    return kind


class History:
    def __init__(self, directory, through=None):
        self.directory = Path(directory)
        registry = read_json(self.directory / "issuer-registry.json")
        need(registry["schema_version"] == 1, "Unsupported issuer registry schema")
        self.registry = registry["issuers"]
        identities = [archive_id(ticker, entry) for ticker, entry in self.registry.items()]
        need(len(identities) == len(set(identities)), "Issuer registry has duplicate stable identifiers")
        self.latest = {}
        self.records = {}
        self.version = 0
        self.head = None
        self.layout = None
        self.meta = None
        for release in sorted((self.directory / "releases").glob("*.jsonl")):
            with release.open(encoding="utf-8") as handle:
                header = json.loads(next(handle))
                rows = [json.loads(line) for line in handle]
            need(release.name == f"{self.version + 1:06d}.jsonl", "Missing or out-of-order release")
            self.apply(header, rows)
            if self.version == through:
                break
        if through is not None:
            need(self.version == through and through > 0, "The requested archive release was not found")

    def render(self):
        prefix, separator, suffix = self.layout
        return (prefix + json_text(list(self.latest.values())) + separator
                + json_text(self.meta) + suffix)

    def apply(self, header, records):
        need(header["schema_version"] == 1 and header["release"] == self.version + 1,
             "Unsupported history schema or release number")
        need(header["previous_dataset_sha256"] == self.head, "Archive release does not follow its parent")
        need(matches(SHA, header["dataset_sha256"]), "Missing published-file fingerprint")
        if self.version == 0:
            self.layout = header["layout"]
        need(header.get("layout", self.layout) == self.layout, "Published JS template changed")
        counts = Counter()
        for record in records:
            self.apply_record(record)
            counts[record["kind"]] += 1
        need(header["changes"] == counts, "History release has an incorrect change count")
        self.meta = header["dataset_metadata"]
        need(len(self.latest) == self.meta["count"] and digest(self.render()) == header["dataset_sha256"],
             "Archive rows cannot reconstruct the announced company-data.js")
        self.version += 1
        self.head = header["dataset_sha256"]

    def apply_record(self, record):
        kind, ticker = record["kind"], record["ticker"]
        need(kind in KINDS, f"Unknown record kind: {kind}")
        before = self.latest.get(ticker)
        if kind == "metadata":
            need(before is not None, f"Metadata change lacks current row: {ticker}")
            patch = record["patch"]
            row = {**before, **patch}
            identity = archive_id(ticker, self.registry.get(ticker))
            need("id" not in patch and fact_hash(row, identity) == fact_hash(before, identity),
                 f"Metadata edit changes facts: {ticker}")
            check_row(row)
            self.latest[ticker] = row
            return

        row = record["row"]
        check_row(row)
        identity = archive_id(ticker, self.registry.get(ticker))
        key = fact_hash(row, identity)
        need(str(row["id"]) == ticker and record["issuer"] == identity and record["fact"] == key
             and record["operating_margin_percent"] == operating_margin(row), f"Fact metadata mismatch: {ticker}")
        need(key not in self.records, f"Duplicate period data: {ticker}")
        if kind in {"amendment", "processing_revision", "new_period"}:
            need(before is not None and record.get("previous_fact") == fact_hash(before, identity),
                 f"Missing previous fact: {ticker}")
            need(scope_identity(row) == scope_identity(before), f"Changed accounting scope: {ticker}")
            if kind == "new_period":
                need(fiscal_period(row)[1] > fiscal_period(before)[1]
                     and row["sourceDocId"] != before["sourceDocId"]
                     and record.get("observed_edinet_code") == identity.removeprefix("edinet:")
                     and identity.startswith("edinet:"), f"New period or issuer does not match: {ticker}")
            else:
                need(fiscal_period(row) == fiscal_period(before)
                     and review_evidence(row, before, identity, record.get("evidence")) == kind,
                     f"Same-period correction is not reviewable: {ticker}")
        else:
            need(self.version == 0 and before is None, f"Import can only run at initialization: {ticker}")
        self.records[key] = record
        if kind != "historical":
            self.latest[ticker] = row


def period_record(history, row, kind, **fields):
    check_row(row)
    ticker = str(row["id"])
    identity = archive_id(ticker, history.registry.get(ticker))
    return {
        "kind": kind, "ticker": ticker, "issuer": identity, "fact": fact_hash(row, identity),
        "operating_margin_percent": operating_margin(row), "row": row, **fields,
    }


def dataset(path):
    raw, match, rows, meta = parse_public(path)
    need(meta.get("count") == len(rows), "Dataset count does not match")
    layout = [raw[:match.start(2)], raw[match.end(2):match.start(4)], raw[match.end(4):]]
    return sha256(Path(path).read_bytes()).hexdigest(), rows, meta, layout


def atomic_create(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent) as pending:
        pending.write(content)
        pending.flush()
        os.fsync(pending.fileno())
        # The numbered filename is the lock: two writers cannot replace one another.
        os.link(pending.name, path)


def save_release(history, source, records, observation, *, dry_run=False):
    sha, _, meta, layout = dataset(source)
    header = {
        "schema_version": 1, "release": history.version + 1,
        "previous_dataset_sha256": history.head, "dataset_sha256": sha,
        "dataset_metadata": meta, "observation": observation,
        "changes": dict(Counter(record["kind"] for record in records)),
    }
    if history.version == 0:
        header["layout"] = layout
    history.apply(header, records)
    if not dry_run:
        path = history.directory / "releases" / f"{history.version:06d}.jsonl"
        lines = "".join(json_text(item) + "\n" for item in (header, *records))
        atomic_create(path, lines)
    return header["changes"]


def from_git(commit):
    """Read the exact historically released company-data.js without fetching."""
    want = re.fullmatch(r"[0-9a-f]{40}", commit)
    need(want is not None, "Historical source needs a full Git commit hash")
    contents = subprocess.check_output(["git", "show", f"{commit}:company-data.js"])
    with NamedTemporaryFile() as path:
        path.write(contents)
        path.flush()
        return dataset(path.name)


def initialize(history, source, commit, historical_commit, captured, deployed_at, *, dry_run=False):
    if history.head == dataset(source)[0]:
        return {}
    need(history.head is None, "Initialization requires an empty release directory")
    checksum, current, _, _ = dataset(source)
    need(checksum == from_git(commit)[0], "Bootstrap input does not match the published Git snapshot")
    need(datetime.fromisoformat(deployed_at) <= datetime.fromisoformat(captured),
         "Deployment evidence must precede archive capture")
    by_code = {str(row["id"]): row for row in current}
    records = []
    for old in from_git(historical_commit)[1]:
        ticker = str(old["id"])
        now = by_code[ticker]
        need(old["name"] == now["name"], f"Historical issuer changed: {ticker}")
        if fiscal_period(old) == fiscal_period(now):
            need(fact_hash(old, "") == fact_hash(now, ""), f"Unreviewed same-period difference: {ticker}")
            continue
        need(fiscal_period(old)[1] < fiscal_period(now)[1], f"Historical period is not earlier: {ticker}")
        records.append(period_record(
            history, old, "historical", source_commit=historical_commit,
            reconstructed_at=captured, acquired_at=None,
        ))
    records.extend(period_record(history, row, "baseline") for row in current)
    return save_release(history, source, records, {
        "kind": "public_baseline", "captured_at": captured, "source_commit": commit,
        "acquired_at": None, "production_verified_at": captured, "deployed_build_completed_at": deployed_at,
    }, dry_run=dry_run)


def record_monthly(history, baseline, candidate, summary, details, commit, run_id, *, dry_run=False):
    if Path(candidate).is_file() and history.head == dataset(candidate)[0]:
        return {}
    need(history.head == dataset(baseline)[0], "Capture the current main dataset before updating")
    plan = validate_monthly(baseline, candidate, summary, details)
    report = read_json(details)
    if not plan["updated"]:
        return {}
    updated = {str(change["ticker"]): change for change in report if change["status"] == "VERIFIED_NEW_PERIOD"}
    records = []
    for row in dataset(candidate)[1]:
        ticker = str(row["id"])
        if ticker not in updated:
            continue
        identity = archive_id(ticker, history.registry.get(ticker))
        records.append(period_record(
            history, row, "new_period", previous_fact=fact_hash(history.latest[ticker], identity),
            observed_edinet_code=updated[ticker].get("edinetCode"),
        ))
    # Keep statuses and public filing IDs. API exception strings stay in the existing evidence artifact.
    held = [
        {"ticker": str(item["ticker"]), "status": item["status"],
         "documents": [doc for doc in item.get("docIDs", [item.get("docID")]) if matches(DOC, doc)]}
        for item in report if item["status"] not in {"VERIFIED_NEW_PERIOD", "UNCHANGED"}
    ]
    return save_release(history, candidate, records, {
        "kind": "monthly_review", "observed_on_jst": read_json(summary)["as_of_jst"],
        "base_commit": commit, "workflow_run_id": run_id, "held": held,
    }, dry_run=dry_run)


def record_reviewed(history, candidate, evidence, commit, *, dry_run=False):
    sha, rows, _, _ = dataset(candidate)
    if history.head == sha:
        return {}
    need([str(row["id"]) for row in rows] == list(history.latest),
         "Issuer membership/order change requires a dedicated registry migration")
    records = []
    proofs = read_json(evidence)
    for row in rows:
        ticker = str(row["id"])
        old = history.latest[ticker]
        if row == old:
            continue
        check_row(row)
        identity = archive_id(ticker, history.registry.get(ticker))
        need(old.keys() <= row.keys(), f"Reviewed row removed fields: {ticker}")
        if fact_hash(row, identity) == fact_hash(old, identity):
            records.append({"kind": "metadata", "ticker": ticker,
                            "patch": {k: v for k, v in row.items() if k not in old or old[k] != v}})
            continue
        proof = proofs[ticker]
        if fiscal_period(row)[1] > fiscal_period(old)[1]:
            need(proof.get("document_type") == "120" and proof.get("document") == row["sourceDocId"]
                 and proof.get("source") == EDINET_PDF + row["sourceDocId"] + ".pdf",
                 f"New period requires checked original: {ticker}")
            record = period_record(history, row, "new_period",
                                   observed_edinet_code=proof.get("edinet_code"))
        else:
            kind = review_evidence(row, old, identity, proof)
            fields = ("kind", "edinet_code", "document_type", "document", "supersedes_document",
                      "source", "source_sha256", "review")
            record = period_record(history, row, kind,
                                   evidence={k: proof[k] for k in fields if k in proof})
        record["previous_fact"] = fact_hash(old, identity)
        records.append(record)
    need(records, "No changes to the published issuer rows were found")
    return save_release(history, candidate, records, {
        "kind": "reviewed_update", "base_commit": commit,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "acquired_at": None,
    }, dry_run=dry_run)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    command = parser.add_subparsers(dest="command", required=True)
    bootstrap = command.add_parser("initialize")
    bootstrap.add_argument("--source", default="company-data.js")
    bootstrap.add_argument("--commit", required=True)
    bootstrap.add_argument("--historical-commit", required=True)
    bootstrap.add_argument("--captured", required=True)
    bootstrap.add_argument("--deployed-at", required=True)
    monthly = command.add_parser("stage-monthly")
    monthly.add_argument("--baseline", default="company-data.js")
    for flag in ("candidate", "summary", "details", "commit"):
        monthly.add_argument(f"--{flag}", required=True)
    monthly.add_argument("--run-id", type=int)
    reviewed = command.add_parser("stage-reviewed")
    for flag in ("candidate", "evidence", "commit"):
        reviewed.add_argument(f"--{flag}", required=True)
    for writer in (bootstrap, monthly, reviewed):
        writer.add_argument("--dry-run", action="store_true")
    check = command.add_parser("verify")
    check.add_argument("--source", default="company-data.js")
    restore = command.add_parser("restore")
    restore.add_argument("target", type=Path)
    restore.add_argument("--release", type=int)
    args = parser.parse_args()
    history = History(args.archive, through=getattr(args, "release", None))

    if args.command == "initialize":
        changes = initialize(history, args.source, args.commit, args.historical_commit,
                             args.captured, args.deployed_at, dry_run=args.dry_run)
    elif args.command == "stage-monthly":
        changes = record_monthly(history, args.baseline, args.candidate, args.summary, args.details,
                                 args.commit, args.run_id, dry_run=args.dry_run)
    elif args.command == "stage-reviewed":
        changes = record_reviewed(history, args.candidate, args.evidence, args.commit, dry_run=args.dry_run)
    elif args.command == "restore":
        need(history.head is not None, "Archive is empty")
        atomic_create(args.target, history.render())
        return
    else:
        need(history.head == dataset(args.source)[0], "Latest approved file and archive differ")
        changes = {}
    print(json.dumps({"changes": changes, "issuers": len(history.latest),
                      "facts": len(history.records), "latest_sha256": history.head}))


if __name__ == "__main__":
    main()
