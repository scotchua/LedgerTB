import os
import signal
import subprocess
import sys
import textwrap
import time
from types import SimpleNamespace

import pytest

from utils import book_lock, parent_watchdog


@pytest.mark.parametrize("actual_pid", [40, 42])
def test_parent_is_alive_rejects_a_different_parent(monkeypatch, actual_pid):
    signals = []
    monkeypatch.setattr(
        parent_watchdog,
        "os",
        SimpleNamespace(getppid=lambda: actual_pid, kill=lambda *args: signals.append(args)),
    )

    assert parent_watchdog._parent_is_alive(41) is False
    assert signals == []


def test_parent_is_alive_checks_process_with_signal_zero(monkeypatch):
    signals = []
    monkeypatch.setattr(
        parent_watchdog,
        "os",
        SimpleNamespace(getppid=lambda: 41, kill=lambda *args: signals.append(args)),
    )

    assert parent_watchdog._parent_is_alive(41) is True
    assert signals == [(41, 0)]


@pytest.mark.parametrize(
    ("error", "alive"),
    [(ProcessLookupError, False), (PermissionError, True)],
)
def test_parent_is_alive_handles_process_probe_errors(monkeypatch, error, alive):
    def fail_probe(pid, signal_number):
        assert (pid, signal_number) == (41, 0)
        raise error

    monkeypatch.setattr(
        parent_watchdog,
        "os",
        SimpleNamespace(getppid=lambda: 41, kill=fail_probe),
    )

    assert parent_watchdog._parent_is_alive(41) is alive


def test_watch_parent_waits_then_releases_books_and_exits(monkeypatch):
    calls = []
    alive = iter([True, False])
    monkeypatch.setattr(parent_watchdog, "_parent_is_alive", lambda pid: next(alive))
    monkeypatch.setattr(
        parent_watchdog,
        "threading",
        SimpleNamespace(Event=lambda: SimpleNamespace(wait=lambda seconds: calls.append(("wait", seconds)))),
    )
    monkeypatch.setattr(
        parent_watchdog,
        "book_lock",
        SimpleNamespace(
            held_books=lambda: ["invented-book.db"],
            release=lambda book: calls.append(("release", book)),
        ),
    )
    monkeypatch.setattr(
        parent_watchdog,
        "logging",
        SimpleNamespace(
            getLogger=lambda name: SimpleNamespace(error=lambda *args: None),
            shutdown=lambda: calls.append("shutdown"),
        ),
    )
    monkeypatch.setattr(
        parent_watchdog,
        "sys",
        SimpleNamespace(
            stdout=SimpleNamespace(flush=lambda: calls.append("stdout")),
            stderr=SimpleNamespace(flush=lambda: calls.append("stderr")),
        ),
    )
    monkeypatch.setattr(
        parent_watchdog,
        "os",
        SimpleNamespace(_exit=lambda code: calls.append(("exit", code))),
    )

    parent_watchdog._watch_parent(41)

    assert calls == [
        ("wait", 2),
        ("release", "invented-book.db"),
        "shutdown",
        "stdout",
        "stderr",
        ("exit", 0),
    ]


@pytest.mark.parametrize("value", ["invalid-pid", "0", "-1"])
def test_start_parent_watchdog_rejects_invalid_parent_ids(monkeypatch, value):
    monkeypatch.setattr(parent_watchdog, "_started", False)
    monkeypatch.setattr(parent_watchdog, "os", SimpleNamespace(environ={parent_watchdog.PARENT_PID_ENV: value}))
    monkeypatch.setattr(
        parent_watchdog,
        "threading",
        SimpleNamespace(Thread=lambda **kwargs: pytest.fail("unexpected watchdog thread")),
    )

    assert parent_watchdog.start_parent_watchdog() is False
    assert parent_watchdog._started is False


def test_start_parent_watchdog_starts_one_daemon_thread(monkeypatch):
    threads = []

    class FakeThread:
        def __init__(self, **kwargs):
            threads.append(kwargs)

        def start(self):
            threads[-1]["started"] = True

    monkeypatch.setattr(parent_watchdog, "_started", False)
    monkeypatch.setattr(parent_watchdog, "os", SimpleNamespace(environ={parent_watchdog.PARENT_PID_ENV: "1"}))
    monkeypatch.setattr(parent_watchdog, "threading", SimpleNamespace(Thread=FakeThread))

    assert parent_watchdog.start_parent_watchdog() is True
    assert parent_watchdog.start_parent_watchdog() is False
    assert parent_watchdog._started is True
    assert threads == [{
        "target": parent_watchdog._watch_parent,
        "args": (1,),
        "name": "ledgertb-parent-watchdog",
        "daemon": True,
        "started": True,
    }]


def test_watchdog_is_disabled_without_desktop_parent(monkeypatch):
    monkeypatch.delenv(parent_watchdog.PARENT_PID_ENV, raising=False)
    monkeypatch.setattr(parent_watchdog, "_started", False)

    assert parent_watchdog.start_parent_watchdog() is False


@pytest.mark.skipif(os.name != "posix", reason="test kills a POSIX parent")
def test_orphaned_streamlit_child_exits_and_releases_lease(tmp_path):
    book = tmp_path / "shared.db"
    child_pid_file = tmp_path / "child.pid"
    child_code = textwrap.dedent(
        f"""
        import os
        import time
        from pathlib import Path
        from utils import book_lock
        from utils.parent_watchdog import start_parent_watchdog

        book_lock.acquire(Path({str(book)!r}))
        start_parent_watchdog()
        Path({str(child_pid_file)!r}).write_text(str(os.getpid()))
        while True:
            time.sleep(1)
        """
    )
    parent_code = textwrap.dedent(
        f"""
        import os
        import subprocess
        import sys
        import time

        env = dict(os.environ, LEDGERTB_PARENT_PID=str(os.getpid()))
        subprocess.Popen([sys.executable, "-c", {child_code!r}], env=env)
        while True:
            time.sleep(1)
        """
    )
    parent = subprocess.Popen([sys.executable, "-c", parent_code])
    try:
        deadline = time.monotonic() + 6
        while not child_pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert child_pid_file.exists()
        child_pid = int(child_pid_file.read_text())
        assert book_lock.lock_path(book).exists()

        os.kill(parent.pid, signal.SIGKILL)
        parent.wait(timeout=2)
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            try:
                os.kill(child_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            pytest.fail("watchdog child did not exit within 6 seconds")
        assert not book_lock.lock_path(book).exists()
    finally:
        if parent.poll() is None:
            parent.kill()
