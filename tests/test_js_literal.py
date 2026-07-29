import pytest

from gw2_wvw_data.importers import ImportError
from gw2_wvw_data.importers.js_literal import parse_js_literal


def test_parses_supported_js_literal_subset():
    value = parse_js_literal(
        """
        {
          identifier_key: "line\\nvalue",
          "quoted-key": -12,
          single: 'quote\\'value',
          flags: [true, false, null],
          unicode: "\\u0054hief"
        }
        """
    )

    assert value == {
        "identifier_key": "line\nvalue",
        "quoted-key": -12,
        "single": "quote'value",
        "flags": [True, False, None],
        "unicode": "Thief",
    }


@pytest.mark.parametrize(
    "text",
    [
        "value.property",
        "fn()",
        "{value: fn()}",
        "{value: 1 /* comment */}",
        "// comment\nnull",
        "`template`",
        "1.5",
        "1e3",
        "{a: 1, a: 2}",
        '{"a": 1, a: 2}',
    ],
)
def test_rejects_executable_or_unsupported_js_syntax(text):
    with pytest.raises(ImportError):
        parse_js_literal(text)


def test_rejects_input_deeper_than_32_containers():
    accepted = "[" * 32 + "null" + "]" * 32
    rejected = "[" * 33 + "null" + "]" * 33

    assert parse_js_literal(accepted) == [[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[[None]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]]
    with pytest.raises(ImportError, match="depth"):
        parse_js_literal(rejected)


@pytest.mark.parametrize("text", ["\u0661", "9" * 5_000])
def test_rejects_non_js_or_unbounded_integer_forms(text):
    with pytest.raises(ImportError):
        parse_js_literal(text)
