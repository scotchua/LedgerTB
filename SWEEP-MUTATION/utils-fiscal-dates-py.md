# Mutation check: `utils/fiscal_dates.py`

## Scope and method

The temporary runner generated 79 single-change AST mutants from all six functions, below the 150-mutant cap. It changed only in-memory copies written to a temporary directory; the source file was never overwritten. Each mutant ran in a fresh subprocess with a five-second limit. The baseline was the two direct date-helper tests in `tests/test_fiscal_dates.py`; the later pass also ran the five new tests in `tests/test_fiscal_dates_mutation.py`. These test functions were extracted from their source and called directly because the repository's `tests/conftest.py` cannot import without the unavailable `platformdirs` package. Database-backed integration tests were therefore outside this offline mutation run.

Mutations targeted comparisons (3), `and`/`or` (1), negated conditions (4), integer constants changed by one (32), returns replaced with `None`, `False`, or empty tuple (18), single statements removed (12), `+`/`-` swaps (7), and dropped raises (2). Docstrings were excluded; the module has no logging or comments containing executable statements.

| Function | Generated | Killed before | Killed after |
| --- | ---: | ---: | ---: |
| `fiscal_year_bounds` | 42 | 34 | 42 |
| `fiscal_year_ending_year` | 5 | 5 | 5 |
| `previous_fiscal_year_bounds` | 8 | 7 | 7 |
| `prior_year_date` | 15 | 15 | 15 |
| `prior_year_period` | 4 | 3 | 4 |
| `require_valid_range` | 5 | 2 | 5 |
| **Total** | **79** | **66 (83.5%)** | **78 (98.7%)** |

The behavior-changing mutation kill rate after the additions is 78/78 (100%). The source SHA-256 before and after was `4d4f48476aa21baef748e7d033248787ef7345a36e7bec5cd9249b034e74961a`.

## Surviving mutants from the first pass

| Mutant IDs | Change | New test that kills it |
| --- | --- | --- |
| 7, 45, 60, 61, 63 | Remove or weaken month validation, or reject valid January | `test_fiscal_year_bounds_rejects_months_outside_calendar` |
| 77, 78, 79 | Use the wrong year when finding February's end in the next fiscal year | `test_fiscal_year_bounds_uses_next_year_for_leap_day` |
| 5 | Remove period validation | `test_prior_year_period_rejects_inverted_dates` |
| 12, 24 | Remove range validation or its raise | `test_require_valid_range_rejects_inverted_dates_with_label` |
| 29 | Reject an inclusive single-day range | `test_require_valid_range_accepts_single_day` |

Each new test passed on the original module and was separately observed to fail on at least one listed mutant: respectively 7, 77, 5, 12, and 29.

## Survivors left

Mutant 37 changes `current_start.toordinal() - 1` to `- 2` in `previous_fiscal_year_bounds`. Both dates fall in the same preceding fiscal year for every representable fiscal-year start, so the returned bounds are identical. At the earliest representable boundary both versions raise. It is equivalent and needs no test. There are no untestable-offline behavior-changing survivors.

## Defects found

None.

## Verification limit

`python3 -m pytest -q --noconftest tests/test_fiscal_dates_mutation.py` passed all five new tests. The requested full suite, `python3 -m pytest -q -m "not performance"`, stopped while importing `tests/conftest.py` because `platformdirs` is not installed. The `python` command is unavailable here, so `python3` was used. No packages were installed and no network was used.
