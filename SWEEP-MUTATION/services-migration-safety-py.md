# Mutation test: `services/migration_safety.py`

## Method and results

The temporary AST runner generated 21 single-change mutants across both functions. It skipped comments, logging, and docstrings, used a 15-second timeout per mutant, and compiled each mutant from a temporary file without writing to the source module. There were no `+` or `-` binary operations to swap. The runner checked that the source bytes were unchanged after all runs.

Because this checkout's Python lacks `platformdirs`, ordinary pytest cannot load `tests/conftest.py`. The runner executed the four existing tests and the five new tests offline with stubbed `database.connection` and `database.crypto` modules. The stubs used temporary SQLite books and represented the active book as encrypted. This checks the migration-safety control flow, but it does not validate SQLCipher integration.

| Test set | Killed | Kill rate |
| --- | ---: | ---: |
| Four existing tests | 14 / 21 | 66.7% |
| Existing and new tests | 21 / 21 | 100% |

## Mutants

| ID | Change | Before | After |
| --- | --- | --- | --- |
| M01 | `active_plaintext_backup`: return `None` | survived | killed |
| M02 | `active_plaintext_backup`: return empty string | survived | killed |
| M03 | `active_plaintext_backup`: return `False` | survived | killed |
| M04 | `remove_active_plaintext_backup`: remove `backup.unlink()` | killed | killed |
| M05 | `remove_active_plaintext_backup`: return `None` | killed | killed |
| M06 | `remove_active_plaintext_backup`: return empty string | killed | killed |
| M07 | `remove_active_plaintext_backup`: return `False` | killed | killed |
| M08 | Missing-backup guard: change `and` to `or` | killed | killed |
| M09 | Missing-backup guard: drop raise | survived | killed |
| M10 | Plaintext-file guard: remove `not` | killed | killed |
| M11 | Plaintext-file guard: drop raise | killed | killed |
| M12 | Encrypted-state guard: change `!=` to `==` | killed | killed |
| M13 | Encrypted-state guard: drop raise | killed | killed |
| M14 | Integrity-result guard: remove `not` | killed | killed |
| M15 | Integrity-result guard: drop raise | killed | killed |
| M16 | Missing-backup guard: remove `not` from `exists()` | killed | killed |
| M17 | Missing-backup guard: remove `not` from `is_symlink()` | survived | killed |
| M18 | Verification cleanup: remove `conn.close()` | survived | killed |
| M19 | Verification exception handler: drop raise | survived | killed |
| M20 | Integrity comparison: change `==` to `!=` | killed | killed |
| M21 | Integrity result index: change `0` to `1` | killed | killed |

## New tests

Each listed test passed on the original module and failed when run alone against its recorded mutant.

| Test | Mutant killed |
| --- | --- |
| `test_active_plaintext_backup_uses_the_current_book` | M01 |
| `test_removal_reports_when_no_copy_exists` | M09 |
| `test_removal_preserves_dangling_symlink` | M17 |
| `test_removal_closes_verified_connection` | M18 |
| `test_removal_preserves_copy_when_opening_live_book_fails` | M19 |

Survivors left: none. Equivalent mutants: none observed. Untestable offline mutants: none. Defects found: none.

## Verification limit

`python3 -m pytest -q -m 'not performance'` stopped during conftest import with `ModuleNotFoundError: No module named 'platformdirs'`. No packages were installed. The isolated offline run passed all nine relevant tests on the original module.
