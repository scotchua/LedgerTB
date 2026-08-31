# Audits, 2026-08-30

Codex authored these; Claude reviewed every one by running its tests in the
real venv against base commit `a9277b4`. Read this file first: two findings
were withdrawn and one Claude conclusion was itself wrong.

## money-engine-audit-2026-08-30.md — two CONFIRMED defects

- **MONEY-01**, invoice COGS discards the weighted-average rounding residual.
  Verified by execution: COGS 909 + ending inventory 0 against an acquired cost
  of 906 over three cycles. `services/inventory.py`, `services/ar_ap.py`.
  Design accepted in `money-01-rounding-residual.md` (option (a): carry the
  residual, clear it into COGS on final depletion, preserving round-then-extend
  and the frozen-cost void guarantee).
  **Scott ruled: fix PROSPECTIVELY. Already-recorded books stand. No correcting
  entry.** Not yet implemented. Oracle exists and is Codex-authored, so the
  implementation must satisfy it rather than edit it.
- **MONEY-02**, as-of AR aging retroactively rewritten by a later credit
  application, because `credit_applications` has no application-date column.
  Verified at base: aging as of 2026-08-10 returned `[('invoice', 7000)]` where
  `[('invoice', 10000), ('credit_memo', -3000)]` was correct.
  **Fixed independently** by `70a33ad` "Harden A/R and A/P chronology" and
  migration `042_ar_ap_chronology.sql`. No action.

Six seams were attacked and held: frozen-cost voids, partial-consume-void-
reissue, allocation with taxed credit memos, taxed-document voids, immutable
posted journals via indirect paths, and atomic inventory/AR-AP writers.

## money-engine-audit-round2-*.md — read the correction, and then read this

Round 2 attacked eight seams. Seven held. Its one finding, **MONEY-R2-01**
(concurrent depreciation leaving an orphan journal), was escalated, then
withdrawn, and the withdrawal is itself partly wrong. Sequence:

1. Codex escalated it, citing `services/fixed_assets.py:56-66` performing the
   read, check, and calculation on separate connections before the write
   transaction.
2. Claude ran the test. It failed with `entry_count=0 run_count=0`, which is
   clean atomic rollback, not an orphan. **Withdrawing on that evidence was
   correct**: a finding whose test proves nothing cannot be carried.
3. Claude then asserted the finding's PREMISE was unfounded, citing
   `BEGIN IMMEDIATE` before the read. **That was wrong.** The line was read
   from the working tree, which held another session's uncommitted rewrite. At
   `a9277b4` the function really did three reads on three connections before
   any write transaction, exactly as Codex described.
4. `a855480` "Harden fixed-asset posting integrity" then rewrote that function
   to thread a connection and open `BEGIN IMMEDIATE` before the reads, with 74
   lines of new tests. The path was genuinely soft.

**So: MONEY-R2-01 stays withdrawn as a finding, its premise was sound, and the
weakness is now fixed.** The round-2 document's `ESCALATE` line and its S7
verdict of HELD should both be read as superseded by this note. Lesson recorded:
never check a claim made against a base commit by reading the checkout; use
`git show <base>:<path>`.

## payroll-parser-spec.md — blocked on Scott

Spec plus a skip-guarded oracle for Gusto Payroll Journal and QBO Payroll
Summary parsers. **Zero aliases are marked CONFIRMED**, correctly, because no
real export was available. Everything is LIKELY or GUESS. Its closing section
names the questions a real sample settles in about ten minutes. Unblocks when
Scott supplies one export of each.

## Adversarial tests are not committed

Each belongs with its fix, as that fix's regression test. Archived at
`~/Claude/docs/codex-audit-2026-08-30/tests/`.

Full session record: `~/Claude/docs/codex-session-2026-08-30-dispositions.md`
