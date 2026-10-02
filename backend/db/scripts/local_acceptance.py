"""Run the deterministic acceptance scenarios on the configured local database."""

from _common import run_cli
from _acceptance import run_acceptance


def main() -> int:
    return run_acceptance("LOCAL")


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
