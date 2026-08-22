"""Choosing an account grouping on the Chart of Accounts page.

The picker is a dropdown rather than free text so that joining an existing
grouping is a pick. These tests hold that: the groupings already in use are
offered, and a new one is only created when someone asks for one.
"""

import streamlit as st
from streamlit.testing.v1 import AppTest

from models.account import Account
from tests.conftest import page_path

PPE = "Property and equipment"


def _page(monkeypatch, client_id):
    import utils.client_selector as selector

    monkeypatch.setattr(selector, "render_client_selector", lambda: client_id)
    monkeypatch.setattr(st, "page_link", lambda *a, **k: None)
    return AppTest.from_file(page_path("pages/3_Chart_of_Accounts.py"),
                             default_timeout=30).run()


def _grouped_account(client_id, number, name, grouping):
    account = Account(client_id=client_id, account_number=number, name=name,
                      type="Asset")
    account.account_grouping = grouping
    account.save()
    return account


def test_groupings_in_use_are_offered_not_retyped(client_id, accounts, monkeypatch):
    _grouped_account(client_id, "1500", "Vehicles", PPE)
    _grouped_account(client_id, "1510", "Shop Equipment", PPE)

    page = _page(monkeypatch, client_id)
    picker = next(s for s in page.selectbox if s.key == "add_grouping")

    assert PPE in picker.options
    # Offered once, however many accounts already use it.
    assert picker.options.count(PPE) == 1
    assert picker.value.startswith("None"), "own line is the default"


def test_a_new_grouping_can_be_named(client_id, accounts, monkeypatch):
    page = _page(monkeypatch, client_id)

    page.text_input(key="add_grouping_new").set_value(PPE)
    next(s for s in page.selectbox if s.key == "add_grouping").set_value(
        "Add new account grouping…")
    page.text_input[0].set_value("1600")          # Account Number
    page.text_input[1].set_value("Kiln")          # Account Name
    next(b for b in page.button if "Add Account" in b.label).click().run()

    assert not page.exception
    saved = next(a for a in Account.get_all(client_id) if a.account_number == "1600")
    assert saved.account_grouping == PPE


def test_an_account_can_join_an_existing_grouping(client_id, accounts, monkeypatch):
    _grouped_account(client_id, "1500", "Vehicles", PPE)
    joiner = _grouped_account(client_id, "1520", "Office Equipment", None)

    page = _page(monkeypatch, client_id)
    next(b for b in page.button if b.key == f"edit_{joiner.id}").click().run()
    grouping_key = f"edit_{joiner.id}_grouping"
    next(s for s in page.selectbox if s.key == grouping_key).set_value(PPE)
    next(b for b in page.button if "Save Changes" in b.label).click().run()

    assert not page.exception
    assert Account.get_by_id(joiner.id, client_id).account_grouping == PPE


def test_an_account_can_be_put_back_on_its_own_line(client_id, accounts, monkeypatch):
    leaver = _grouped_account(client_id, "1520", "Office Equipment", PPE)

    page = _page(monkeypatch, client_id)
    next(b for b in page.button if b.key == f"edit_{leaver.id}").click().run()
    grouping_key = f"edit_{leaver.id}_grouping"
    picker = next(s for s in page.selectbox if s.key == grouping_key)
    picker.set_value(next(o for o in picker.options if o.startswith("None")))
    next(b for b in page.button if "Save Changes" in b.label).click().run()

    assert not page.exception
    assert Account.get_by_id(leaver.id, client_id).account_grouping is None


def test_the_current_grouping_is_preselected_when_editing(client_id, accounts, monkeypatch):
    account = _grouped_account(client_id, "1500", "Vehicles", PPE)

    page = _page(monkeypatch, client_id)
    next(b for b in page.button if b.key == f"edit_{account.id}").click().run()

    grouping_key = f"edit_{account.id}_grouping"
    assert next(s for s in page.selectbox if s.key == grouping_key).value == PPE


def test_edit_opens_without_error_for_every_account(client_id, accounts, monkeypatch):
    """The form used to render below the whole chart, so it was off-screen and
    the button looked dead. It is a dialog now; this at least holds that
    opening one renders its fields."""
    page = _page(monkeypatch, client_id)
    edit_buttons = [b for b in page.button if (b.key or "").startswith("edit_")]
    assert edit_buttons

    edited_id = edit_buttons[0].key.removeprefix("edit_")
    edit_buttons[0].click().run()

    assert not page.exception
    assert any(
        s.key == f"edit_{edited_id}_grouping" for s in page.selectbox
    )
    assert any(b.label == "Save Changes" for b in page.button)


# --- managing groupings -----------------------------------------------------

def test_a_grouping_can_be_removed_without_touching_the_accounts(client_id, accounts):
    """Removing a grouping is not a delete. The accounts and their balances
    survive; they just present on their own lines again."""
    a = _grouped_account(client_id, "1500", "Vehicles", PPE)
    b = _grouped_account(client_id, "1510", "Shop Equipment", PPE)

    freed = Account.remove_grouping(client_id, PPE)

    assert freed == 2
    assert Account.get_by_id(a.id, client_id).account_grouping is None
    assert Account.get_by_id(b.id, client_id).account_grouping is None
    assert Account.get_by_id(a.id, client_id).name == "Vehicles"
    assert PPE not in Account.groupings_in_use(client_id)


def test_a_grouping_can_be_renamed_across_every_member(client_id, accounts):
    a = _grouped_account(client_id, "1500", "Vehicles", PPE)
    b = _grouped_account(client_id, "1510", "Shop Equipment", PPE)
    other = _grouped_account(client_id, "1600", "Kiln", "Other equipment")

    moved = Account.rename_grouping(client_id, PPE, "Plant and equipment")

    assert moved == 2
    assert Account.get_by_id(a.id, client_id).account_grouping == "Plant and equipment"
    assert Account.get_by_id(b.id, client_id).account_grouping == "Plant and equipment"
    # An unrelated grouping is left alone.
    assert Account.get_by_id(other.id, client_id).account_grouping == "Other equipment"


def test_renaming_a_grouping_is_audited_per_account(client_id, accounts):
    """Every mutation writes the audit trail, including a bulk one."""
    from models.audit_log import AuditLog

    a = _grouped_account(client_id, "1500", "Vehicles", PPE)
    Account.rename_grouping(client_id, PPE, "Plant and equipment")

    latest = AuditLog.get_history("accounts", a.id)[0]
    assert latest.old_values["account_grouping"] == PPE
    assert latest.new_values["account_grouping"] == "Plant and equipment"


def test_a_grouping_cannot_be_renamed_to_nothing(client_id, accounts):
    a = _grouped_account(client_id, "1500", "Vehicles", PPE)

    import pytest
    with pytest.raises(ValueError, match="cannot be empty"):
        Account.rename_grouping(client_id, PPE, "   ")

    assert Account.get_by_id(a.id, client_id).account_grouping == PPE


def test_the_groupings_tab_lists_and_removes(client_id, accounts, monkeypatch):
    _grouped_account(client_id, "1500", "Vehicles", PPE)
    _grouped_account(client_id, "1510", "Shop Equipment", PPE)

    page = _page(monkeypatch, client_id)
    # The grouping name is the expander label, which AppTest does not surface;
    # its members and its buttons are the reachable evidence that it listed.
    listed = " ".join(str(c.value) for c in page.caption)
    assert "1500 · Vehicles" in listed
    assert "1510 · Shop Equipment" in listed
    assert any(b.key == f"do_rename_{PPE}" for b in page.button)

    next(b for b in page.button if b.key == f"do_remove_{PPE}").click().run()

    assert not page.exception
    assert Account.groupings_in_use(client_id) == []


# --- creating a grouping from the groupings tab ----------------------------

def test_a_grouping_is_created_with_its_members(client_id, accounts):
    """Naming one without members would create nothing to find later."""
    a = _grouped_account(client_id, "1500", "Vehicles", None)
    b = _grouped_account(client_id, "1510", "Shop Equipment", None)

    moved = Account.assign_grouping(client_id, [a.id, b.id], PPE)

    assert moved == 2
    assert Account.groupings_in_use(client_id) == [PPE]
    assert Account.get_by_id(a.id, client_id).account_grouping == PPE


def test_an_account_moves_out_of_its_old_grouping(client_id, accounts):
    a = _grouped_account(client_id, "1500", "Vehicles", PPE)

    Account.assign_grouping(client_id, [a.id], "Plant and equipment")

    assert Account.get_by_id(a.id, client_id).account_grouping == "Plant and equipment"
    assert PPE not in Account.groupings_in_use(client_id)


def test_creating_a_grouping_needs_a_name(client_id, accounts):
    import pytest

    a = _grouped_account(client_id, "1500", "Vehicles", None)
    with pytest.raises(ValueError, match="cannot be empty"):
        Account.assign_grouping(client_id, [a.id], "   ")


def test_a_duplicate_name_is_caught_whatever_the_case(client_id, accounts):
    """Two spellings of one grouping would present as two lines."""
    _grouped_account(client_id, "1500", "Vehicles", PPE)

    assert Account.grouping_exists(client_id, "property AND equipment") == PPE
    assert Account.grouping_exists(client_id, "  Property and equipment  ") == PPE
    assert Account.grouping_exists(client_id, "Plant and equipment") is None


def test_assigning_is_audited_and_skips_accounts_already_there(client_id, accounts):
    from models.audit_log import AuditLog

    a = _grouped_account(client_id, "1500", "Vehicles", PPE)
    b = _grouped_account(client_id, "1510", "Shop Equipment", None)

    moved = Account.assign_grouping(client_id, [a.id, b.id], PPE)

    assert moved == 1, "the account already in the grouping is left alone"
    latest = AuditLog.get_history("accounts", b.id)[0]
    assert latest.new_values["account_grouping"] == PPE


def test_a_grouping_can_be_created_from_the_groupings_tab(client_id, accounts, monkeypatch):
    a = _grouped_account(client_id, "1500", "Vehicles", None)
    b = _grouped_account(client_id, "1510", "Shop Equipment", None)

    page = _page(monkeypatch, client_id)
    page.text_input(key="new_grouping_name").set_value(PPE)
    page.multiselect(key="new_grouping_members").set_value([a.id, b.id])
    next(btn for btn in page.button if btn.key == "do_create_grouping").click().run()

    assert not page.exception
    assert Account.groupings_in_use(client_id) == [PPE]


def test_accounts_can_be_added_to_an_existing_grouping_from_the_tab(client_id, accounts, monkeypatch):
    _grouped_account(client_id, "1500", "Vehicles", PPE)
    joiner = _grouped_account(client_id, "1510", "Shop Equipment", None)

    page = _page(monkeypatch, client_id)
    page.multiselect(key=f"add_to_{PPE}").set_value([joiner.id])
    next(btn for btn in page.button if btn.key == f"do_add_{PPE}").click().run()

    assert not page.exception
    assert Account.get_by_id(joiner.id, client_id).account_grouping == PPE
