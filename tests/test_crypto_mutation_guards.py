"""Offline regression guards for the crypto helpers and their file transitions."""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "database" / "crypto.py"


@pytest.fixture
def crypto():
    source = Path(os.environ.get("SWEEP_CRYPTO_SOURCE", SOURCE))
    spec = importlib.util.spec_from_file_location("crypto_mutation_guard", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeConnection:
    def __init__(self, path, integrity="ok", version=1):
        self.path = Path(path)
        self.integrity = integrity
        self.version = version
        self.statements = []
        self.closed = False

    def execute(self, statement):
        self.statements.append(statement)
        if statement.startswith("ATTACH DATABASE "):
            destination = statement.split("'", 2)[1].replace("''", "'")
            Path(destination).write_bytes(b"encrypted export")
        self.last = statement
        return self

    def fetchone(self):
        if self.last == "PRAGMA integrity_check":
            return (self.integrity,)
        if self.last == "PRAGMA cipher_page_size":
            return (8192,)
        if self.last == "PRAGMA data_version":
            if isinstance(self.version, list):
                return (self.version.pop(0),)
            return (self.version,)
        return (1,)

    def close(self):
        self.closed = True


class FakeDriver:
    def __init__(self, integrity="ok", versions=(1, 1)):
        self.integrity = integrity
        self.versions = versions
        self.connections = []

    def connect(self, path):
        index = len(self.connections)
        version = self.versions[min(index, len(self.versions) - 1)]
        if isinstance(version, tuple):
            version = list(version)
        conn = FakeConnection(path, self.integrity, version)
        self.connections.append(conn)
        return conn


def test_key_pragma_rejects_non_hex_and_wrong_length(crypto):
    for value in ("0" * 63, "0" * 63 + "g"):
        with pytest.raises(ValueError, match="64-character hex"):
            crypto.key_pragma(value)
    assert crypto.key_pragma("A" * 64) == '"x\'' + "A" * 64 + '\'"'


def test_sql_str_doubles_quotes_in_an_invented_book_name(crypto):
    assert crypto._sql_str("O'Vale Books.db") == "'O''Vale Books.db'"


def test_has_sqlite_header_requires_all_sixteen_bytes(crypto, tmp_path):
    path = tmp_path / "Invented Books.db"
    path.write_bytes(b"SQLite format 3")
    assert crypto._has_sqlite_header(path) is False
    path.write_bytes(b"SQLite format 3\x00payload")
    assert crypto._has_sqlite_header(path) is True


def test_database_state_distinguishes_missing_empty_plain_and_encrypted(crypto, tmp_path):
    path = tmp_path / "Invented Books.db"
    assert crypto.database_state(path) == "absent"
    path.touch()
    assert crypto.database_state(path) == "absent"
    path.write_bytes(b"SQLite format 3\x00payload")
    assert crypto.database_state(path) == "plaintext"
    path.write_bytes(b"encrypted payload")
    assert crypto.database_state(path) == "encrypted"


def test_plaintext_backup_path_appends_suffix(crypto, tmp_path):
    path = tmp_path / "Invented Books.db"
    assert crypto.plaintext_backup_path(path) == tmp_path / "Invented Books.db.plaintext.bak"


def test_is_plaintext_sqlite_rejects_symlink(crypto, tmp_path):
    path = tmp_path / "Invented Books.db"
    path.write_bytes(b"SQLite format 3\x00payload")
    link = tmp_path / "Invented Link.db"
    link.symlink_to(path)
    assert crypto.is_plaintext_sqlite(path) is True
    assert crypto.is_plaintext_sqlite(link) is False


def test_verify_passphrase_closes_connection_after_success_and_failure(crypto, tmp_path):
    driver = FakeDriver()
    crypto.sqlcipher3 = driver
    assert crypto.verify_passphrase(tmp_path / "Invented Books.db", "invented passphrase") is True
    assert driver.connections[0].closed is True
    assert any(sql.startswith("PRAGMA key = ") for sql in driver.connections[0].statements)
    assert "SELECT count(*) FROM sqlite_master" in driver.connections[0].statements

    def fail(_path):
        raise RuntimeError("wrong key")

    crypto.sqlcipher3 = SimpleNamespace(connect=fail)
    assert crypto.verify_passphrase(tmp_path / "Invented Books.db", "other passphrase") is False


def test_fsync_path_closes_fd_when_sync_fails(crypto, monkeypatch, tmp_path):
    closed = []
    monkeypatch.setattr(crypto.os, "open", lambda *_: 42)
    monkeypatch.setattr(crypto.os, "fsync", lambda *_: (_ for _ in ()).throw(OSError("unsupported")))
    monkeypatch.setattr(crypto.os, "close", closed.append)
    crypto._fsync_path(tmp_path / "Invented Books.db")
    assert closed == [42]


def test_on_windows_uses_os_name(crypto, monkeypatch):
    monkeypatch.setattr(crypto.os, "name", "nt")
    assert crypto._on_windows() is True
    monkeypatch.setattr(crypto.os, "name", "posix")
    assert crypto._on_windows() is False


def test_replace_or_explain_replaces_prepared_book(crypto, tmp_path):
    prepared = tmp_path / "Invented Books.tmp"
    target = tmp_path / "Invented Books.db"
    prepared.write_bytes(b"new book")
    target.write_bytes(b"old book")
    crypto._replace_or_explain(prepared, target)
    assert target.read_bytes() == b"new book"
    assert not prepared.exists()


def test_data_version_reads_first_column(crypto):
    conn = FakeConnection("Invented Books.db", version=17)
    assert crypto._data_version(conn) == 17
    assert conn.statements == ["PRAGMA data_version"]


def test_rekey_file_rejects_bad_integrity_and_preserves_source(crypto, tmp_path, monkeypatch):
    path = tmp_path / "Invented Books.db"
    path.write_bytes(b"original encrypted book")
    driver = FakeDriver(integrity="corrupt")
    crypto.sqlcipher3 = driver
    monkeypatch.setattr(crypto, "_fsync_path", lambda *_: None)
    with pytest.raises(RuntimeError, match="integrity check"):
        crypto.rekey_file(path, "a" * 64, "b" * 64)
    assert path.read_bytes() == b"original encrypted book"
    assert not list(tmp_path.glob("*.rekey-*.tmp"))


def test_key_fingerprint_is_stable_and_key_specific(crypto):
    first = crypto.key_fingerprint("a" * 64)
    assert first == crypto.key_fingerprint("a" * 64)
    assert first != crypto.key_fingerprint("b" * 64)
    assert len(first) == 16


def test_change_passphrase_rejects_changed_data_version(crypto, tmp_path, monkeypatch):
    path = tmp_path / "Invented Books.db"
    path.write_bytes(b"original encrypted book")
    driver = FakeDriver(versions=((4, 5), 4, 4))
    crypto.sqlcipher3 = driver
    monkeypatch.setattr(crypto, "_fsync_path", lambda *_: None)
    with pytest.raises(RuntimeError, match="Another connection wrote"):
        crypto.change_passphrase(path, "a" * 64, "invented new passphrase")
    assert path.read_bytes() == b"original encrypted book"
    assert not list(tmp_path.glob("*.rekey-*.tmp"))


def test_encrypt_plaintext_db_rejects_corrupt_export(crypto, tmp_path):
    path = tmp_path / "Invented Books.db"
    path.write_bytes(b"SQLite format 3\x00invented data")
    crypto.sqlcipher3 = FakeDriver(integrity="corrupt")
    with pytest.raises(RuntimeError, match="integrity check"):
        crypto.encrypt_plaintext_db(path, "invented passphrase")
    assert path.read_bytes() == b"SQLite format 3\x00invented data"
    assert not crypto.plaintext_backup_path(path).exists()
    assert not path.with_suffix(".db.enc.tmp").exists()
