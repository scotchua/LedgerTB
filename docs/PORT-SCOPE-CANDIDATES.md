# Port scope: candidate features from SlowBooks Pro 2026

Status: [proposed] — reviewed by Codex (codex-cli 0.147.0, xhigh reasoning,
2026-08-28). Confidence: high. Verdict: "directionally useful but not
approval-ready." Findings incorporated below per section; see "Codex review"
at the end for the full adversarial pass. Grounded in direct code inspection
of both repos (LedgerTB as of 2026-08-28, SlowBooks Pro 2026 as cloned same
day), not the READMEs alone.

Nothing here ports as a file diff. LedgerTB is Streamlit + dataclass models
over SQLCipher SQLite; SlowBooks Pro is FastAPI + SQLAlchemy over
Postgres/SQLite. Every item below is "reimplement the approach," not "copy
the code." Each design is checked against LedgerTB's own invariants
(`CLAUDE.md`): unbalanced entries never post, every mutation writes the audit
trail with OS-user attribution, the database stays encrypted, and assistant
(MCP) access is a leveled, engine-enforced dial that can never UPDATE/DELETE.

---

## 1. SimpleFIN bank feeds

**Objective**: live transaction sync feeding the existing CSV import→review→
post pipeline, instead of manual upload only.

**Current state (LedgerTB)**: `services/csv_import.py` is the only import
path. Dedup logic in `services/import_identity.py` — `row_fingerprint()` and
`ensure_import_identity()` — is already **format-agnostic**: it operates on
plain transaction dicts keyed by `source_id`/`source_row_number` (falling
back to a content fingerprint), not on CSV columns. That means a live feed
can reuse this dedup path directly. `models/import_profile.py`
(`ImportProfile`) is CSV-column-mapping specific (date/amount/debit-credit
columns) and is **not** reusable for a feed that returns structured JSON.

**Reference (SlowBooks Pro)**: `app/services/simplefin_service.py` (271
lines) + `app/routes/simplefin.py` (146 lines). One-time base64 setup token →
decoded claim URL → single `POST` exchanges it for a permanent access URL
with embedded basic-auth credentials. Manual "Sync Now" only, no background
scheduler. First sync pulls 85 days back; later syncs use a 7-day overlap
window. SimpleFIN's transaction `id` becomes the dedup key (their own FITID
equivalent). Includes an SSRF guard (`_assert_public_https`) since the access
URL is user-supplied and embeds live credentials.

**Design for LedgerTB**:
- New `services/bank_feed.py`: fetch via `httpx` (new dependency — LedgerTB
  currently has none), map results into the same dict shape
  `csv_import.py` produces (`source_id` = SimpleFIN transaction id), call
  `ensure_import_identity()` / `classify_import_duplicates()`, stage into
  `imported_transactions` exactly as `pages/4_Import_Transactions.py`
  already expects. Categorization and posting are untouched.
- Access URL/token stored in `utils/secure_store.py` (OS vault), one named
  secret per client/bank account — never in the SQLite DB, matching how the
  Anthropic key is already handled.
- New migration (next free number) adding a `bank_connections` table
  (client_id, bank_account_id, last_synced_at, sync window marker). Do not
  touch `ImportProfile` or migrations 006/021.
- Manual "Sync Now" only — matches LedgerTB's local-first/no-daemon posture
  (and matches SlowBooks' own choice; no scheduler exists there either).
- Port the SSRF host-allowlist guard — the access URL is effectively a
  bearer credential embedded in a URL; validate it the same way SlowBooks
  does.
- MCP exposure: a `propose`-level tool that stages rows into the
  `imported_transactions` inbox — never `post`, per the existing
  `mcp_server.py` leveling pattern (`_require_level`, `@_mutating`).
- Explicitly **do not** port a separate "bank rules on arrival"
  auto-categorization engine — LedgerTB already has AI categorization
  serving that role; duplicating it would be scope creep.

**Acceptance criteria**:
- Linking a SimpleFIN account stores credentials only in the OS vault.
- "Sync Now" stages new transactions with correct dedup (no dupes across
  the 7-day overlap window on repeated syncs).
- Existing categorization/posting pipeline works unmodified against staged
  rows.
- New tests use the existing autouse fake-vault fixture; never touch the
  real OS keychain (per LedgerTB's testing rules).

**Risks**: the SimpleFIN access URL is a long-lived bearer credential — losing
vault confidentiality means losing bank read access; needs a documented
revoke/rotate path. Adds LedgerTB's first outbound network dependency beyond
Anthropic — should get the same "off by default, disclosed" treatment.

**Effort**: Medium. New service, new migration, settings UI addition, one
new MCP tool, tests.

**Codex pushback**: the SSRF design as written is incomplete for a
credential-bearing URL — both the claim URL and the resulting permanent
access URL need validation, redirects must be disabled or revalidated at
every hop, and DNS resolution must reject loopback/private/link-local/
special-use addresses, not just check "public HTTPS." Credentials must
never appear in logs, exceptions, audit payloads, or UI state. Separately,
treating the SimpleFIN transaction `id` as globally unique is an unverified
assumption — the durable identity should be scoped by provider + connection
+ remote account + transaction id unless SimpleFIN's contract explicitly
guarantees global uniqueness. Sync-state advancement (`last_synced_at`) and
staged-row insertion must commit atomically — a crash between the two can
silently lose or duplicate transactions; this needs its own acceptance
criteria (mid-page failure, concurrent "Sync Now" clicks, malformed
responses).

---

## 2. Tamper-evident close package PDF

**Objective**: print a SHA-256 hash + audit ID in the close-package PDF
footer, independently verifiable.

**Correction to initial framing**: this was scoped assuming LedgerTB already
had an audit hash chain to hook into. It does not. `models/audit_log.py`
(`AuditLog.write()`) is a flat table — autoincrement id, no
`prev_hash`/`row_hash` column in any migration (checked 005, 020). This is
schema work, not a footer tweak.

**Current state**: `services/close_package.py` (1532 lines) builds the PDF
with reportlab; the footer (~line 1108) is static text (client/period/page
number), no hash.

**Reference (SlowBooks Pro)**: `document_audits` table — one row per
issuance (`doc_type`, `doc_key`, `content_hash`, `created_at`), **not** a
hash chain across rows; the trust anchor is the DB row itself. Hash =
`sha256(json.dumps(canonicalized_payload, sort_keys=True))` — content-only,
so identical data reproduces the same hash. This is simpler than a chain and
sufficient for the stated goal ("recompute and confirm unedited since
generation").

**Design for LedgerTB**:
- New migration adding a `document_audits`-equivalent table (client_id,
  doc_type='close_package', period, content_hash, created_at, FK to the
  export's `AuditLog.write()` row).
- **Confirm `EXPORT` is already an allowed value in `AUDIT_ACTIONS` before
  writing to it.** LedgerTB's own `CLAUDE.md` documents that
  `AUDIT_ACTIONS` and the `audit_log` CHECK constraint must move together
  as a table-rebuild migration — this exact class of mistake silently
  broke Book Review's REVIEW events until migration 015. Do not repeat it.
- `close_package.py`: two-pass build (reportlab can't hash itself
  mid-render) — build once to get the underlying report snapshot data, hash
  the canonicalized snapshot (not raw PDF bytes, so re-renders of identical
  data stay verifiable), write the audit row, re-render with hash + audit ID
  in the footer.

**Acceptance criteria**:
- Every close package export writes exactly one audit row and prints a
  matching audit ID + short hash.
- Re-exporting identical period data reproduces the identical hash
  (determinism check).
- A reviewer can trace a printed audit ID back to its audit-log row and
  independently recompute the hash.
- No change to existing close packages already delivered.

**Risks**: two-pass build adds latency to an already-large generator — test
against the largest close-package fixture. Migration must respect the
AUDIT_ACTIONS/CHECK-constraint coupling above.

**Effort**: Small–medium. One migration, ~50–150 lines in
`close_package.py`, no new dependency (`hashlib` is stdlib).

**Codex pushback — significant, changes the design**: as written, this is
**not tamper-evident or independently verifiable**, and calling it that is
misleading. Hashing the canonical *source data* proves nothing about the
*rendered PDF* — someone can alter visible amounts or narrative text while
keeping the original footer intact, since the hash never touches the
document itself. The flat SQLite audit row is also not a trust anchor
against anyone capable of editing the database directly. Two ways forward,
neither of which is the current design as-written:
- **Rename and scope down**: call this "snapshot traceability" (proves the
  export ties to a specific data snapshot, recomputable by re-running the
  report) rather than "tamper-evident," and say so plainly to whoever relies
  on it.
- **Actually build tamper-evidence**: hash the rendered PDF bytes and sign
  that hash with a key anchored outside the SQLite database (so a person
  with DB access alone can't forge a valid signature).
Also flagged: the two-pass issuance lifecycle is underspecified — if the
audit row is written before the final render and rendering then fails, an
audit row exists for a document that was never delivered (or vice versa if
ordered the other way). Define what "exactly one audit row" means across
success/failure/retry, and reconcile the fact that the design produces both
an `audit_log` row and a separate `document_audits` row without saying how
they relate. **Recommendation revised**: proceed, but decide which of the
two paths above before writing the migration — the current acceptance
criteria describe a feature stronger than what the design delivers.

---

## 3. Fuzzy duplicate detection — HOLD, flagged conflict

**Do not treat this as a default-approved candidate.** The firm has a
standing, ratified position directly on point: four production
name-matching failures in a single day (both over- and under-matching);
the firm's own guidance is to prefer structural identifiers (AccountType /
AccountSubType / ids) and per-client ratified lists over name similarity.
Porting SlowBooks' name-similarity duplicate detector as designed would
contradict that position outright.

**Current state (LedgerTB)**: zero fuzzy-matching anywhere. The chart
importer (`services/coa_import.py`) does exact, case-normalized dictionary
lookups. Bank dedup (`services/import_identity.py`) is exact-hash only, by
explicit design ("content identity" per its own comment) — this path should
not be touched.

**Reference (SlowBooks Pro)**: `app/services/duplicate_detection.py` (82
lines) — stdlib `difflib.SequenceMatcher` only (no rapidfuzz dependency),
name-only (no address/tax-ID), 0.85 threshold, explicitly documented in its
own comments as not scaling past low thousands of records.

**If Scott explicitly overrides the standing caution**: scope narrowly to
the chart importer's one-time, human-reviewed setup step only (e.g. flagging
"Accounts Receivable" vs "Accounts Receivable — Trade" as a suggestion at
chart-creation time) — never touching the exact-hash bank-dedup path, and
surfaced strictly as a suggestion the human confirms, never an auto-merge.

**Recommendation**: hold, don't build, pending Scott's explicit sign-off.
Tabled, not rejected, in case a narrowly-scoped variant is wanted later.

**Codex pushback**: the hold itself is reasonable as a provisional process
decision, but the "would contradict the ratified position outright"
framing overstates what this document establishes. Production entity
matching (which caused the four firm failures) and a non-destructive,
human-reviewed chart-import suggestion have materially different failure
consequences — this document doesn't reproduce the ratified rule's actual
scope, confirm Scott is the required override authority, or establish that
the four production failures are relevant to one-time chart-account setup
specifically. Keep the hold, but soften the claim: hold because the
objective, an evaluation set, and an acceptable false-positive rate remain
undefined — not because all fuzzy suggestions necessarily contradict
structural matching everywhere.

---

## 4. Fixed assets / depreciation

**Objective**: an asset register with depreciation schedules
(straight-line, declining-balance) and disposal-with-gain/loss — entirely
absent from LedgerTB today.

**Current state**: confirmed no existing model. `AccountSubtype.FIXED_ASSET`
exists only as a chart-of-accounts classification; depreciation today is
just an expense-account subtotal bucket in P&L reporting, no schedule
behind it. The closest architectural template is the `draft_entry.py` stack
— a full example of how a new standalone domain object is built end-to-end
in LedgerTB (model → migration 012 → service logic → dedicated numbered
page → MCP exposure).

**Reference (SlowBooks Pro)**: `models/fixed_assets.py` (2 tables:
`fixed_asset_types` holding GL account mappings + method + useful
life/rate; `fixed_assets` holding cost/salvage/accumulated
depreciation/status) and `services/fixed_assets.py` (357 lines) — month-
granular depreciation runs capped at the salvage floor, one journal entry
per asset per run; disposal derecognizes cost + accumulated depreciation,
books proceeds, plugs the residual to a Gain/Loss on Disposal account. Book
value is always derived (cost − accumulated), never stored — worth copying
this choice; it avoids drift bugs.

**Design for LedgerTB**:
- New migration: `fixed_asset_types` + `fixed_assets` tables, following
  the plain-CREATE-TABLE + CHECK-constraint pattern migration 012 uses.
- New `models/fixed_asset.py` dataclass pair, mirroring `draft_entry.py`'s
  structure.
- New `services/fixed_assets.py`: reuse SlowBooks' depreciation-run formula
  (a standard, well-understood method, not proprietary logic) — each run
  posts through LedgerTB's existing journal-entry validation, so "unbalanced
  entries never post" applies unchanged.
- New numbered page for register + run-depreciation action + disposal
  action, following the `pages/14_Close_Map.py` pattern.
- MCP exposure: `propose`-level only. Depreciation timing and useful-life
  estimates are judgment calls that should default to draft, never
  auto-post, per the existing leveling pattern.

**Acceptance criteria**:
- Depreciation runs post balanced JEs only.
- Disposal correctly computes gain/loss through the same validated posting
  path.
- Book value is derived, never stored redundantly.
- New MCP tool respects read/propose/post leveling; runs default to
  propose.

**Effort**: Medium–large — genuinely new domain (new tables, service, page,
MCP tool), but SlowBooks' logic is a usable reference so there's no
algorithm-design risk, just integration work.

**Codex pushback**: "posts a balanced JE" is far too weak an acceptance
test — a perfectly balanced entry can still use the wrong amount, date,
account, sign, or period. Needs explicit, numerically-fixtured
specification of: in-service date conventions, partial-month handling,
declining-balance rate/method-switch behavior, decimal rounding, salvage-
floor treatment, catch-up runs after a missed period, behavior against a
closed period, disposal-date depreciation, zero/negative disposal proceeds,
and reversal handling. Also missing: an immutable, per-asset run/event
record linked to the journal entry it produced, with a uniqueness
constraint preventing two depreciation runs from posting for the same
asset+period — without this, retries or double-clicks can double-post, and
accumulated depreciation can't be reliably reconciled back to its source
runs.

---

## 5. Multi-provider AI abstraction

**Objective**: let LedgerTB categorize via a chosen provider instead of
Anthropic-only, without weakening the "off by default, suggestions only"
posture.

**Current state**: `services/categorization.py` hardcodes
`Anthropic(api_key=...).messages.create(...)` with a fixed tool schema.
`utils/secure_store.py` is already generic (`get_secret`/`set_secret` by
name string) — it needs **zero** changes to store additional provider keys.

**Reference (SlowBooks Pro)**: a `PROVIDERS` registry keyed by provider
name, each declaring one of three `wire_format`s (openai / anthropic /
gemini); one request-builder + one response-parser per wire format, reused
across providers that share a shape (grok/groq/cloudflare/openai all speak
"openai"-shaped chat completions) — not 7 bespoke adapters. Per-provider
URL allowlist revalidated on every call.

**Flag from research — do not carry this over**: SlowBooks' own README
claims "versioned, rotatable ciphertext" for AI provider keys, but the code
actually uses a simpler single-key Fernet scheme; the real versioned/
rotatable scheme (PBKDF2-derived, `_PREV` key chain, offline rewrap) is used
for payroll bank-account PII, not AI keys. Port what the code does, not what
the README claims — and note LedgerTB's OS-keychain-backed `secure_store`
is arguably already a stronger primitive than SlowBooks' single-key file.

**Design for LedgerTB**:
- New `services/ai_providers/` package: a small `ProviderSpec` registry
  (name, wire_format, base_url, model) plus one builder/parser per
  wire_format — start with anthropic + openai only; skip gemini/grok/groq
  initially since LedgerTB needs categorization, not general "AI Insights".
- Replace the hardcoded call in `categorization.py` with a call through the
  registry, selected by a new `AI_PROVIDER` config constant defaulting to
  `"anthropic"` — existing installs see zero behavior change.
- Carry over the per-provider URL allowlist revalidation; it's real
  hardening, not scope creep.
- Keys via existing `secure_store.py`, one named secret per provider.

**Acceptance criteria**:
- Default behavior (Anthropic, no config change) is unchanged for existing
  installs.
- Switching `AI_PROVIDER` produces suggestions through the same
  suggestion→review→post flow; no provider call ever posts directly.

**Effort**: Small–medium — mostly refactoring existing working code behind
an interface, plus one new provider to prove the abstraction. Scott to
confirm which second provider actually matters to the firm before building
it.

**Codex pushback**: switching provider changes *which third party receives
client transaction descriptions* — a privacy-scope change this document
doesn't surface. Acceptance criteria are missing: explicit provider
authorization before any switch, minimized fields transmitted, a fixed
per-provider endpoint registry with exact host/port matching (not just an
allowlist check), disabled or revalidated redirects, and fail-closed
behavior on an unknown provider or missing key — no silent fallback that
could send bookkeeping data (or one provider's credential) to the wrong
endpoint.

---

## Cross-cutting findings (apply across multiple items)

Pulled from Codex's review, not tied to one section:

- **Unverified prerequisites treated as established facts.** Several
  designs assume something works a certain way without confirming it in
  code: that `EXPORT` is already an allowed `AUDIT_ACTIONS` value; that
  `AuditLog.write()` returns a usable ID and participates in the caller's
  transaction (needed for atomic audit+mutation writes); that
  `secure_store.py` supports collision-safe namespacing, deletion, and
  rotation, not just get/set; that `close_package.py` exposes a stable data
  snapshot without needing to refetch; that journal posting is reusable,
  atomic, and callable from a "propose" context. **Each of these should be
  an explicit verification step before implementation, not an assumption
  baked into "Proceed."**
- **The audit-trail invariant is under-specified for every new mutation.**
  Linking/unlinking a bank connection, creating/editing an asset, running
  depreciation, disposing an asset — all of these are mutations that need a
  defined audit event, OS-user attribution, and atomic coupling to the
  business write, and none of the five designs above enumerate this
  explicitly.
- **Sequencing**: establish the audit-event pattern, transaction
  boundaries, MCP side-effect model (see below), secret naming/lifecycle,
  and outbound-HTTP security policy *once*, as shared infrastructure —
  before building items 1, 2, and 4 independently and re-inventing pieces
  of it three times. Decide whether fixed-asset schedules belong in the
  close package before freezing item 2's canonical snapshot format, or
  version the manifest so adding them later doesn't silently change past
  hashes.
- **MCP dial semantics need tightening.** "Propose-level only" and "no
  UPDATE/DELETE ever" don't by themselves control INSERTs, outbound network
  calls, vault-secret use, or calls into posting services. Define
  capabilities by business operation, and verify explicitly that every
  "propose" action produces only a reviewable draft/staged row and never
  advances posted accounting state — this matters especially for item 1
  (staging is already a persistent side effect) and item 4 (a
  "depreciation run" reads like an operation that posts).
- **Acceptance criteria across all five items should add**: client-tenant
  isolation checks, rollback/failure-injection tests, concurrency/
  idempotency tests, an upgrade path from an existing encrypted database,
  backup/restore coverage, secret cleanup on unlink/delete, and negative
  tests proving prohibited posting cannot occur. As scoped, an
  implementation could pass every happy-path acceptance criterion while
  still leaking credentials, duplicating entries, skipping audits, or
  producing financially incorrect-but-balanced journals.

## Summary table

| # | Feature | Effort | Recommendation |
|---|---|---|---|
| 1 | SimpleFIN bank feeds | Medium | Proceed — close the SSRF/identity-scoping/atomicity gaps first |
| 2 | Tamper-evident close package | Small–medium | Proceed — but resolve the "traceability vs. true tamper-evidence" design choice first |
| 3 | Fuzzy duplicate detection | Small (if narrowed) | **Hold** — pending an evaluation set and false-positive threshold, not an outright policy conflict |
| 4 | Fixed assets / depreciation | Medium–large | Proceed — needs a much richer accounting/idempotency spec |
| 5 | Multi-provider AI abstraction | Small–medium | Proceed — add the privacy/fail-closed acceptance criteria |
