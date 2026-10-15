# Mutation sweep: `services/duplicate_detection.py`

## Scope and method

The service has one function, `propose_duplicates`. A temporary runner made one textual change per mutant in a temporary source file and loaded it with an injected `database.connection` module. The production file was never written. Each process had a five-second timeout. Mutations targeted executable Python and the SQL query, excluding comments and the module docstring. The source SHA-256 before and after was `3e651b2e9f081b0787c1fae4c6bf358448d4eda369c3c76f258744693a9c90d6`; its Git blob matched `HEAD` (`6374b7acc151bceef7c014f11e88421b0c8a9419`).

The installed Python lacks `platformdirs`, so pytest cannot load `tests/conftest.py`. For the **before** measurement, the runner extracted and executed the original `test_duplicate_parameters_rejected` body and its five parameter cases from `tests/test_counterparty_duplicates.py`, using the same isolated module loader. The other existing integration tests could not run in this environment. The **after** measurement ran all eight new tests in `tests/test_duplicate_detection_mutations.py` against each mutant. Thus the before rate describes the executable existing-test slice, not the unavailable full test suite.

| Measurement | Killed | Generated | Kill rate |
| --- | ---: | ---: | ---: |
| Before: existing parameter test, five cases | 2 | 41 | 4.9% |
| After: eight new offline tests | 41 | 41 | 100% |

No mutant timed out. The two before kills were M02 and M07. All 39 before survivors were killed by the new tests. No equivalent mutants, untestable mutants, or survivors remain in this sample.

## Mutants generated

| IDs | Single changes | Before | After |
| --- | --- | --- | --- |
| M01–M09 | Type/boolean validation, inclusive bounds, numeric maxima, dropped validation/client raises, negated client check | M02, M07 killed; seven survived | All killed |
| M10–M14 | Reversed source check, `or`/`and` changes, source equality, removed source skip | Survived | All killed |
| M15–M17 | Reference `and`/`or`, equality, removed reference skip | Survived | All killed |
| M18–M24 | Proposal key condition, removed line append, empty proposals, `None` metadata/status/name/note | Survived | All killed |
| M25–M33 | SQL entry ordering, date comparison, account/sign/client comparisons, four reversal checks | Survived | All killed |
| M34–M36 | Signed amount `-` to `+`, amount range `-` to `+`, removed connection close | Survived | All killed |
| M37–M41 | Entire return to `False`/`None`, default numeric constants, SQL `AND` to `OR` | Survived | All killed |

## New tests and mutant witnesses

All use invented names, accounts, amounts, and dates in a temporary SQLite database. Each passed on the original and failed on at least one recorded mutant.

| Test name (in `tests/test_duplicate_detection_mutations.py`) | Witness mutants |
| --- | --- |
| `test_propose_duplicates_rejects_invalid_bounds_and_missing_client` | M01–M09 |
| `test_propose_duplicates_returns_complete_grouped_proposal` | M19–M24, M37–M40 |
| `test_propose_duplicates_excludes_distinct_sources_and_reversed_entries` | M10–M14 |
| `test_propose_duplicates_filters_references_after_trimming` | M15–M17 |
| `test_propose_duplicates_observes_amount_and_date_boundaries` | M26, M35 |
| `test_propose_duplicates_observes_account_sign_client_and_reversal` | M25, M27, M28 |
| `test_propose_duplicates_reports_signed_credit_amounts` | M34 |
| `test_propose_duplicates_closes_connection_on_success_and_error` | M36 |

## Verification and limitations

`python3 -m pytest -q --noconftest tests/test_duplicate_detection_mutations.py`: 8 passed. The same tests passed with `python3 tests/test_duplicate_detection_mutations.py -q`. The requested full command, using the available `python3` executable, stopped during conftest import with `ModuleNotFoundError: No module named 'platformdirs'`; it did not reach test collection. No packages were installed and no network or external API was used. The before kill rate cannot be generalized to the full existing suite.

## Defects found

None in the 41 sampled mutations. No expected failures were added.
