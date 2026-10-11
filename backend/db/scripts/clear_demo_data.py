"""Delete only the configured identity's explicitly tagged demo artifacts."""
from _common import run_cli
from _demo import clear, run


def main():
    run(clear)
    print('Demo data removed')
    return 0


if __name__=='__main__':raise SystemExit(run_cli(main))
