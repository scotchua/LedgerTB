# Port scope: Invoicing/AR/AP, Payroll, Inventory (from SlowBooks Pro 2026)

Status: [proposed] — reviewed by Codex (codex-cli 0.147.0, xhigh reasoning,
2026-08-28). Confidence: high. Verdict: sound as a present-tense
authorization decision, but not as a categorical, indefinite rejection of
all three — and the inventory/AR/AP dependency claim specifically did not
hold up. Findings incorporated below; see "Codex review" at the end.
Decision document, not an implementation plan.

## Framing

LedgerTB's own documentation defines what it is: multi-client double-entry
bookkeeping and close workflow for a CPA firm, built around encrypted
per-client books, an audit trail, and a review/signoff close process. It is
explicitly not an invoicing/AR/AP/payroll/inventory system — that is
SlowBooks Pro's job, for one business at a time.

Porting these three modules would not be "adding a feature." It would change
what LedgerTB *is*: from a firm-side close tool serving many clients into a
full accounting system serving one entity's operational transactions.
AR/AP, payroll, and inventory are inherently single-entity, deeply coupled
concerns — none of them bolt on cleanly beside LedgerTB's current design.

Per standing policy, scope changes of this size are Scott's decision, not a
default outcome of a porting exercise. Each section below gives the real
size and the specific reasons it conflicts with LedgerTB's current design,
so the decision is grounded rather than abstract.

---

## Invoicing / AR / AP

**Size in SlowBooks Pro**: 6 tables (invoices, invoice_lines, bills,
bill_lines, bill_payments, bill_payment_allocations), ~20+ REST routes,
dedicated PDF/email templates, dedicated frontend JS modules.

**What it would take in LedgerTB's architecture**: 6 new tables (one or more
migrations), ~6 new model files, a new `services/ar_ap.py` handling posting
rules (invoice → A/R + revenue, payment → cash + A/R, bill payment → cash +
A/P, multi-invoice payment allocation — SlowBooks' most complex piece here),
2–3 new numbered pages, PDF generation (reportlab, matching
`close_package.py` rather than adding WeasyPrint as a second PDF library).

**Where it fights LedgerTB's design**: every invoice/bill is a source of
journal entries, which integrates fine with "unbalanced entries never
post." But AR/AP also requires a customer/vendor master-data model that
does not exist in LedgerTB at all — LedgerTB's client + chart-of-accounts
model has no concept of a sub-entity ("customer," "vendor") within a
client's book. This is a new master-data layer under every existing
client's book, not an incremental addition.

**Effort**: Large. Multi-week; new master-data model; new posting-rule set;
no existing LedgerTB analog covers multi-line, multi-payment allocation.

---

## Payroll / HR

**Size in SlowBooks Pro**: 8–10 tables across three tiers (onboarding/time/
PTO, deductions/garnishments, tax forms + employee self-service portal),
60+ routes, token-authenticated employee self-service, W-2/W-3/940/941
generation.

**Where it fights LedgerTB's design hardest**: payroll requires storing
employee PII — SSNs, direct-deposit bank account numbers — a materially
different data-sensitivity class than anything LedgerTB handles today, and
one that raises the firm's own IRC 7216 and data-handling concerns at the
*product* level, not just per engagement. It also requires a second class of
user (employees, not firm staff) authenticating into the app — LedgerTB's
firm-mode single-passphrase-per-book model has no concept of this at all.

It also duplicates a function the firm already sources elsewhere: the firm
runs Gusto for payroll today, and Gusto's API explicitly forbids building
this exact kind of own-account integration (see
`gusto-api-forbids-own-account-integration` in firm memory). Building
payroll into LedgerTB would take on W-2/940/941 tax-form-correctness
liability as software the firm maintains itself, on top of duplicating an
already-solved problem.

**Effort**: Very large, and the wrong home for it regardless of effort.

**Recommendation**: do not port. Direct conflict with an existing firm
tooling decision and an unfavorable risk trade even before effort is
considered.

---

## Inventory

**Size in SlowBooks Pro**: smallest of the three — 2 tables (items,
inventory_movements), ~500 lines, 9 routes. Perpetual-ledger, weighted-
average cost: every purchase/sale/adjustment appends a movement row and
recalculates `avg_cost`; sales post COGS at current avg_cost; includes a
`reverse_sale` path for voided invoices.

**Where it fights LedgerTB's design**: inventory-driven COGS is only
meaningful if a "sale" concept exists to trigger it — this module is a
downstream dependent of the AR/AP module above, not a standalone feature.
Scoping it independently of the AR/AP decision doesn't make sense.

**Effort**: Small on its own (matches SlowBooks' own compact footprint),
but blocked on the AR/AP decision — sequence after, never before or
independently of it.

**Codex pushback — this claim did not survive review**: "blocked on AR/AP"
is an artifact of *SlowBooks' specific implementation* (sales trigger COGS,
`reverse_sale` handles invoice voids), not an inherent accounting
dependency. Inventory accounting fundamentally needs receipt, issue, count,
adjustment, and valuation events — not necessarily LedgerTB-native invoices
or bills. A close-oriented inventory subledger could import movements from
a client's existing POS/e-commerce/warehouse system, support manual
period-end count adjustments, calculate a month-end valuation + COGS entry,
and produce an inventory rollforward for review/signoff — which arguably
fits LedgerTB's close mission *better* than operational invoicing does, and
doesn't require the AR/AP master-data layer at all. Also: the ~500-line
SlowBooks footprint is not a reliable effort signal either way — backdated
movements, negative stock, landed costs, returns, multi-location stock, and
period locking can dominate a production-grade implementation regardless
of the reference's size.

**Revised recommendation**: don't default to "blocked on AR/AP." Run a
small, bounded discovery spike instead — scope an import/manual-movement-
only inventory subledger independent of invoicing, and check how tightly
that design actually needs an AR/AP master-data layer versus just a
"movement" and "valuation" concept.

---

## Overall recommendation

Hold all three as an implementation-authorization decision today. None fit
LedgerTB's stated scope as a CPA-firm close/bookkeeping tool as currently
designed. But Codex's review found the reasoning here partly circular
("LedgerTB is defined as not having these, therefore adding them is out of
scope" is a restatement, not an argument) and missing the inputs an actual
decision-maker needs — see below.

### Codex review (adversarial pass)

**1. "Hold" is justified; "do not build, indefinitely" is not, as written.**
The document supports a provisional "do not authorize implementation now."
It does not establish the stronger, effectively permanent conclusion,
because it never tests current client demand, cost of *not* building, or
firm strategy against the scope boundary — it just restates the boundary.
**Fix**: ratify a hold with explicit revisit triggers (see below), not an
indefinite one.

**2. Inventory's AR/AP dependency claim is unjustified** (detailed above,
under Inventory) — this is the single biggest correction to the original
document. Move it from "blocked" to "bounded discovery."

**3. The payroll rejection leans on the wrong arguments.** PII handling and
a second authenticated-user class (employees) are hazardous and expensive,
but they're solvable engineering problems (encryption, field-level access
control, separate identities, isolated portals), not proof of
impossibility. The *actually* strong reasons to reject are: recurring
federal/state/local tax-rule maintenance, filing and deposit correctness,
payment operations, garnishments, year-end form correctness, professional
liability exposure, and single-developer continuity risk if the person
maintaining tax-form logic is unavailable. Recommend replacing the PII/
Gusto framing with these as the primary rationale.

**4. The Gusto argument alone is insufficient.** A restriction on using
Gusto's API for an own-account integration doesn't, by itself, prohibit an
independently-built payroll engine that never calls that API. It shows
duplication/opportunity cost, but "direct conflict" requires either an
explicit firm buy-not-build policy or a contractual restriction — quote the
actual policy language if this is meant to be load-bearing, rather than
inferring a conflict from an API restriction that covers a different
integration pattern.

**5. "Inherently single-entity, conflicts with multi-client design" is
overstated for all three.** LedgerTB already isolates per-client books —
operational modules could in principle exist once per client. The real
architectural mismatches are transaction volume, customer/vendor/employee
identity models, client-side user accounts, uptime expectations, and
continuous-operations vs. periodic-close workflow — name those concretely
instead of the broader "single-entity" framing.

**6. Missing input: cost of NOT building.** The decision needs actual
demand evidence — number of affected clients, duplicate-entry hours lost,
close delays/errors attributable to the gap, third-party subscription costs
already being paid, any lost engagements — compared against five-year
maintenance cost and risk. Without this, "hold" is asserted, not evaluated.

**7. Effort estimates by table/route/line count are weak.** They omit
architecture adaptation, encrypted multi-client isolation, migrations,
authorization, audit semantics, import/export, reconciliation, testing,
support, and upstream-maintenance burden as SlowBooks and LedgerTB diverge
over time. Conversely, a *narrower* AR/AP (import/reconciliation only, no
client-facing invoicing/PDF/email) might have real value at a fraction of
the "full port" effort — worth naming as a fourth option below.

**8. Only two options were considered; there are at least four.** No
change / import-reconcile with external systems / a narrow close-oriented
subledger / a full operational port. The document jumps straight to "full
port vs. nothing" for all three modules.

**Revised disposition** (Codex's recommended framing, adopted here):
- **Payroll**: do not port, absent a deliberate firm-wide product pivot —
  keep the recurring-compliance/liability/continuity rationale as primary.
- **Full AR/AP**: hold pending demonstrated demand and economics — but note
  a narrow import/reconciliation subledger is a distinct, cheaper option
  not yet evaluated on its own.
- **Inventory**: move to a bounded discovery decision, not an automatic
  "blocked on AR/AP."
- **Set a review date and named triggers** (affected-client count, hours
  saved, acceptable five-year ownership cost) so this hold is an actionable
  decision Scott can reopen on evidence, not an unreviewed permanent
  rejection.

If there's a real business driver for LedgerTB to become a fuller product
for firm clients, that's a scope conversation with Scott on its own — not
something to greenlight or foreclose as a byproduct of a feature-porting
exercise.
