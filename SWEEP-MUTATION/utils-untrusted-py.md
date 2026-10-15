# `utils/untrusted.py` mutation sweep

## Method and result

The throwaway runner parsed `utils/untrusted.py`, made one AST change per mutant, and loaded each changed module from a temporary file in a fresh Python process. It never wrote to the production module. Each test run had a 15-second timeout. The original module's SHA-256 was `1874a52793f524bf8ec2e1bf7786b30d74a0f22df95998f790ef7691d6e28766` before and after the sweep.

The existing baseline was the standalone `test_client_text_cannot_forge_prompt_structure` function from `tests/test_book_review.py`, extracted into a temporary test file so it could run without the repository's unavailable dependencies. The same baseline plus `tests/test_untrusted.py` was used for the after sweep. Both baselines passed on the original module. The normal repository pytest setup could not collect tests because `platformdirs` is absent; see Verification below.

| Stage | Generated | Killed | Survived | Kill rate |
| --- | ---: | ---: | ---: | ---: |
| Existing standalone test | 33 | 20 | 13 | 60.6% |
| Existing standalone test and new tests | 33 | 33 | 0 | 100% |

Mutants cover `flatten_untrusted`, `defang_markdown`, and `untrusted_block`, plus the module-level length limit used by `flatten_untrusted`. The applicable operators were comparison flip, condition negation, numeric constant increment, return replacement, statement removal, and `+` to `-`. There are no executable `and`/`or` expressions or exception raises in this module, so those operators generated no mutants. Comments and docstrings were excluded.

## Mutants generated

| ID | Function | Line | Mutation | Before | After |
| --- | --- | ---: | --- | --- | --- |
| M001 | `flatten_untrusted` default | 23 | numeric constant +1 | survived | killed |
| M002 | `flatten_untrusted` | 37 | negate condition | killed | killed |
| M003 | `flatten_untrusted` | 40 | negate condition | killed | killed |
| M004 | `flatten_untrusted` | 42 | return None | killed | killed |
| M005 | `flatten_untrusted` | 42 | return empty | killed | killed |
| M006 | `flatten_untrusted` | 42 | return False | killed | killed |
| M007 | `defang_markdown` | 55 | negate condition | survived | killed |
| M008 | `defang_markdown` | 60 | return None | survived | killed |
| M009 | `defang_markdown` | 60 | return empty | survived | killed |
| M010 | `defang_markdown` | 60 | return False | survived | killed |
| M011 | `untrusted_block` | 78 | return None | killed | killed |
| M012 | `untrusted_block` | 78 | return empty | killed | killed |
| M013 | `untrusted_block` | 78 | return False | killed | killed |
| M014 | `flatten_untrusted` | 38 | return None | killed | killed |
| M015 | `flatten_untrusted` | 38 | return False | killed | killed |
| M016 | `flatten_untrusted` | 40 | flip comparison | killed | killed |
| M017 | `defang_markdown` | 56 | return None | survived | killed |
| M018 | `defang_markdown` | 56 | return False | survived | killed |
| M019 | `flatten_untrusted` | 41 | swap + and - | killed | killed |
| M020 | `flatten_untrusted` | 37 | remove statement | killed | killed |
| M021 | `flatten_untrusted` | 39 | remove statement | killed | killed |
| M022 | `flatten_untrusted` | 40 | remove statement | killed | killed |
| M023 | `flatten_untrusted` | 42 | remove statement | killed | killed |
| M024 | `flatten_untrusted` | 38 | remove statement | killed | killed |
| M025 | `flatten_untrusted` | 41 | remove statement | killed | killed |
| M026 | `defang_markdown` | 55 | remove statement | survived | killed |
| M027 | `defang_markdown` | 57 | remove statement | survived | killed |
| M028 | `defang_markdown` | 58 | remove statement | survived | killed |
| M029 | `defang_markdown` | 59 | remove statement | survived | killed |
| M030 | `defang_markdown` | 60 | remove statement | survived | killed |
| M031 | `defang_markdown` | 56 | remove statement | survived | killed |
| M032 | `untrusted_block` | 72 | remove statement | killed | killed |
| M033 | `untrusted_block` | 78 | remove statement | killed | killed |

## New tests

Grouped by function in `tests/test_untrusted.py`:

- `test_flatten_untrusted_default_limit_keeps_exactly_two_hundred_characters`: kills M001.
- `test_defang_markdown_none_is_empty_text`: kills M007, M017, M018, M026, M031.
- `test_defang_markdown_removes_image_and_link_targets`: kills M007–M010 and M027–M030.

Each new test was run separately against every mutant it killed and passed on the original module. The remaining mutants were already killed by the existing standalone test.

## Survivors left

None. No equivalent mutants, offline-untestable mutants, or defects found in this generated set. No expected-failure tests were needed.

## Verification

`python3 -m pytest -q --noconftest -p no:cacheprovider tests/test_untrusted.py`: **3 passed**. The mutation runner's original-module baseline and after baseline also passed. `python3 -m pytest -q -m "not performance"` stopped while importing `tests/conftest.py`: `ModuleNotFoundError: No module named 'platformdirs'`. No packages were installed and no network calls were made. The full suite result remains unverified in this environment.
