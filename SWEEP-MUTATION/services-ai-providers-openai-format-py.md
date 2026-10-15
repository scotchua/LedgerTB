# Mutation results: `services/ai_providers/openai_format.py`

The runner generated 29 single-change AST mutants, capped below 150 and covering all four methods. It skipped comments, logging and docstrings. This module has no eligible `and`/`or`, comparison, or `+`/`-` expression to mutate. Each mutant lived in a temporary file; the production module was never rewritten. Each test subprocess had a 20-second timeout.

| Phase | Killed | Survived | Kill rate |
| --- | ---: | ---: | ---: |
| Existing relevant tests, before | Not measurable | Not measurable | N/A: 0 valid runs |
| New isolated offline tests, after | 29 | 0 | 29/29 (100%) |

The existing relevant tests in `tests/test_categorization.py` could not collect: the repository's `tests/conftest.py` imports `config.py`, which fails with `ModuleNotFoundError: No module named 'platformdirs'` in this environment. The requested full-suite command fails at the same point. The initial attempts against all mutants stopped at import; those import errors were excluded from killed counts. The new tests load only the target file under a synthetic package, stub the URL validator and HTTP transport, and require no network or production edits. Thus the after rate measures the new tests, while a comparable before rate remains unavailable.

## Mutants generated

| IDs | Method | Changes | After |
| --- | --- | --- | --- |
| M001–M004 | `__init__` | Remove each stored constructor input | 4 killed |
| M005–M007 | `url` | Return `None`, an empty list, or `False` | 3 killed |
| M008–M010 | `payload` | Return `None`, an empty list, or `False` | 3 killed |
| M011–M012 | `payload` | Change `max_tokens` from 4000 to 3999 or 4001 | 2 killed |
| M013 | `payload` | Remove function definition assignment | 1 killed |
| M014–M016 | `send` | Return `None`, an empty list, or `False` | 3 killed |
| M017 | `send` | Negate the `isinstance(arguments, str)` condition | 1 killed |
| M018 | `send` | Drop the exception raise | 1 killed |
| M019–M020 | `send` | Change timeout from 60 to 59 or 61 | 2 killed |
| M021–M024 | `send` | Change each first-item index from 0 to -1 or 1 | 4 killed |
| M025–M029 | `send` | Remove one validation, request, response, argument, or tool-input statement | 5 killed |

Survivors left: none. Equivalent mutants: none. Mutants untestable offline: none, after isolated loading. Defects found: none. The original file remained byte-identical after the mutation run.

## New tests

All nine collected test cases pass on the original and each fails on at least one recorded mutant:

| Test | Example mutant killed |
| --- | --- |
| `TestOpenAIRequestInit.test_keeps_constructor_inputs` | M002 |
| `TestOpenAIRequestUrl.test_appends_chat_completions_to_base_url` | M005 |
| `TestOpenAIRequestPayload.test_uses_tool_schema_and_forces_named_tool` | M011 |
| `TestOpenAIRequestSend.test_posts_json_with_authentication_and_timeout` | M019 |
| `TestOpenAIRequestSend.test_reads_first_choice_and_first_tool_call` | M021 |
| `TestOpenAIRequestSend.test_accepts_object_arguments_and_missing_suggestions` | M017 |
| `TestOpenAIRequestSend.test_rejects_missing_or_invalid_tool_call[payload0]` | M018 |
| `TestOpenAIRequestSend.test_rejects_missing_or_invalid_tool_call[payload1]` | M018 |
| `TestOpenAIRequestSend.test_rejects_missing_or_invalid_tool_call[payload2]` | M018 |

Verification: `python3 -m pytest -q --noconftest -p no:cacheprovider tests/test_openai_format_mutations.py` passed (9 tests). `python3 -m pytest -q -m 'not performance' -p no:cacheprovider` could not load `tests/conftest.py` because `platformdirs` is absent. `python` is not available in this environment, so `python3` was used for the requested verification.
