# Mutation test: `utils/statement_format.py`

The 30 mutants each changed one executable expression or statement in `statement_amount`. Each mutant ran in a temporary module loaded as `utils.statement_format`; the repository source was never replaced. Runs had a 15-second timeout. The original module's SHA-256 was `f499761be166a6c51004b527f0549d574e039cffa66a114c3088e7b227de35f4` before and after the runs.

The before run used exact copies of the existing `test_amount_formatting` and `test_percent_formatting_has_no_dash_rule` tests from `tests/test_statement_presentation.py`. The after run added `tests/test_statement_format_mutation.py`. Pytest ran these without the repository's `conftest.py` because normal collection stops at a missing `platformdirs` dependency. No network or API access was used.

| Phase | Killed | Generated | Kill rate | Behavior-changing mutants killed |
| --- | ---: | ---: | ---: | ---: |
| Before | 22 | 30 | 73.3% | 22/26 (84.6%) |
| After | 26 | 30 | 86.7% | 26/26 (100%) |

| Mutant | Change | Before | After |
| --- | --- | --- | --- |
| M01 | Negate `None` guard | killed | killed |
| M02 | Change percent `==` to `!=` | killed | killed |
| M03 | Change percent `< 0` to `<= 0` | killed | killed |
| M04 | Change percent `< 0` to `< -1` | survived | killed |
| M05 | Change percent `< 0` to `>= 0` | killed | killed |
| M06 | Change zero `==` to `!=` | killed | killed |
| M07 | Change zero `==` to `<` | killed | killed |
| M08 | Change zero constant from `0` to `1` | killed | killed |
| M09 | Replace blank return with `None` | killed | killed |
| M10 | Replace blank return with `False` | killed | killed |
| M11 | Replace dash return with blank | killed | killed |
| M12 | Replace dash return with `None` | killed | killed |
| M13 | Remove percent thousands grouping | survived | killed |
| M14 | Increase percent decimal places | killed | killed |
| M15 | Remove percent negative choice | killed | killed |
| M16 | Replace percent return with `None` | killed | killed |
| M17 | Remove money thousands grouping | killed | killed |
| M18 | Change money `< 0` to `<= 0` | survived | survived |
| M19 | Change money `< 0` to `< -1` | survived | killed |
| M20 | Change money `< 0` to `> 0` | killed | killed |
| M21 | Remove money parentheses assignment | killed | killed |
| M22 | Remove lead dollar choice | killed | killed |
| M23 | Replace final return with `None` | killed | killed |
| M24 | Negate lead dollar condition | killed | killed |
| M25 | Change zero literal from `0` to `0.0` | survived | survived |
| M26 | Change `is None` to `== None` | survived | survived |
| M27 | Require literal `True` for lead dollar | survived | survived |
| M28 | Change money `< 0` to `< 1` | survived | killed |
| M29 | Change percent `< 0` to `< 1` | killed | killed |
| M30 | Remove `abs` from money formatting | killed | killed |

The executable function contains no `and`/`or`, arithmetic `+`/`-`, or exception raise to mutate. Docstrings and comments were excluded. The operators, constants, returns, condition, formatting expression, and assignment present in the function were sampled; 30 is below the 150-mutant cap.

## New tests

- `test_statement_amount_parenthesizes_fractional_negative_values`: kills M04 and M19.
- `test_statement_amount_keeps_positive_fraction_unparenthesized`: kills M28.
- `test_statement_amount_groups_large_percent_values`: kills M13.

Each new test passed against the original module and failed individually against its listed mutant. The three tests also passed with `python3 -m pytest -q --noconftest tests/test_statement_format_mutation.py`.

## Survivors left

- M18 is equivalent for numeric values: exact zero returns at the preceding guard, so `<= 0` reaches no extra value here.
- M25 is equivalent for numeric values: `0` and `0.0` compare equal.
- M26 is equivalent for the supported numeric-or-`None` inputs. Custom objects with overloaded equality are outside this formatting contract.
- M27 is equivalent for the annotated Boolean `lead_dollar` argument. Non-Boolean truthy values are outside that contract.

## Defects found

None. No expected-failure tests were needed.

## Verification limit

`python3 -m pytest -q -m "not performance"` stopped during `tests/conftest.py` import with `ModuleNotFoundError: No module named 'platformdirs'`. The requested `python` executable is unavailable in this environment; `python3` was used. The full suite was therefore not verified here.
