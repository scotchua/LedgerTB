# Mutation test: `database/schema.py`

## Result

The original module was imported and exercised offline. A temporary pytest plugin supplied test-process shims for unavailable `platformdirs`, `pandas`, and `portalocker`; it disabled dotenv reads and used SQLite's unencrypted test fallback. The plugin and mutants lived in temporary files. Each mutant changed one AST node in a copy of `schema.py`; the source file was never written. Every run had a 30-second limit. The two existing suites were `tests/test_schema_migrations.py` and `tests/test_upstream_sync_schema.py` (27 tests). The after pass also ran `tests/test_schema_mutation.py` (6 new tests).

| Pass | Generated | Killed | Survived | Raw kill rate |
| --- | ---: | ---: | ---: | ---: |
| Before new tests | 34 | 27 | 7 | 79.4% |
| After new tests | 34 | 33 | 1 | 97.1% |

All 33 behavior-changing mutants were killed after the new tests. The sole survivor, M003, is equivalent. The original passed 27/27 relevant existing tests and 33/33 relevant tests after additions.

## Mutants

Each row is one AST mutation. `line` refers to the unchanged source. `killed` means the relevant pytest run failed; `survived` means it passed. No run timed out.

| ID | Function | Line | Mutation | Before | After |
| --- | --- | ---: | --- | --- | --- |
| M001 | `_added_column_if_sole_statement` | 31 | return to `None` | killed | killed |
| M002 | `_added_column_if_sole_statement` | 28 | `or` to `and` | killed | killed |
| M003 | `_added_column_if_sole_statement` | 29 | `return None` to `return None` | survived | survived |
| M004 | `_added_column_if_sole_statement` | 28 | `!=` to `==` | killed | killed |
| M005 | `_added_column_if_sole_statement` | 28 | remove `not` | killed | killed |
| M006 | `_added_column_if_sole_statement` | 28 | `1` to `2` | killed | killed |
| M007 | `_added_column_if_sole_statement` | 31 | `1` to `2` | killed | killed |
| M008 | `_added_column_if_sole_statement` | 26 | remove `not` | killed | killed |
| M009 | `_reconcile_document_audits` | 42 | return to `None` | killed | killed |
| M010 | `_reconcile_document_audits` | 49 | remove `reference.executescript` | killed | killed |
| M011 | `_reconcile_document_audits` | 55 | remove `BEGIN IMMEDIATE` | survived | killed |
| M012 | `_reconcile_document_audits` | 61 | remove tracking insert | killed | killed |
| M013 | `_reconcile_document_audits` | 64 | remove commit | survived | killed |
| M014 | `_reconcile_document_audits` | 56 | `!=` to `==` | killed | killed |
| M015 | `_reconcile_document_audits` | 57 | drop mismatch raise | killed | killed |
| M016 | `_reconcile_document_audits` | 66 | remove rollback | survived | killed |
| M017 | `_reconcile_document_audits` | 67 | drop re-raise | killed | killed |
| M018 | `create_tables` | 76 | remove tracking-table creation | killed | killed |
| M019 | `create_tables` | 82 | remove initial commit | survived | killed |
| M020 | `create_tables` | 84 | remove version query | killed | killed |
| M021 | `create_tables` | 89 | `in` to `not in` | killed | killed |
| M022 | `create_tables` | 93 | remove `not` | killed | killed |
| M023 | `create_tables` | 94 | `+=` to `-=` | survived | killed |
| M024 | `create_tables` | 95 | `and` to `or` | killed | killed |
| M025 | `create_tables` | 113 | remove migration execution | killed | killed |
| M026 | `create_tables` | 85 | `0` to `1` | killed | killed |
| M027 | `create_tables` | 95 | `==` to `!=` | killed | killed |
| M028 | `create_tables` | 95 | `in` to `not in` | killed | killed |
| M029 | `create_tables` | 115 | remove rollback | killed | killed |
| M030 | `create_tables` | 135 | drop error re-raise | killed | killed |
| M031 | `create_tables` | 122 | `and` to `or` | survived | killed |
| M032 | `create_tables` | 129 | remove healing insert | killed | killed |
| M033 | `create_tables` | 133 | remove healing commit | killed | killed |
| M034 | `create_tables` | 123 | `==` to `!=` | killed | killed |

## New tests

| Test | Mutant killed | Behavior checked |
| --- | --- | --- |
| `test_reconcile_document_audits_locks_schema_during_comparison` | M011 | Concurrent DDL cannot change the schema after comparison but before recording the rename. |
| `test_reconcile_document_audits_commits_tracking_row` | M013 | The tracking row remains after closing and reopening the database. |
| `test_reconcile_document_audits_rolls_back_on_schema_mismatch` | M016 | A failed reconciliation leaves no open transaction. |
| `test_create_tables_commits_tracking_table_with_no_migrations` | M019 | Initial setup commits even when there are no migration files. |
| `test_create_tables_accepts_migration_without_final_semicolon` | M023 | A migration missing its final semicolon still runs and is recorded. |
| `test_create_tables_does_not_heal_other_sql_errors` | M031 | A missing table error is not mistaken for a duplicate column. |

Each listed test passed on the original and was the failing test in its corresponding after-mutant run. The tests use invented database filenames and SQL objects.

## Survivors left

- **M003, equivalent:** the generated replacement for the explicit `return None` at line 29 is the same `return None`; it cannot change behavior and needs no test.

Untestable offline: none among the generated mutants. Defects found: none.

## Verification limit

The requested `python -m pytest -q -m "not performance"` could not start because this environment has no `python` command. The available `python3` also could not collect the full suite because `platformdirs` is not installed. The relevant 33 tests passed with temporary shims; this does not establish a full-suite pass. No packages were installed or network calls made. `database/schema.py` remained byte-identical (SHA-256 `dacf0cd6b5c0466a5336139b1bab4c7686d93c215cbbf246f561cbcd40b418cf`).
