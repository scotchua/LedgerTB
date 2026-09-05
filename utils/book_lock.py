"""Held leases for shared book files.

SQLite's own locking is unreliable on network shares (SMB/NFS), so a shared
book has a visible sidecar lease naming its writer. Acquisition uses exclusive
file creation and each owner has a random token. ``O_EXCL`` is not perfectly
atomic on every network filesystem. The heartbeat and owner-token checks
reduce the resulting risk, but they are not a mathematical guarantee.
"""
import getpass
import json
import os
import socket
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


STALE_AFTER_SECONDS = 10 * 60
HEARTBEAT_SECONDS = 30
TAKEN_OVER_MESSAGE = "Another computer took over this book"

_leases = {}
_heartbeat_stops = {}
_lease_lock = threading.RLock()


def lock_path(book) -> Path:
    book = Path(book)
    return book.with_name(book.name + ".lock")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _me(token=None) -> dict:
    now = _now().isoformat(timespec="seconds")
    return {
        "token": token or uuid.uuid4().hex,
        "user": getpass.getuser(),
        "host": socket.gethostname(),
        "pid": os.getpid(),
        "acquired_at": now,
        "heartbeat_at": now,
    }


def read_lock(book):
    """The current holder dict, or None."""
    try:
        return json.loads(lock_path(book).read_text())
    except Exception:
        return None


def _write_handle(fd, holder: dict) -> None:
    payload = (json.dumps(holder, indent=2) + "\n").encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    os.write(fd, payload)
    os.fsync(fd)


def _remember(book, token: str, fd: int) -> None:
    key = str(lock_path(book))
    with _lease_lock:
        previous = _leases.pop(key, None)
        if previous:
            os.close(previous[1])
        _leases[key] = (token, fd)
    _start_heartbeat(book)


def _forget(book) -> None:
    key = str(lock_path(book))
    with _lease_lock:
        heartbeat_stop = _heartbeat_stops.pop(key, None)
        if heartbeat_stop:
            heartbeat_stop.set()
        lease = _leases.pop(key, None)
        if lease:
            try:
                os.close(lease[1])
            except OSError:
                pass


def _reset() -> None:
    """Close and forget all process-held leases."""
    for book in held_books():
        _forget(book)


def _owned_token(book):
    with _lease_lock:
        lease = _leases.get(str(lock_path(book)))
        return lease[0] if lease else None


def held_books():
    """Return the books whose leases are currently held by this process."""
    with _lease_lock:
        return [Path(path).with_name(Path(path).name.removesuffix(".lock"))
                for path in list(_leases)]


def _heartbeat(book, stop: threading.Event) -> None:
    """Refresh an idle lease independently of Streamlit request handling.

    Previously only ``require_unlock`` called ``verify_and_refresh``. Streamlit
    runs that path during a request or rerun, so an orphaned server with no
    browser connected kept its acquisition timestamp forever.
    """
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            verify_and_refresh(book)
        except (OSError, RuntimeError):
            return


def _start_heartbeat(book) -> None:
    key = str(lock_path(book))
    with _lease_lock:
        current = _heartbeat_stops.get(key)
        if current and not current.is_set():
            return
        stop = threading.Event()
        _heartbeat_stops[key] = stop
    threading.Thread(
        target=_heartbeat,
        args=(Path(book), stop),
        name="ledgertb-book-heartbeat",
        daemon=True,
    ).start()


def is_stale(holder: dict, now=None) -> bool:
    stamp = holder.get("heartbeat_at")
    if not stamp:
        return True
    try:
        heartbeat = datetime.fromisoformat(stamp)
        if heartbeat.tzinfo is None:
            heartbeat = heartbeat.replace(tzinfo=timezone.utc)
        return ((now or _now()) - heartbeat).total_seconds() > STALE_AFTER_SECONDS
    except (TypeError, ValueError):
        return True


def acquire(book) -> dict:
    """Atomically acquire a new lease, or report the current holder."""
    path = lock_path(book)
    token = _owned_token(book)
    holder = read_lock(book)
    if token and holder and holder.get("token") == token:
        return {"acquired": True, "token": token}

    path.parent.mkdir(parents=True, exist_ok=True)
    mine = _me()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return {"acquired": False, "holder": read_lock(book) or {}}
    try:
        _write_handle(fd, mine)
    except Exception:
        os.close(fd)
        path.unlink(missing_ok=True)
        raise
    _remember(book, mine["token"], fd)
    return {"acquired": True, "token": mine["token"]}


def takeover(book) -> dict:
    """Replace a stale lease with a newly tokened lease."""
    path = lock_path(book)
    holder = read_lock(book)
    if holder and not is_stale(holder):
        return {"acquired": False, "holder": holder}

    observed_token = holder.get("token") if holder else None
    if holder:
        current = read_lock(book)
        if not current or current.get("token") != observed_token:
            return {"acquired": False, "holder": current or {}}
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    return acquire(book)


def verify_and_refresh(book) -> bool:
    """Fence a former owner and refresh the current owner's heartbeat."""
    with _lease_lock:
        token = _owned_token(book)
        if not token:
            return
        holder = read_lock(book)
        if not holder or holder.get("token") != token:
            _forget(book)
            raise RuntimeError(TAKEN_OVER_MESSAGE)
        holder["heartbeat_at"] = _now().isoformat(timespec="seconds")
        _write_handle(_leases[str(lock_path(book))][1], holder)
        return True


def release(book) -> None:
    """Remove the sidecar only while its token is still ours."""
    with _lease_lock:
        path = lock_path(book)
        token = _owned_token(book)
        try:
            holder = read_lock(book)
            if token and holder and holder.get("token") == token:
                path.unlink(missing_ok=True)
        finally:
            _forget(book)


def describe(holder: dict) -> str:
    opened = holder.get("acquired_at", holder.get("opened_at", ""))
    if opened:
        try:
            local = datetime.fromisoformat(opened).astimezone()
            hour = local.strftime("%I").lstrip("0") or "0"
            opened = (
                f"{local.strftime('%b')} {local.day} at "
                f"{hour}:{local.strftime('%M %p')}"
            )
        except (TypeError, ValueError):
            pass
    return (f"{holder.get('user', '?')} on {holder.get('host', '?')}"
            + (f" since {opened}" if opened else ""))
