"""Restore tooling must never target application or remote databases."""

import pytest

from db.scripts.backup_restore_smoke import test_url as validate_url


@pytest.mark.parametrize(
    "value",
    [
        "postgresql+psycopg://fixture@production.example/counton_test",
        "postgresql+psycopg://fixture@localhost/counton",
        "postgresql+psycopg://fixture@localhost/counton_test?host=production.example",
        "postgresql+psycopg://fixture@localhost/counton_test?service=production",
        "postgresql://fixture@localhost/counton_test",
        "postgresql+psycopg://fixture@localhost/application_test",
        "postgresql+psycopg://fixture@localhost/unsafe-name_test",
    ],
)
def test_unsafe_restore_target_denied(value):
    with pytest.raises(ValueError):
        validate_url(value, "application_test")


def test_distinct_loopback_test_target_accepted():
    url = validate_url("postgresql+psycopg://fixture@127.0.0.1/counton_test", "counton")
    assert url.host == "127.0.0.1" and url.database == "counton_test"
