# `utils/actor.py` mutation test

The 43-line module was read in full. Existing actor coverage was found in
`tests/test_access_levels.py`, `tests/test_activity_feed.py`,
`tests/test_assistant_setup_and_review.py`, `tests/test_branding.py`, and
`tests/test_close_map.py`. The directly relevant assertions in
`test_assistant_process_actor_carries_ai_suffix` were run for each mutant.
Its database portion and the other integration tests could not load in this
environment because the repository pytest setup imports missing
`platformdirs`. The rates below use the isolated original assertions as the
**before** baseline and their union with `tests/test_actor.py` as **after**.

| Measure | Before | After |
| --- | ---: | ---: |
| Mutants generated | 17 | 17 |
| Killed, all mutants | 7/17 (41.2%) | 16/17 (94.1%) |
| Killed, excluding one equivalent mutant | 7/16 (43.8%) | 16/16 (100%) |

Each mutant changed one executable source fragment in memory and ran in a
separate subprocess with a 15-second timeout. No mutant timed out. The source
file was checked byte for byte after every run; its SHA-256 remained
`d578f302a871835e0391a6a377bc293b6b476144f9ca1834428295cf2c17d1a9`.
No comments, logging, or docstrings were mutated. Comparison and Boolean
operator swaps, `+`/`-` swaps, and dropped raises had no applicable executable
site in this module.

| ID | Function | Mutation | Before | After |
| --- | --- | --- | --- | --- |
| M01 | `mark_as_assistant` | assign `False` | killed | killed |
| M02 | `mark_as_assistant` | remove assignment | killed | killed |
| M03 | `mark_as_assistant` | remove `global` | killed | killed |
| M04 | `_os_actor` | cache size 1 to 0 | survived | killed |
| M05 | `_os_actor` | cache size 1 to 2 | survived | survived |
| M06 | `_os_actor` | use GECOS field 1 | survived | killed |
| M07 | `_os_actor` | omit whitespace trimming | survived | killed |
| M08 | `_os_actor` | negate full-name condition | survived | killed |
| M09 | `_os_actor` | return `None` for full name | killed | killed |
| M10 | `_os_actor` | remove full-name return | survived | killed |
| M11 | `_os_actor` | return `None` for username | survived | killed |
| M12 | `_os_actor` | remove username return | survived | killed |
| M13 | `_os_actor` | return `None` for unknown | survived | killed |
| M14 | `_os_actor` | remove unknown return | survived | killed |
| M15 | `current_actor` | negate assistant condition | killed | killed |
| M16 | `current_actor` | return `None` for assistant | killed | killed |
| M17 | `current_actor` | return `None` for human | killed | killed |

M05 is equivalent for this no-argument function's attribution behavior: both
cache sizes retain its sole call signature. It is the only survivor. There
were no offline-untestable survivors.

## Defects found

None.

## New tests

All five tests pass on the original and each fails on a recorded mutant in an
isolated subprocess:

| Test in `tests/test_actor.py::TestOsActor` | Witness mutant |
| --- | --- |
| `test_uses_trimmed_full_name_before_gecos_details` | M06 |
| `test_blank_full_name_uses_short_username` | M11 |
| `test_pwd_failure_uses_short_username` | M12 |
| `test_both_name_sources_fail_uses_unknown` | M13 |
| `test_name_is_captured_once_per_process` | M04 |

`python3 -m pytest --noconftest -q tests/test_actor.py` passed (5 tests).
The requested full-suite command, `python -m pytest -q -m "not performance"`,
could not run because `python` is absent; its `python3` equivalent stops while
loading `tests/conftest.py` with `ModuleNotFoundError: platformdirs`.
