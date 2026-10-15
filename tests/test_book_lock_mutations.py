"""Offline edge cases for shared book leases."""
import os
import threading
from datetime import datetime, timedelta, timezone

import pytest

from utils import book_lock


@pytest.fixture(autouse=True)
def clean_book_leases():
    book_lock._reset()
    yield
    book_lock._reset()


def test_read_lock_returns_none_for_unreadable_sidecar(tmp_path):
    book = tmp_path / "Juniper Lantern Books.db"
    assert book_lock.read_lock(book) is None
    book_lock.lock_path(book).write_text("not json")
    assert book_lock.read_lock(book) is None


def test_write_handle_flushes_sidecar(tmp_path, monkeypatch):
    path = tmp_path / "Juniper Lantern Books.db.lock"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    flushed = []
    truncated = []
    original_truncate = os.ftruncate

    def record_truncate(handle, length):
        truncated.append((handle, length))
        original_truncate(handle, length)

    monkeypatch.setattr(book_lock.os, "ftruncate", record_truncate)
    monkeypatch.setattr(book_lock.os, "fsync", flushed.append)
    try:
        book_lock._write_handle(fd, {"token": "juniper-token"})
        assert truncated == [(fd, 0)]
        assert flushed == [fd]
    finally:
        os.close(fd)


def test_forget_stops_heartbeat_and_closes_handle(tmp_path):
    book = tmp_path / "Juniper Lantern Books.db"
    book_lock.acquire(book)
    key = str(book_lock.lock_path(book))
    stop = book_lock._heartbeat_stops[key]
    fd = book_lock._leases[key][1]
    try:
        book_lock._forget(book)
        assert stop.is_set()
        with pytest.raises(OSError):
            os.fstat(fd)
    finally:
        stop.set()
        try:
            os.close(fd)
        except OSError:
            pass


def test_reset_forgets_all_held_books(tmp_path):
    books = [tmp_path / "Juniper Lantern Books.db",
             tmp_path / "Copper Fern Books.db"]
    for book in books:
        book_lock.acquire(book)
    try:
        book_lock._reset()
        assert book_lock.held_books() == []
    finally:
        for book in books:
            book_lock._forget(book)


def test_held_books_lists_its_book(tmp_path):
    book = tmp_path / "Juniper Lantern Books.db"
    book_lock.acquire(book)
    try:
        assert book_lock.held_books() == [book]
    finally:
        book_lock.release(book)


def test_heartbeat_refreshes_until_stopped(tmp_path, monkeypatch):
    book = tmp_path / "Juniper Lantern Books.db"
    refreshed = []
    monkeypatch.setattr(book_lock, "verify_and_refresh", refreshed.append)

    class Stop:
        calls = 0

        def wait(self, interval):
            self.calls += 1
            return self.calls > 1

    book_lock._heartbeat(book, Stop())
    assert refreshed == [book]


def test_start_heartbeat_tracks_its_stop_event(tmp_path, monkeypatch):
    book = tmp_path / "Juniper Lantern Books.db"
    started = []

    class Thread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def start(self):
            started.append(self.kwargs)

    monkeypatch.setattr(book_lock.threading, "Thread", Thread)
    key = str(book_lock.lock_path(book))
    try:
        book_lock._start_heartbeat(book)
        assert isinstance(book_lock._heartbeat_stops[key], threading.Event)
        assert len(started) == 1
    finally:
        stop = book_lock._heartbeat_stops.pop(key, None)
        if stop:
            stop.set()


def test_is_stale_handles_naive_fresh_and_invalid_timestamps():
    now = datetime(2031, 4, 5, 12, 0, tzinfo=timezone.utc)
    fresh_naive = (now - timedelta(seconds=1)).replace(tzinfo=None)
    exact_boundary = now - timedelta(seconds=book_lock.STALE_AFTER_SECONDS)
    assert book_lock.is_stale({"heartbeat_at": fresh_naive.isoformat()}, now) is False
    assert book_lock.is_stale({"heartbeat_at": exact_boundary.isoformat()}, now) is False
    assert book_lock.is_stale({"heartbeat_at": "invalid"}, now) is True


def test_acquire_propagates_write_failure_and_removes_sidecar(tmp_path,
                                                              monkeypatch):
    book = tmp_path / "Juniper Lantern Books.db"

    def fail_write(fd, holder):
        raise OSError("invented disk failure")

    monkeypatch.setattr(book_lock, "_write_handle", fail_write)
    try:
        with pytest.raises(OSError, match="invented disk failure"):
            book_lock.acquire(book)
        assert not book_lock.lock_path(book).exists()
    finally:
        book_lock._forget(book)


def test_takeover_refuses_when_observed_holder_disappears(tmp_path,
                                                          monkeypatch):
    book = tmp_path / "Juniper Lantern Books.db"
    observations = iter([{"token": "old-juniper-token"}, None])
    monkeypatch.setattr(book_lock, "read_lock", lambda unused: next(observations))
    monkeypatch.setattr(book_lock, "is_stale", lambda holder: True)
    assert book_lock.takeover(book) == {"acquired": False, "holder": {}}


def test_verify_and_refresh_reports_current_ownership(tmp_path):
    book = tmp_path / "Juniper Lantern Books.db"
    book_lock.acquire(book)
    try:
        assert book_lock.verify_and_refresh(book) is True
    finally:
        book_lock.release(book)


def test_release_removes_its_sidecar(tmp_path):
    book = tmp_path / "Juniper Lantern Books.db"
    book_lock.acquire(book)
    path = book_lock.lock_path(book)
    try:
        book_lock.release(book)
        assert not path.exists()
    finally:
        book_lock._forget(book)
        path.unlink(missing_ok=True)
