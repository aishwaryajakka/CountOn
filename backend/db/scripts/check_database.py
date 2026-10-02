"""Read-only connection check using the application's configured engine."""

from _common import run_cli


def main() -> int:
    from sqlalchemy import text
    from app.db.session import engine

    try:
        with engine.connect() as connection:
            database, user, version = connection.execute(
                text("SELECT current_database(), current_user, version()")
            ).one()
        print("Connected successfully")
        print(f"Database: {database}")
        print(f"User: {user}")
        print(f"PostgreSQL: {version}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
