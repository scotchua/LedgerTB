"""Offline behavior checks for saved import formats."""

from contextlib import contextmanager
from datetime import datetime
import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
from types import ModuleType

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "models" / "import_profile.py"


@pytest.fixture
def profile_module(monkeypatch):
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE accounts (
            id INTEGER PRIMARY KEY, client_id INTEGER, type TEXT, is_active INTEGER
        );
        CREATE TABLE import_profiles (
            id INTEGER PRIMARY KEY, client_id INTEGER, bank_account_id INTEGER,
            name TEXT, date_column TEXT, description_column TEXT,
            amount_format TEXT, amount_column TEXT, debit_column TEXT,
            credit_column TEXT, sign_convention TEXT, header_signature TEXT,
            created_at TEXT DEFAULT '2025-06-12 00:00:00',
            updated_at TEXT DEFAULT '2025-06-12 00:00:00'
        );
        INSERT INTO accounts VALUES (11, 7, 'Asset', 1);
        INSERT INTO accounts VALUES (12, 8, 'Asset', 1);
        INSERT INTO accounts VALUES (13, 7, 'Expense', 1);
        """
    )

    @contextmanager
    def get_cursor(commit=False):
        cursor = connection.cursor()
        try:
            yield cursor
            if commit:
                connection.commit()
        finally:
            cursor.close()

    events = []
    database = ModuleType("database")
    database.__path__ = []
    database_connection = ModuleType("database.connection")
    database_connection.get_cursor = get_cursor
    audit = ModuleType("models.audit_log")

    class AuditLog:
        @staticmethod
        def write(cursor, client_id, table, row_id, action, **values):
            events.append((client_id, table, row_id, action, values))

    audit.AuditLog = AuditLog
    monkeypatch.setitem(sys.modules, "database", database)
    monkeypatch.setitem(sys.modules, "database.connection", database_connection)
    monkeypatch.setitem(sys.modules, "models.audit_log", audit)
    source = Path(os.environ.get("IMPORT_PROFILE_MUTANT_SOURCE", SOURCE))
    spec = importlib.util.spec_from_file_location("_offline_import_profile", source)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    yield module, connection, events
    connection.close()


def make_profile(module, **overrides):
    values = {
        "client_id": 7,
        "bank_account_id": 11,
        "name": "Invented Bank",
        "date_column": "Posted",
        "description_column": "Detail",
        "amount_format": "single",
        "amount_column": "Value",
        "sign_convention": "bank",
    }
    values.update(overrides)
    return module.ImportProfile(**values)


def test_from_row_preserves_all_saved_fields(profile_module):
    module, connection, _ = profile_module
    profile = make_profile(module, header_signature='["Posted","Detail","Value"]')
    profile.save()
    row = connection.execute("SELECT * FROM import_profiles WHERE id = ?", (profile.id,)).fetchone()
    loaded = module.ImportProfile._from_row(row)
    assert loaded.header_signature == profile.header_signature
    assert loaded.bank_account_id == 11
    assert isinstance(loaded.created_at, datetime)


def test_validate_rejects_boundary_length_and_missing_account(profile_module):
    module, _, _ = profile_module
    valid = make_profile(module, name="N" * 80)
    valid.validate()
    assert valid.name == "N" * 80
    with pytest.raises(ValueError, match="80 characters"):
        make_profile(module, name="N" * 81).validate()
    with pytest.raises(ValueError, match="Client and bank account"):
        make_profile(module, bank_account_id=0).validate()


def test_validate_clears_unused_columns_and_requires_separate_amount(profile_module):
    module, _, _ = profile_module
    single = make_profile(module, debit_column="Debit", credit_column="Credit")
    single.validate()
    assert (single.debit_column, single.credit_column) == (None, None)
    with pytest.raises(ValueError, match="debit or credit"):
        make_profile(module, amount_format="separate", amount_column=None).validate()


def test_validate_accepts_one_separate_amount_column(profile_module):
    module, _, _ = profile_module
    profile = make_profile(
        module, amount_format="separate", amount_column="Unused",
        debit_column="Debit", credit_column=None
    )
    profile.validate()
    assert profile.amount_column is None
    assert profile.debit_column == "Debit"


def test_validate_rejects_unknown_sign_convention(profile_module):
    module, _, _ = profile_module
    with pytest.raises(ValueError, match="Sign convention is invalid"):
        make_profile(module, sign_convention="unknown").validate()


def test_signature_distinguishes_header_order_and_escaping(profile_module):
    module, _, _ = profile_module
    signature = module.ImportProfile.signature_for_columns(["A,B", "C"])
    assert signature == '["A,B","C"]'
    assert signature != module.ImportProfile.signature_for_columns(["C", "A,B"])


def test_save_requires_existing_profile_and_eligible_account(profile_module):
    module, _, _ = profile_module
    with pytest.raises(ValueError, match="no longer exists"):
        make_profile(module, id=999).save()
    with pytest.raises(ValueError, match="belong to the client"):
        make_profile(module, bank_account_id=12).save()
    with pytest.raises(ValueError, match="asset or liability"):
        make_profile(module, bank_account_id=13).save()


def test_save_updates_exact_record_and_audits_new_values(profile_module):
    module, connection, events = profile_module
    first = make_profile(module)
    first_id = first.save()
    second = make_profile(module, name="Other Export")
    second_id = second.save()
    changed = make_profile(module, id=first_id, name="New Export", amount_column="Net")
    assert changed.save() == first_id
    assert module.ImportProfile.get_by_id(7, first_id).amount_column == "Net"
    assert module.ImportProfile.get_by_id(7, second_id).name == "Other Export"
    assert events[-1][3] == "UPDATE"
    assert events[-1][4]["new_values"]["amount_column"] == "Net"
    assert connection.execute("SELECT COUNT(*) FROM import_profiles").fetchone()[0] == 2


def test_get_by_id_rejects_other_client_and_unknown_id(profile_module):
    module, _, _ = profile_module
    profile_id = make_profile(module).save()
    assert module.ImportProfile.get_by_id(7, profile_id).id == profile_id
    assert module.ImportProfile.get_by_id(8, profile_id) is None
    assert module.ImportProfile.get_by_id(7, profile_id + 100) is None


def test_list_for_account_orders_names_and_scopes_account(profile_module):
    module, _, _ = profile_module
    make_profile(module, name="zeta").save()
    make_profile(module, name="Alpha").save()
    assert [item.name for item in module.ImportProfile.list_for_account(7, 11)] == [
        "Alpha", "zeta"
    ]
    assert module.ImportProfile.list_for_account(8, 11) == []


def test_match_for_columns_prefers_exact_and_rejects_ambiguous(profile_module):
    module, _, _ = profile_module
    exact = make_profile(module, header_signature=module.ImportProfile.signature_for_columns(
        ["Posted", "Detail", "Value"]
    ))
    other = make_profile(module, name="Other Export")
    assert module.ImportProfile.match_for_columns(
        [exact, other], ["Posted", "Detail", "Value"]
    ) is exact
    assert module.ImportProfile.match_for_columns(
        [exact, other], ["Posted", "Detail", "Value", "Extra"]
    ) is None


def test_match_for_columns_accepts_one_compatible_legacy_profile(profile_module):
    module, _, _ = profile_module
    compatible = make_profile(module)
    incompatible = make_profile(module, name="Other", amount_column="Missing")
    assert module.ImportProfile.match_for_columns(
        [compatible, incompatible], ["Posted", "Detail", "Value"]
    ) is compatible


def test_delete_removes_only_requested_profile_and_audits(profile_module):
    module, _, events = profile_module
    first_id = make_profile(module).save()
    second_id = make_profile(module, name="Other Export").save()
    assert module.ImportProfile.delete(8, first_id) is False
    assert module.ImportProfile.delete(7, first_id) is True
    assert module.ImportProfile.get_by_id(7, first_id) is None
    assert module.ImportProfile.get_by_id(7, second_id).id == second_id
    assert events[-1][3] == "DELETE"


def test_resolve_columns_applies_separate_mapping_and_falls_back(profile_module):
    module, _, _ = profile_module
    profile = make_profile(
        module, amount_format="separate", amount_column=None,
        debit_column="Out", credit_column="In"
    )
    applied = profile.resolve_columns(["Posted", "Detail", "Out", "In"], {})
    assert applied["applied"] is True
    assert (applied["debit_column"], applied["credit_column"]) == ("Out", "In")
    fallback = profile.resolve_columns(
        ["Date", "Text", "Debit", "Credit"],
        {"date": "Date", "description": "Text", "debit": "Debit", "credit": "Credit"},
    )
    assert fallback["applied"] is False
    assert fallback["missing"] == ["Posted", "Detail", "Out", "In"]
    assert fallback["amount_format"] == "separate"
    assert fallback["debit_column"] == "Debit"


def test_resolve_columns_uses_detected_single_amount(profile_module):
    module, _, _ = profile_module
    profile = make_profile(module)
    fallback = profile.resolve_columns(
        ["Date", "Text", "Net"],
        {"date": "Date", "description": "Text", "amount": "Net"},
    )
    assert fallback["amount_format"] == "single"
    assert fallback["amount_column"] == "Net"
