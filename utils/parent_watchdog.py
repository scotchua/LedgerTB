"""End a desktop-launched Streamlit server after its parent disappears."""

import logging
import os
import sys
import threading

from utils import book_lock


PARENT_PID_ENV = "LEDGERTB_PARENT_PID"
WATCHDOG_SECONDS = 2
_started = False


def _parent_is_alive(expected_pid: int) -> bool:
    if os.getppid() != expected_pid:
        return False
    try:
        os.kill(expected_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _watch_parent(expected_pid: int) -> None:
    while _parent_is_alive(expected_pid):
        threading.Event().wait(WATCHDOG_SECONDS)
    logging.getLogger(__name__).error(
        "Desktop parent process %s is no longer alive; stopping Streamlit",
        expected_pid,
    )
    for book in book_lock.held_books():
        book_lock.release(book)
    logging.shutdown()
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(0)


def start_parent_watchdog() -> bool:
    """Start once only for a child launched by ``desktop.py``.

    Browser/source mode has no ``LEDGERTB_PARENT_PID`` and remains unchanged.
    """
    global _started

    value = os.environ.get(PARENT_PID_ENV)
    if not value or _started:
        return False
    try:
        expected_pid = int(value)
    except ValueError:
        return False
    if expected_pid <= 0:
        return False
    _started = True
    threading.Thread(
        target=_watch_parent,
        args=(expected_pid,),
        name="ledgertb-parent-watchdog",
        daemon=True,
    ).start()
    return True
