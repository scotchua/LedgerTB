import hashlib
import os

from utils.assistant_access import (
    AssistantCredentialNames,
    LEGACY_SECRET_NAMES,
    book_scope,
    credential_names,
    revoke_legacy_credentials,
)


def test_book_scope_is_32_characters_of_canonical_path_hash(tmp_path):
    book = tmp_path / "invented-book.db"
    canonical = os.path.normcase(str(book.resolve()))

    assert book_scope(book) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def test_credential_names_are_stable_per_canonical_book_path(tmp_path):
    book_a = tmp_path / "folder" / ".." / "book-a.db"
    same_book = tmp_path / "book-a.db"
    book_b = tmp_path / "book-b.db"

    assert credential_names(book_a) == credential_names(same_book)
    assert credential_names(book_a) != credential_names(book_b)
    assert str(tmp_path) not in credential_names(book_a).key


def test_credential_names_include_every_book_scoped_secret(tmp_path):
    book = tmp_path / "invented-book.db"
    scope = book_scope(book)

    assert credential_names(book) == AssistantCredentialNames(
        key=f"mcp_book:{scope}:db_key",
        level=f"mcp_book:{scope}:access_level",
        book_id=f"mcp_book:{scope}:book_id",
        export_roots=f"mcp_book:{scope}:export_roots",
    )


def test_legacy_machine_wide_authorization_is_revoked(fake_credential_vault):
    from utils.secure_store import set_secret

    for name in LEGACY_SECRET_NAMES:
        set_secret(name, "legacy")

    assert revoke_legacy_credentials() is True
    assert not any(name in fake_credential_vault for name in LEGACY_SECRET_NAMES)
    assert revoke_legacy_credentials() is False
