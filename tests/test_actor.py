"""Direct tests for OS actor attribution and its fallbacks."""

import sys
from types import SimpleNamespace

import pytest

from utils import actor


@pytest.fixture(autouse=True)
def clear_actor_cache():
    actor._os_actor.cache_clear()
    yield
    actor._os_actor.cache_clear()


class TestOsActor:
    def test_uses_trimmed_full_name_before_gecos_details(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "pwd",
            SimpleNamespace(getpwuid=lambda uid: SimpleNamespace(
                pw_gecos=" Morgan Cedar ,Room 4"
            )),
        )
        monkeypatch.setattr(actor.os, "getuid", lambda: 42)
        monkeypatch.setattr(actor.getpass, "getuser", lambda: "mcedar")

        assert actor._os_actor() == "Morgan Cedar"

    def test_blank_full_name_uses_short_username(self, monkeypatch):
        monkeypatch.setitem(
            sys.modules, "pwd",
            SimpleNamespace(getpwuid=lambda uid: SimpleNamespace(
                pw_gecos=" ,Room 4"
            )),
        )
        monkeypatch.setattr(actor.getpass, "getuser", lambda: "mcedar")

        assert actor._os_actor() == "mcedar"

    def test_pwd_failure_uses_short_username(self, monkeypatch):
        def unavailable(uid):
            raise KeyError(uid)

        monkeypatch.setitem(
            sys.modules, "pwd", SimpleNamespace(getpwuid=unavailable)
        )
        monkeypatch.setattr(actor.getpass, "getuser", lambda: "mcedar")

        assert actor._os_actor() == "mcedar"

    def test_both_name_sources_fail_uses_unknown(self, monkeypatch):
        def unavailable(*args):
            raise RuntimeError("name source unavailable")

        monkeypatch.setitem(
            sys.modules, "pwd", SimpleNamespace(getpwuid=unavailable)
        )
        monkeypatch.setattr(actor.getpass, "getuser", unavailable)

        assert actor._os_actor() == "unknown"

    def test_name_is_captured_once_per_process(self, monkeypatch):
        calls = []

        def user_record(uid):
            calls.append(uid)
            name = "Morgan Cedar" if len(calls) == 1 else "Avery Vale"
            return SimpleNamespace(pw_gecos=name)

        monkeypatch.setitem(
            sys.modules, "pwd", SimpleNamespace(getpwuid=user_record)
        )
        monkeypatch.setattr(actor.os, "getuid", lambda: 42)

        assert actor._os_actor() == "Morgan Cedar"
        assert actor._os_actor() == "Morgan Cedar"
        assert calls == [42]
