WITHDRAWN

# MONEY-R2-01 correction

MONEY-R2-01 is not supported and is withdrawn. S7's verdict becomes **HELD**,
and the audit's **ESCALATE** line must be removed.

## Why the diagnostic was zero/zero

The result `entry_count=0 run_count=0` is the expected atomic rollback for the
interleaving the original test produced:

1. The `db` fixture only redirects the database, initializes it, and yields; it
   does not enclose the test in a transaction or roll it back
   (`tests/conftest.py:69-93`). The `client_id` fixture calls `Client.save`
   (`tests/conftest.py:96-99`), and normal setup writes are committed by their
   model methods. Thus the fixture did not silently discard the test's writes.
2. `run_depreciation` creates one connection and passes that exact connection
   to `JournalEntry.save` (`services/fixed_assets.py:85-88`).
   `JournalEntry.save` explicitly participates in the caller's transaction when
   given a connection (`models/journal_entry.py:82-87`); `owns_conn` is false
   (`models/journal_entry.py:110-113`), so it does not commit
   (`models/journal_entry.py:182-191`). The save hook did fire, but its journal
   insert remained uncommitted on the depreciation transaction's connection.
3. The depreciation-run insert follows on that same connection
   (`services/fixed_assets.py:89-95`). When the competing insert makes it fail,
   `run_depreciation` rolls the connection back
   (`services/fixed_assets.py:104-109`). That rollback removes both the
   uncommitted journal entry and the attempted run. The competing connection in
   the original test was also not committed, so its cleanup removed its run.
   The final observable counts are consequently zero journal entries and zero
   depreciation runs.

The original trace incorrectly treated `JournalEntry.save(conn=conn)` as an
independently committed write. It is deliberately the opposite: the journal
entry and depreciation-run record form one transaction. Therefore the trace
never demonstrated an orphan journal, and its assertion `entry_count ==
run_count == 1` failed only because it expected a committed survivor from a
schedule in which both transactions were rolled back.

This diagnosis does not activate the correction brief's escalation condition.
It identifies transaction ownership specific to the rejected S7 depreciation
attack, not a fixture that discards writes globally; none of the other seven
HELD verdicts is invalidated. The corrected S7 section should say that the
depreciation path **HELD** because the journal entry and run record share a
single connection and rollback boundary. The audit should contain no
**ESCALATE** line for MONEY-R2-01.

This is a hand-trace only. Per the correction brief, pytest was not run.
