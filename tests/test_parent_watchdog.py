import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

from utils import book_lock, parent_watchdog


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
