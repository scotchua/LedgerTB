from pathlib import Path

from utils.client_context import (
    client_context_identity,
    pop_client_intent,
    scope_page_to_client,
    set_client_intent,
    sync_active_client_context,
)


def test_client_context_identity_includes_resolved_book_and_client(tmp_path):
    book = tmp_path / "folder" / ".." / "book.db"

    assert client_context_identity(book, 7) == (
        str((tmp_path / "book.db").resolve()),
        7,
    )


def test_book_identity_falls_back_when_resolution_fails(tmp_path, monkeypatch):
    book = tmp_path / "cedar.db"

    def fail_resolution(self, strict=False):
        raise OSError

    with monkeypatch.context() as patch:
        patch.setattr(Path, "resolve", fail_resolution)
        identity = client_context_identity(book, 7)

    assert identity == (str(book.absolute()), 7)


def test_active_context_changes_for_client_or_book(tmp_path):
    state = {}
    first_book = tmp_path / "first.db"
    second_book = tmp_path / "second.db"

    assert sync_active_client_context(state, 1, first_book) is False
    assert sync_active_client_context(state, 1, first_book) is False
    assert sync_active_client_context(state, 2, first_book) is True
    # Client ids restart in each book; the path must still trigger a change.
    assert sync_active_client_context(state, 2, second_book) is True
    assert state["_active_client_context_generation"] == 2


def test_active_context_initializes_and_counts_each_switch(tmp_path):
    state = {}
    book = tmp_path / "cedar.db"

    assert sync_active_client_context(state, 3, book) is False
    assert state["_active_client_context_generation"] == 0
    assert sync_active_client_context(state, 3, book) is False
    assert state["_active_client_context_generation"] == 0
    assert sync_active_client_context(state, 4, book) is True
    assert state["_active_client_context_generation"] == 1


def test_active_context_recovers_missing_generation_on_switch(tmp_path):
    state = {}
    book = tmp_path / "cedar.db"
    sync_active_client_context(state, 3, book)
    state.pop("_active_client_context_generation")

    assert sync_active_client_context(state, 4, book) is True
    assert state["_active_client_context_generation"] == 1


def test_page_scope_rotates_every_time_ownership_changes(tmp_path):
    state = {}
    first_book = tmp_path / "first.db"
    second_book = tmp_path / "second.db"

    first = scope_page_to_client(state, "journal_entries", 1, first_book)
    stable = scope_page_to_client(state, "journal_entries", 1, first_book)
    other_book = scope_page_to_client(state, "journal_entries", 1, second_book)
    returned = scope_page_to_client(state, "journal_entries", 1, first_book)

    assert (first.generation, first.changed) == (0, False)
    assert (stable.generation, stable.changed) == (0, False)
    assert (other_book.generation, other_book.changed) == (1, True)
    assert (returned.generation, returned.changed) == (2, True)
    assert returned.key("save") == "save__journal_entries_g2"


def test_page_scope_updates_app_context(tmp_path):
    state = {}
    book = tmp_path / "cedar.db"

    scope_page_to_client(state, "invoices", 3, book)

    assert state["_active_client_context"] == client_context_identity(book, 3)
    assert state["_active_client_context_generation"] == 0


def test_page_scope_recovers_missing_generation_on_switch(tmp_path):
    state = {}
    book = tmp_path / "cedar.db"
    scope_page_to_client(state, "invoices", 3, book)
    state.pop("_client_context_generation_invoices")

    scope = scope_page_to_client(state, "invoices", 4, book)

    assert (scope.generation, scope.changed) == (1, True)


def test_client_intent_is_one_shot_for_its_owner(tmp_path):
    state = {}
    book = tmp_path / "book.db"
    value = {"entry_id": 42, "view": "New Entry"}

    set_client_intent(state, "journal", value, 7, book)

    assert pop_client_intent(state, "journal", 7, book) == value
    assert pop_client_intent(state, "journal", 7, book) is None


def test_client_intent_rejects_other_clients_and_same_id_in_other_book(tmp_path):
    state = {}
    first_book = tmp_path / "first.db"
    second_book = tmp_path / "second.db"

    set_client_intent(state, "journal", {"entry_id": 11}, 1, first_book)
    assert pop_client_intent(state, "journal", 2, first_book) is None

    set_client_intent(state, "journal", {"entry_id": 11}, 1, first_book)
    assert pop_client_intent(state, "journal", 1, second_book) is None


def test_client_intent_returns_default_for_missing_and_stale_values(tmp_path):
    state = {}
    book = tmp_path / "cedar.db"
    default = object()

    assert pop_client_intent(state, "journal", 3, book, default) is default
    set_client_intent(state, "journal", {"account_id": 17}, 3, book)
    assert pop_client_intent(state, "journal", 4, book, default) is default


def test_book_scoped_key_tracks_the_book(tmp_path):
    from utils.client_context import book_scoped_key

    first = tmp_path / "first.db"
    second = tmp_path / "second.db"

    assert book_scoped_key("firm_date_format", first) == \
        book_scoped_key("firm_date_format", first)
    assert book_scoped_key("firm_date_format", first) != \
        book_scoped_key("firm_date_format", second)
    # Path spelling must not matter — the same book is the same key.
    assert book_scoped_key("firm_date_format", first) == \
        book_scoped_key("firm_date_format", tmp_path / "sub" / ".." / "first.db")
    assert book_scoped_key("firm_date_format", first).startswith("firm_date_format_")


def test_book_scoped_key_uses_twelve_hex_digits(tmp_path):
    from utils.client_context import book_scoped_key

    suffix = book_scoped_key("firm_date_format", tmp_path / "cedar.db").split("_")[-1]

    assert len(suffix) == 12
    assert all(character in "0123456789abcdef" for character in suffix)
