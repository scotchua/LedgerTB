# Design: three features, 2026-09-04

Status: proposed, awaiting Codex adversarial review, then Scott's approval.
Build is Codex's. Review of the build is Claude's.

Common thread. All three are human actions taken in the app, which runs with
no authorizer and full write rights. The assistant can do none of them: the
MCP process is INSERT-only on allowlisted tables. Each writes an audit row.
Each destructive action uses the app's existing two-step confirm pattern
(button, then inline warning with Confirm and Cancel, as Import Formats does
at pages/4_Import_Transactions.py:837-873).

---

## 1. Delete a draft pay run

### Facts

- No delete path exists for `pay_runs` or `pay_stubs`.
- `pay_stubs.pay_run_id` references `pay_runs(id)` with no `ON DELETE`;
  foreign keys are enforced, so stubs must go first.
- `pay_runs.status` is `CHECK(status IN ('draft','posted'))`. A soft
  "discarded" status needs a table-rebuild migration.
- A draft accepted from a provider import marks its `payroll_import_rows`
  `accepted`, but the row-to-run link is written only into the audit
  `new_values` (services/payroll_recording.py, accept_payroll_batch). **There
  is no stored column linking an import row to the pay run it produced.**
- `accept_payroll_batch` re-accepts only `pending` rows.

### Consequence that shapes the design

Deleting a draft that came from an import would strand its rows as
`accepted` with no run behind them, and they could never be re-accepted.
So a plain delete is wrong for imported drafts, and there is no stored data
to tell an imported draft from a hand-entered one.

### Design

- Migration 904 (fork band): `ALTER TABLE payroll_import_rows ADD COLUMN
  pay_run_id INTEGER NULL REFERENCES pay_runs(id)`. `accept_payroll_batch`
  sets it. One additive line in an upstream function.
- `discard_pay_run(pay_run_id)` in services/payroll_recording.py, one
  transaction:
  - refuse unless `status = 'draft'` and `journal_entry_id IS NULL`
  - revert linked import rows to `pending` (audit UPDATE each)
  - delete stubs, then the run
  - one audit DELETE row on `pay_runs` whose `old_values` snapshot the run
    and every stub (employee id, gross, net, deductions), so the history is
    reconstructable after the rows are gone. Precedent:
    `ImportedTransaction.delete` (models/transaction.py:468).
- UI: in the Pay Runs tab, when the selected run is a draft, a "Discard this
  draft" button below the stubs. Two-step confirm. The warning names the
  stub count and, when import rows are linked, says they return to the
  Import tab for review.
- Wording: "Discard", not "Delete". The app already says "dismiss" for
  import rows and "reject" for draft entries; drafts are discarded, ledger
  history is reversed.

Hard delete over soft status: drafts are not ledger history, the app already
hard-deletes non-ledger rows with an audit snapshot, and a soft status costs
a table rebuild for no user-visible gain.

---

## 2. Delete a journal entry after a warning

### Facts

- `JournalEntry.delete` exists and refuses by design: "Posted entries cannot
  be deleted. Reverse this entry instead." (models/journal_entry.py:464).
- Upstream v1.7.0 added `reverses_journal_entry_id` and
  `reversed_by_journal_entry_id` (migration 041, titled
  "immutable_journal_entries") and a Reverse Entry flow with guards for
  reconciled lines, imported postings, and invoice/bill/payment-controlled
  entries (models/journal_entry.py:reverse).
- Today reversing takes three steps: click Reverse on the entry, land on the
  Reverse Entry tab, fill the form. That friction is real.
- Draft entries already have Reject.

### The honest position

A hard delete of a posted entry reverses an explicit upstream architecture
decision and is wrong bookkeeping: it breaks the audit trail, can unbalance
a closed period, orphans reconciliation items and import links, and the
guards in `reverse()` exist precisely because those links are live. This is
Scott's call as a matter of professional judgment and costly-to-reverse
architecture, and it would be a permanent upstream divergence. **I recommend
against it, and design the thing that gives the same experience without the
damage.**

### Design: Void

- "Void" on a posted entry, one confirm, no form. It posts the equal and
  opposite entry through the existing `JournalEntry.reverse`, dated the same
  day as the original, memo "Void of JE #n", and inherits every existing
  guard unchanged. Nothing is deleted.
- The pair is hidden from View Entries and the general ledger by default
  behind a "Show voided" toggle, so the register reads as if the entry were
  gone. Trial balance and statements are unaffected either way because the
  pair nets to zero.
- Warning text, in the app's plain voice: "This posts a reversing entry
  dated [date] and hides both from the register. The original stays in the
  audit trail. Nothing is deleted."
- If the guards refuse (reconciled, imported, invoice-linked), the user sees
  the existing guard message and the existing paths remain: Correct
  category, batch reversal, reopen reconciliation.
- Void of a void is refused by the existing already-reversed check.

Scope note. "Hidden by default" is a read-side filter on
`reversed_by_journal_entry_id IS NULL AND reverses_journal_entry_id IS NULL`
plus the toggle. No schema change. The reversal columns already exist.

If Scott nonetheless wants true deletion, that is a separate design with its
own migration, its own guard list, and an explicit ratification. Not
proposed here.

---

## 3. AI categorization through MCP, no API key

Designed twice already with Codex; see `scope-mcp-suggest-categories-v2.md`
and its disposition. Not repeated. What remains is two decisions and one
reframing.

### Reframing, from Scott's brief

"It's stupid that it's a separate feature that requires separate setup."
Agreed, and it resolves Codex's strongest pass-2 finding. Today's in-app
categorizer and the MCP path become **one mechanism**: both write
`import_suggestions` (source `in_app` or `assistant`) and both are read
through the single `effective_coding` projection. The API key stops being a
requirement and becomes an optional second source for users without an MCP
client. For this firm it is simply unused.

### Decision 1: stop preselecting (recommended)

A suggestion is shown beside an empty account picker with its confidence and
reason; the CPA picks. This closes BLOCKER 1 (an accepted-but-unchanged
preselect never fires `on_change`, so the AI's choice would post with no
human decision recorded) and removes the whole class: no detached reason, no
ambiguity about who chose. One click per row. The in-app button changes to
match, which is the unification above.

Alternative: keep the preselect and add a per-row Accept control. Works,
more UI, and leaves the grid showing an AI choice with no decision behind it
until Accept is pressed.

### Decision 2: on_change persistence

Recommend writing the human decision on the picker's `on_change`, with an
audit row, plus a transactional batch path for bulk categorize (which sets
session state in a loop and never fires per-widget callbacks,
pages/4_Import_Transactions.py:1805). Alternative is an explicit save
button. Not recommended.

### Carried forward, already accepted

Consistency trigger on `import_suggestions` (BLOCKER 2), tagged state
projection, audit on decision writes, book-namespaced widget keys,
newest-then-stale eligibility, conditional insert against `decided_at`,
restrict-plus-explicit-cleanup instead of CASCADE, request idempotency id,
per-item tool results. Test matrix as listed in v2.

---

## Order and shape

1 and 2 are small, independent, and low risk. 3 is the large one. Recommend
Codex builds them as three separate commits in that order, each with tests,
each reviewed before the next starts. Nothing pushes until all three are
reviewed.

---

# Codex adversarial review, disposition

Peer: codex-cli 0.151.0, session 01a06cbc, 2026-09-04. 20 findings, 5
BLOCKERs. Each checked against code. [fact] = verified by inspection,
[proposed] = accepted on reasoning, awaiting build evidence.

## Feature 1, discard a draft pay run

Accepted:
- **BLOCKER. The new foreign key blocks the delete.** Reverting an import
  row's status without clearing `pay_run_id` leaves a RESTRICT reference and
  the run cannot be deleted. Fix: one UPDATE sets `status='pending',
  pay_run_id=NULL` per linked row, before the deletes. Design omission. [fact]
- **Legacy rows.** Rows accepted before migration 904 have no link. Fix: 904
  backfills `pay_run_id` from `audit_log.new_values` (json_extract on rows
  where table_name='payroll_import_rows' and action='UPDATE'), which is where
  accept_payroll_batch already records it. Deterministic, no guessing. [proposed]
- **One audit row per deleted stub, plus one for the run.** Matches the
  existing precedent in `ImportedTransaction.delete_batch`
  (models/transaction.py:492), which writes a DELETE row per transaction. [fact]
- **`BEGIN IMMEDIATE`** and revalidate after the write lock. Already the house
  pattern in four places (models/transaction.py:291, services/bank_feed.py,
  services/close_package.py:79). [fact]
- Hard delete for drafts: Codex concurs. Kept.

Rejected with evidence:
- **"A later dismissal could be erased."** Unreachable. `dismiss_payroll_row`
  refuses any row whose status is not `pending`
  (services/payroll_recording.py:511-513), so accepted rows cannot be
  dismissed. Reverting only rows with `status='accepted'` is adopted anyway
  as a free guard. [fact]
- **"A second acceptance can create an empty run."** `accept_payroll_batch`
  refuses when no rows are pending and refuses when any row is dismissed
  (services/payroll_recording.py:437-441). [fact]

## Feature 2, Void

Accepted:
- **BLOCKER. Closed period.** Same-date reversal into a closed period is
  refused by `reverse()` itself (models/journal_entry.py:554, 565). Void
  preflights the period and, when closed, shows that message and points to
  Reverse Entry for an open date. No silent date substitution. Found
  independently before the review returned. [fact]
- **BLOCKER. Void is not distinguishable from a deliberate reversal.** My
  "no schema change" claim was wrong. The proposed predicate would hide every
  reversal pair in the book, including accrual reversals a CPA wants visible.
  Fix: migration 905 adds `journal_entries.reversal_kind TEXT NULL CHECK
  (reversal_kind IN ('reversal','void'))`. `reverse()` gains a `kind`
  argument and stamps both sides in its existing transaction. Legacy NULL
  means ordinary reversal. The filter matches `kind='void'` only. [fact]
- **The filter is presentation, never an accounting input.** Verified scope:
  the only readers of the link columns are models/journal_entry.py and
  pages/2_Journal_Entries.py. models/reports.py (general ledger, statements)
  never touches them. The toggle lives in `JournalEntry.get_all`'s shared
  WHERE clauses behind a flag that only View Entries passes, so list and
  totals cannot disagree (models/journal_entry.py:325) and the general
  ledger, reconciliation, and close see the complete ledger. [fact]
- Audit action stays REVERSE with `kind` in new_values. Codex concurs.
- Pair symmetry: `reverse()` writes `reverses_journal_entry_id` on the new
  entry and `reversed_by_journal_entry_id` on the original in one transaction
  (models/journal_entry.py:585-612). [fact]

## Feature 3, categorization

Accepted:
- **BLOCKER. A suggestion must never become effective coding for posting.**
  Stated explicitly now: `effective_coding` returns candidates; the effective
  account is NULL until `decided_account_id` is written; posting requires it.
  Today's posting already refuses uncategorized rows, so this is the same
  gate made durable. [proposed]
- **BLOCKER. Client-consistency trigger.** Already in the build list from
  pass 2. Codex's point is that accepted is not built. Agreed.
- **500 rows of empty pickers is impractical.** Decision 1 amended: empty
  picker, plus a per-row "Use suggestion" button, plus one "Accept all
  high-confidence suggestions" action behind a confirm. Every path writes a
  human decision transactionally with an audit row. The explicit human act
  is preserved; the click count is not. [proposed]
- **`decided_suggestion_id`**, nullable, on `imported_transactions`, so the
  accepted candidate is known when two sources proposed the same account.
  NULL means a manual pick. [proposed]
- **Deterministic multi-source display**: newest by (created_at, id) shown,
  all candidates retained, conflicts surfaced. A late suggestion never
  supersedes a decision, enforced by the conditional insert. [proposed]
- **`source` is hard-coded per write path.** The tool never accepts it. [proposed]
- Decision 2 (on_change plus batch path) confirmed by Codex. Kept.

## Net effect on scope

- Feature 1: one migration (904) with a backfill, one service function, one
  UI block. Small.
- Feature 2: one migration (905), a `kind` argument on `reverse()`, a flag on
  `get_all`, one UI action and toggle. Small.
- Feature 3: as pass 2, plus two accept controls and one column. Large, as
  already known.

---

# Ratification

2026-09-04, Scott: "Approved all three, void is fine, have codex build."
[settled] Feature 1 hard-delete discard; Feature 2 Void in place of delete;
Feature 3 with amended accept controls. Build order 1, 2, 3, Codex authors in
the confined worktree, Claude reviews each diff before the next starts.
