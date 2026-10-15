import pytest

from utils.secure_store import (
    SERVICE_NAME,
    get_secret,
    migrate_legacy_secret,
    set_secret,
)

pytestmark = pytest.mark.real_vault


def test_get_secret_returns_none_when_vault_has_no_entry(monkeypatch):
    monkeypatch.setattr("keyring.get_password", lambda service, name: None)

    assert get_secret("cedar_api") is None


def test_get_secret_returns_none_when_vault_read_fails(monkeypatch):
    def fail_read(service, name):
        raise RuntimeError("vault unavailable")

    monkeypatch.setattr("keyring.get_password", fail_read)

    assert get_secret("cedar_api") is None


def test_set_secret_rejects_empty_value(monkeypatch):
    def fail_write(service, name, value):
        pytest.fail("empty value reached the vault")

    monkeypatch.setattr("keyring.set_password", fail_write)

    with pytest.raises(ValueError, match="cannot be empty"):
        set_secret("cedar_api", "")


def test_set_secret_rejects_unverified_write(monkeypatch):
    monkeypatch.setattr("keyring.set_password", lambda service, name, value: None)
    monkeypatch.setattr("keyring.get_password", lambda service, name: None)

    with pytest.raises(RuntimeError, match="did not verify"):
        set_secret("cedar_api", "cedar-token")


def test_migrate_legacy_secret_returns_existing_vault_value(tmp_path, monkeypatch):
    legacy = tmp_path / "cedar-secret"
    legacy.write_text("older-token\n")
    monkeypatch.setattr("keyring.get_password",
                        lambda service, name: "current-token" if service == SERVICE_NAME else None)

    assert migrate_legacy_secret("cedar_api", legacy) == "current-token"
    assert legacy.read_text() == "older-token\n"


def test_migrate_legacy_secret_returns_none_when_file_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("keyring.get_password", lambda service, name: None)

    assert migrate_legacy_secret("cedar_api", tmp_path / "missing-secret") is None


def test_migrate_legacy_secret_preserves_blank_file(tmp_path, monkeypatch):
    legacy = tmp_path / "cedar-secret"
    legacy.write_text(" \n\t")
    monkeypatch.setattr("keyring.get_password", lambda service, name: None)

    assert migrate_legacy_secret("cedar_api", legacy) is None
    assert legacy.read_text() == " \n\t"
