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
        print(f"FAIL {error_category(error)} ({type(error).__name__})")
        print("Check backend/.env.local, connectivity, and Alembic migrations.")
        return 1


def require_target(expected: str) -> bool:
    from app.core.config import get_settings
    if get_settings().database_target == expected:
        return True
    label = "Supabase" if expected == "supabase" else "local"
    print(f"Refusing to run {label} acceptance test because DATABASE_TARGET is not {expected}.")
    return False


def error_category(error: Exception) -> str:
    """Classify without returning credential-bearing exception text."""
    message = str(error).lower()
    if any(word in message for word in ("resolve", "name resolution", "nodename", "name or service", "getaddrinfo")):
        return "DNS/host resolution failure"
    if any(word in message for word in ("password authentication", "authentication failed", "tenant or user not found")):
        return "authentication failure"
    if any(word in message for word in ("ssl", "certificate", "tls")):
        return "SSL failure"
    if any(word in message for word in ("timeout", "timed out")):
        return "network timeout"
    if "connection refused" in message:
        return "connection refused"
    if any(word in message for word in ("operation not permitted", "permission denied")):
        return "network/access restriction"
    if type(error).__name__ in ("ValidationError", "ArgumentError", "ValueError"):
        return "invalid database configuration"
    return "verification failure"
