# MONEY-01: weighted-average rounding residual

## Decision

Choose option (a): carry the residual in the inventory layer and clear it into
COGS on the final depletion movement.

For an item, `value_cents` is the signed sum of every movement's quantity times
its stored whole-cent unit cost. The residual is that value when quantity is
zero. A reduction that leaves quantity above zero keeps the existing
round-then-extend rule: round the pre-movement weighted-average unit cost to a
whole cent, store that cost on the movement, and extend quantity by that stored
cost. A reduction that leaves quantity exactly zero also stores that rounded
unit cost, but its inventory and COGS posting is the ordinary extension plus
the entire pre-movement residual. That final posting makes inventory zero and
puts cumulative acquired cost into COGS. Negative stock remains blocked.

Example: buy one unit at 100 cents and two at 101 cents. The exact average is
302 / 3 cents, so the three-unit sale stores 101 cents. Its ordinary extension
is 303 cents and the pre-sale residual is -1 cent. The sale therefore posts
302 cents to COGS and credits inventory 302 cents. The stored movement cost
remains 101 cents; the residual-clearing amount is separate movement metadata
and is included in the movement's posting value.

This costs an additional integer-cent residual (or equivalent adjustment)
field in the inventory movement representation and corresponding migration,
replay, rollforward, posting, audit, and reversal logic. Final-depletion COGS
will not always equal `abs(quantity * unit_cost_cents)`, so reports and callers
must use the movement's stored posting value rather than reconstructing it from
quantity and unit cost alone. COGS also absorbs small rounding adjustments,
which are less visible than a dedicated rounding account.

## Exact semantics

- `inventory_position()` reports the signed historical `value_cents` even at
  zero quantity. Before the final-depletion movement has been corrected or for
  legacy history, a residual is therefore visible rather than forced to zero.
  `weighted_average_unit_cost_cents` is `0` whenever quantity is zero because
  no per-unit average exists.
- A new final-depletion movement clears the complete pre-movement value into
  COGS. Its resulting position is exactly quantity `0`, weighted-average unit
  cost `0`, and value `0`.
- A void appends a movement at the original movement's stored whole-cent unit
  cost and reverses exactly the original GL posting, including any separately
  stored residual-clearing amount. If that void returns quantity to non-zero,
  the residual survives: replay restores the exact inventory value that
  existed immediately before the voided movement, and the weighted average is
  computed from that value and restored quantity.
- If an item is fully depleted and later repurchased, the depletion has already
  cleared the old residual into COGS. The repurchase starts a new cost pool at
  its explicit purchase cost; no old residual changes its weighted average.
- Backdated replay applies the same rules in movement-date/id order. Any changed
  residual-clearing amount is a correction, not a mutation of a posted journal:
  use the existing reversal or atomic reverse-and-correct-at-Save path.
- All persisted costs and adjustments are integer cents. No stored float or
  fractional-cent amount is introduced.

## Frozen-cost void guarantee

The guarantee is preserved, but its unit-cost field alone is no longer the
complete reversal oracle for a final depletion. The original stored unit cost
is never recomputed, and the void uses it. The void must also reverse the
original movement's immutable stored residual-clearing amount. Thus the void's
inventory and COGS entries are exactly equal and opposite to the original,
even if purchases at different costs occurred later. Recomputing a residual at
void time would violate the guarantee and is forbidden.

## Rejected options

- Option (b), a dedicated rounding account, conserves cost and can preserve the
  frozen-cost void guarantee if both original posting components are stored and
  reversed. It was rejected because it adds an account configuration and a GL
  line for a sub-cent-average artifact on every affected depletion, while
  moving part of acquisition cost outside COGS.
- Option (c), storing an exact higher-precision movement cost and rounding only
  at GL posting, conflicts with round-then-extend. Its inventory movement would
  no longer freeze the whole-cent unit cost used for extension. It could
  preserve voiding only by storing and reversing the final rounded posting too,
  but it changes the settled valuation policy.
- Option (d) was not chosen. In particular, silently resetting the residual or
  carrying it into a later repurchase either loses cost or contaminates a new
  cost pool. Adjusting a final movement's `unit_cost_cents` to force balance
  also breaks the rule that its unit cost is the rounded weighted average.

## Existing stored data

Already-stored movement unit costs and posted journal amounts are historical
facts and are not rewritten. However, any existing fully depleted cost pool
whose rounded reductions did not equal its acquired cost has an incorrect
inventory/COGS allocation by the discarded residual. For the confirmed three
cycles, stored COGS is 909 cents and acquired cost is 906 cents, so COGS is
overstated by 3 cents; the forced zero position hides the offset. Such history
requires an explicit correcting entry (and residual metadata sufficient for
future exact voids) if the books are to reflect the specified allocation.
Items without a nonzero historical residual need no monetary correction.

The implementation can be prospective for new movements, in which case old
posted books remain as recorded and only future depletions conserve cost. Or a
client-specific correcting entry can address identified legacy residuals.
That is a factual distinction: this design does not decide whether a client
should correct prior books.
