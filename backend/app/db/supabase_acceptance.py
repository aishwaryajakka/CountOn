"""Use the same core logic when DATABASE_TARGET selects Supabase."""

from _common import require_target, run_cli
from _acceptance import run_acceptance


def main() -> int:
    if not require_target("supabase"):
        return 1
    return run_acceptance("SUPABASE")


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
