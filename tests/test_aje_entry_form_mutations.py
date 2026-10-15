"""Offline behavior checks for the adjusting-entry form and quick add."""

from datetime import date
import importlib.util
import os
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


SOURCE = Path(__file__).resolve().parents[1] / "utils" / "aje_entry_form.py"
START = date(2025, 1, 1)
END = date(2025, 1, 31)


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self.accounts = {}
        self.amounts = {}
        self.memos = {}
        self.submitted = False
        self.cancelled = False
        self.messages = []
        self.widgets = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def form(self, key):
        self.widgets.append(("form", key))
        return self

    def columns(self, widths):
        return [self] * len(widths)

    def subheader(self, value):
        self.messages.append(("subheader", value))

    def markdown(self, value):
        pass

    def warning(self, value):
        self.messages.append(("warning", value))

    def success(self, value):
        self.messages.append(("success", value))

    def error(self, value):
        self.messages.append(("error", value))

    def text_input(self, label, **kwargs):
        self.widgets.append((label, kwargs))
        if label == "AJE Reference":
            return kwargs["value"]
        if label == "Description":
            return "Invented month-end accrual"
        if label == "Source Reference":
            return "" if not self.memos.get("source") else "WP-7"
        return self.memos.get(label, "")

    def date_input(self, label, **kwargs):
        self.widgets.append((label, kwargs))
        return date(2025, 1, 30)

    def selectbox(self, label, **kwargs):
        self.widgets.append((label, kwargs))
        return self.accounts.get(label, kwargs["options"][kwargs["index"]])

    def number_input(self, label, **kwargs):
        self.widgets.append((label, kwargs))
        return self.amounts.get(label, 0.0)

    def form_submit_button(self, label, **kwargs):
        return self.submitted if label == "Save AJE" else self.cancelled


class EntryLine:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Entry:
    calls = []
    saved = []
    save_error = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    @classmethod
    def get_next_aje_reference(cls, *args):
        cls.calls.append(args)
        return "AJE-019"

    def save(self):
        if self.save_error:
            raise self.save_error
        self.saved.append(self)


class Account:
    rows = []
    calls = []

    @classmethod
    def get_all(cls, client_id):
        cls.calls.append(client_id)
        return cls.rows


def load_form():
    st = FakeStreamlit()
    journal_module = types.ModuleType("models.journal_entry")
    journal_module.JournalEntry = Entry
    journal_module.JournalEntryLine = EntryLine
    account_module = types.ModuleType("models.account")
    account_module.Account = Account
    preferences_module = types.ModuleType("services.preferences")
    preferences_module.get_date_format = lambda: "MM/DD/YYYY"
    modules = {
        "streamlit": st,
        "models": types.ModuleType("models"),
        "models.journal_entry": journal_module,
        "models.account": account_module,
        "services": types.ModuleType("services"),
        "services.preferences": preferences_module,
    }
    source = Path(os.environ.get("AJE_MUTANT_FILE", SOURCE))
    spec = importlib.util.spec_from_file_location("aje_entry_form_under_test", source)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module, st


class AjeFormTests(unittest.TestCase):
    def setUp(self):
        Entry.calls = []
        Entry.saved = []
        Entry.save_error = None
        Account.calls = []
        Account.rows = [
            types.SimpleNamespace(id=11, account_number="1100", name="Invented Cash"),
            types.SimpleNamespace(id=22, account_number="2200", name="Invented Accrual"),
        ]
        self.form, self.st = load_form()

    def render(self, **kwargs):
        return self.form.render_aje_form(7, START, END, **kwargs)

    def test_no_accounts_warns_and_does_not_open_form(self):
        Account.rows = []
        self.assertIsNone(self.render())
        self.assertEqual(Account.calls, [7])
        self.assertEqual(Entry.calls, [(7, START, END)])
        self.assertTrue(any(kind == "warning" for kind, _ in self.st.messages))
        self.assertFalse(any(kind == "form" for kind, _ in self.st.widgets))

    def test_cancel_calls_only_cancel_callback(self):
        self.st.cancelled = True
        self.st.submitted = True
        callbacks = []
        self.assertIsNone(self.render(on_cancel=lambda: callbacks.append("cancel"),
                                      on_save=lambda entry: callbacks.append("save")))
        self.assertEqual(callbacks, ["cancel"])
        self.assertEqual(Entry.saved, [])

    def test_save_builds_selected_lines_metadata_and_calls_callback(self):
        self.st.submitted = True
        self.st.accounts = {"Account 1": 22, "Account 2": 11, "Account 3": 22}
        self.st.amounts = {"Debit 1": 81.25, "Credit 2": 81.25, "Debit 3": 0.0}
        self.st.memos = {"Memo 1": "Invented debit", "source": True}
        callbacks = []
        entry = self.render(prefill_account_id=22, form_key="invented_aje",
                            on_save=callbacks.append)
        self.assertIs(entry, Entry.saved[0])
        self.assertEqual(callbacks, [entry])
        self.assertEqual((entry.client_id, entry.entry_date, entry.description),
                         (7, date(2025, 1, 30), "Invented month-end accrual"))
        self.assertEqual((entry.source_reference, entry.entry_type, entry.aje_reference),
                         ("WP-7", "Adjusting", "AJE-019"))
        self.assertEqual([(line.account_id, line.debit, line.credit, line.memo)
                          for line in entry.lines],
                         [(22, 81.25, 0.0, "Invented debit"),
                          (11, 0.0, 81.25, None)])
        account_widget = next(options for label, options in self.st.widgets
                              if label == "Account 1")
        self.assertEqual(account_widget["index"], 1)
        self.assertEqual(account_widget["key"], "invented_aje_line1_acct")
        self.assertIn(("form", "invented_aje"), self.st.widgets)
        self.assertIn(("success", "AJE AJE-019 saved successfully!"), self.st.messages)

    def test_optional_line_requires_account_and_positive_amount(self):
        self.st.submitted = True
        self.st.accounts = {"Account 3": None, "Account 4": 22}
        self.st.amounts = {"Debit 1": 40.0, "Credit 2": 40.0,
                           "Debit 3": 9.0, "Credit 4": 0.0}
        entry = self.render(prefill_account_id=999)
        self.assertEqual(len(entry.lines), 2)
        self.assertEqual(entry.lines[0].account_id, 11)

    def test_positive_optional_credit_is_included(self):
        self.st.submitted = True
        self.st.accounts = {"Account 3": 22}
        self.st.amounts = {"Debit 1": 15.0, "Credit 2": 10.0, "Credit 3": 5.0}
        entry = self.render()
        self.assertEqual([(line.account_id, line.debit, line.credit)
                          for line in entry.lines],
                         [(11, 15.0, 0.0), (11, 0.0, 10.0), (22, 0.0, 5.0)])

    def test_save_validation_error_is_shown_and_not_returned(self):
        self.st.submitted = True
        self.st.amounts = {"Debit 1": 10.0, "Credit 2": 10.0}
        Entry.save_error = ValueError("Invented validation error")
        callbacks = []
        self.assertIsNone(self.render(on_save=callbacks.append))
        self.assertEqual(callbacks, [])
        self.assertEqual(Entry.saved, [])
        self.assertIn(("error", "Invented validation error"), self.st.messages)


class AjeQuickAddTests(unittest.TestCase):
    def setUp(self):
        Entry.calls = []
        Entry.saved = []
        Entry.save_error = None
        self.form, self.st = load_form()

    def add(self, **kwargs):
        return self.form.render_aje_quick_add(
            7, START, END, 11, 22, 73.45, "Invented adjustment", **kwargs)

    def test_quick_add_saves_balanced_entry_and_metadata(self):
        entry = self.add(source_reference="WP-8")
        self.assertIs(entry, Entry.saved[0])
        self.assertEqual(Entry.calls, [(7, START, END)])
        self.assertEqual((entry.client_id, entry.entry_date, entry.description,
                          entry.source_reference, entry.entry_type, entry.aje_reference),
                         (7, END, "Invented adjustment", "WP-8", "Adjusting", "AJE-019"))
        self.assertEqual([(line.account_id, line.debit, line.credit)
                          for line in entry.lines],
                         [(11, 73.45, 0), (22, 0, 73.45)])

    def test_quick_add_returns_none_on_validation_error(self):
        Entry.save_error = ValueError("Invented invalid account")
        self.assertIsNone(self.add())
        self.assertEqual(Entry.saved, [])
