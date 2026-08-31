# Money engine seam audit — 2026-08-30

## ESCALATE

Data already written by the application can be silently wrong: MONEY-01 is reached through the normal invoice-posting path and can permanently overstate COGS while hiding the offsetting negative inventory residual when fractional weighted-average cost is rounded before extension.

## MONEY-01 — Invoice COGS loses fractional weighted-average value

**Broken invariant.** The settled round-then-extend policy requires the current weighted-average unit cost to be rounded once per movement and then extended. This path does that, but it discards the resulting movement-rounding residual: `inventory_position()` rounds the average to a whole cent in its public result, `_record_movement()` consumes that rounded result, and zero quantity silently resets the residual to zero. The break is at `services/inventory.py:132-145` and `services/inventory.py:172-176`; the resulting COGS entry is extended at `services/ar_ap.py:324-333`.

**Concrete failing sequence (hand trace).** Purchase 1 unit at 100 cents, then 2 units at 101 cents. The register value is 302 cents for 3 units, so the exact weighted average is 100.666... cents. Post an invoice for 3 units. The code returns a rounded average of 101 cents, stores 101 cents on the sale movement, and posts COGS of `3 × 101 = 303` cents. The movement history then computes `302 - 303 = -1` cent at zero quantity, but `inventory_position()` forcibly resets zero-quantity value to 0. Books show COGS $3.03 even though all inventory acquired cost $3.02; COGS plus ending inventory exceeds total cost by one cent. Repeating this realistic three-unit purchase/sale cycle three times overstates COGS by 3 cents, exceeding the one-cent tolerance.

**Accounting consequence.** Gross profit is understated by one cent per cycle, while the subledger suppresses the corresponding negative residual whenever quantity reaches zero. The GL inventory credit can therefore exceed acquired inventory cost even though the displayed ending inventory is zero.

**Suggested fix.** Continue rounding the movement unit cost before extension, but retain and explicitly clear the accumulated rounding residual (for example in the final depletion movement) rather than zeroing it invisibly.

**Confidence: high.** This is a direct hand trace through the production arithmetic and normal invoice posting path; the regression test asserts the conservation equation that the current code violates.

## MONEY-02 — As-of aging applies future credit applications retroactively

**Broken invariant.** An as-of aging report must reflect only events effective by the report date. The invoice branch limits credit applications by the credit memo's `memo_date`, not by an application date; `credit_applications` has no application-date column (`database/migrations/039_sales_tax_credit_memos.sql:35-41`), and the query at `services/ar_ap.py:1669` therefore retroactively applies a later allocation. The open-credit branch has the same missing temporal fact at `services/ar_ap.py:1621-1626`.

**Concrete failing sequence (hand trace).** On August 1 post a $100.00 invoice (AR debit $100). On August 5 post a $30.00 credit memo (AR credit $30), leaving August 10 aging at `$100 invoice - $30 unapplied credit = $70`, equal to the $70 AR GL. On August 20 apply all $30 to the invoice. Re-run aging **as of August 10**. Because the memo date is August 5, the query subtracts the $30 application from the invoice and also subtracts it from the memo's remaining credit: it reports only a $70 invoice and no credit, net $70. The total happens to tie to GL, but the underlying August 10 detail is false: it should show a $100 debit and a separate $30 credit. Thus the three-way total can report agreement while both aging components were rewritten by a future event.

**Accounting consequence.** Historical AR detail is not reproducible. Collection and credit-exposure reports for a closed date misstate which invoice was outstanding and which customer credit was unapplied, even though the net control-account tie-out appears clean.

**Suggested fix.** Persist `applied_at` (or an effective application date) on every credit application and use it in both the invoice and open-credit as-of predicates.

**Confidence: high.** The schema makes the required time dimension impossible to query, and both halves of the hand-traced aging query demonstrably use the memo date instead.

## Checked and found sound

- Frozen-cost invoice void: hand-traced two invoice lines, an intervening higher-cost purchase, and a later void; each reversal movement restores the original line quantity at its stored original cost.
- Partial consumption, void, and re-issue: hand-traced 10 units purchased, 4 invoiced, that invoice voided, and 6 re-issued; source-line uniqueness and additive movements leave quantity equal to the movement sum.
- Allocation plus taxed credit memo plus partial payment: hand-traced a $106.50 taxed invoice, $40 payment, and $22 credit application; stored control accounts keep current aging and AR GL at $44.50.
- Taxed document void: hand-traced the generated reversal lines; receivable, revenue, and sales-tax liability are all reversed together, and an applied credit correctly blocks the void.
- Immutable posted journals: inspected model save/delete/reverse ownership checks and direct SQL writers in the scoped services; no surviving supported path mutating posted journal headers or lines was found.
- Atomic inventory and AR/AP writers: inspected invoice, void, movement, CSV import, payment, refund, credit-posting, and credit-application paths; state-changing read/write sequences use the caller transaction or `BEGIN IMMEDIATE`.
