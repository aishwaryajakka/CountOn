"""Use the same core logic after DATABASE_URL is switched to Supabase."""

from _common import run_cli
from _acceptance import run_acceptance


def main() -> int:
    return run_acceptance("SUPABASE")


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
