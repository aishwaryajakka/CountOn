"""Run the deterministic acceptance scenarios on the configured local database."""

from _common import require_target, run_cli
from _acceptance import run_acceptance


def main() -> int:
    if not require_target("local"):
        return 1
    return run_acceptance("LOCAL")


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
