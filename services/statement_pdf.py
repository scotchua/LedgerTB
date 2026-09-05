"""Client-facing PDF rendering for the four financial statements."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import logging

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from models.client import Client
from services.branding import get_branding, get_client_branding
from services.close_package import (
    _PDF_BODY,
    _PDF_H1,
    _PDF_H2,
    _PDF_META,
    _logo_flowable,
    _safe_paragraph,
    _wrap,
)
from utils.dates import long_datetime
from utils.statement_format import DOUBLE_RULE_BELOW, LEAD_DOLLAR, RULE_ABOVE, statement_amount

logger = logging.getLogger(__name__)


def statement_pdf_audit_args(client_id, view, file_name, payload, generated_at):
    return (client_id, "EXPORT", f"{view.report_slug}_pdf_export", {
        "format": "pdf",
        "file_name": file_name,
        "params": dict(view.params),
        "row_count": len(view.rows),
        "generated_at": generated_at,
        "sha256": sha256(payload).hexdigest(),
    })


@dataclass(frozen=True)
class StatementView:
    client_id: int
    title: str
    period_text: str
    rows: tuple
    headers: tuple = ()
    formats: tuple = ()
    show_numbers: bool = False
    report_slug: str = "statement"
    params: tuple = ()
    basis: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "rows", tuple(tuple(row) for row in self.rows))
        object.__setattr__(self, "headers", tuple(self.headers or ()))
        object.__setattr__(self, "formats", tuple(self.formats or ()))
        amount_columns = self.amount_columns
        if amount_columns > 1 and not self.headers:
            raise ValueError("headers are required for statements with multiple amount columns")
        if self.headers and len(self.headers) != amount_columns:
            raise ValueError("headers must match the number of amount columns")
        if self.formats and len(self.formats) != amount_columns:
            raise ValueError("formats must match the number of amount columns")

    @property
    def amount_columns(self) -> int:
        row_columns = max(
            (len(row[2]) for row in self.rows if len(row) > 2 and row[2] is not None),
            default=0,
        )
        return max(row_columns, len(self.headers), len(self.formats), 1)


class NumberedCanvas(Canvas):
    def __init__(self, *args, footer, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []
        self._footer = footer

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        page_count = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self._footer(self, page_count)
            super().showPage()
        super().save()


def _no_split_ranges(rows):
    ranges = set()
    for index, row in enumerate(rows):
        kind = row[0]
        if kind == "section" and index + 1 < len(rows):
            ranges.add((index, index + 1))
        if kind == "item" and index + 1 < len(rows) and rows[index + 1][0] in {"subtotal", "total"}:
            ranges.add((index, index + 1))
        if kind == "subtotal" and index + 1 < len(rows) and rows[index + 1][0] == "total":
            ranges.add((index, index + 1))
    return sorted(ranges)


def _statement_table(view: StatementView, page_width: float) -> Table:
    amount_columns = view.amount_columns
    formats = list(view.formats or ("money",) * amount_columns)
    label_columns = 2 if view.show_numbers else 1
    table_rows = [[
        *(["Acct #", "Account"] if view.show_numbers else ["Account"]),
        *(view.headers or ("Amount",)),
    ]]
    styles = [
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LINEBELOW", (0, 0), (-1, 0), 0.75, colors.black),
        ("ALIGN", (label_columns, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    rows = view.rows or (("note", "No activity for this period.", ()),)
    for data_index, row in enumerate(rows):
        kind, label = row[0], str(row[1])
        amounts = row[2] if len(row) > 2 and row[2] is not None else ()
        note = row[3] if len(row) > 3 else None
        number = row[5] if len(row) > 5 else None
        row_index = data_index + 1
        suffix = f" <font color='#777777'>{_safe_text(str(note))}</font>" if note else ""
        label_cell = Paragraph(_safe_text(label) + suffix, _PDF_BODY)
        if kind in {"section", "group", "note"}:
            table_rows.append([label_cell] + [""] * (label_columns + amount_columns - 1))
            styles.append(("SPAN", (0, row_index), (-1, row_index)))
        else:
            cells = ([str(number or ""), label_cell] if view.show_numbers else [label_cell])
            values = list(amounts) + [None] * (amount_columns - len(amounts))
            cells.extend(
                statement_amount(value, kind in LEAD_DOLLAR, formats[index])
                for index, value in enumerate(values)
            )
            table_rows.append(cells)
        if kind in {"section", "group", "subtotal", "total"}:
            styles.append(("FONTNAME", (0, row_index), (-1, row_index), "Helvetica-Bold"))
        if kind == "section":
            styles.extend([
                ("TOPPADDING", (0, row_index), (-1, row_index), 9),
                ("BOTTOMPADDING", (0, row_index), (-1, row_index), 4),
            ])
        if kind == "group":
            styles.append(("BACKGROUND", (0, row_index), (-1, row_index), colors.HexColor("#F1F1EE")))
        if kind == "note":
            styles.extend([
                ("TEXTCOLOR", (0, row_index), (-1, row_index), colors.HexColor("#777777")),
                ("FONTSIZE", (0, row_index), (-1, row_index), 7),
            ])
        if kind in RULE_ABOVE:
            styles.append(("LINEABOVE", (label_columns, row_index), (-1, row_index), 0.5, colors.HexColor("#777777")))
        if kind in DOUBLE_RULE_BELOW:
            styles.append(("LINEBELOW", (label_columns, row_index), (-1, row_index), 0.75, colors.black, None, None, None, 2, 1.2))
    for start, end in _no_split_ranges(rows):
        styles.append(("NOSPLIT", (0, start + 1), (-1, end + 1)))

    usable_width = page_width - inch
    number_width = 0.68 * inch if view.show_numbers else 0
    amount_width = min(1.35 * inch, usable_width * 0.62 / amount_columns)
    label_width = usable_width - number_width - amount_width * amount_columns
    widths = ([number_width, label_width] if view.show_numbers else [label_width])
    widths.extend([amount_width] * amount_columns)
    table = Table(table_rows, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle(styles))
    return table


def _safe_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;")


def build_statement_pdf(view: StatementView, generated_at: datetime) -> bytes:
    client = Client.get_by_id(view.client_id)
    if not client:
        raise ValueError("Client not found.")
    client_branding = get_client_branding(view.client_id)
    firm_branding = get_branding()
    entity = client_branding.display_name or client.name
    accent_hex = client_branding.accent_hex or firm_branding.accent_hex
    accent = colors.HexColor(accent_hex) if accent_hex else colors.black
    page_size = letter if view.amount_columns <= 2 else landscape(letter)
    heading_1 = ParagraphStyle("statement_h1", parent=_PDF_H1, textColor=accent)
    heading_2 = ParagraphStyle("statement_h2", parent=_PDF_H2, textColor=accent)
    running = ParagraphStyle("statement_running", parent=_PDF_META, fontSize=7.5, leading=9)
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=page_size,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.72 * inch, bottomMargin=0.82 * inch,
        title=f"{view.title} - {entity}",
        author=firm_branding.firm_name or "LedgerTB",
    )

    def footer(canvas, page_count):
        canvas.saveState()
        width, height = page_size
        page_number = canvas.getPageNumber()
        canvas.setFillColor(colors.HexColor("#666666"))
        if page_number > 1:
            canvas.setFont("Helvetica", 7.5)
            canvas.drawString(0.5 * inch, height - 0.36 * inch, f"{entity} · {view.title} · {view.period_text}")
        canvas.setFont("Helvetica", 7)
        canvas.drawString(0.5 * inch, 0.47 * inch, f"{entity} · {view.period_text}")
        canvas.drawRightString(width - 0.5 * inch, 0.47 * inch, f"Page {page_number} of {page_count}")
        prepared = f"Prepared by {firm_branding.firm_name}" if firm_branding.firm_name else "Prepared by LedgerTB"
        center = f"{prepared} from the books as of {long_datetime(generated_at)} {generated_at.tzname() or ''}. {firm_branding.report_legend}"
        paragraph = Paragraph(_safe_text(center), running)
        paragraph.wrapOn(canvas, width - 3.0 * inch, 0.35 * inch)
        paragraph.drawOn(canvas, 1.5 * inch, 0.12 * inch)
        canvas.restoreState()

    logo = None
    if client_branding.logo:
        logo = _logo_flowable(client_branding, max_height=0.55 * inch)
        if logo is None:
            logger.warning("Could not render client logo for statement PDF")
    story = []
    if logo:
        logo.hAlign = "LEFT"
        story.extend([logo, Spacer(1, 5)])
    story.extend([
        _safe_paragraph(entity, heading_1),
        _safe_paragraph(view.title, heading_2),
        _safe_paragraph(view.period_text, _PDF_META),
    ])
    if view.basis:
        story.append(_safe_paragraph(f"{view.basis.title()} basis", _PDF_META))
    story.extend([Spacer(1, 10), _statement_table(view, page_size[0])])
    doc.build(story, canvasmaker=lambda *args, **kwargs: NumberedCanvas(*args, footer=footer, **kwargs))
    return buffer.getvalue()
