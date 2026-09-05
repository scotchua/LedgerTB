# Upstream sync log

## 2026-09-05 — Option A, financial statement groupings and cash flow

Base: `94bb6c3` on main. Source classification: internal. The read-only fetched
branch `upstream/feature/financial-statement-groupings-cash-flow` contains
exactly the following three commits outside main; there are no additional
report commits, so the escalation condition does not fire.

| Upstream commit | Content taken and retained |
|---|---|
| `9b57e4df5fe15cf6971f38b0035810b211f52eda` | Curated statement sections and subtype normalization in constants, accounts, seeds and COA import; grouped and comparative statements; indirect cash flow; chart review, Reports, MCP, spreadsheet and close-package integration, with their tests. |
| `bfa19baa8abe9a62a82b6a252a3c7407457e5135` | Bank and equipment aliases and conservative legacy cash detection; stale chart-selection handling; shared income-statement row assembly and unresolved-subtype warnings; opening-balance and mixed-entry cash-flow corrections; reuse of captured cash-flow reports in close packages; regression tests. |
| `9c2a0600b7b070f6fc89f2f04aaeece99d983bd2` | Cash-flow review corrections: explicit subtypes take precedence over cash-like names, word-boundary name detection, exact mixed-entry allocation, noncash disclosures and reconciliation readiness, financing proceeds/repayments and warning/export presentation; related regression tests. Its merge parent also brings the import-batch reversal work already in main. |

All three commits' final content was already incorporated by upstream's
squashed commit `159ccff97e133cc87902462e86f833b4ee2fdf09`, an ancestor of main.
`git diff 159ccff 9c2a060` is empty across the entire repository, and both
commits have tree `ceb5460bd0606cb9c72d640dfa7affbe660b32ce`. Consequently no
upstream content needed replaying. This sync preserves that content and the
subsequent fork/upstream fixes, including the newer earnings attribution and
conservative capital-alias handling. No merge, cherry-pick, branch creation,
commit, push or network operation was performed.

### Migration compatibility

Scott's explicit Option A selection renames only `900_account_grouping`,
`901_cash_flow_section` and `902_document_audits` to 043, 044 and 045,
respectively. Their SQL bodies are byte-for-byte identical to the base.
The fetched feature branch ends at 021, fetched upstream/main at 024, and
main's occupied low numbers at 042. Neither upstream ref occupies 043--045;
all current filenames have unique numeric prefixes. Existing 903--908 files
keep their names, and new fork migrations remain in the 900+ band.

The loader's narrow single-column recovery handles 043/044. The compatibility
step for 045 requires a recorded 902 stem and the exact complete shipped
table/index DDL, including checks, foreign keys and absence of extra objects.
It verifies and inserts the new tracking row in one transaction, preserving
the old row and all business data. It rejects missing/changed objects and
does not automatically reconcile an untracked existing table. Fresh history
contains 51 stems; the corresponding 900-upgraded history contains 54.

`test_fresh_and_900_upgraded_books_have_identical_schema` reconstructs the
base's filename ordering from the unchanged SQL bodies, builds both empty
and populated books, upgrades twice, and compares every table's DDL, columns,
foreign keys, indexes and index columns, including triggers and internal
schema objects. It checks business-row preservation, the explicit history
mapping, foreign keys and integrity using SQLite and the application's book
driver. Negative cases cover missing tables/indexes, wrong columns/checks/
foreign keys/index ordering, extra triggers and absent legacy tracking.

### Report composition and recorded expectations

Captions retain the subtype resolved against the original account name and
the containing statement section. Comparative matching uses that section,
so a shared caption stays inside Charlie's sections even when a different
account contributes first in each year. This also preserves the classification
of a legacy `Capital` account named Common Stock after its caption replaces
the account name. Scott's existing explicit cash-flow override remains ahead
of subtype classification and financing labels.

`tests/fixtures/upstream_sync_reports.json` records hand-calculated outputs
for `tests/test_upstream_sync_reports.py`. The fixture posts inventory
purchases and invoice COGS, a taxed invoice/payment/credit memo, a bill and
vendor payment, two fixed-asset depreciation runs, and prior/current payroll
with recorded deductions and employer benefits. Only the opening capital
and equipment acquisition use direct journals. All identities are invented;
payroll records supplied amounts and performs no tax calculation.

The expected current income is $130 revenue less $1,050 expenses = -$920.
Assets of $9,173 equal $193 liabilities plus $8,980 equity. The Workshop costs
caption compares $850 operating expenses with $100 prior-year expenses despite
different contributing accounts/legacy subtypes. The same caption remains
separate in COGS ($50) and depreciation ($150); balance-sheet captions also
remain separate across Current Assets and PP&E.

Cash falls from $9,900 to $7,330. With no override, operating cash is -$770
and investing cash -$1,800. Assigning Accounts Payable to financing moves its
$400 payment from operating to financing: operating -$370, investing -$1,800,
financing -$400. The $500 noncash expense financed by that payable is disclosed
and reconciled. Both paths tie and are ready, including comparative output
and the shared cash-flow export labels.

### Validation

- The requested `.venv/bin/python -m pytest -q -p no:cacheprovider` could not
  start because this worktree has no `.venv/bin/python` (exit 127).
- The existing interpreter at
  `/Users/scottedwards/Claude/apps/LedgerTB/.venv/bin/python` can execute the
  worktree's tests. It is used with `PYTHONDONTWRITEBYTECODE=1`, `-B`, and
  `-p no:cacheprovider` so it does not write bytecode into that external venv.
- Targeted schema/grouping/subtype/cash-flow and engine regressions: 83 passed
  in 7.69 seconds, before adding the two book-driver schema cases.
- Full suite using that existing interpreter, from this worktree:
  `PYTHONDONTWRITEBYTECODE=1 /Users/scottedwards/Claude/apps/LedgerTB/.venv/bin/python -B -m pytest -q -p no:cacheprovider`
  — **1,049 passed, 5 skipped in 124.22 seconds**. The five skips are the
  existing Windows NTFS alternate-data-stream cases in
  `tests/test_windows_blocking.py`; they require Windows and are skipped on
  macOS. Collection excluding the two new modules confirms 1,036 existing
  cases; the 18 added cases bring the total to 1,054, including the book-driver
  upgrades. No existing tests were removed or newly skipped.
- Running the new engine grouping regression with the original
  `HEAD:models/reports.py` fails as expected: its $100 prior-year operating
  expense appears on a separate caption instead of alongside the current
  $850. The same test passes with this change.
- Standalone SQLite checks: 13 passed before the book-driver parameter was
  added. Changed Python files parse, and `git diff --check` passes.
- A packaged application smoke test and real client-book upgrade were not
  run; schema upgrade coverage uses generated fixtures.
