"""How a financial statement is laid out, asserted against the markup itself.

``financial_statement`` draws through ``st.html``, which AppTest cannot observe
at all, so every one of these properties used to be unverifiable and all three
presentation defects below shipped unnoticed. ``statement_html`` exists to make
the markup assertable; these are the assertions.

The defects, for whoever reads this after a regression:

* a caption that sometimes began with an account number and sometimes did not
  put the words on two different left edges, so a grouped statement looked
  ragged. The number is its own column now and a caption never contains one.
* subtotal and total rules ran the full width, under the caption. A statement
  rules the amount columns and stops.
* the screen and the PDF formatted the same negative two different ways. One
  shared policy now answers that, so a test here covers both.
"""

import re
from datetime import datetime, timezone

import pytest

from utils.statement_format import statement_amount
from utils.ui import statement_html

ROWS = [
    ("section", "Assets", []),
    ("item", "Operating Checking", [48210.55], None, None, "1000"),
    ("item", "Accounts receivable, net", [96500.25], None, None, ""),
    ("subtotal", "Total Assets", [144710.80]),
    ("total", "Total Liabilities & Equity", [144710.80]),
]


def _rows_of(html, css_class):
    return re.findall(rf"<tr class='{css_class}'>(.*?)</tr>", html)


# ---- the ragged left edge

def test_a_caption_never_contains_an_account_number():
    """The defect itself: numbers glued into captions is what misaligned them."""
    html = statement_html(ROWS, show_numbers=True)
    for cell in re.findall(r"<td class='lbl'>(.*?)</td>", html):
        assert not re.match(r"^\d+\s*-", cell), cell


def test_numbered_and_unnumbered_items_put_the_caption_in_the_same_column():
    html = statement_html(ROWS, show_numbers=True)
    items = _rows_of(html, "item")
    assert "<td class='num'>1000</td><td class='lbl'>Operating Checking</td>" in items[0]
    # The grouped line has no number, but still an empty cell, so the caption
    # starts at the same x as the numbered one above it.
    assert "<td class='num'></td><td class='lbl'>Accounts receivable, net</td>" in items[1]


def test_headings_span_the_number_column_so_they_stay_outdented():
    """Without the span the number gutter pushes headings right of their items."""
    html = statement_html(ROWS, show_numbers=True)
    for kind in ("section", "subtotal", "total"):
        assert f"<td class='lbl' colspan='2'>" in _rows_of(html, kind)[0]


def test_group_headings_span_the_number_column_and_keep_their_style():
    html = statement_html([
        ("section", "Assets", []),
        ("group", "Current Assets", []),
        ("item", "Cash", [1.0], None, None, "1000"),
    ], show_numbers=True)
    group = _rows_of(html, "group")[0]
    assert "<td class='lbl' colspan='2'>Current Assets</td>" in group
    assert "table.pb-statement tr.group td" in html


def test_no_number_column_at_all_when_numbers_are_off():
    """The five call sites that never had numbers must keep today's markup."""
    html = statement_html(ROWS, show_numbers=False)
    assert "<td class='num'>" not in html
    # The stylesheet always carries the numbered rule; the table must not opt in.
    assert re.search(r"<table class='[^']*numbered", html) is None
    assert "colspan='2'" not in html


# ---- rules stop at the caption

def test_rules_sit_on_the_amount_cells_not_the_row():
    html = statement_html(ROWS)
    assert "tr.subtotal td.amt { border-top" in html
    assert "tr.subtotal td { font-weight: 700; padding-bottom" in html
    assert re.search(r"tr\.subtotal td \{[^}]*border-top", html) is None


def test_the_grand_total_keeps_its_double_rule():
    assert "border-bottom: 3px double" in statement_html(ROWS)


# ---- amounts

@pytest.mark.parametrize("value,lead,expected", [
    (0, False, "–"),            # exact zero reads as a dash
    (0.0, True, "–"),           # and a dash outranks the currency symbol
    (None, False, ""),          # no value at all is not the same as zero
    (-18124.0, False, "(18,124.00)"),
    (1234.5, True, "$1,234.50"),
    (1234.5, False, "1,234.50"),
])
def test_amount_formatting(value, lead, expected):
    assert statement_amount(value, lead) == expected


@pytest.mark.parametrize("value,expected", [
    (-4.2, "(4.2%)"), (0.0, "0.0%"), (18.1, "18.1%"), (None, ""),
])
def test_percent_formatting_has_no_dash_rule(value, expected):
    """A zero percent change is a real answer, not an absent one."""
    assert statement_amount(value, False, "percent") == expected


def test_the_currency_symbol_marks_only_the_summed_rows():
    html = statement_html(ROWS)
    assert "<td class='amt'>48,210.55</td>" in html
    assert "<td class='amt'>$144,710.80</td>" in html


# ---- shapes the callers actually pass

def test_short_rows_still_render():
    """Five of seven call sites pass three- and four-element rows."""
    html = statement_html([
        ("section", "Revenue", []),
        ("item", "Service revenue", [100.0]),
        ("item", "Other", [50.0], "Revenue"),
        ("subtotal", "Total", [150.0]),
    ])
    assert "<span class='muted'>Revenue</span>" in html
    assert "class='num'" not in html


def test_note_row_spans_every_column():
    plain = statement_html([("note", "No revenue recorded", [])])
    assert "colspan='2'" in plain
    numbered = statement_html(
        [("item", "x", [1.0], None, None, "1"),
         ("note", "No revenue recorded", [])],
        show_numbers=True)
    assert "colspan='3'" in numbered


def test_comparative_layout_widens_and_dates_its_headings():
    html = statement_html(
        [("item", "Cash", [1.0, 2.0, -1.0, -50.0], None, None, "1000")],
        headers=["As of Aug 31, 2026", "As of Aug 31, 2025", "$ Change", "% Change"],
        formats=["money", "money", "money", "percent"], show_numbers=True)
    assert "pb-statement wide numbered" in html
    assert "As of Aug 31, 2026" in html
    assert "<td class='amt'>(50.0%)</td>" in html


def test_an_empty_statement_does_not_explode():
    assert "<table" in statement_html([])


def test_consecutive_totals_each_keep_their_rule():
    html = statement_html([("total", "A", [1.0]), ("total", "B", [2.0])])
    assert len(_rows_of(html, "total")) == 2


def test_a_caption_with_markup_in_it_is_escaped():
    html = statement_html([("item", "R&D <script>", [1.0], None, None, "6000")],
                          show_numbers=True)
    assert "R&amp;D &lt;script&gt;" in html
    assert "<script>" not in html


def test_very_large_values_stay_on_one_line():
    html = statement_html([("total", "Total", [9876543210.99])])
    assert "$9,876,543,210.99" in html
    assert "white-space: nowrap" in html


# ---- the PDF half of the same policy

def _pdf_table_for(**kwargs):
    from services.close_package import _pdf_table
    return _pdf_table(
        ["Account", "Amount"], [["Cash", "1.00"]], [4.0, 1.0],
        money_from=1, totals_row=["Total", "1.00"], **kwargs)


def test_a_pdf_statement_drops_the_grid_shading():
    """Alternating row shading is a spreadsheet habit; statements do not use it."""
    listing = _pdf_table_for()
    statement = _pdf_table_for(statement=True)
    assert any(c[0] == "ROWBACKGROUNDS" for c in listing._bkgrndcmds)
    assert not any(c[0] == "ROWBACKGROUNDS" for c in statement._bkgrndcmds)


def test_a_pdf_statement_rule_starts_at_the_money_column():
    listing = _pdf_table_for()
    statement = _pdf_table_for(statement=True)
    listing_above = [c for c in listing._linecmds if c[0] == "LINEABOVE"][-1]
    statement_above = [c for c in statement._linecmds if c[0] == "LINEABOVE"][-1]
    assert listing_above[1][0] == 0        # today: spans the caption too
    assert statement_above[1][0] == 1      # fixed: starts at the first amount


def test_a_pdf_grand_total_gets_the_double_rule_it_never_had():
    plain = _pdf_table_for(statement=True)
    grand = _pdf_table_for(statement=True, grand_total=True)
    below_plain = [c for c in plain._linecmds
                   if c[0] == "LINEBELOW" and c[1][1] == -1]
    below_grand = [c for c in grand._linecmds
                   if c[0] == "LINEBELOW" and c[1][1] == -1]
    assert below_plain == []
    assert below_grand and below_grand[0][8] == 2   # two lines, not one


def test_a_pdf_statement_caption_carries_no_account_number():
    """The client-facing artifact had the ragged edge too, not just the screen."""
    from services.close_package import _statement_label
    numbered = {"account_number": "1000", "name": "Cash"}
    grouped = {"account_number": "", "name": "Property and equipment, net"}
    assert _statement_label(numbered) == "Cash"
    assert _statement_label(grouped) == "Property and equipment, net"


def test_both_renderers_format_the_same_negative_the_same_way():
    """The drift this policy exists to stop: (18,124.00) on screen, -18,124.00 in the PDF."""
    from services.close_package import _pdf_comparison_values
    item = {"current": -18124.0, "prior": None, "change": 0,
            "change_percent": None}
    assert _pdf_comparison_values(item) == ["(18,124.00)", "", "–", ""]
    assert "(18,124.00)" in statement_html([("item", "x", [-18124.0])])


def _statement_view(client_id, rows, **kwargs):
    from services.statement_pdf import StatementView

    return StatementView(
        client_id, "Income Statement",
        "For the period January 1, 2026 to January 31, 2026",
        tuple(rows), report_slug="income_statement", **kwargs,
    )


def _statement_pdf_text(payload):
    import pypdfium2 as pdfium

    document = pdfium.PdfDocument(payload)
    pages = []
    try:
        for index in range(len(document)):
            page = document[index]
            text_page = page.get_textpage()
            try:
                pages.append(text_page.get_text_range())
            finally:
                text_page.close()
                page.close()
    finally:
        document.close()
    return pages


def test_statement_view_validates_amount_shapes(client_id):
    from services.statement_pdf import StatementView

    with pytest.raises(ValueError, match="headers are required"):
        _statement_view(client_id, [("item", "x", [1, 2])])
    with pytest.raises(ValueError, match="headers must match"):
        _statement_view(
            client_id, [("item", "x", [1, 2])], headers=("Amount",),
        )
    with pytest.raises(ValueError, match="formats must match"):
        _statement_view(
            client_id, [("item", "x", [1, 2])],
            headers=("Current", "Prior"), formats=("money",),
        )
    assert StatementView(client_id, "Empty", "As of January 1, 2026", ()).amount_columns == 1


@pytest.mark.parametrize("columns,portrait", [(1, True), (2, True), (3, False), (4, False)])
def test_statement_pdf_orientation(client_id, columns, portrait):
    import pypdfium2 as pdfium
    from services.statement_pdf import build_statement_pdf

    view = _statement_view(
        client_id, [("item", "x", [1] * columns)],
        headers=tuple(f"H{i}" for i in range(columns)),
    )
    document = pdfium.PdfDocument(build_statement_pdf(view, datetime.now(timezone.utc)))
    page = document[0]
    try:
        width, height = page.get_size()
        assert (height > width) is portrait
    finally:
        page.close()
        document.close()


def test_statement_pdf_row_grammar_escaping_and_amount_parity(client_id):
    from services.statement_pdf import build_statement_pdf

    rows = [
        ("section", "Revenue", []),
        ("group", "Operating", []),
        ("item", "R&D <script>", [-18124.0, 0.0, 12.5], "note-slot", "?secret=1", "6000"),
        ("subtotal", "Subtotal", [0.0, 0.0, 0.0]),
        ("total", "Total", [-18124.0, 0.0, 12.5]),
        ("note", "A statement note", []),
    ]
    view = _statement_view(
        client_id, rows, headers=("Amount", "Zero", "Percent"),
        formats=("money", "money", "percent"), show_numbers=False,
    )
    text = "\n".join(_statement_pdf_text(build_statement_pdf(view, datetime.now(timezone.utc))))
    for expected in ("Revenue", "Operating", "R&D <script>", "Subtotal", "Total", "A statement note"):
        assert expected in text
    assert text.count("note-slot") == 1
    assert "?secret=1" not in text
    assert "6000" not in text
    assert "(18,124.00)" in text and "0.0%" in text and "12.5%" in text


def test_empty_statement_and_custom_legend_render(client_id):
    from services.branding import save_branding
    from services.statement_pdf import build_statement_pdf

    save_branding("Firm", report_legend="Custom report legend.")
    text = "\n".join(_statement_pdf_text(build_statement_pdf(
        _statement_view(client_id, []), datetime.now(timezone.utc)
    )))
    assert "No activity for this period." in text
    assert "Custom report legend." in text


def test_statement_pdf_optional_accounting_basis(client_id):
    from services.statement_pdf import build_statement_pdf

    generated_at = datetime.now(timezone.utc)
    period = "For the period January 1, 2026 to January 31, 2026"
    cash_pages = _statement_pdf_text(build_statement_pdf(
        _statement_view(client_id, [], basis="cash"), generated_at
    ))
    unset_pages = _statement_pdf_text(build_statement_pdf(
        _statement_view(client_id, []), generated_at
    ))

    assert cash_pages[0].count("Cash basis") == 1
    assert all("Cash basis" not in page and "Accrual basis" not in page
               for page in unset_pages)
    for expected in ("Test Co", "Income Statement", period):
        assert expected in cash_pages[0]
        assert expected in unset_pages[0]


def test_statement_pdf_corrupt_client_logo_fails_soft(client_id, caplog):
    from database.connection import get_cursor
    from services.branding import save_client_branding
    from services.statement_pdf import build_statement_pdf

    save_client_branding(
        client_id, logo=b"valid placeholder", logo_mime="image/png",
    )
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            "UPDATE client_branding SET logo = ? WHERE client_id = ?",
            (b"not an image", client_id),
        )

    with caplog.at_level("WARNING", logger="services.statement_pdf"):
        payload = build_statement_pdf(
            _statement_view(client_id, [("item", "x", [1])]),
            datetime.now(timezone.utc),
        )

    assert payload.startswith(b"%PDF")
    assert caplog.messages.count(
        "Could not render client logo for statement PDF"
    ) == 1


def test_long_statement_footer_running_header_and_final_total(client_id):
    from services.branding import save_branding
    from services.statement_pdf import build_statement_pdf

    save_branding("Invented Firm", report_legend="Every page legend.")
    rows = [("section", "Details", [])]
    rows.extend(("item", f"Line {index}", [index]) for index in range(200))
    rows.append(("total", "Final Total", [19900]))
    pages = _statement_pdf_text(build_statement_pdf(
        _statement_view(client_id, rows), datetime.now(timezone.utc)
    ))
    assert len(pages) > 1
    assert all("Every page legend." in page for page in pages)
    assert all("Prepared by Invented Firm" in page and "as of" in page for page in pages)
    assert all("Snapshot ID" not in page and "Document Audits" not in page for page in pages)
    assert "Income Statement" in pages[1]
    assert "Line 199" in pages[-1] and "Final Total" in pages[-1]
