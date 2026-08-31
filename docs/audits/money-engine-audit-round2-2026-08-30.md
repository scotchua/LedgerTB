ESCALATE — MONEY-R2-01: concurrent fixed-asset depreciation can commit an orphan duplicate journal entry, silently overstating depreciation already written to the ledger.

# Money engine audit, round 2 — 2026-08-30

Method: static code and SQL hand-trace only. The unavailable runtime dependencies were not bypassed and no test suite was run. MONEY-01 and MONEY-02 are treated as known external fixes, not findings below.

## S1. Frozen cost against void against partial quantity — HELD

Attack constructed: purchase 10 units at 901 cents, invoice A for 4, purchase 10 at 2,003, invoice B for 8, then void B and A in reverse posting order. A freezes 901; after the second purchase the register is 16 units/29,040 cents, so B freezes the rounded 1,815-cent average. The two sales therefore carry -3,604 and -14,520 cents. Reverse voids append +8 at 1,815 and +4 at 901; every invoice movement has an equal-and-opposite movement and the movement sum returns to the two purchases, 29,040 cents. Re-issuing 6 after A's void freezes the then-current stored average, and voiding that re-issue reads its own original movement cost, not the current average, so that pair also nets zero.

Code path followed: `post_invoice` calls `_record_movement`, which stores one integer `unit_cost_cents` on each invoice line movement; `void_invoice` selects that exact row by `(source_type, source_id, source_line_id)` and appends the opposite quantity at the selected cost (`services/ar_ap.py:304-353`, `services/ar_ap.py:834-891`). The unique source index prevents the same invoice line movement from being recreated (`database/migrations/035_shared_domain_contracts.sql:15-17`).

Verdict: **HELD**. Intervening purchases and reverse-order voids do not reprice a posted sale. Stored-cost movement arithmetic and the paired COGS journals reconcile to zero for every post/void pair. This verdict is about frozen-cost reversibility, not the separately known weighted-average residual defect.

## S2. Round-then-extend across a longer horizon — HELD

Attack constructed: acquire 2 units at 1 cent and 1 unit at 2 cents (4 cents total), consume one unit three times, and compare every cost consumer. The position calculation rounds the running 4/3-cent average to 1 cent before `_record_movement` stores it; COGS extends the stored 1-cent cost, void reversal reads and extends the same 1 cent, and `inventory_rollforward` sums the same stored movement values. Thus COGS, credit-side inventory movement journals, void reversal, register value, and rollforward all agree with each other at every step even though the known residual issue can make the horizon disagree with acquired cost.

The search covered `services/inventory.py:103-143` and `374-436`, invoice COGS and void reversal at `services/ar_ap.py:304-353` and `834-891`, credit memos at `services/ar_ap.py:938-1141`, and fixed-asset depreciation at `services/fixed_assets.py:14-49`. Credit memos have no inventory quantity/cost fields and therefore do not recompute cost. Fixed assets round monthly amounts but cap the final straight-line month to the remaining depreciable basis, e.g. 10,000 cents over three months posts 3,333 + 3,333 + 3,334 = 10,000.

Verdict: **HELD**. No second rounded-then-consumed implementation was found that can disagree with another cost consumer: all inventory consumers read the stored movement unit cost. This does not re-report the already-settled residual loss.

## S3. Allocation engine against overapplication and ordering — HELD

Attack constructed: post a 10,000-cent invoice and 3,000-cent credit memo, apply the memo, then attempt a 10,000-cent allocated payment. It is refused because the invoice open balance is 7,000. A 10,000-cent payment with only 7,000 allocated is permitted as a deliberate 3,000-cent on-account credit: GL credits AR 10,000; aging shows invoice zero plus an open-credit row -3,000, matching AR. Voiding the applied credit memo is refused because applications exist. Applying one 10,000-cent memo as 6,000 to invoice A and then 5,000 to invoice B is refused on B because only 4,000 remains; a 4,000 application succeeds. An invoice carrying any credit application cannot be voided.

Code path followed: allocation and payment limits are checked inside `BEGIN IMMEDIATE` transactions (`services/ar_ap.py:387-525`, `1068-1111`); memo void and invoice void explicitly block existing applications (`services/ar_ap.py:825-828`, `1113-1127`). Applications create no GL because the memo already credited AR; aging nets the invoice and memo/open-credit detail against those posted entries.

Verdict: **HELD**. The engine refuses document overapplication, refuses aggregate memo overapplication, deliberately permits unallocated payment credit, and blocks both prohibited void orders. No silent overapplication path survived.

## S4. The three-way tie-out as an adversary — HELD

Attack constructed: searched for a structurally different false agreement using (a) payment allocation followed by dated payment void, (b) unapplied payment credit, (c) unapplied credit memo, (d) invoice and memo voids dated after the as-of date, and (e) documents routed to two different AR accounts. With numbers 10,000 invoice, 4,000 payment, 2,500 unapplied memo, and later voids, both detail and GL select source/reversal entries by their dates; the 3,500 net is represented as invoice 6,000 and memo -2,500. A second AR account produces a real per-account mismatch only if a caller incorrectly compares combined aging to one account, not an engine false tie.

Inverse attack: a 10,000 payment made after the as-of date and later voided cannot create a false disagreement because both allocation and open-credit queries exclude it by `payment_date`; a pre-as-of payment voided after as-of remains included in both detail and GL. The same date symmetry exists for invoice, payment, and credit-memo reversals (`services/ar_ap.py:1582-1694`).

Verdict: **HELD**. Apart from the known undated-credit-application mechanism, every modeled event has a source date and reversal journal date used symmetrically by aging and GL. No second false agreement or false disagreement was produced. This is a bounded uniqueness claim: direct database corruption and comparing combined multi-control-account aging to only one account are outside the tie-out contract.

## S5. Sales tax (039) crossing voids and credits — HELD

Attack constructed: post a 10,000-cent invoice at 10% (tax liability credit 1,000) and a partial 4,000-cent taxed credit memo at 10% (tax liability debit 400). Applying the memo does not post another journal. Attempting to void the invoice first is refused while the application exists; attempting to void the memo first is also refused. For the executable order with an unapplied memo, void invoice then memo: +1,000 -400 -1,000 +400 = zero tax liability. Reversing the void order gives +1,000 -400 +400 -1,000 = zero.

Code path followed: tax is stored at document creation, posted as a liability credit/debit (`services/ar_ap.py:278-303`, `990-1032`), and each void copies the original journal lines with debit and credit swapped (`services/ar_ap.py:744-760`, `807-833`, `1113-1141`).

Verdict: **HELD**. Both permitted void orders return account 039 to zero. The prompt's applied-credit sequence cannot proceed to either void by design; the refusal preserves the same 600-cent net liability until an unapply workflow exists.

## S6. Immutable posted journals (041) via indirect paths — HELD

Attack constructed: followed schema migrations/backfills, CSV/document staging into `post_transaction`, import category correction, batch reversal, close-package generation, fixed-asset depreciation/disposal, and depreciation draft approval. Searched all production SQL for `UPDATE`/`DELETE` against journal headers and lines. None changes posted amounts or lines. Corrections and batch reversal append entries; imports reach `JournalEntry.save`; close-package code is read-only except export audit rows; fixed assets also append through `JournalEntry.save`.

The sole production header update is reversal linkage, `reversed_by_journal_entry_id`, after an equal-and-opposite entry is saved (`models/journal_entry.py:569-612`). Migration 041 only adds reversal-link columns (`database/migrations/041_immutable_journal_entries.sql:1-4`). The amount/line backfill predates the posted immutability contract and constructs replacement tables during schema migration (`database/migrations/002_money_to_cents.sql:1-45`), rather than editing a live posted row through an application workflow.

Verdict: **HELD**. No inspected indirect path reaches a posted journal amount, account, date, or line without appending a new entry. Reversal-link metadata is the intended exception and does not rewrite accounting content.

## S7. Concurrency — BROKEN (MONEY-R2-01)

Finding: concurrent fixed-asset depreciation leaves an orphan duplicate journal entry.

File and line: `services/fixed_assets.py:56-66` performs the read/check/calculation on separate connections before the write transaction; `services/fixed_assets.py:85-95` saves the journal before inserting the uniquely constrained depreciation run. The constraint is `database/migrations/028_fixed_assets.sql:50-59` (also reinforced by `database/migrations/033_depreciation_draft_links.sql:1-2`).

Worked sequence: asset cost 10,000 cents, zero salvage, three-month straight-line life, no prior runs. Writer A and writer B both read zero runs and calculate January depreciation of 3,333 cents. A saves JE A (debit depreciation expense 3,333; credit accumulated depreciation 3,333) and inserts the January run. B entered before A's transaction but its first write may wait on SQLite's lock; after A commits, B's `entry.save(conn=conn)` commits JE B because `JournalEntry.save` sees an externally supplied connection and does not commit, then B's insert of the `(asset, January)` run violates the unique constraint. B's exception handler rolls back only B's current transaction, but the deferred transaction was implicitly committed between its pre-check read connection and write connection boundary; under the interleaving exercised by the matching test hook, JE B remains while only one 3,333-cent depreciation run exists. The register says accumulated depreciation 3,333 and book value 6,667, while GL says accumulated depreciation 6,666 and expense 6,666.

Accounting consequence: depreciation expense and accumulated depreciation are silently overstated by 3,333 cents; the fixed-asset subledger understates accumulated depreciation by 3,333 relative to GL. A caller sees an exception, but already-written ledger data is wrong.

Confidence: **high**. The read/check/calculation is visibly outside any caller transaction, and the unique constraint protects only `depreciation_runs`, not the preceding journal. The executable regression test deterministically inserts the competing run at the `JournalEntry.save` boundary and asserts that no orphan journal may remain; it is expected to fail. This is distinct from weighted-average rounding.

The broader concurrency attack also inspected invoice/payment/credit paths (all start `BEGIN IMMEDIATE` before read), inventory movement paths (same), batch reversal (`BEGIN IMMEDIATE` before blockers), payroll (compare-and-swap update rolls its same-transaction journal back), and import idempotency (unique key rolls its same-transaction journal back). Those paths held under the traced two-writer schedules.

## S8. Departments and source-links (035) — HELD

Attack constructed: an invoice line for 4 units creates movement source `(invoice, 41, line 87)`, then attempts to remove/recreate/renumber the line. There is no production edit/delete API for invoice lines after creation; the invoice remains the durable owner, foreign keys prevent deleting the parent, and the partial unique index prevents recreating the same source tuple. Void lookup uses the immutable line id, not display order (`services/ar_ap.py:225-250`, `834-861`; `database/migrations/035_shared_domain_contracts.sql:15-17`).

Department attack: create Operations and Sales, assign an employee to Operations, add a 10,000-cent gross-pay stub, then attempt to delete/merge Operations before and after posting. `Department` exposes create/list only and refuses in-place edit (`models/department.py:18-54`); no production delete or merge path exists. The FK from employees blocks raw deletion while referenced. Payroll resolves the employee's current department at posting, so a supported reassignment before posting deliberately routes the entire draft run to the new department; after posting, the journal stores the selected wages account and memo and later employee changes cannot rewrite it (`services/payroll_recording.py:141-229`).

Verdict: **HELD**. Supported paths cannot orphan or retarget source-line links, delete/merge referenced departments, or retroactively reroute posted wages. The one policy edge is explicit: department is not snapshotted on the pay stub, so reassignment before posting changes draft routing; that is observable pre-post behavior, not silent history mutation.
