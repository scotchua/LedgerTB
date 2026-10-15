"""Book registry edge cases exercised by mutation tests."""
import json
import os

import pytest

from utils import books


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr(books, "SETTINGS_PATH", tmp_path / "registry" / "books.json")
    monkeypatch.setattr(books, "DEFAULT_BOOK", tmp_path / "default.ledgertb")
    monkeypatch.delenv("LEDGERTB_DB_PATH", raising=False)
    monkeypatch.delenv("PROBOOKS_DB_PATH", raising=False)
    return tmp_path


def test_save_creates_private_registry_directory(registry):
    previous_umask = os.umask(0)
    try:
        books._save({"active": str(registry / "Aster Company.ledgertb")})
    finally:
        os.umask(previous_umask)

    assert books.SETTINGS_PATH.is_file()
    assert books.SETTINGS_PATH.parent.stat().st_mode & 0o777 == 0o700
    assert books.SETTINGS_PATH.stat().st_mode & 0o777 == 0o600


def test_save_restricts_existing_registry_directory(registry):
    books.SETTINGS_PATH.parent.mkdir(mode=0o755)
    books.SETTINGS_PATH.parent.chmod(0o755)

    books._save({"active": str(registry / "Birch Company.ledgertb")})

    assert books.SETTINGS_PATH.parent.stat().st_mode & 0o777 == 0o700


def test_save_closes_temporary_file(registry, monkeypatch):
    closed = []
    real_close = os.close

    def record_close(fd):
        closed.append(fd)
        real_close(fd)

    with monkeypatch.context() as patch:
        patch.setattr(books.os, "close", record_close)
        books._save({"active": str(registry / "Cedar Company.ledgertb")})

    assert len(closed) == 1


def test_save_uses_stable_json_format(registry):
    books._save({"active": "Dahlia Company.ledgertb"})

    assert books.SETTINGS_PATH.read_text() == (
        json.dumps({"active": "Dahlia Company.ledgertb"}, indent=2) + "\n"
    )


def test_set_active_book_keeps_eight_recent_books(registry):
    paths = [registry / f"Invented Company {number}.ledgertb"
             for number in range(9)]
    for path in paths:
        books.set_active_book(path)

    assert books._load()["recent"] == [str(path) for path in reversed(paths[1:])]


def test_is_local_book_returns_false_when_path_resolution_fails(monkeypatch):
    class UnresolvablePath:
        def expanduser(self):
            return self

        def resolve(self):
            raise OSError("invented path cannot be resolved")

    with monkeypatch.context() as patch:
        patch.setattr(books, "Path", lambda _path: UnresolvablePath())
        result = books.is_local_book("invented path")

    assert result is False
