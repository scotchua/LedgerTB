# Mutation sweep: `services/activity_feed.py`

The runner generated 32 single-change mutants across all eight functions in the
module. It changed a temporary copy of the source, ran each case in a fresh
offline Python process with an eight-second limit, and left the source file
byte-identical (SHA-256 `b5437eb3791ea22b9900838a2b689df3403638adde86fa06e16cdd4817c3411c`).
No comment, logging, or docstring was mutated. There were no timeouts.
The source contains no exception `raise` statement to drop.

| Phase | Killed | Total | Kill rate |
| --- | ---: | ---: | ---: |
| Before new tests | 3 | 32 | 9.4% |
| After new tests | 32 | 32 | 100% |

The before phase ran the two existing `describe_when` tests that can execute
without the database dependencies. The after phase ran those tests and the
eight new focused tests. Both phases used stub model modules and invented data;
they did not access the database, credentials, or network. The baseline is
therefore for the runnable offline subset of existing tests, not the entire
database-backed activity feed test file.

| ID | Function | Mutation | Before | After |
| --- | --- | --- | --- | --- |
| P01 | `_parse` | `or` to `and` in the initial guard | survived | killed |
| P02 | `_parse` | timestamp split index `0` to `1` | survived | killed |
| L01 | `_plural` | `== 1` to `!= 1` | survived | killed |
| A01 | `_account_label` | account count `> 1` to `>= 1` | survived | killed |
| A02 | `_account_label` | negate account-number guard | survived | killed |
| A03 | `_account_label` | fallback return to `None` | survived | killed |
| I01 | `_import_events` | filename count `> 1` to `>= 1` | survived | killed |
| I02 | `_import_events` | pending plus categorized to subtraction | survived | killed |
| I03 | `_import_events` | negate unposted guard | survived | killed |
| I04 | `_import_events` | remove event append statement | survived | killed |
| I05 | `_import_events` | return `None` instead of events | survived | killed |
| J01 | `_journal_events` | adjusting condition `and` to `or` | survived | killed |
| J02 | `_journal_events` | beginning-balance `==` to `!=` | survived | killed |
| J03 | `_journal_events` | negate description guard | survived | killed |
| J04 | `_journal_events` | remove event append statement | survived | killed |
| J05 | `_journal_events` | return `None` instead of events | survived | killed |
| U01 | `_audit_events` | export `==` to `!=` | survived | killed |
| U02 | `_audit_events` | reverse `==` to `!=` | survived | killed |
| U03 | `_audit_events` | remove event append statement | survived | killed |
| U04 | `_audit_events` | return `None` instead of events | survived | killed |
| D01 | `describe_when` | negative-seconds `<` to `<=` | survived | killed |
| D02 | `describe_when` | 90-second `<` to `<=` | survived | killed |
| D03 | `describe_when` | 3600-second `<` to `<=` | killed | killed |
| D04 | `describe_when` | 86400-second `<` to `<=` | survived | killed |
| D05 | `describe_when` | 172800-second `<` to `<=` | survived | killed |
| D06 | `describe_when` | 604800-second `<` to `<=` | survived | killed |
| D07 | `describe_when` | singular-hour `==` to `!=` | killed | killed |
| D08 | `describe_when` | yesterday return to `None` | killed | killed |
| G01 | `get_recent_activity` | default limit `6` to `7` | survived | killed |
| G02 | `get_recent_activity` | descending sort to ascending | survived | killed |
| G03 | `get_recent_activity` | return `None` instead of slice | survived | killed |
| G04 | `get_recent_activity` | remove sort statement | survived | killed |

## New tests

The following tests all passed on the original source and each killed at least
one recorded mutant:

- `test_parse_preserves_datetimes_and_accepts_sqlite_strings`
- `test_plural_uses_singular_only_for_one`
- `test_account_label_uses_count_number_and_fallback`
- `test_import_events_report_files_and_both_unposted_statuses`
- `test_journal_events_name_entries_and_keep_details`
- `test_audit_events_name_exports_reversals_and_fallbacks`
- `test_describe_when_switches_at_each_boundary`
- `test_recent_activity_sorts_limits_and_keeps_missing_timestamps`

## Survivors left

None. No equivalent, untestable, or defect mutants remain in this sweep.

## Defects found

None.

## Verification limit

`python3 -m pytest -q -m "not performance"` stops while loading
`tests/conftest.py`: `ModuleNotFoundError: No module named 'platformdirs'`.
The requested `python` executable is also absent. No packages were installed.
The full suite and database-backed activity feed tests could not be verified
in this environment.
