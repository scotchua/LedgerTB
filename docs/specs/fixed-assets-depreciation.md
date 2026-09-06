# Fixed assets and depreciation

All amounts are integer cents. Runs are keyed by `(fixed_asset_id, period_end,
run_seq)`, starting at zero. Migration 910 upgrades existing books without
changing their amounts, journals, IDs or draft links. The historical named
unique index is retained, with `run_seq` as its third column.

## Posting and corrections

`run_depreciation` posts a run. `propose_depreciation_run` files a draft through
the existing MCP tool; it never posts or reverses a journal. Both accept
`run_seq=0` and optional `units_produced`. Approval carries those values and
recalculates against persisted state before posting. An already posted sequence
is refused by all three entry points; a second pending proposal for the same
sequence is also refused. Rejected drafts can be proposed again.

A correction requests exactly the preceding sequence plus one, for the asset's
latest posted period. In one transaction, the posting flow calls
`JournalEntry.reverse()` on the prior run's journal, posts the corrected journal,
inserts the replacement run, and sets the prior run's `superseded_by` to the new
run ID. Failure rolls back the reversal, replacement, run links and audit rows.
The generic journal reversal action still refuses source-controlled depreciation.
Earlier periods cannot be corrected while later runs exist: later calculations
would otherwise depend on an obsolete balance. Disposed assets and closed fiscal
periods refuse runs, proposals, approvals and corrections. Disposal also refuses
a closed date. Original posted journal amounts and lines remain immutable.

## Methods and conventions

The named default is **`full_month`**, preserving existing books and callers:
the in-service month receives a full month, and straight-line's final posted
month takes the rounding remainder. Dates must be calendar month-ends, on or
after the in-service month, in chronological order. Skipped months are not
automatically posted.

Explicit time conventions use the calendar year, independently of the client's
fiscal year. They are book policies, not a jurisdiction-specific tax schedule:

* **`mid_month`**: straight-line receives half a month in the first month, full
  months thereafter, and half a month in the terminal month (useful life months
  after the service month). Declining balance receives half its ordinary monthly
  charge in the first month. Days within the service month do not change it.
* **`half_year`**: the first calendar year's six-month allowance is spread over
  its eligible months: monthly weight `6 / (13 - in_service_month)`. Later years
  use weight 1. Straight-line requires a whole number of useful-life years; its
  terminal calendar year uses weight 1/2 each month. This gives half an annual
  charge in each boundary year. Time-based methods with explicit conventions
  require consecutive months from the service month.

Straight-line uses `(cost - salvage) / useful_life_months * monthly_weight`.
The final scheduled period takes the remaining depreciable cents. Declining
balance uses `opening_book_value * annual_rate / 12 * monthly_weight`, capped
at salvage; no automatic switch to straight-line is made. Each charge rounds
half up to a cent, with a minimum one cent for a positive calculation.

Units of production uses `(cost - salvage) * units_produced / total_units`.
`total_units` is a positive integer on the asset type; each run records a positive
integer number of actual units. Time conventions do not prorate actual output.
Output cannot exceed remaining lifetime units; the last units take the rounding
remainder. Corrections replace the prior run's units as well as its amount.

Arithmetic oracles (all cents):

* Straight-line, cost 10,000, salvage 0, three full months: 3,333; 3,333; 3,334.
* Mid-month, cost 12,000, salvage 0, three-month life: 2,000; 4,000; 4,000; 2,000.
* Half-year, January service, cost 24,000, 24-month life: 500/month in year 1,
  1,000/month in year 2, 500/month in year 3; total 24,000.
* Half-year, October service, cost 12,000, 12-month life: 2,000/month in October
  through December, then 500/month for the following year; total 12,000.
* Declining balance, cost 100,000, rate 24%: full-month charges 2,000; 1,960;
  1,921. Mid-month first two charges: 1,000; 1,980. Half-year January first two
  charges: 1,000; 990. A 99,950 salvage floor caps the first charge at 50.
* Production, cost 10,000, salvage 1,000, capacity 100: 25 units = 2,250;
  correction to 40 units = 3,600; remaining 60 units = 5,400.

## Disposal and reports

Disposal uses recorded, effective depreciation through the disposal date. It
does not silently accrue another period; callers record desired depreciation
before disposal. Disposal cannot predate an existing effective run. It removes
cost and accumulated depreciation, debits proceeds, and credits a gain or debits
a loss for `proceeds - (cost - accumulated)`. For cost 10,000 and accumulated
3,000, proceeds 8,000 gives a 1,000 gain; proceeds 5,000 gives a 2,000 loss.

`fixed_asset_register(client_id, as_of)` reports cost, accumulated depreciation
and book value at the requested date, with zero carrying balances after disposal.
`depreciation_roll_forward(client_id, start_date, end_date)` groups accumulated
depreciation by GL account: opening + depreciation - disposal removals = closing.
`depreciation_gl_tie_out(client_id, as_of)` compares register accumulated cents
with posted GL credits minus debits and exposes the difference per account.
All three use only runs with `superseded_by IS NULL`. Reports restate corrected
periods; the reversal and replacement journals use the same original period.
Registration itself does not post acquisition cost; tie-out does not conceal
manual GL entries or opening balances.

The existing uniqueness consumers are `run_depreciation`,
`propose_depreciation_run`, `DraftEntry.approve`,
`FixedAsset.accumulated_depreciation_cents`, `_depreciation_amount_cents`, and
`dispose_asset` (both accumulation and chronology). The journal reversal guard
reads by journal ID, not asset/period. No outside balance consumer was found.
