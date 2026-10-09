"""Ensure Ashley's local profile or real Supabase Auth account and profile."""
from _common import run_cli


def main() -> int:
    import httpx
    from sqlalchemy.orm import Session
    from app.core.config import get_settings
    from app.db.session import engine
    from db.scripts._demo import DEMO_NAME, configured_owner
    from db.scripts._demo_identity import ensure_auth_user, ensure_demo_profile

    settings = get_settings()
    cloud = settings.database_target == "supabase"
    try:
        if cloud:
            if not settings.supabase_url:
                print("Set SUPABASE_URL for demo Auth setup.")
                raise RuntimeError("Auth configuration required")
            with httpx.Client(base_url=settings.supabase_url.rstrip("/"), timeout=30) as client:
                owner = ensure_auth_user(client, settings)
        else:
            owner = configured_owner(settings)
        with engine.begin() as connection:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
                ensure_demo_profile(db, owner, verified_auth=cloud)
        print(f"Database target: {settings.database_target}")
        if cloud:
            print("Demo Auth user: ready")
        print("Demo profile: ready")
        print(f"Name: {DEMO_NAME}")
        print(f"Email: {settings.counton_demo_email}")
        print(f"User ID: {owner}")
        print("DEMO USER READY")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
