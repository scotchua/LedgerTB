# Payroll parser mutation sweep

The sweep compiled each mutant in memory as `services.payroll_parsers`; it never wrote the production module. Each subprocess had a 15-second limit. Mutations changed executable code only, one site at a time. The 33 selected mutants covered every function and method in `services/payroll_parsers.py`, with comparison flips, `and`/`or` swaps, condition negation, a numeric constant change, return replacement, statement removal, sign swap, and a dropped raise.

## Results

| Test set | Killed | Survivors | Kill rate |
| --- | ---: | ---: | ---: |
| Before: seven existing offline parser cases | 23/33 | 10 | 69.7% |
| After: existing cases plus seven new cases | 31/33 | 2 | 93.9% |

The existing cases were copied from `tests/test_payroll_parser_oracle.py` into an isolated pytest module so its database-dependent `conftest.py` would not import unavailable packages. This baseline does not include the oracle tests that stage rows or assert database atomicity. The after run passed all 14 cases on the original module. Every new case failed on at least one mutant and passed on the original.

## Mutants

| ID | Change | Before | After |
| --- | --- | --- | --- |
| M01 | `ParsedBatch.__getitem__` returns `None` | Survived | Killed |
| M02 | `ParserRefusal` discards unknown headers | Survived | Killed |
| M03 | Header BOM condition `and` to `or` | Killed | Killed |
| M04 | Provider alias equality flipped | Killed | Killed |
| M05 | Header map canonical values replaced with `None` | Killed | Killed |
| M06 | PII header set replaced with empty set | Killed | Killed |
| M07 | Empty-content condition negated | Killed | Killed |
| M08 | NUL-byte exception raise dropped | Survived | Killed |
| M09 | Provider match-count equality flipped | Killed | Killed |
| M10 | Parenthesis detection `or` to `and` | Survived | Survived: equivalent |
| M11 | Trailing-minus condition negated | Killed | Killed |
| M12 | Money multiplier 100 to 101 | Killed | Killed |
| M13 | Negative money sign changed to positive | Killed | Killed |
| M14 | Decimal-point count `>` to `>=` | Killed | Killed |
| M15 | Month ambiguity boundary `<=` to `<` | Survived | Killed |
| M16 | Day ambiguity boundary `<=` to `<` | Survived | Killed |
| M17 | Invalid-date condition negated | Killed | Killed |
| M18 | Canonical-item guard `and` to `or` | Survived | Survived: equivalent |
| M19 | Sum fallback 0 to 1 | Killed | Killed |
| M20 | Trailing-empty-record removal dropped | Survived | Killed |
| M21 | Header-only record-count equality flipped | Killed | Killed |
| M22 | Duplicate-header condition negated | Killed | Killed |
| M23 | Unknown-header condition negated | Killed | Killed |
| M24 | Missing-header condition negated | Killed | Killed |
| M25 | Row-length equality flipped | Killed | Killed |
| M26 | Present-date condition negated | Killed | Killed |
| M27 | Row-type validity condition negated | Killed | Killed |
| M28 | Period-end comparison `<` to `<=` | Survived | Killed |
| M29 | Pay-date comparison `<` to `<=` | Survived | Killed |
| M30 | Grand-total comparison `!=` to `==` | Killed | Killed |
| M31 | Department-total comparison `!=` to `==` | Killed | Killed |
| M33 | Gusto wrapper returns `None` | Killed | Killed |
| M34 | QuickBooks wrapper returns `None` | Killed | Killed |

M10 is equivalent for accepted and refused money strings: a lone parenthesis is still rejected by the later character validation, and a matched pair enters the same branch. M18 is equivalent through parser entry points: `present` is made from seen headers, and `values` has no non-`None` amount for an unseen field.

## New tests

All are in `tests/test_payroll_parser_mutations.py` and use invented names, amounts, and dates.

| Test | Mutant killed |
| --- | --- |
| `test_parsed_batch_getitem_returns_named_value` | M01 |
| `test_parser_refusal_preserves_unknown_headers` | M02 |
| `test_read_records_refuses_nul_byte` | M08 |
| `test_date_refuses_ambiguous_month_day[12/12/2026]` | M15, M16 |
| `test_date_refuses_ambiguous_month_day[01/12/2026]` | M16 |
| `test_parse_ignores_trailing_empty_records` | M20 |
| `test_parse_accepts_equal_period_end_and_pay_date` | M28, M29 |

## Defects found

None among the selected mutants.

## Verification limits

The requested `python -m pytest -q -m "not performance"` could not start because `python` is absent. With `python3`, pytest stopped while importing `tests/conftest.py` because `platformdirs` is not installed. No package was installed or network call made. The isolated parser sweep passed on the original; the full suite remains unverified in this environment. The production source was byte-identical before and after every mutation run.
