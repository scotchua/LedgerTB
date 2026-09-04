# Design pass 2: assistant category suggestions

Supersedes the design half of `scope-mcp-suggest-categories.md`. That file's
Codex disposition still stands and is not repeated here.

Status: proposed. Not built. Not yet re-reviewed.

Date: 2026-09-04

## What pass 1 got wrong

Pass 1 assumed a CPA's coding of a Pending row was durable, and built a
precedence rule on top of it. It is not durable. `suggested_account_id` is
written only at posting time (services/posting.py:211) and by a post-hoc
recode (services/import_corrections.py:135). While a row is Pending, the
human's choice exists only in Streamlit session state.

Two consequences, both of which pass 1 missed:

- The precedence rule was vacuous. "Seed only when the column is empty" is
  always true for a Pending row, so an assistant suggestion would seed over
  work in progress.
- There was no way to express "I looked at this and rejected the suggestion,"
  so a dismissed suggestion would return on every reload forever.

## The fact that reframes the design

The SQLite authorizer is installed **only when `ASSISTANT_ACCESS_LEVEL` is
set** (database/connection.py:283-286), which happens only in the MCP
process. The Streamlit app runs with no authorizer and full write rights.

So there are two writers with different rights, and the append-only
constraint is a property of the assistant, not of the data:

- Assistant: INSERT only, on allowlisted tables. Proposals.
- App, acting for the human: full rights. Decisions.

Pass 1 treated append-only as a property of the whole feature and ended up
trying to express a human decision as the absence of one. A decision is the
app's to record, plainly.

## Design

Three parts. Each is separately useful and they land in this order.

### 1. Stable identity for staged rows

`row_key("cat", t)` is `f"cat_{t['uid']}"`, and `ensure_row_ids` mints a
fresh `uuid4` per load. Pressing "Load staged" a second time therefore
abandons every widget key and re-seeds from scratch, discarding in-session
coding. That is a live defect today, independent of this feature.

Fix: in `prepare_staged_for_review`, set `uid = f"s{staged_id}"` before
calling `ensure_row_ids`, which already preserves a pre-existing uid
(guarded by tests/test_import_review.py:33). CSV rows with no staged_id keep
uuid4.

Effect: a staged row's widget key is stable for the life of the session, so
"this row already has a value" becomes a meaningful question and a reload
stops destroying work.

### 2. Durable human decision

New columns on `imported_transactions` (migration 903, fork band):

- `decided_account_id INTEGER NULL REFERENCES accounts(id)`
- `decided_at TIMESTAMP NULL`
- `decided_by TEXT NULL`

Written app-side when the CPA changes a row's account, via the selectbox
`on_change`. `decided_at IS NOT NULL` is the marker, so the tri-state falls
out naturally:

- `decided_at` NULL: never ruled on. A suggestion may seed.
- `decided_at` set, account set: the CPA's coding. Nothing may override it.
- `decided_at` set, account NULL: explicitly cleared. A suggestion may not
  seed. This is the dismissal Codex asked for, at no extra structure.

Deliberately NOT reusing `suggested_account_id`: it means "what was posted"
for a Posted row, and overloading it with "what a human picked while still
Pending" would make both meanings ambiguous for every existing reader.

This also fixes something unrelated and real: coding a long import no longer
evaporates if the app restarts before posting.

### 3. Assistant proposals

`import_suggestions` as in pass 1, with the review's corrections applied:

```sql
CREATE TABLE IF NOT EXISTS import_suggestions (
    id INTEGER PRIMARY KEY,
    imported_transaction_id INTEGER NOT NULL
        REFERENCES imported_transactions(id) ON DELETE CASCADE,
    suggested_account_id INTEGER NOT NULL
        REFERENCES accounts(id) ON DELETE RESTRICT,
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_import_suggestions_txn
    ON import_suggestions(imported_transaction_id, created_at DESC, id DESC);
```

Changes from pass 1, each tracing to a finding:

- `client_id` dropped. It was redundant and unconstrained, and allowed a
  structurally valid but internally inconsistent triple. The client is
  reached through the transaction.
- `ON DELETE` stated explicitly. CASCADE on the transaction, because a
  proposal about a deleted row is meaningless. RESTRICT on the account, to
  match how every other account reference behaves.
- Index carries the ordering, `id` as final tie-breaker. Timestamps tie
  inside one batch.
- `Account.deletion_blockers` gains this table (models/account.py:344). Its
  docstring promises every referencing table is checked.

### 4. One canonical projection

A single repository function, the only place precedence is expressed:

```python
def effective_coding(client_id) -> dict[int, Coding]:
    """Per staged transaction: what the grid should show and why."""
```

Returns, per transaction id: the account to preselect (or None), the
provenance (`human` / `assistant` / `none`), and, when assistant, the
confidence and reason. Precedence: a human decision wins; otherwise the
newest non-superseded suggestion whose account is still active and still
Revenue or Expense; otherwise nothing.

Consumed by **both** `prepare_staged_for_review` and `list_staged_imports`.
Two independent rankings is how the UI and the assistant drift apart.

Eligibility is revalidated here, not just at insert: an account can be
deactivated or retyped after a suggestion is stored.

### 5. The tool

`suggest_categories(client_id, suggestions)` at propose level.
`suggestions`: `{transaction_id, account_number, confidence, reason}`.

- Duplicate transaction_ids within one request: rejected.
- `reason` bounded at 500 characters.
- Per-item results, not first-error-aborts-all:
  `{accepted: [...], rejected: [{transaction_id, why}]}`. Valid rows are
  written; a row that got posted between listing and suggesting is reported,
  not fatal. One stale row must not reject 499 good proposals.
- Rows already carrying a human decision are reported as skipped, not
  written. The assistant does not get to re-open a settled row.
- Cap 500, one transaction, audit_log row using the existing `INSERT`
  action, actor stamped `<user> (AI)`.

`list_staged_imports` returns the effective coding and its provenance, so a
second assistant run can skip what is already handled.

### 6. What the CPA sees

A seeded dropdown alone must never read as sign-off. An assistant-suggested
row shows the account preselected plus a visible marker naming it as an AI
suggestion, with the confidence and reason. Touching the row records a human
decision and the marker goes; the reason is not left attached to an account
the CPA has since changed.

## Open

- **Write on every `on_change`, or on an explicit save?** Recommend
  `on_change`: it is one small UPDATE on a local SQLite file, it matches what
  a CPA expects from a desktop app, and an explicit "save coding" button is
  new UI surface for no gain. Flagging it because it is the one part that
  changes behavior on a flow with your staged imports currently in it.
- **Should the in-app categorizer write `import_suggestions` too?** It would
  make one mechanism instead of two and give in-app suggestions the same
  durability. Recommend yes, but as a follow-on, after this lands.
- Migration 903 now carries columns and a table. Fine as one migration; it is
  one feature.

## Test matrix

Named because pass 1's absence of one was a finding.

- Reload with dirty edits: coding survives a second "Load staged".
- Rejection: cleared row stays cleared across reload.
- Human decision blocks a later assistant suggestion on that row.
- Tied timestamps inside one batch resolve by id.
- Duplicate transaction_ids in one request rejected.
- Suggestion for an account later deactivated or retyped: not seeded.
- Per-item results: one stale row, 499 valid, all 499 written.
- Authorizer: refused at read, accepted at propose, UPDATE refused at every
  level including post.
- `deletion_blockers` reports the new table.
- Audit failure rolls back the batch.
- Concurrent UI and MCP write.

---

# Codex review of pass 2, disposition

Peer: codex-cli 0.151.0, same session, 2026-09-04. 29 findings, two BLOCKERs.
Both BLOCKERs accepted. Checked against code, not against the summary.

## BLOCKER 1: `on_change` cannot capture acceptance. Accepted. [fact]

If the assistant preselects an account and the CPA agrees, the selectbox never
changes, so `on_change` never fires and `decided_at` stays NULL. The AI's
choice then posts as though a human made it. That is precisely the "a seeded
dropdown must never read as sign-off" failure pass 2 claimed to fix. I built
the mechanism and left the main path through it uncovered.

Options:

- **Stop preselecting.** Show the suggestion beside an empty selectbox and
  require an affirmative pick. Kills the entire class: no unchanged-value
  case, no detached reason, no ambiguity about who chose. Costs one click per
  row, and differs from how the in-app categorizer behaves today.
- Add an explicit Accept control per row, keeping the preselect.
- Record the displayed coding as a human decision atomically at posting.
  Posting is already an explicit, audited human act, so this closes the
  posting path, but leaves the pre-post grid still showing an AI choice with
  no decision recorded.

Recommend the first. It is the accounting-correct answer: a CPA affirms
coding rather than declining to disagree with it. **Scott's call, because it
changes user-visible behavior.**

## BLOCKER 2: new assistant-writable cross-client surface. Accepted. [fact]

Note carefully: this is **not** the finding Scott ratified as rejected. That
one claimed `_resolve_account` was unscoped, which was factually wrong.

The new argument is different and correct. The assistant cannot UPDATE
`imported_transactions.suggested_account_id` at all, so today it has no write
path that pairs a transaction with an account. `import_suggestions` gives it
one. A correct tool implementation cannot emit a cross-client pair, but the
database would not catch it if the service-layer check were wrong. That is a
real loss of defense in depth, not a restatement.

Fix: a BEFORE INSERT trigger requiring the account's client to match the
transaction's client, plus the same check in the projection. Cheap, and it
does not reintroduce the redundant `client_id` column Codex asked me to drop.

## Also accepted

- **The in-app categorizer defeats the "one canonical projection" claim.**
  It still writes only session state, so the grid can show AI coding that
  `effective_coding` and MCP never see. Routing it through
  `import_suggestions` moves from follow-on into this change. Scope grows
  again. [fact]
- **Eligibility filtering can resurrect a superseded suggestion.** "Newest
  whose account is still active" silently promotes an older proposal when the
  newest one's account is deactivated. Select newest first, then mark it
  stale. Never fall back silently. [fact]
- **Return a closed tagged state**, not account-or-None: `unreviewed`,
  `human_coded`, `human_cleared`, `assistant`, `stale`. Consumers must not
  branch on nullability, which is how human-cleared collapses back into
  never-reviewed. [proposed]
- **The decision UPDATE has no audit.** Pass 2 specified auditing for the
  tool and forgot it for the human write, against the project's own
  every-mutation-audits invariant. [fact]
- **Bulk categorization assigns session state in a loop**
  (pages/4_Import_Transactions.py:1805), so per-widget `on_change` will not
  fire. Bulk must be an explicit transactional batch. [fact]
- **`s{staged_id}` is not a safe session-state namespace.** Keys span pages
  and books; two books reuse integer ids. Namespace with book identity. [fact]
- **Race on the skip guarantee.** MCP can read `decided_at` NULL, the UI can
  record a decision, then the INSERT lands. Needs a conditional insert, not a
  prior check. [proposed]
- **CASCADE erases evidence, and the delete paths are real.**
  `ImportedTransaction.delete` and `delete_batch` exist and write a DELETE
  audit row whose `old_values` would not include cascaded suggestions
  (models/transaction.py:468, 492). Either restrict and clean up explicitly,
  or snapshot cascaded rows into the parent's audit payload. [fact]
- **Accepted only after commit**, with stated behavior when insertion fails
  after prevalidation. [proposed]
- Request idempotency id, audit batch linkage, load-time reconciliation of
  stale widget keys, merge-safe refresh for proposals arriving mid-session.
  [proposed]

## Rejected with evidence

- **"Reversal gives a stored decision no lifecycle boundary."** Half wrong.
  Reversal does not return a row to Pending: it sets `superseded_by_batch`
  and leaves the stored status alone, with "Reversed" derived at read time
  (services/import_batch_reversal.py:311). So a stale decision cannot be
  re-seeded into a Pending grid. The other half stands: a post-hoc recode can
  leave `decided_account_id` disagreeing with what was posted, so the recode
  path must update it. [fact]
- **"A re-import inheriting a decision."** Codex marked this no finding
  itself; a re-imported row is a new row and inherits nothing. [fact]

## Where this leaves it

Two rounds, and the design has roughly doubled again. What began as one MCP
tool is now: a proposal table with a consistency trigger, durable audited
human decisions, a tagged canonical projection, the in-app categorizer
rerouted through it, and a stable namespaced widget identity.

That is no longer a tool addition. It is a rework of how import coding is
represented, and the tool is the smallest part. Recommend deciding whether
that is worth it before writing any of it.
