# Mutation test: `utils/report_dates.py`

## Method and result

- Generated 115 distinct, compilable single-edit mutants (70 in `period_for_preset`, 45 in `as_of_for_preset`), below the 150-mutant cap. The edits included comparison flips, condition negation, numeric changes by one, return replacement, statement removal, and arithmetic swaps. The module has no boolean `and`/`or` expressions or exception raises to mutate. Comments, logging, and docstrings were excluded.
- The temporary runner compiled each mutant into a fresh in-memory `utils.report_dates` module and ran the existing `test_report_date_presets_cover_fiscal_and_calendar_periods` function body in a separate process, with a 30-second timeout. It repeated the run with the six new tests. The original function body passed before both sweeps; no mutant timed out.
- **Before:** 61/115 killed (53.0%); 54/115 survived.
- **After:** 113/115 killed (98.3%); 2/115 survived. Excluding the two equivalent mutants, the behavioral kill rate is 113/113 (100%).
- `utils/report_dates.py` remained untouched throughout; all mutant source existed only in memory or temporary runner output.

## New tests

Each test passed on the original and failed on the listed mutant from the first sweep. Tests are in `tests/test_report_dates.py`.

| Function | Test | Example mutant killed |
| --- | --- | ---: |
| `period_for_preset` | `test_period_for_preset_this_calendar_year_starts_on_january_first` | 18 |
| `period_for_preset` | `test_period_for_preset_rolling_windows_span_leap_day` | 26 |
| `period_for_preset` | `test_period_for_preset_custom_has_no_calculated_range` | 7 |
| `as_of_for_preset` | `test_as_of_for_preset_today_uses_supplied_date` | 78 |
| `as_of_for_preset` | `test_as_of_for_preset_last_calendar_year_ends_on_december_thirty_first` | 90 |
| `as_of_for_preset` | `test_as_of_for_preset_custom_has_no_calculated_date` | 75 |

## Survivors left

- **63, equivalent:** removing the final `return None` in `period_for_preset` leaves the same implicit `None` return for unmatched presets.
- **111, equivalent:** removing the final `return None` in `as_of_for_preset` leaves the same implicit `None` return for unmatched presets.
- Untestable offline: none of the surviving behavioral mutants. Defects found: none.

## Verification limit

- The six new tests passed under isolated pytest (`6 passed`) with the repository on `PYTHONPATH` and no repository `conftest.py`.
- The requested full suite, `python3 -m pytest -q -m "not performance"`, could not collect: this interpreter lacks `platformdirs`, imported by `config.py` through `tests/conftest.py`. The `python` executable is also unavailable. No packages were installed and no network was used.

## Mutant ledger

| ID | Function | Source line | Edit | Before | After |
| ---: | --- | ---: | --- | --- | --- |
| 1 | `period_for_preset` | 30 | negate condition | killed | killed |
| 2 | `period_for_preset` | 33 | negate condition | killed | killed |
| 3 | `period_for_preset` | 35 | negate condition | killed | killed |
| 4 | `period_for_preset` | 37 | negate condition | killed | killed |
| 5 | `period_for_preset` | 39 | negate condition | survived | killed |
| 6 | `period_for_preset` | 41 | negate condition | survived | killed |
| 7 | `period_for_preset` | 43 | return False | survived | killed |
| 8 | `period_for_preset` | 43 | return empty | survived | killed |
| 9 | `period_for_preset` | 30 | flip comparison | killed | killed |
| 10 | `period_for_preset` | 32 | return None | killed | killed |
| 11 | `period_for_preset` | 32 | return False | killed | killed |
| 12 | `period_for_preset` | 32 | return empty | killed | killed |
| 13 | `period_for_preset` | 33 | flip comparison | killed | killed |
| 14 | `period_for_preset` | 34 | return None | killed | killed |
| 15 | `period_for_preset` | 34 | return False | killed | killed |
| 16 | `period_for_preset` | 34 | return empty | killed | killed |
| 17 | `period_for_preset` | 35 | flip comparison | killed | killed |
| 18 | `period_for_preset` | 36 | return None | survived | killed |
| 19 | `period_for_preset` | 36 | return False | survived | killed |
| 20 | `period_for_preset` | 36 | return empty | survived | killed |
| 21 | `period_for_preset` | 37 | flip comparison | killed | killed |
| 22 | `period_for_preset` | 38 | return None | killed | killed |
| 23 | `period_for_preset` | 38 | return False | killed | killed |
| 24 | `period_for_preset` | 38 | return empty | killed | killed |
| 25 | `period_for_preset` | 39 | flip comparison | survived | killed |
| 26 | `period_for_preset` | 40 | return None | survived | killed |
| 27 | `period_for_preset` | 40 | return False | survived | killed |
| 28 | `period_for_preset` | 40 | return empty | survived | killed |
| 29 | `period_for_preset` | 41 | flip comparison | survived | killed |
| 30 | `period_for_preset` | 42 | return None | survived | killed |
| 31 | `period_for_preset` | 42 | return False | survived | killed |
| 32 | `period_for_preset` | 42 | return empty | survived | killed |
| 33 | `period_for_preset` | 40 | swap +/- | survived | killed |
| 34 | `period_for_preset` | 42 | swap +/- | survived | killed |
| 35 | `period_for_preset` | 36 | integer -1 | survived | killed |
| 36 | `period_for_preset` | 36 | integer +1 | survived | killed |
| 37 | `period_for_preset` | 36 | integer -1 | survived | killed |
| 38 | `period_for_preset` | 36 | integer +1 | survived | killed |
| 39 | `period_for_preset` | 38 | swap +/- | killed | killed |
| 40 | `period_for_preset` | 38 | integer -1 | killed | killed |
| 41 | `period_for_preset` | 38 | integer +1 | killed | killed |
| 42 | `period_for_preset` | 38 | integer -1 | killed | killed |
| 43 | `period_for_preset` | 38 | integer +1 | killed | killed |
| 44 | `period_for_preset` | 38 | swap +/- | killed | killed |
| 45 | `period_for_preset` | 38 | integer -1 | killed | killed |
| 46 | `period_for_preset` | 38 | integer +1 | killed | killed |
| 47 | `period_for_preset` | 38 | integer -1 | killed | killed |
| 48 | `period_for_preset` | 38 | integer +1 | killed | killed |
| 49 | `period_for_preset` | 38 | integer -1 | killed | killed |
| 50 | `period_for_preset` | 38 | integer +1 | killed | killed |
| 51 | `period_for_preset` | 38 | integer -1 | killed | killed |
| 52 | `period_for_preset` | 38 | integer +1 | killed | killed |
| 53 | `period_for_preset` | 40 | integer -1 | survived | killed |
| 54 | `period_for_preset` | 40 | integer +1 | survived | killed |
| 55 | `period_for_preset` | 42 | integer -1 | survived | killed |
| 56 | `period_for_preset` | 42 | integer +1 | survived | killed |
| 57 | `period_for_preset` | 30 | remove statement | killed | killed |
| 58 | `period_for_preset` | 33 | remove statement | killed | killed |
| 59 | `period_for_preset` | 35 | remove statement | survived | killed |
| 60 | `period_for_preset` | 37 | remove statement | killed | killed |
| 61 | `period_for_preset` | 39 | remove statement | survived | killed |
| 62 | `period_for_preset` | 41 | remove statement | survived | killed |
| 63 | `period_for_preset` | 43 | remove statement | survived | survived |
| 64 | `period_for_preset` | 31 | remove statement | killed | killed |
| 65 | `period_for_preset` | 32 | remove statement | killed | killed |
| 66 | `period_for_preset` | 34 | remove statement | killed | killed |
| 67 | `period_for_preset` | 36 | remove statement | survived | killed |
| 68 | `period_for_preset` | 38 | remove statement | killed | killed |
| 69 | `period_for_preset` | 40 | remove statement | survived | killed |
| 70 | `period_for_preset` | 42 | remove statement | survived | killed |
| 71 | `as_of_for_preset` | 48 | negate condition | killed | killed |
| 72 | `as_of_for_preset` | 50 | negate condition | killed | killed |
| 73 | `as_of_for_preset` | 52 | negate condition | killed | killed |
| 74 | `as_of_for_preset` | 54 | negate condition | survived | killed |
| 75 | `as_of_for_preset` | 56 | return False | survived | killed |
| 76 | `as_of_for_preset` | 56 | return empty | survived | killed |
| 77 | `as_of_for_preset` | 48 | flip comparison | killed | killed |
| 78 | `as_of_for_preset` | 49 | return None | survived | killed |
| 79 | `as_of_for_preset` | 49 | return False | survived | killed |
| 80 | `as_of_for_preset` | 49 | return empty | survived | killed |
| 81 | `as_of_for_preset` | 50 | flip comparison | killed | killed |
| 82 | `as_of_for_preset` | 51 | return None | killed | killed |
| 83 | `as_of_for_preset` | 51 | return False | killed | killed |
| 84 | `as_of_for_preset` | 51 | return empty | killed | killed |
| 85 | `as_of_for_preset` | 52 | flip comparison | killed | killed |
| 86 | `as_of_for_preset` | 53 | return None | killed | killed |
| 87 | `as_of_for_preset` | 53 | return False | killed | killed |
| 88 | `as_of_for_preset` | 53 | return empty | killed | killed |
| 89 | `as_of_for_preset` | 54 | flip comparison | survived | killed |
| 90 | `as_of_for_preset` | 55 | return None | survived | killed |
| 91 | `as_of_for_preset` | 55 | return False | survived | killed |
| 92 | `as_of_for_preset` | 55 | return empty | survived | killed |
| 93 | `as_of_for_preset` | 51 | swap +/- | killed | killed |
| 94 | `as_of_for_preset` | 53 | integer -1 | killed | killed |
| 95 | `as_of_for_preset` | 53 | integer +1 | killed | killed |
| 96 | `as_of_for_preset` | 55 | swap +/- | survived | killed |
| 97 | `as_of_for_preset` | 55 | integer -1 | survived | killed |
| 98 | `as_of_for_preset` | 55 | integer +1 | survived | killed |
| 99 | `as_of_for_preset` | 55 | integer -1 | survived | killed |
| 100 | `as_of_for_preset` | 55 | integer +1 | survived | killed |
| 101 | `as_of_for_preset` | 55 | integer -1 | survived | killed |
| 102 | `as_of_for_preset` | 55 | integer +1 | survived | killed |
| 103 | `as_of_for_preset` | 51 | integer -1 | killed | killed |
| 104 | `as_of_for_preset` | 51 | integer +1 | killed | killed |
| 105 | `as_of_for_preset` | 51 | integer -1 | killed | killed |
| 106 | `as_of_for_preset` | 51 | integer +1 | killed | killed |
| 107 | `as_of_for_preset` | 48 | remove statement | survived | killed |
| 108 | `as_of_for_preset` | 50 | remove statement | killed | killed |
| 109 | `as_of_for_preset` | 52 | remove statement | killed | killed |
| 110 | `as_of_for_preset` | 54 | remove statement | survived | killed |
| 111 | `as_of_for_preset` | 56 | remove statement | survived | survived |
| 112 | `as_of_for_preset` | 49 | remove statement | survived | killed |
| 113 | `as_of_for_preset` | 51 | remove statement | killed | killed |
| 114 | `as_of_for_preset` | 53 | remove statement | killed | killed |
| 115 | `as_of_for_preset` | 55 | remove statement | survived | killed |
