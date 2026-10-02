"""Shared CLI bootstrapping and credential-safe failures."""

import os
from pathlib import Path
import sys
from collections.abc import Callable

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("PGCONNECT_TIMEOUT", "10")


def run_cli(operation: Callable[[], int]) -> int:
    try:
        return operation()
    except KeyboardInterrupt:
        print("FAIL Verification interrupted")
        return 1
    except Exception as error:
        # Database and settings exceptions can include URLs/passwords. Never
        # print their message or traceback, even when connection setup fails.
        print(f"FAIL Verification failed ({type(error).__name__})")
        print("Check backend/.env.local, connectivity, and Alembic migrations.")
        return 1
