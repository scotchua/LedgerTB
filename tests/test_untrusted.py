from utils.untrusted import defang_markdown, flatten_untrusted


def test_flatten_untrusted_default_limit_keeps_exactly_two_hundred_characters():
    name = "Larkspur Orbit LLC"
    padded = name + "x" * (200 - len(name))

    assert flatten_untrusted(padded) == padded
    assert flatten_untrusted(padded + "x") == padded + "…"


def test_defang_markdown_none_is_empty_text():
    assert defang_markdown(None) == ""


def test_defang_markdown_removes_image_and_link_targets():
    memo = (
        "Review ![receipt](https://assets.invalid/receipt?amount=42) and "
        "[entry](https://assets.invalid/entry?date=2026-03-04) for "
        "Larkspur Orbit LLC."
    )

    assert defang_markdown(memo) == (
        "Review [image: receipt] and entry for Larkspur Orbit LLC."
    )
