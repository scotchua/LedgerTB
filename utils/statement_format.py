"""One presentation policy for financial statements, shared by both renderers.

Statements are drawn twice from the same report dictionaries: on screen as an
HTML table and into the close package as a PDF table. Nothing used to hold the
two together, and they had already drifted: the same negative balance printed
as ``(18,124.00)`` on screen and ``-18,124.00`` in the PDF a client receives.

This module owns the decisions a reader would notice, so the two cannot answer
them differently. It deliberately does not own layout. An HTML table and a
ReportLab table have nothing useful to share about geometry, and forcing one
abstraction over both would be a larger change than the problem justifies.

Deliberately absent: a currency symbol beyond the dollar the app already
assumes, unit scaling, and whole-dollar rounding. Rounding each line
independently stops the lines adding to their subtotals, and there is no honest
way to show that without a footing policy this app has no reason to carry yet.
"""

# A statement rule sits over the amount columns and stops at the caption. A
# line running under the words is a data-grid idiom; statements do not use it.
RULE_ABOVE = frozenset({"subtotal", "total"})
DOUBLE_RULE_BELOW = frozenset({"total"})

# Accounting's first-and-last convention, reduced to what these statements
# need: the currency symbol marks where a column is summed, not every line.
LEAD_DOLLAR = frozenset({"subtotal", "total"})

# An exact zero prints as a dash. Only an exact zero: nothing here rounds, so
# there is no "rounds to zero" case for a dash to quietly hide. ``None`` means
# "no value at all" and prints blank, which is a different statement about the
# number and has to keep looking different.
ZERO_DASH = "\u2013"


def statement_amount(value, lead_dollar: bool = False,
                     value_format: str = "money") -> str:
    """Format one amount for a statement, screen or PDF.

    Negatives in parentheses, thousands grouped, two decimals, an exact zero as
    a dash, and the currency symbol only where ``lead_dollar`` says a column is
    being summed.
    """
    if value is None:
        return ""
    if value_format == "percent":
        body = f"{abs(value):,.1f}%"
        return f"({body})" if value < 0 else body
    if value == 0:
        return ZERO_DASH
    body = f"{abs(value):,.2f}"
    if value < 0:
        body = f"({body})"
    return f"${body}" if lead_dollar else body
