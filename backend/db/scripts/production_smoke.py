"""Offline startup/transport/worker smoke; real local PostgreSQL, mocked providers.

Never probes a production account or claims live Alexa/Bedrock verification.
"""

import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
GROUPS = {
    "API startup and six MCP contracts": ["tests/test_startup.py"],
    "Streamable HTTP and ownership": ["tests/test_mcp_network.py"],
    "Signed Alexa verification and dialogue": ["tests/test_alexa.py"],
    "Durable conversations and shared monitoring persistence": [
        "tests/test_production_conversations.py"
    ],
    "Confirmed capture, provider tracking and notification recovery": [
        "tests/test_release_journey.py",
        "tests/test_automatic_tracking.py",
    ],
    "Source planning, cross-provider correlation and operation budgets": [
        "tests/test_source_planning.py",
        "tests/test_source_correlation.py",
        "tests/test_orchestration_budgets.py",
        "tests/test_orchestration_eval.py",
    ],
}


def main():
    if not os.environ.get("TEST_DATABASE_URL"):
        print(
            "BLOCKED: set TEST_DATABASE_URL to a distinct loopback database ending in _test"
        )
        return 2
    failed = False
    for label, paths in GROUPS.items():
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--tb=short", *paths],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        # Never echo subprocess exceptions/SQL or configuration. Full diagnostics
        # are available by running the named tests directly against a test database.
        print(("PASS" if result.returncode == 0 else "FAIL") + " " + label)
        failed |= result.returncode != 0
    print("External cloud/device acceptance: NOT RUN")
    return int(failed)


if __name__ == "__main__":
    raise SystemExit(main())
