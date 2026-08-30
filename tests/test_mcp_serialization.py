import threading
import time

import mcp_server
from database import connection as dbconn


def test_tool_invocations_are_serialized_end_to_end(monkeypatch):
    active = threading.Event()
    overlaps = []
    observed = []
    state = [("book-a.db", "read"), ("book-b.db", "post")]
    state_lock = threading.Lock()

    def refresh():
        with state_lock:
            path, level = state.pop(0)
        dbconn.DATABASE_PATH = path
        dbconn.ASSISTANT_ACCESS_LEVEL = level
        return level

    def slow_tool():
        if active.is_set():
            overlaps.append(True)
        active.set()
        before = (dbconn.DATABASE_PATH, dbconn.ASSISTANT_ACCESS_LEVEL)
        time.sleep(0.002)
        after = (dbconn.DATABASE_PATH, dbconn.ASSISTANT_ACCESS_LEVEL)
        observed.append((before, after))
        active.clear()
        return []

    monkeypatch.setattr(mcp_server, "_refresh_access", refresh)
    monkeypatch.setattr(mcp_server.mcp_tools, "list_clients", slow_tool)

    for _ in range(50):
        state[:] = [("book-a.db", "read"), ("book-b.db", "post")]
        observed.clear()
        threads = [threading.Thread(target=mcp_server.list_clients)
                   for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=2)
        assert all(not thread.is_alive() for thread in threads)
        assert observed == [(("book-a.db", "read"),) * 2,
                            (("book-b.db", "post"),) * 2]

    assert overlaps == []


def test_refresh_precedes_per_book_lock_and_state_reads(monkeypatch):
    events = []

    def refresh():
        events.append("refresh")
        dbconn.DATABASE_PATH = "book-b.db"
        dbconn.ASSISTANT_ACCESS_LEVEL = "post"
        return "post"

    class Writer:
        def __enter__(self):
            events.append(("lock", dbconn.DATABASE_PATH))

        def __exit__(self, *exc):
            pass

    monkeypatch.setattr(mcp_server, "_refresh_access", refresh)
    monkeypatch.setattr("utils.maintenance_lock.writer", lambda path: Writer())
    monkeypatch.setattr(
        mcp_server.mcp_tools, "post_entry",
        lambda *args: events.append(
            ("body", dbconn.DATABASE_PATH, dbconn.ASSISTANT_ACCESS_LEVEL)
        ) or {},
    )

    mcp_server.post_entry(1, "2026-01-01", "test", [])

    assert events == ["refresh", ("lock", "book-b.db"),
                      ("body", "book-b.db", "post")]
