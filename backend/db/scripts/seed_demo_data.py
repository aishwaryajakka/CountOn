"""Seed/reuse tagged Ashley Mccormick mock data for the selected database."""
from _common import run_cli
from _demo import run,seed


def main():
    result=run(seed)
    print('Demo profile: ready')
    for label,key in [('Integration connections','connections'),('Expectations','expectations'),('Evidence rows','evidence'),('Evaluations','evaluations'),('Notifications','notifications')]:
        print(f'{label}: {result[key]}')
    print('DEMO DATA READY')
    return 0


if __name__=='__main__':raise SystemExit(run_cli(main))
