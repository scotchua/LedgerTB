from models.audit_log import AuditLog
from services.preferences import (
    AppPreferences,
    DEFAULT_DATE_FORMAT,
    get_date_format,
    save_date_format,
)


def test_app_preference_mutation_default_value():
    assert AppPreferences().date_format == DEFAULT_DATE_FORMAT


def test_get_date_format_preference_mutation_reads_saved_format(db):
    save_date_format("DD/MM/YYYY")

    assert get_date_format() == "DD/MM/YYYY"


def test_save_date_format_preference_mutation_audits_initial_default(db):
    save_date_format(DEFAULT_DATE_FORMAT)

    history = AuditLog.get_history("app_preferences", 1)
    assert len(history) == 1
    assert history[0].action == "INSERT"
    assert history[0].old_values is None


def test_save_date_format_preference_mutation_audits_changed_value(db):
    save_date_format("DD/MM/YYYY")
    save_date_format("YYYY/MM/DD")

    history = AuditLog.get_history("app_preferences", 1)
    assert len(history) == 2
    assert history[0].action == "UPDATE"
    assert history[0].old_values == {"date_format": "DD/MM/YYYY"}
    assert history[0].new_values == {"date_format": "YYYY/MM/DD"}


def test_save_date_format_preference_mutation_skips_unchanged_audit(db):
    save_date_format("DD/MM/YYYY")
    save_date_format("DD/MM/YYYY")

    assert len(AuditLog.get_history("app_preferences", 1)) == 1
