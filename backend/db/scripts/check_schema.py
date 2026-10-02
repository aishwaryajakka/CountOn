"""Read-only checks of public tables and the applied Alembic revision."""

from _common import BACKEND_ROOT, run_cli


def main() -> int:
    from alembic.config import Config
    from alembic.script import ScriptDirectory
    from sqlalchemy import inspect, text
    from app.db.session import engine

    required = ("alembic_version", "expectations", "evidence", "evaluations")
    try:
        with engine.connect() as connection:
            tables = set(inspect(connection).get_table_names(schema="public"))
            for table in required:
                print(f"{'PASS' if table in tables else 'FAIL'} {table}")
            if "alembic_version" not in tables:
                print("Alembic revision: unavailable")
                return 1
            revisions = set(connection.scalars(text("SELECT version_num FROM public.alembic_version")))
        print(f"Alembic revision: {', '.join(sorted(revisions)) or 'none'}")
        expected = set(ScriptDirectory.from_config(Config(str(BACKEND_ROOT / "alembic.ini"))).get_heads())
        current = revisions == expected
        if not current:
            print("FAIL Alembic revision is not current; run alembic upgrade head")
        return 0 if set(required) <= tables and current else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
