# Scope: categorize staged imports from MCP

Status: proposed, not built. Needs Codex adversarial review, then Scott's
approval, before any code.

Date: 2026-09-03

## The point

Let Claude Desktop suggest account coding for staged bank rows, so the
suggestions arrive in Import Transactions' Review & Categorize grid the same
way today's in-app suggestions do. No API key involved, because the app never
initiates the call.

## Correction to what I told Scott first

I said a suggestion tool could write `imported_transactions.suggested_account_id`
with no schema change. Half right, and the wrong half matters.

- Right: the grid really does read that column. `prepare_staged_for_review`
  seeds `st.session_state[row_key("cat", row)]` from
  `transaction.suggested_account_id` (pages/4_Import_Transactions.py:136).
  Persisting a suggestion does light up the grid.
- Wrong: an assistant connection cannot write it. Setting a column on an
  existing row is an UPDATE, and **no UPDATE is grantable at any access
  level** (database/connection.py:81, and the invariant in CLAUDE.md). The
  authorizer allows INSERT on allowlisted tables and nothing else.

So the column is reachable by the app and permanently unreachable by the
assistant. That is not a gap to close. It is the containment working.

Second thing found while scoping: the in-app AI categorizer does not persist
at all. It mutates in-memory dicts and writes Streamlit session state
(pages/4_Import_Transactions.py:1733). Suggestions on a fresh CSV live in one
browser session and die with it. Only rows loaded from the database via
"Load staged" get their suggestion from the column.

## Design

A new append-only table, not a mutable field.

```sql
-- database/migrations/903_import_suggestions.sql
CREATE TABLE IF NOT EXISTS import_suggestions (
    id INTEGER PRIMARY KEY,
    client_id INTEGER NOT NULL,
    imported_transaction_id INTEGER NOT NULL,
    suggested_account_id INTEGER NOT NULL,
    confidence TEXT NOT NULL CHECK (confidence IN ('high', 'medium', 'low')),
    reason TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,          -- 'assistant', later 'in_app'
    created_at TIMESTAMP NOT NULL,
    created_by TEXT NOT NULL,      -- '<user> (AI)' via utils.actor
    FOREIGN KEY (client_id) REFERENCES clients(id),
    FOREIGN KEY (imported_transaction_id) REFERENCES imported_transactions(id),
    FOREIGN KEY (suggested_account_id) REFERENCES accounts(id)
);
CREATE INDEX IF NOT EXISTS idx_import_suggestions_txn
    ON import_suggestions(imported_transaction_id);
```

INSERT-only fits the propose allowlist exactly. Nothing is overwritten, so a
second opinion is a second row rather than a lost first one, and every
suggestion carries who, when, and why. The human's decision stays the only
thing that writes a category.

The grid keeps its current precedence. On "Load staged", seed the widget key
from the newest suggestion for the row only when
`suggested_account_id` is empty. A person's saved coding always outranks a
proposal. `prepare_staged_for_review` runs behind an explicit button
(pages/4_Import_Transactions.py:1431), not on every rerun, so there is no
path where seeding clobbers a choice made moments earlier.

## Tool contract

`suggest_categories(client_id, suggestions)` at **propose** level.

- `suggestions`: list of `{transaction_id, account_number, confidence, reason}`.
- Every `transaction_id` must be a Pending row for that client. Anything else
  is an error naming the offending entry, no partial write.
- `account_number` resolves through `_resolve_account`; a Revenue or Expense
  account only, matching what the in-app path offers.
- Cap at 500 per call, same as `propose_import`.
- Whole batch in one transaction.
- Returns counts plus a note saying nothing was posted and a person decides in
  Import Transactions.

Reuses the existing shape: `@mutating`, `_require_level("propose")`, the
`utils.actor` stamp, and an audit_log row. `INSERT` is already in
`AUDIT_ACTIONS`, so no CHECK rebuild migration is needed.

## Files

- `database/migrations/903_import_suggestions.sql` (new)
- `models/import_suggestion.py` (new)
- `services/mcp_tools.py`: `suggest_categories`, plus `list_staged_imports`
  gaining `suggested_account_id` so the assistant can skip already-coded rows
- `mcp_server.py`: one wrapper
- `database/connection.py`: `import_suggestions` into the propose allowlist
- `pages/4_Import_Transactions.py`: seed from the newest suggestion when the
  column is empty, and show confidence and reason on the row
- `CLAUDE.md`: propose-surface enumeration, kept in sync with the allowlist
- `docs/MCP.md`: the new tool
- Tests: authorizer refuses at read, accepts at propose, precedence (human
  choice wins), bad transaction_id rejected whole, non-P&L account rejected

## Open, needs Scott

- **Docstring fix, unrelated but adjacent.** `list_staged_imports` says
  "Assistant-staged transactions" and actually returns every Pending row for
  the client. The behavior is right and the sentence is wrong. Fix in this
  change or separately.
- **Should the in-app categorizer persist too?** It would make the two paths
  one mechanism and stop suggestions dying with a browser session. It is also
  scope creep on a tool change, and it touches a flow with staged imports
  currently sitting in it. Recommend: not now, note it.
- **Upstream.** This is fork-only by construction (900 band). Charlie may want
  it, but it presumes the leveled dial, which is ours.

## Not in scope

- MCP sampling, where the server asks the client for inference. It would
  remove the API key from the in-app button, which is a different problem from
  this one. Whether Claude Desktop implements sampling as a client is
  unverified, and I will not design against an unconfirmed capability.
- Anything that posts. Suggestions never become entries without a person.
- The single-account-per-row model in Review & Categorize. Untouched.

---

# Codex adversarial review, disposition

Peer: codex-cli 0.151.0, session 01a06a14, 2026-09-04. 24 findings, one
BLOCKER. Every row below was checked against the code, not against the
summary. Provenance tags: [proposed] raised, [fact] verified by inspection,
[settled] ratified by Scott.

## The design's central claim was wrong

Codex disputed "a human's saved coding always outranks a proposal." It is
right, and the defect is worse than it argued.

`imported_transactions.suggested_account_id` is written in exactly two
places: at posting time, with `status="Posted"` (services/posting.py:211),
and by a post-hoc recode (services/import_corrections.py:135). **Nothing
saves a category on a still-Pending row.** A CPA's in-progress coding lives
in Streamlit session state and nowhere else until they post.

So on a Pending row that column is essentially always NULL, and my precedence
rule ("seed only when empty") is vacuous. It would seed from the assistant's
suggestion every time, including over a choice the CPA made and had not yet
posted. Three Codex findings collapse into this one and all are accepted:
precedence unsupported, reload discards unsaved selections, and NULL cannot
distinguish "never reviewed" from "rejected this suggestion."

The fix is not a tweak to the seeding condition. The design needs a durable,
append-only human disposition (accept / reject / supersede) so acceptance is
an event, not the absence of one. That is a larger change than the original
scope and it is the right one. [fact]

## Accepted, must change before build

- Human disposition must be an explicit append-only event. Acceptance may not
  be inferred from a seeded selectbox. [fact]
- `list_staged_imports` must return the *effective* suggestion from the new
  table. My version added the legacy column, which stays NULL for anything
  the assistant proposed, so a second run would re-suggest the same rows
  forever. [fact]
- One canonical projection (a repository function or SQL view) resolving
  precedence, dismissal, and provenance, consumed by BOTH the grid and MCP.
  Two independent readers of the same ranking is how they drift. [proposed]
- `Account.deletion_blockers` must learn the new table. Its docstring claims
  every referencing table is checked and it enumerates them by hand
  (models/account.py:344). Miss it and a friendly blocker becomes a raw
  IntegrityError. Found independently before the review came back. [fact]
- Decide `ON DELETE` explicitly for all three foreign keys rather than
  inheriting the restrictive default. [proposed]
- Deterministic newest-first ordering: `ORDER BY created_at DESC, id DESC`.
  Timestamps tie inside one batch. [fact]
- Reject duplicate transaction_ids within a single request. [proposed]
- Per-item validation results instead of first-error-aborts-everything. One
  row posted between listing and suggesting should not reject 499 good
  proposals, and a CPA should not be told only about the first bad one. [proposed]
- Bound `reason` length in the tool. [proposed]
- Revalidate account eligibility when projecting, not just at insert. An
  account can be deactivated or retyped after a suggestion is stored. [proposed]
- Stated test matrix: reload with dirty edits, rejection, tied timestamps,
  duplicate ids, inactive account, audit rollback, parent deletion,
  concurrent UI and MCP access. [proposed]

## Rejected, with evidence

- **BLOCKER, cross-client account resolution.** Codex assumed
  `account_number` resolves unscoped. It does not: `_resolve_account(client_id,
  account_number)` filters `Account.get_all(client_id, ...)`
  (services/mcp_tools.py:123). A client-A transaction cannot reach a client-B
  account through this tool. The residual point, that the FK does not enforce
  the pairing at the database layer, is true and is equally true of today's
  `imported_transactions.suggested_account_id`. No new exposure, so not a
  blocker. **A rejected BLOCKER needs Scott's ratification before it closes.**
  [fact, awaiting ratification]
- **Foreign keys may not be enforced.** They are: `PRAGMA foreign_keys = ON`
  on every connection (database/connection.py:274). [fact]
- **Lock failures unhandled.** `PRAGMA busy_timeout = 30000` is already set
  (database/connection.py:279). The operator-message half of the finding
  stands as a MINOR. [fact]
- **`CREATE TABLE IF NOT EXISTS` weakens the migration.** True in the
  abstract, and it is the convention in all 45 existing migrations. Changing
  it is a project-wide decision, not this design's to make. [fact]

## Deferred

- Request idempotency keys, payload caps, retention policy. Reasonable for a
  multi-tenant service; this is a single-user local app where the assistant
  is the user's own session. Revisit if suggestion volume ever matters. [proposed]
- Re-import and reversal lifecycle. Worth specifying, but ID linkage means a
  re-imported row is a new row and inherits nothing. Low risk. [proposed]

## Where this leaves the scope

Bigger than first written. The suggestion table alone was the easy half; the
disposition model is the part that makes it safe. Recommend a second design
pass before any code.
