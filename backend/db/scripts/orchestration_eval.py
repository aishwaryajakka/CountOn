"""Offline synthetic golden evaluation. Human approval is a separate release gate.

No database, inbox, calendar, AWS call or private data is read. Output contains only
aggregate counts/timing; it is not live extraction accuracy or cloud latency/cost.
"""

import argparse
import base64
import json
import os
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from app.integrations.extraction_cache import ExtractionCache
from app.integrations.normalization import calendar_facts, mail_facts
from app.integrations.worker import matches
from app.monitoring.correlation import association
from app.schemas.provider_sync import SourceRule

DATASET = (
    Path(__file__).resolve().parents[2] / "tests/fixtures/orchestration-golden.json"
)


def email_payload(text):
    return {
        "id": "synthetic",
        "threadId": "t1",
        "internalDate": "1791806400000",
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "From", "value": "fixture@example.test"},
                {"name": "Subject", "value": "Synthetic fixture"},
            ],
            "body": {"data": base64.urlsafe_b64encode(text.encode()).decode()},
        },
    }


def run_case(case):
    if case["operation"] == "association":
        result = association([SourceRule.model_validate(r) for r in case["rules"]])
        return result == case["expected_association"], None
    if case["operation"] == "match":
        predicted = matches(
            case["facts"], case["external_id"], SourceRule.model_validate(case["rule"])
        )
        return predicted == case["expected_match"], predicted
    if case["operation"] not in ("email", "calendar"):
        raise ValueError("Unknown golden operation")
    provider = case.get("provider", "google")
    facts = (
        mail_facts(case.get("payload") or email_payload(case["text"]), provider)
        if case["operation"] == "email"
        else calendar_facts(case["event"], provider)
    )
    return all(
        facts.get(key) == value for key, value in case["expected"].items()
    ) and all(key not in facts for key in case["absent"]), None


def evaluate(dataset, *, require_review=False):
    cases = dataset["cases"]
    if not cases or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Golden cases must be nonempty and uniquely identified")
    pending = sum(
        c["critical"]
        and (c["review_status"] != "human_reviewed" or not c["reviewed_by"])
        for c in cases
    )
    if require_review and pending:
        return {"blocked": True, "pending_human_review": pending}
    durations, passed, tp, fp, fn = [], 0, 0, 0, 0
    for case in cases:
        start = perf_counter()
        correct, predicted = run_case(case)
        durations.append((perf_counter() - start) * 1000)
        passed += correct
        if predicted is not None:
            tp += predicted and case["expected_match"]
            fp += predicted and not case["expected_match"]
            fn += not predicted and case["expected_match"]
    return {
        "blocked": False,
        "cases": len(cases),
        "passed": passed,
        "pending_human_review": pending,
        "matching_true_positive": tp,
        "matching_false_positive": fp,
        "matching_false_negative": fn,
        "median_ms": statistics.median(durations),
        "p95_ms": sorted(durations)[max(0, int(len(durations) * 0.95) - 1)],
        "bedrock_calls": 0,
    }


def benchmark(repeat):
    payload = email_payload("Total due: $162.00")
    cache, calls = ExtractionCache(), [0]

    def normalize(value):
        calls[0] += 1
        return mail_facts(value, "google")

    start = perf_counter()
    for _ in range(repeat):
        cache.extract(
            ("synthetic-owner", "connection", "generation", "inbox"),
            "synthetic",
            "email",
            payload,
            normalize,
        )
    cache.close()
    return {
        "records": repeat,
        "normalizations": calls[0],
        "hits": repeat - calls[0],
        "duration_ms": (perf_counter() - start) * 1000,
        "bedrock_calls": 0,
    }


# These existing suites cover compilation, stateful clarification, model failures,
# security, source choice, provider normalization, real SQL workers and correlation.
REGRESSION_MODULES = (
    "test_expectation_compiler",
    "test_clarification",
    "test_bedrock",
    "test_source_planning",
    "test_source_correlation",
    "test_provider_sync",
    "test_automatic_tracking",
    "test_orchestration_budgets",
    "test_release_journey",
)


def mocked_regressions():
    """Opt-in isolated test execution; never infer success from prior reports."""
    try:
        url = make_url(os.environ.get("TEST_DATABASE_URL", ""))
        if url.host not in ("localhost", "127.0.0.1", "::1") or not (
            url.database or ""
        ).endswith("_test"):
            return {
                "status": "BLOCKED",
                "reason": "Requires explicit loopback *_test database",
            }
    except (ArgumentError, ValueError):
        return {
            "status": "BLOCKED",
            "reason": "Requires explicit loopback *_test database",
        }
    with tempfile.TemporaryDirectory(prefix="counton-eval-") as directory:
        report = Path(directory) / "tests.xml"
        result = subprocess.run(  # no shell, fixed test paths, output never printed
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "--tb=short",
                f"--junitxml={report}",
                *[f"tests/{name}.py" for name in REGRESSION_MODULES],
            ],
            cwd=Path(__file__).resolve().parents[2],
            capture_output=True,
            timeout=600,
            check=False,
        )
        if not report.exists():
            return {"status": "FAIL", "exit_code": result.returncode}
        suites = ET.parse(report).getroot().iter("testsuite")
        counts = {key: 0 for key in ("tests", "failures", "errors", "skipped")}
        for suite in suites:
            for key in counts:
                counts[key] += int(suite.get(key, "0"))
        return {
            "status": "PASS"
            if result.returncode == 0 and not counts["skipped"]
            else "FAIL",
            "exit_code": result.returncode,
            **counts,
        }


def categories(dataset, synthetic, *, mocked=None):
    reviewed = [
        c
        for c in dataset["cases"]
        if c["review_status"] == "human_reviewed" and c["reviewed_by"]
    ]
    human = evaluate({"cases": reviewed}) if reviewed else None
    return {
        "synthetic_agreement": {
            "status": "PASS"
            if synthetic.get("passed") == synthetic.get("cases")
            and not synthetic.get("blocked")
            else "FAIL",
            "cases": synthetic.get("cases"),
            "passed": synthetic.get("passed"),
        },
        "human_reviewed": {
            "status": "BLOCKED"
            if not human or synthetic["pending_human_review"]
            else "PASS"
            if human["passed"] == human["cases"]
            else "FAIL",
            "reviewed_cases": len(reviewed),
            "reviewed_passed": human["passed"] if human else 0,
            "pending": synthetic["pending_human_review"],
        },
        "mocked_provider_regressions": mocked
        or {
            "status": "BLOCKED",
            "reason": "Not run; use --run-regressions with isolated TEST_DATABASE_URL",
        },
        "live_provider_verification": {
            "status": "BLOCKED",
            "reason": "Requires real consent, subscribed events and recorded acceptance",
        },
        "real_bedrock_verification": {
            "status": "BLOCKED",
            "reason": "Requires real AWS/model acceptance; offline tests do not invoke AWS",
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-human-review", action="store_true")
    parser.add_argument(
        "--repeat", type=int, choices=range(1, 1001), default=200, metavar="1..1000"
    )
    parser.add_argument(
        "--run-regressions",
        action="store_true",
        help="Run existing mocked-provider/SQL intelligence suites on explicit local test DB",
    )
    args = parser.parse_args()
    dataset = json.loads(DATASET.read_text())
    report = evaluate(dataset)
    separated = categories(
        dataset, report, mocked=mocked_regressions() if args.run_regressions else None
    )
    print(json.dumps({"verification_categories": separated}, sort_keys=True))
    print(json.dumps(report, sort_keys=True))
    if args.require_human_review and report["pending_human_review"]:
        print("BLOCKED critical golden cases require recorded human review")
        return 2
    print(
        "Synthetic unchanged-record benchmark:",
        json.dumps(benchmark(args.repeat), sort_keys=True),
    )
    print("Live provider accuracy, AWS latency and billed cost: NOT MEASURED")
    return int(
        report["passed"] != report["cases"]
        or (
            args.run_regressions
            and separated["mocked_provider_regressions"]["status"] != "PASS"
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
