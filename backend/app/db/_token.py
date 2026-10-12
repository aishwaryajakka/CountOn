"""Get a real access token without printing or storing it."""
import getpass
import os


def access_token() -> str:
    token = os.getenv("COUNTON_ACCESS_TOKEN")
    if not token:
        token = getpass.getpass("Supabase access token (hidden): ")
    if not token:
        raise RuntimeError("A real Supabase access token is required")
    return token
