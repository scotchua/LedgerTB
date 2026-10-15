# Mutation test: `utils/secure_store.py`

## Method

Parsed the complete module and generated 49 single-edit AST mutants across all five functions (cap: 150). Operators used: comparison flips, `and`/`or` swaps, condition negation, return replacement with `None`/empty string/`False`, statement removal, and dropped raises. The module has no numeric constants or `+`/`-` expressions inside functions, so those operators generated no mutants. Comments and docstrings were not mutated.

Each mutant was compiled from an in-memory copy, written to a temporary file, and loaded as `utils.secure_store` in a fresh pytest subprocess with a 12-second timeout. The original module was never overwritten. The relevant original tests (`tests/test_secure_store.py`) and new tests were copied to the temporary directory to avoid the application-wide `conftest.py`; the installed interpreter lacks `platformdirs`. No network or real vault access was used.

## Results

| Stage | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Existing tests | 33 | 49 | 67.3% |
| Existing and new tests | 46 | 49 | 93.9% |

The three remaining mutants are behaviorally equivalent, so the after rate among the 46 behavioral mutants is 100%. No run timed out.

| ID | Function | Line | Mutation | Before | After |
| --- | --- | ---: | --- | --- | --- |
| M001 | `_read` | 11 | return None | killed | killed |
| M002 | `_read` | 11 | return empty | killed | killed |
| M003 | `_read` | 11 | return False | killed | killed |
| M004 | `set_secret` | 39 | negate condition | killed | killed |
| M005 | `set_secret` | 42 | remove statement | killed | killed |
| M006 | `set_secret` | 43 | negate condition | killed | killed |
| M007 | `migrate_legacy_secret` | 70 | remove statement | killed | killed |
| M008 | `migrate_legacy_secret` | 71 | negate condition | killed | killed |
| M009 | `migrate_legacy_secret` | 73 | negate condition | killed | killed |
| M010 | `_read` | 11 | swap and/or | killed | killed |
| M011 | `get_secret` | 17 | remove statement | killed | killed |
| M012 | `get_secret` | 18 | negate condition | killed | killed |
| M013 | `get_secret` | 20 | remove statement | killed | killed |
| M014 | `get_secret` | 21 | negate condition | killed | killed |
| M015 | `get_secret` | 33 | return None | killed | killed |
| M016 | `get_secret` | 33 | return empty | killed | killed |
| M017 | `get_secret` | 33 | return False | killed | killed |
| M018 | `set_secret` | 40 | drop raise | survived | killed |
| M019 | `set_secret` | 43 | flip comparison | killed | killed |
| M020 | `set_secret` | 44 | drop raise | survived | killed |
| M021 | `set_secret` | 51 | remove statement | killed | killed |
| M022 | `migrate_legacy_secret` | 72 | return None | survived | killed |
| M023 | `migrate_legacy_secret` | 72 | return empty | survived | killed |
| M024 | `migrate_legacy_secret` | 72 | return False | survived | killed |
| M025 | `migrate_legacy_secret` | 74 | return empty | survived | killed |
| M026 | `migrate_legacy_secret` | 74 | return False | survived | killed |
| M027 | `migrate_legacy_secret` | 76 | remove statement | killed | killed |
| M028 | `migrate_legacy_secret` | 77 | negate condition | killed | killed |
| M029 | `migrate_legacy_secret` | 79 | remove statement | killed | killed |
| M030 | `migrate_legacy_secret` | 80 | remove statement | killed | killed |
| M031 | `migrate_legacy_secret` | 81 | return None | killed | killed |
| M032 | `migrate_legacy_secret` | 81 | return empty | killed | killed |
| M033 | `migrate_legacy_secret` | 81 | return False | killed | killed |
| M034 | `get_secret` | 19 | return None | killed | killed |
| M035 | `get_secret` | 19 | return empty | killed | killed |
| M036 | `get_secret` | 19 | return False | killed | killed |
| M037 | `get_secret` | 22 | return empty | survived | killed |
| M038 | `get_secret` | 22 | return False | survived | killed |
| M039 | `get_secret` | 28 | remove statement | killed | killed |
| M040 | `get_secret` | 29 | negate condition | survived | survived |
| M041 | `get_secret` | 35 | return empty | survived | killed |
| M042 | `get_secret` | 35 | return False | survived | killed |
| M043 | `delete_secret` | 63 | remove statement | killed | killed |
| M044 | `migrate_legacy_secret` | 78 | return empty | survived | killed |
| M045 | `migrate_legacy_secret` | 78 | return False | survived | killed |
| M046 | `migrate_legacy_secret` | 84 | return empty | killed | killed |
| M047 | `migrate_legacy_secret` | 84 | return False | killed | killed |
| M048 | `get_secret` | 29 | flip comparison | survived | survived |
| M049 | `get_secret` | 30 | drop raise | survived | survived |

## New tests

Each named test passed on the original module and failed when run alone against the paired recorded mutant. The combined run killed all 13 behavioral survivors from the original suite.

- `test_get_secret_returns_none_when_vault_has_no_entry` → M037
- `test_get_secret_returns_none_when_vault_read_fails` → M041
- `test_set_secret_rejects_empty_value` → M018
- `test_set_secret_rejects_unverified_write` → M020
- `test_migrate_legacy_secret_returns_existing_vault_value` → M022
- `test_migrate_legacy_secret_returns_none_when_file_is_missing` → M025
- `test_migrate_legacy_secret_preserves_blank_file` → M044

## Survivors left

- M040 (negate condition at line 29): equivalent. Either branch has the same vault calls and returns the legacy value; a raised verification error is swallowed by the adjacent `except`.
- M048 (flip comparison at line 29): equivalent for the same reason.
- M049 (drop raise at line 30): equivalent for the same reason.
- Untestable offline: none.
- Defect survivors: none.

## Defects found

None.

## Verification limits

The isolated secure-store tests passed on the original module. `python3 -m pytest -q -m "not performance"` could not collect the full suite: `tests/conftest.py` imports `config.py`, which requires the unavailable `platformdirs` package. The exact requested `python` executable is also unavailable in this environment. No packages were installed.
