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

import pytest

from utils.statement_format import statement_amount
from utils.ui import statement_html

ROWS = [
    ("section", "Assets", []),
    ("item", "Operating Checking", [48210.55], None, "1000"),
    ("item", "Accounts receivable, net", [96500.25], None, ""),
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
        ("item", "Cash", [1.0], None, "1000"),
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
        [("item", "x", [1.0], None, "1"), ("note", "No revenue recorded", [])],
        show_numbers=True)
    assert "colspan='3'" in numbered


def test_comparative_layout_widens_and_dates_its_headings():
    html = statement_html(
        [("item", "Cash", [1.0, 2.0, -1.0, -50.0], None, "1000")],
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
    html = statement_html([("item", "R&D <script>", [1.0], None, "6000")],
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
