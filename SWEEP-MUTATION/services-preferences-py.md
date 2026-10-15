# Mutation probe: `services/preferences.py`

The probe generated 32 one-change mutants, covering `AppPreferences`, `normalize_date_format`, `get_preferences`, `get_date_format`, and `save_date_format`. It skipped comments, logging, and docstrings. Each mutant was compiled and loaded from a separate temporary copy, with a 15-second subprocess timeout. The source file was never edited; its SHA-256 was checked before and after both runs.

The baseline used the two existing `test_date_format_preference_*` tests from `tests/test_preferences.py`. Because this checkout lacks `platformdirs`, the runner loaded the service with an in-memory cursor and audit stub and ran those test functions with `--noconftest`. The after run added the five tests in `tests/test_preferences_mutation.py` under the same stub. The stub models committed writes and audit history, but it is not a substitute for the full database suite.

| Result | All generated mutants | Behavior-changing mutants |
| --- | ---: | ---: |
| Killed before | 22/32 (68.75%) | 22/31 (70.97%) |
| Killed after | 31/32 (96.88%) | 31/31 (100%) |

`K` means at least one selected test failed on the mutant; `S` means all selected tests passed.

| ID | Change | Before | After |
| --- | --- | :---: | :---: |
| M01 | Empty `AppPreferences` default | S | K |
| M02 | Return unknown format unchanged | K | K |
| M03 | Always return default format | K | K |
| M04 | Return `None` from normalizer | K | K |
| M05 | Negate format membership | K | K |
| M06 | Read preference row with ID 2 | K | K |
| M07 | Reverse row-presence expression | K | K |
| M08 | Ignore selected row | K | K |
| M09 | Skip normalization when reading | K | K |
| M10 | Return `None` from `get_preferences` | K | K |
| M11 | Return `None` from `get_date_format` | S | K |
| M12 | Return constant default from `get_date_format` | S | K |
| M13 | Skip normalization before save | K | K |
| M14 | Invert validation comparison | K | K |
| M15 | Drop invalid-format exception | K | K |
| M16 | Open save cursor without commit | K | K |
| M17 | Look up old row with ID 2 | S | K |
| M18 | Use stored old format without normalization | S | S |
| M19 | Reverse old-row presence expression | K | K |
| M20 | Persist default instead of requested format | K | K |
| M21 | Swap audit condition `or` for `and` | S | K |
| M22 | Treat an existing row as an audit trigger | S | K |
| M23 | Audit equal instead of changed formats | S | K |
| M24 | Disable audit branch | K | K |
| M25 | Remove audit write | K | K |
| M26 | Reverse insert/update audit action | S | K |
| M27 | Change audit client ID from `None` to 1 | K | K |
| M28 | Change audit record ID from 1 to 2 | K | K |
| M29 | Drop previous format from audit event | S | K |
| M30 | Empty new-format audit value | K | K |
| M31 | Return `None` after save | K | K |
| M32 | Return default preferences after save | K | K |

## New tests

| Test | Kills previously surviving mutants |
| --- | --- |
| `test_app_preference_mutation_default_value` | M01 |
| `test_get_date_format_preference_mutation_reads_saved_format` | M11, M12 |
| `test_save_date_format_preference_mutation_audits_initial_default` | M21, M22, M26 |
| `test_save_date_format_preference_mutation_audits_changed_value` | M17, M21, M23, M26, M29 |
| `test_save_date_format_preference_mutation_skips_unchanged_audit` | M22, M23 |

## Survivors left

- **M18 - equivalent for valid database state.** The `app_preferences.date_format` column has a `CHECK` constraint admitting only the three supported formats. For every stored value, normalization returns that value. With no row, the changed `old_format` is only used behind a branch that omits `old_values`. A corrupt value would require bypassing the schema, so no test was added.

## Defects found

None.

## Verification limits

- The offline original run passed 2 existing preference tests; the after run passed those 2 plus all 5 new tests. Every new test failed on at least one recorded mutant and passed on the original.
- `python3 -m pytest -q -m "not performance"` cannot collect the full suite in this environment: `tests/conftest.py` imports `config.py`, which raises `ModuleNotFoundError: No module named 'platformdirs'`. No packages were installed and no production file was changed.
