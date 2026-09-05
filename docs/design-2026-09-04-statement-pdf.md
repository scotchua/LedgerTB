# Design: Download PDF for the four financial statements

Status: proposed, Codex-reviewed (codex-cli 0.151.0, session 01a06dd5,
2026-09-04, 34 findings, 1 BLOCKER). Awaiting Scott's decisions below, then
Codex builds and Claude reviews.

## The point

A "Download PDF" beside each "Download Excel" on Trial Balance, Income
Statement, Balance Sheet, and Cash Flow. The PDF is built from the exact row
tuples the screen just drew, through the same amount policy, so screen and
paper cannot disagree by construction. It is an ad hoc export and must not
read as a close package.

## Design, revised after review

### One view model per statement

Each statement builds a frozen `StatementView` once and hands the same object
to the screen and to the PDF:

- `rows`: the `(kind, label, amounts, note, href, number)` tuples
- `headers`, `formats`, `show_numbers`
- `title` ("Balance Sheet"), `period_text` in statement-specific language:
  "As of September 4, 2026" for TB and BS, "For the period January 1, 2026
  to September 4, 2026" for IS and CF; comparative mode puts the exact dates
  in the column headers, which are required whenever there is more than one
  amount column
- `client_id` only; entity display name comes from client branding then the
  Client record, never from a second name argument

`financial_statement` keeps its signature; the page passes the view's fields.
This closes the copy-paste divergence Codex raised: there is one source for
both renderers.

### `services/statement_pdf.py`, statement-specific, no shared refactor

`build_statement_pdf(view, generated_at) -> bytes`. It does NOT move
`_pdf_table` or the close-package composers. The close package's table
carries close semantics (one totals row, close-specific ruling) and its
masthead and footer carry trust stamps that must never appear here. Shared
with the close package: only `_logo_flowable`, the escaping helper, and page
geometry constants, imported read-only. Codex's re-export and globals
findings disappear because nothing moves.

Row mapping:

- section: bold heading spanning label columns, top padding, kept with its
  first child
- group: bold grey label spanning label columns
- item: label (number in its own column when `show_numbers`), amounts
- subtotal: bold, rule above the amount cells only
- total: bold, rule above and double rule below the amount cells only
- note kind: small grey caption spanning every column
- the `note` slot on any row: rendered as a muted suffix after the label,
  exactly as `statement_html` does
- `href`: dropped; a PDF has no drill-down, and app-local URLs must not
  print
- `number`: never printed when `show_numbers` is off

Amounts through `statement_amount(value, kind in LEAD_DOLLAR, formats[i])`.
Column count is the empty-safe max over rows, headers, and formats; lengths
are validated; an empty statement renders a "No activity for this period"
line. Every string crosses one escaping boundary before it becomes a
Paragraph. Fonts stay Helvetica, as the close package does today; a
Unicode-embedded font is deferred with the entry condition "a real client
name fails to render" (same limitation the close package has now).

Page: portrait letter for 1 or 2 amount columns, landscape for 3 or more.
Column headers repeat on every page. A compact running header (entity,
title, period) on continuation pages. No-split ranges are narrow: heading
plus first child, last detail row plus its subtotal or total, subtotal plus
following total. Never a whole section.

### What the page says about itself

Masthead: client logo if any, entity display name in the accent color,
statement title, period text.

Footer, every page: entity and period left, "Page n of N" right, and a
center line: "Prepared by <firm> from the books as of <timestamp with time
zone>." plus the legend (decision 1 below).

Deliberately absent: snapshot hash, document-audit id, and anything else the
close package uses as a trust mark.

### Audit

`on_click=AuditLog.log_event(client_id, "EXPORT", "<report>_pdf_export",
payload)` where payload carries the filename, the report parameters (dates,
comparative flag, grouping, show_numbers), `generated_at`, row count, and
the SHA-256 of the bytes offered. Streamlit runs the callback on the click,
not on render (Codex confirmed; a test asserts zero rows after render, one
after one click). The event records an export attempt; delivery is the
browser's. Same semantics as Excel today, with a richer payload.

### Widget and filename hygiene

Stable keys through `report_key("<report>_pdf")`. Filenames slugged and
length-limited: `balance_sheet_<client-slug>_2026-09-04.pdf`; the readable
entity name lives inside the document. Logo rendering fails soft: a bad logo
logs a warning and the statement prints without it.

### Performance

Bytes are cached by a hash of the view plus branding revision, so reruns do
not regenerate; `generated_at` is fixed at first build within a session so
the audit hash and the printed timestamp agree.

## Decisions for Scott

1. **Legend wording on every page.** Codex's point stands on its own and it
   is also a standards point: when a CPA firm prepares financial statements
   for a client, each page should carry a no-assurance legend (AR-C 70).
   Proposed default, editable in Firm Settings as a new "Report legend"
   field: "No assurance is provided on these financial statements. Prepared
   for management use from the client's books." Your wording, your call.
2. **Basis.** The app does not track cash vs accrual anywhere. Two options:
   omit basis from the PDF for now, or add a per-client basis setting
   (migration, Clients page, one line on the masthead). Recommend omit now
   and add the setting as its own small change, because printing a basis
   the app does not know would be invention.
3. **"Prepared by."** Keep the firm name as the close package does, or
   print only the legend. Recommend keep it.

## Codex disposition summary

Accepted: required document context (as the view model plus decisions
above), note-slot rendering, empty and ragged handling, required comparative
headers, href dropped, central escaping, no shared refactor of `_pdf_table`
and separate composers, per-document styles, richer audit payload with
artifact hash, stable widget keys, single view model, filename slugging,
logo fail-soft, pagination no-split ranges, repeated headers, running
header, Page n of N, statement-specific period language, timestamp with
time zone, GL and AR/AP explicitly out of scope for this renderer.

Rejected or reframed with evidence:

- "Existing close-package tests are insufficient for the refactor." Moot:
  nothing moves. Also, tests/test_close_package.py:718-720 already assert
  the snapshot id and document-audit id in the rendered footer.
- "Currency and units must be stated." The app is USD only with no
  multi-currency anywhere; a per-page "USD" is noise. Not adopted.
- "Audited serving endpoint for fail-closed delivery." Out of scope and
  inconsistent with the Excel path; the honest fix is to name the event an
  export attempt and hash the bytes, which is adopted.
- "Embed a Unicode font." Deferred with an entry condition; the close
  package has the identical limitation today and no client name has failed.

Deferred: Unicode font embedding; per-client basis setting (decision 2).
