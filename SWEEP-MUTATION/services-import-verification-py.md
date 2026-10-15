# Mutation testing: `services/import_verification.py`

## Method and result

- Generated 74 single-change AST mutants (150 maximum), covering `_match_key`, both `is_clean` properties, `expected_count`, `difference`, `check_row_continuity`, and `verify_against_source`.
- Operators used: 27 return replacements (None, False, or empty list), 18 numeric constants increased by one, 14 statement removals, 6 `and`/`or` swaps, 5 condition negations, and 4 `+`/`-` swaps. No `<`, `<=`, `>`, `>=`, `==`, or `!=` comparisons and no exception raises occur in executable code, so those operators yielded no mutants. Comments and docstrings were excluded.
- Each mutant was compiled, loaded from a temporary file, and given a separate 12-second test process. The source module was never edited. The process ran `tests/test_import_verification.py` with project model and identity dependencies substituted offline; the canonical description substitute copied the production normalization algorithm. No run timed out.
- **Before:** 58/74 killed (78.4%); 16 survived.
- **After:** 73/74 killed (98.6%); 1 survived (equivalent).
- Original source SHA-256 before and after: `8e19d2d8920a8e186299fdf6976bf4562b65a4fc7ea0bed2d70c3187125774fa`.

## Mutant inventory

| ID | Function | Source line | Mutation | Before | After |
| --- | --- | ---: | --- | --- | --- |
| M001 | `_match_key` | 31 | remove | killed | killed |
| M002 | `_match_key` | 31 | negate | survived | killed |
| M003 | `_match_key` | 31 | boolean | survived | killed |
| M004 | `_match_key` | 31 | constant | survived | killed |
| M005 | `_match_key` | 32 | return (None) | killed | killed |
| M006 | `_match_key` | 32 | return (False) | killed | killed |
| M007 | `_match_key` | 32 | return (empty) | killed | killed |
| M008 | `_match_key` | 32 | boolean | killed | killed |
| M009 | `_match_key` | 32 | constant | survived | killed |
| M010 | `_match_key` | 32 | constant | survived | killed |
| M011 | `is_clean` | 47 | return (None) | killed | killed |
| M012 | `is_clean` | 47 | return (False) | killed | killed |
| M013 | `is_clean` | 47 | return (empty) | killed | killed |
| M014 | `expected_count` | 51 | negate | killed | killed |
| M015 | `expected_count` | 51 | boolean | survived | killed |
| M016 | `expected_count` | 52 | return (None) | survived | killed |
| M017 | `expected_count` | 52 | return (False) | survived | killed |
| M018 | `expected_count` | 52 | return (empty) | survived | killed |
| M019 | `expected_count` | 53 | return (None) | killed | killed |
| M020 | `expected_count` | 53 | return (False) | killed | killed |
| M021 | `expected_count` | 53 | return (empty) | killed | killed |
| M022 | `expected_count` | 53 | arithmetic | killed | killed |
| M023 | `expected_count` | 53 | arithmetic | killed | killed |
| M024 | `expected_count` | 53 | constant | killed | killed |
| M025 | `check_row_continuity` | 63 | remove | killed | killed |
| M026 | `check_row_continuity` | 64 | remove | killed | killed |
| M027 | `check_row_continuity` | 64 | constant | killed | killed |
| M028 | `check_row_continuity` | 66 | negate | killed | killed |
| M029 | `check_row_continuity` | 67 | return (None) | killed | killed |
| M030 | `check_row_continuity` | 67 | return (False) | killed | killed |
| M031 | `check_row_continuity` | 67 | return (empty) | killed | killed |
| M032 | `check_row_continuity` | 67 | constant | killed | killed |
| M033 | `check_row_continuity` | 69 | remove | killed | killed |
| M034 | `check_row_continuity` | 70 | return (None) | killed | killed |
| M035 | `check_row_continuity` | 70 | return (False) | killed | killed |
| M036 | `check_row_continuity` | 70 | return (empty) | killed | killed |
| M037 | `check_row_continuity` | 71 | constant | killed | killed |
| M038 | `check_row_continuity` | 72 | constant | killed | killed |
| M039 | `check_row_continuity` | 74 | constant | killed | killed |
| M040 | `check_row_continuity` | 74 | arithmetic | killed | killed |
| M041 | `check_row_continuity` | 74 | constant | killed | killed |
| M042 | `check_row_continuity` | 74 | constant | killed | killed |
| M043 | `is_clean` | 93 | return (None) | killed | killed |
| M044 | `is_clean` | 93 | return (False) | killed | killed |
| M045 | `is_clean` | 93 | return (empty) | killed | killed |
| M046 | `is_clean` | 93 | boolean | killed | killed |
| M047 | `difference` | 97 | return (None) | killed | killed |
| M048 | `difference` | 97 | return (False) | killed | killed |
| M049 | `difference` | 97 | return (empty) | killed | killed |
| M050 | `difference` | 97 | arithmetic | killed | killed |
| M051 | `difference` | 97 | constant | survived | killed |
| M052 | `verify_against_source` | 114 | remove | killed | killed |
| M053 | `verify_against_source` | 116 | remove | killed | killed |
| M054 | `verify_against_source` | 118 | remove | killed | killed |
| M055 | `verify_against_source` | 119 | remove | killed | killed |
| M056 | `verify_against_source` | 122 | remove | killed | killed |
| M057 | `verify_against_source` | 122 | constant | survived | killed |
| M058 | `verify_against_source` | 123 | remove | killed | killed |
| M059 | `verify_against_source` | 124 | negate | killed | killed |
| M060 | `verify_against_source` | 125 | remove | killed | killed |
| M061 | `verify_against_source` | 125 | constant | killed | killed |
| M062 | `verify_against_source` | 126 | negate | killed | killed |
| M063 | `verify_against_source` | 127 | remove | survived | survived |
| M064 | `verify_against_source` | 129 | remove | killed | killed |
| M065 | `verify_against_source` | 131 | remove | killed | killed |
| M066 | `verify_against_source` | 133 | return (None) | killed | killed |
| M067 | `verify_against_source` | 133 | return (False) | killed | killed |
| M068 | `verify_against_source` | 133 | return (empty) | killed | killed |
| M069 | `verify_against_source` | 139 | boolean | killed | killed |
| M070 | `verify_against_source` | 139 | constant | survived | killed |
| M071 | `verify_against_source` | 139 | constant | survived | killed |
| M072 | `verify_against_source` | 140 | boolean | killed | killed |
| M073 | `verify_against_source` | 140 | constant | survived | killed |
| M074 | `verify_against_source` | 140 | constant | survived | killed |

## New tests

| Test | Recorded mutant it kills |
| --- | --- |
| `test_match_key_accepts_a_timestamp_string_as_a_calendar_date` | M002 (also M003, M004) |
| `test_match_key_uses_whole_cents_for_zero_and_positive_amounts` | M009 (also M010) |
| `test_expected_count_of_an_empty_batch_is_an_integer_zero` | M016 (also M017, M018) |
| `test_expected_count_with_one_unknown_boundary_uses_present_count` | M015 |
| `test_duplicate_matches_preserve_import_order` | M061 |
| `test_source_without_amount_matches_zero_amount_import` | M057 |
| `test_verification_totals_keep_zero_and_round_to_cents` | M070 (also M071, M073, M074) |
| `test_difference_stays_rounded_to_cents_for_large_balances` | M051 |

Each named test passed against the original module and failed against its listed mutant in an isolated run. The final offline run passed all 22 verification tests.

## Survivors left

- **M063, equivalent:** removing `del remaining[key]` leaves an empty list in the candidate map. Later lookup still sees a false value, and flattening the map still emits no unmatched import. No report field changes.
- **Untestable offline:** none among generated mutants.
- **Defects found:** none.

## Verification limit

`python3 -m pytest -q -m "not performance"` could not collect the full suite: `tests/conftest.py` imports `config.py`, which requires the unavailable `platformdirs` package. No package was installed. The requested `python` executable is also absent locally; the offline verification tests ran with `python3`.
