"""Normal identity tests mock Auth Admin; PostgreSQL cases use the isolated test DB."""
from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import Settings
from db.scripts._demo import DEMO_EMAIL, DEMO_NAME, LOCAL_DEMO_ID, configured_owner
from db.scripts._demo_identity import ensure_auth_user, ensure_demo_profile


def settings(**overrides):
    values = dict(supabase_secret_key=SecretStr("sb_secret_test_fixture"),
                  counton_demo_email=DEMO_EMAIL, counton_demo_user_id=None,
                  counton_demo_password=SecretStr("unit-test-only-generated-password"))
    return SimpleNamespace(**(values | overrides))


def test_canonical_identity_and_safe_settings_defaults(monkeypatch):
    for key in ("COUNTON_DEMO_USER_ID", "COUNTON_DEMO_EMAIL", "COUNTON_DEMO_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    value = Settings(_env_file=None, database_target="local",
                     local_database_url="postgresql+psycopg://localhost/test")
    assert value.counton_demo_email == DEMO_EMAIL == "demo@counton.app"
    assert DEMO_NAME == "Ashley Mccormick"
    assert value.counton_demo_password is None
    assert Settings.model_fields["counton_demo_password"].default is None
    hidden = settings().counton_demo_password
    assert hidden.get_secret_value() not in repr(value.model_copy(update={"counton_demo_password": hidden}))


def test_stable_local_uuid_and_explicit_override(monkeypatch):
    import dotenv
    monkeypatch.setattr(dotenv, "dotenv_values", lambda path: {})
    monkeypatch.delenv("COUNTON_DEMO_USER_ID", raising=False)
    assert configured_owner(SimpleNamespace(database_target="local")) == LOCAL_DEMO_ID
    assert LOCAL_DEMO_ID == UUID("741dc8cd-6d44-5e2f-bdc9-ce8b6d3df1e1")  # historical identity
    chosen = uuid4()
    monkeypatch.setenv("COUNTON_DEMO_USER_ID", str(chosen))
    assert configured_owner(SimpleNamespace(database_target="local")) == chosen


def test_auth_reuses_existing_account_without_password_or_write():
    owner = uuid4()
    requests = []
    def handler(request):
        requests.append(request)
        assert request.method == "GET"
        assert "authorization" not in request.headers  # modern secret is not a JWT
        return httpx.Response(200, json={"users": [{"id": str(owner), "email": DEMO_EMAIL}]})
    with httpx.Client(base_url="https://test.supabase.co", transport=httpx.MockTransport(handler)) as client:
        config = settings(counton_demo_password=None)
        assert ensure_auth_user(client, config) == owner
        assert ensure_auth_user(client, config) == owner
    assert len(requests) == 2


def test_auth_create_then_second_setup_reuses_uuid():
    owner = uuid4()
    created = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"users": created})
        assert request.method == "POST" and request.url.path == "/auth/v1/admin/users"
        import json
        body = json.loads(request.content)
        assert body["email"] == DEMO_EMAIL and body["email_confirm"] is True
        assert body["user_metadata"]["display_name"] == DEMO_NAME
        created.append({"id": str(owner), "email": DEMO_EMAIL})
        return httpx.Response(200, json={"id": str(owner)})
    with httpx.Client(base_url="https://test.supabase.co", transport=httpx.MockTransport(handler)) as client:
        assert ensure_auth_user(client, settings()) == owner
        assert ensure_auth_user(client, settings()) == owner
    assert len(created) == 1


def test_auth_pagination_before_creation_and_uuid_mismatch():
    owner = uuid4()
    def handler(request):
        assert request.method == "GET"
        users = [{"id": str(uuid4()), "email": "other@example.test"}] * 1000
        if request.url.params["page"] == "2":
            users = [{"id": str(owner), "email": DEMO_EMAIL.upper()}]
        return httpx.Response(200, json={"users": users})
    with httpx.Client(base_url="https://test.supabase.co", transport=httpx.MockTransport(handler)) as client:
        assert ensure_auth_user(client, settings()) == owner
        with pytest.raises(RuntimeError, match="UUID mismatch"):
            ensure_auth_user(client, settings(counton_demo_user_id=uuid4()))


def test_failed_lookup_never_creates_user():
    def handler(request):
        assert request.method == "GET"
        return httpx.Response(503)
    with httpx.Client(base_url="https://test.supabase.co", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            ensure_auth_user(client, settings())


def test_missing_password_does_not_create_account():
    def handler(request):
        assert request.method == "GET"
        return httpx.Response(200, json={"users": []})
    with httpx.Client(base_url="https://test.supabase.co", transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="password required"):
            ensure_auth_user(client, settings(counton_demo_password=None))


def test_concurrent_creation_reuses_winner_without_reset():
    owner = uuid4()
    posts = []
    def handler(request):
        if request.method == "GET":
            users = [{"id": str(owner), "email": DEMO_EMAIL}] if posts else []
            return httpx.Response(200, json={"users": users})
        assert request.method == "POST"
        posts.append(request)
        return httpx.Response(422, json={"code": "email_exists"})
    with httpx.Client(base_url="https://test.supabase.co", transport=httpx.MockTransport(handler)) as client:
        assert ensure_auth_user(client, settings()) == owner
    assert len(posts) == 1


@pytest.mark.integration
def test_profile_created_reused_and_canonical_name(db):
    owner = uuid4()
    first = ensure_demo_profile(db, owner)
    assert first.display_name == DEMO_NAME and first.timezone == "America/Chicago"
    assert ensure_demo_profile(db, owner) is first
    first.display_name = "Former demo name"
    db.commit()
    assert ensure_demo_profile(db, owner).display_name == DEMO_NAME


@pytest.mark.integration
def test_verified_auth_adopts_profile_without_deleting_application_data(db, users, numeric_payload):
    from app.schemas.expectation import ExpectationCreate
    from app.services.expectation_service import create_expectation
    from app.db.models import Expectation, Profile
    from db.scripts._demo import seed, clear
    owner = users[0].id
    original = create_expectation(db, ExpectationCreate(**numeric_payload), owner)
    with pytest.raises(RuntimeError, match="unrelated profile"):
        ensure_demo_profile(db, owner)
    profile = ensure_demo_profile(db, owner, verified_auth=True)
    assert profile.display_name == DEMO_NAME
    seed(db, owner)
    clear(db, owner)
    assert db.get(Expectation, original.id) is not None
    assert db.get(Profile, owner) is profile
