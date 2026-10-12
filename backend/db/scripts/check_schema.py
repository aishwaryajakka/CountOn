"""Read-only checks of public tables and the applied Alembic revision."""

from _common import run_cli


def main() -> int:
    from sqlalchemy.orm import Session

    from app.db.base import Base
    from app.db.session import engine
    from app.services.readiness import inspect_readiness
    try:
        with Session(engine) as db:
            result = inspect_readiness(db)
        if result.code.startswith("DATABASE_") or result.code == "MIGRATION_FILES_UNAVAILABLE":
            print(f"FAIL {result.code}; inspect private service configuration and safe readiness logs")
            return 1
        for table in sorted(set(Base.metadata.tables) | {"alembic_version"}):
            print(f"{'FAIL' if table in result.missing_tables else 'PASS'} {table}")
        print(f"Alembic revision: {', '.join(result.observed) or 'unavailable'}")
        print(f"Expected revision: {', '.join(result.expected)}")
        for column in result.missing_columns:
            print(f"FAIL column {column}")
        print(f"{'PASS' if result.ready else 'FAIL'} {result.code}")
        if not result.ready:
            print("Review migration plan before applying changes; this check does not migrate.")
        return int(not result.ready)
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
