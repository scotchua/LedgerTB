# Mutation check: `database/seed_data.py`

## Method

Read the full module and the existing direct seed test in `tests/test_account_subtypes.py`. The existing `test_every_new_seed_chart_uses_curated_subtypes` was executed from its unchanged AST against each in-memory mutant. The other existing tests use the application database fixture and cannot run in this offline environment because required packages are absent. New tests use invented chart templates and in-memory SQLite. Each mutant ran in a separate subprocess with a five-second timeout. The runner never wrote to the production module and verified its SHA-256 remained `ce36737daa34c2ebf1f6d3f7382ea20df5a15db7a3fb90789a49797ff1bf8216`.

The 31 generated mutants cover all four functions. Mutations touched executable statements only: condition negation, comparison changes, `0` to `1`, return replacement, and single-statement removal. There are no `and`/`or`, arithmetic `+`/`-`, or exception raises in these function bodies to mutate. The no-op deprecated function has one equivalent return mutation. No comments, logging, docstrings, or static chart data were mutated.

## Results

| Stage | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Existing direct seed test | 3 | 31 | 9.7% |
| Existing direct seed test plus new tests | 29 | 31 | 93.5% |

All 29 behavior-changing mutants were killed after the new tests. No mutant timed out.

| ID | Function | Mutation | Before | After |
| ---: | --- | --- | --- | --- |
| 1 | `get_accounts_for_client` | negate entity match | survived | killed |
| 2 | `get_accounts_for_client` | drop entity accounts | survived | killed |
| 3 | `get_accounts_for_client` | drop entity fallback | survived | killed |
| 4 | `get_accounts_for_client` | negate entity-specific match | survived | killed |
| 5 | `get_accounts_for_client` | drop entity-specific accounts | survived | killed |
| 6 | `get_accounts_for_client` | negate business match | survived | killed |
| 7 | `get_accounts_for_client` | drop business accounts | survived | killed |
| 8 | `get_accounts_for_client` | drop business fallback | survived | killed |
| 9 | `get_accounts_for_client` | negate first-occurrence check | survived | killed |
| 10 | `get_accounts_for_client` | drop seen-set addition | survived | killed |
| 11 | `get_accounts_for_client` | drop unique-list append | survived | killed |
| 12 | `get_accounts_for_client` | drop subtype normalization | killed | killed |
| 13 | `get_accounts_for_client` | drop sorting | survived | killed |
| 14 | `get_accounts_for_client` | return `None` | killed | killed |
| 15 | `get_accounts_for_client` | return empty list | survived | killed |
| 16 | `get_accounts_for_client` | return `False` | killed | killed |
| 17 | `get_accounts_for_entity_type` | return `None` | survived | killed |
| 18 | `get_accounts_for_entity_type` | return empty list | survived | killed |
| 19 | `get_accounts_for_entity_type` | return `False` | survived | killed |
| 20 | `get_accounts_for_entity_type` | choose `Other` business | survived | killed |
| 21 | `seed_chart_of_accounts` | replace `pass` with `return None` | survived | survived: equivalent |
| 22 | `seed_chart_of_accounts_for_client` | `==` to `!=` | survived | killed |
| 23 | `seed_chart_of_accounts_for_client` | `==` to `<` | survived | killed |
| 24 | `seed_chart_of_accounts_for_client` | `==` to `<=` | survived | survived: equivalent |
| 25 | `seed_chart_of_accounts_for_client` | `==` to `>` | survived | killed |
| 26 | `seed_chart_of_accounts_for_client` | `==` to `>=` | survived | killed |
| 27 | `seed_chart_of_accounts_for_client` | `0` to `1` | survived | killed |
| 28 | `seed_chart_of_accounts_for_client` | negate zero condition | survived | killed |
| 29 | `seed_chart_of_accounts_for_client` | drop count query | survived | killed |
| 30 | `seed_chart_of_accounts_for_client` | drop data construction | survived | killed |
| 31 | `seed_chart_of_accounts_for_client` | drop insert | survived | killed |

## New tests

| Test | Previously surviving mutant it kills |
| --- | ---: |
| `test_get_accounts_for_client_selects_entity_and_fallback` | 1 |
| `test_get_accounts_for_client_selects_business_and_fallback` | 6 |
| `test_get_accounts_for_client_deduplicates_by_number_and_sorts` | 10 |
| `test_get_accounts_for_entity_type_uses_professional_services` | 20 |
| `test_seed_chart_of_accounts_for_client_inserts_only_for_new_client` | 22 |
| `test_seed_chart_of_accounts_for_client_leaves_transaction_to_caller` | 31 |

Each listed test passed on the original and failed on its listed mutant in an isolated subprocess. `python3 -m pytest -q --noconftest tests/test_seed_data_mutations.py` passed all six tests.

## Survivors left

- **21, equivalent:** A `pass` function and a `return None` function have the same result and side effects.
- **24, equivalent:** SQLite `COUNT(*)` is nonnegative, so `count <= 0` and `count == 0` select the same rows.

## Defects found

None in the sampled mutations.

## Verification limit

The requested full pytest command cannot collect in this environment: `python` is absent, and `python3 -m pytest` stops while importing `tests/conftest.py` because `platformdirs` is not installed. The environment also lacks `sqlcipher3` and `streamlit`. No packages were installed or network calls made.
