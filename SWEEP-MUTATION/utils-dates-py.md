# Mutation probe: `utils/dates.py`

The probe generated 64 single-change AST mutants across all five functions. Each mutant was compiled and exercised in memory in a separate Python process with a 3-second timeout. The original module was never written; its SHA-256 was `93d38ac8f91b7218b28dc607c95069143deb512cb21feadc5bf3f015dbb402fe` before and after both passes.

The baseline exercised the three parameter cases in the existing `test_display_date_honors_preference` test from `tests/test_preferences.py`. The second pass also exercised the six tests in `tests/test_dates.py`. The relevant existing test function was extracted and run directly because normal pytest collection is blocked by the missing `platformdirs` dependency in this offline environment.

| Mutants | Function and change | Killed before | Killed after |
| --- | --- | ---: | ---: |
| M001–M004 | `long_date`: replace or remove return | 0/4 | 4/4 |
| M005–M008 | `short_date`: replace or remove return | 0/4 | 4/4 |
| M009–M012 | `slash_date`: replace or remove return | 0/4 | 4/4 |
| M013–M015 | `display_date`: remove import; negate or remove string check | 3/3 | 3/3 |
| M016–M019 | `display_date`: negate or remove format checks | 4/4 | 4/4 |
| M020–M023 | `display_date`: replace or remove default-format return | 4/4 | 4/4 |
| M024–M033 | `display_date`: flip format comparisons; replace or remove branch returns | 10/10 | 10/10 |
| M034–M037 | `display_date`: replace or remove invalid-ISO return | 0/4 | 4/4 |
| M038–M055 | `display_date`: decrease or increase day, month, or year format width by one | 12/18 | 18/18 |
| M056–M059 | `long_datetime`: replace or remove return | 0/4 | 4/4 |
| M060 | `long_datetime`: swap `or` to `and` | 0/1 | 1/1 |
| M061–M064 | `long_datetime`: change each `12` by one | 0/4 | 4/4 |
| **Total** | **Kill rate** | **33/64 (51.6%)** | **64/64 (100%)** |

Statement removals leave `pass` where Python requires a nonempty block. The file has no `+` or `-` expression, exception raise, or other comparison or Boolean operator eligible for the requested operators. Comments, logging, and docstrings were excluded.

## New tests and baseline survivors killed

| Test | Baseline survivors killed |
| --- | --- |
| `test_long_date_uses_full_month_and_unpadded_day` | M001–M004 |
| `test_short_date_uses_abbreviated_month_and_unpadded_day` | M005–M008 |
| `test_slash_date_uses_unpadded_month_and_day` | M009–M012 |
| `test_display_date_preserves_invalid_iso_text` | M034–M037 |
| `test_display_date_pads_single_digits_and_early_years` | M040, M042, M044, M048, M050, M054 |
| `test_long_datetime_handles_midnight_noon_and_afternoon` | M056–M064 |

## Survivors left

None. Equivalent mutants: none. Untestable offline mutants: none. Defects found: none. No expected failures were added.

## Verification

`python3 -m pytest --noconftest -q tests/test_dates.py`: 6 passed. The in-memory mutation pass killed all 64 mutants after adding the tests. `python3 -m pytest -q -m "not performance"` stopped during collection because `config.py` imports `platformdirs`, which is not installed. No packages were installed.
