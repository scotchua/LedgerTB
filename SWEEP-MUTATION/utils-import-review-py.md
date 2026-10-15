# Mutation results: `utils/import_review.py`

## Method

- Generated 52 single-change AST mutants, covering all four functions (cap: 150). Changes included comparison flips, boolean swaps, condition negation, numeric changes by one, return replacement, statement removal, and `+`/`-` swaps. No raise exists to drop. AST selection excluded comments and docstrings; this module has no logging statements.
- Each mutant was loaded from an in-memory copy through an import hook in a separate Python process. Each test run had an 8-second timeout. The source file was checked for byte identity after every mutant and matches `HEAD` SHA-256 `064c96bc1f34b7e551762d68d1b6d7bdb709996d15546d5431f15288d341a805`.
- Scoring used the offline relevant tests: `python3 -m pytest --noconftest -q tests/test_import_review.py -k "not parking"`. The parking-account test exercises `utils.ui`, outside this module, and the full test configuration requires unavailable dependencies.

## Kill rates

| Run | Killed | Total | Kill rate |
| --- | ---: | ---: | ---: |
| Existing tests | 45 | 52 | 86.54% |
| With new tests | 52 | 52 | 100% |

## Mutants generated

| ID | Function | Line | Change | Before | After |
| --- | --- | ---: | --- | --- | --- |
| M001 | `classify_review_rows` | 34 | statement: deleted | killed | killed |
| M002 | `classify_review_rows` | 42 | return: None | killed | killed |
| M003 | `classify_review_rows` | 42 | return: [] | killed | killed |
| M004 | `classify_review_rows` | 42 | return: False | killed | killed |
| M005 | `ensure_row_ids` | 54 | return: None | survived | killed |
| M006 | `ensure_row_ids` | 54 | return: [] | survived | killed |
| M007 | `ensure_row_ids` | 54 | return: False | survived | killed |
| M008 | `row_key` | 64 | return: None | killed | killed |
| M009 | `row_key` | 64 | return: [] | killed | killed |
| M010 | `row_key` | 64 | return: False | killed | killed |
| M011 | `scope_import_state_to_client` | 173 | statement: deleted | killed | killed |
| M012 | `scope_import_state_to_client` | 174 | statement: deleted | killed | killed |
| M013 | `scope_import_state_to_client` | 175 | statement: deleted | killed | killed |
| M014 | `scope_import_state_to_client` | 176 | condition: negated | killed | killed |
| M015 | `scope_import_state_to_client` | 179 | condition: negated | killed | killed |
| M016 | `scope_import_state_to_client` | 192 | statement: deleted | killed | killed |
| M017 | `scope_import_state_to_client` | 195 | statement: deleted | killed | killed |
| M018 | `scope_import_state_to_client` | 198 | statement: deleted | killed | killed |
| M019 | `scope_import_state_to_client` | 199 | statement: deleted | killed | killed |
| M020 | `scope_import_state_to_client` | 200 | statement: deleted | killed | killed |
| M021 | `scope_import_state_to_client` | 201 | return: None | killed | killed |
| M022 | `scope_import_state_to_client` | 201 | return: [] | killed | killed |
| M023 | `scope_import_state_to_client` | 201 | return: False | killed | killed |
| M024 | `classify_review_rows` | 36 | condition: negated | killed | killed |
| M025 | `ensure_row_ids` | 52 | condition: negated | killed | killed |
| M026 | `scope_import_state_to_client` | 177 | statement: deleted | killed | killed |
| M027 | `scope_import_state_to_client` | 178 | return: None | killed | killed |
| M028 | `scope_import_state_to_client` | 178 | return: [] | killed | killed |
| M029 | `scope_import_state_to_client` | 179 | comparison: != | killed | killed |
| M030 | `scope_import_state_to_client` | 180 | return: None | killed | killed |
| M031 | `scope_import_state_to_client` | 180 | return: [] | killed | killed |
| M032 | `scope_import_state_to_client` | 183 | condition: negated | killed | killed |
| M033 | `scope_import_state_to_client` | 193 | arithmetic: - | killed | killed |
| M034 | `scope_import_state_to_client` | 196 | arithmetic: - | killed | killed |
| M035 | `classify_review_rows` | 37 | statement: deleted | killed | killed |
| M036 | `classify_review_rows` | 38 | condition: negated | killed | killed |
| M037 | `ensure_row_ids` | 53 | statement: deleted | killed | killed |
| M038 | `scope_import_state_to_client` | 184 | boolean: and | killed | killed |
| M039 | `scope_import_state_to_client` | 187 | statement: deleted | killed | killed |
| M040 | `scope_import_state_to_client` | 193 | number: +1 (increment literal) | killed | killed |
| M041 | `scope_import_state_to_client` | 193 | number: -1 (increment literal) | killed | killed |
| M042 | `scope_import_state_to_client` | 196 | number: +1 (increment literal) | killed | killed |
| M043 | `scope_import_state_to_client` | 196 | number: -1 (increment literal) | killed | killed |
| M044 | `classify_review_rows` | 38 | comparison: != | killed | killed |
| M045 | `classify_review_rows` | 39 | statement: deleted | killed | killed |
| M046 | `classify_review_rows` | 41 | statement: deleted | killed | killed |
| M047 | `scope_import_state_to_client` | 193 | number: +1 (missing-key default literal) | survived | killed |
| M048 | `scope_import_state_to_client` | 193 | number: -1 (missing-key default literal) | survived | killed |
| M049 | `scope_import_state_to_client` | 196 | number: +1 (missing-key default literal) | survived | killed |
| M050 | `scope_import_state_to_client` | 196 | number: -1 (missing-key default literal) | survived | killed |
| M051 | `classify_review_rows` | 38 | number: +1 | killed | killed |
| M052 | `classify_review_rows` | 38 | number: -1 | killed | killed |

## New tests

- `test_ensure_row_ids_returns_input_list` kills M005–M007. It passes on the original and fails on each listed mutant.
- `test_client_switch_starts_missing_uploader_nonces_at_one` kills M047–M050. It passes on the original and fails on each listed mutant.

## Survivors left

None. Equivalent: 0; untestable offline: 0; defects: 0.

## Defects found

None.

## Verification

- Isolated original-module run: 16 passed, 1 deselected.
- Requested full-suite command with available interpreter, `python3 -m pytest -q -m "not performance"`, stopped while loading `tests/conftest.py`: `ModuleNotFoundError: No module named platformdirs`. No package was installed and no network was used.
- `git diff --exit-code -- utils/import_review.py` passed; all production files remain unchanged.
