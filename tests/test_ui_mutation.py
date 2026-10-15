"""Small offline checks for the shared UI helpers' observable behavior."""

from utils import ui


def test_apply_default_on_change_tracks_dependency_and_updates_value(monkeypatch):
    state = {}
    monkeypatch.setattr(ui.st, "session_state", state)

    ui.apply_default_on_change("account_view", None, "bank")
    assert state == {"_account_view_depends_on": None, "account_view": "bank"}

    state["account_view"] = "manual"
    ui.apply_default_on_change("account_view", None, "bank")
    assert state["account_view"] == "manual"

    ui.apply_default_on_change("account_view", 42, "credit_card")
    assert state == {"_account_view_depends_on": 42, "account_view": "credit_card"}


def test_view_switcher_syncs_programmatic_selection_and_user_click(monkeypatch):
    state = {"report_view": "Missing"}
    markup = []
    calls = []
    monkeypatch.setattr(ui.st, "session_state", state)
    monkeypatch.setattr(ui.st, "html", markup.append)

    def radio(label, options, **kwargs):
        calls.append((label, options, kwargs))
        return state[kwargs["key"]]

    monkeypatch.setattr(ui.st, "radio", radio)
    assert ui.view_switcher(["Overview", "Details"], "report_view") == "Overview"
    assert state["report_view"] == state["_report_view_widget"] == state["_report_view_rendered"]
    assert ".st-key-_report_view_widget" in markup[0]
    assert calls[0][0] == "View"

    state["report_view"] = "Details"
    assert ui.view_switcher(["Overview", "Details"], "report_view") == "Details"
    assert state["_report_view_widget"] == "Details"

    state["_report_view_widget"] = "Overview"
    assert ui.view_switcher(["Overview", "Details"], "report_view") == "Overview"
    assert state["report_view"] == state["_report_view_rendered"] == "Overview"


def test_external_link_button_opens_only_after_click(monkeypatch):
    import webbrowser

    opened = []
    calls = []
    monkeypatch.setattr(webbrowser, "open", opened.append)

    def button(label, **kwargs):
        calls.append((label, kwargs))
        return len(calls) == 2

    monkeypatch.setattr(ui.st, "button", button)
    ui.external_link_button("Example report", "https://example.invalid/report", key="report", disabled=False)
    assert opened == []
    ui.external_link_button("Example report", "https://example.invalid/report", key="report", disabled=False)
    assert opened == ["https://example.invalid/report"]
    assert calls == [("Example report", {"key": "report", "disabled": False})] * 2


def test_is_parking_account_returns_a_boolean_for_each_label():
    assert ui.is_parking_account("Ask My Accountant") is True
    assert ui.is_parking_account("Suspense") is True
    assert ui.is_parking_account("Office supplies") is False
    assert ui.is_parking_account(None) is False


def test_statement_html_accepts_a_short_note_row_and_escapes_links():
    short = ui.statement_html([("note", "No activity")])
    assert "<tr class='note'>" in short
    assert "No activity" in short

    linked = ui.statement_html([
        ("item", "Cash <Operating>", [15.0], None, "?account=1&view=detail"),
    ])
    assert "href='?account=1&amp;view=detail'" in linked
    assert ">Cash &lt;Operating&gt;</a>" in linked


def test_financial_statement_sends_markup_to_streamlit(monkeypatch):
    rendered = []
    monkeypatch.setattr(ui.st, "html", rendered.append)
    rows = [("item", "Invented sales", [12.5])]

    ui.financial_statement(rows, headers=["October 2026"])

    assert rendered == [ui.statement_html(rows, headers=["October 2026"])]


def test_ledger_table_renders_rows_with_alignment_and_default_classes(monkeypatch):
    rendered = []
    monkeypatch.setattr(ui.st, "html", rendered.append)

    ui.ledger_table(["Account", "Amount"], [["Cash & bank", "15.00"]], ["l", "r"])

    assert len(rendered) == 1
    assert "<th class=''>Account</th><th class='r'>Amount</th>" in rendered[0]
    assert "<tr class=''><td class=''>Cash &amp; bank</td><td class='r'>15.00</td></tr>" in rendered[0]


def test_ledger_table_renders_optional_total(monkeypatch):
    rendered = []
    monkeypatch.setattr(ui.st, "html", rendered.append)

    ui.ledger_table(["Account", "Amount"], [["Sales", "8.00"]], ["l", "r"],
                    total_row=["Total", "8.00"], row_classes=["muted"])

    assert "<tr class='muted'>" in rendered[0]
    assert "<tr class='total'><td class=''>Total</td><td class='r'>8.00</td></tr>" in rendered[0]
