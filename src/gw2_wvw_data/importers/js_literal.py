"""A non-evaluating parser for the literal subset used by GW2Skills."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gw2_wvw_data.importers import ImportError


_MAX_CONTAINER_DEPTH = 32
_MAX_INTEGER_DIGITS = 128
_WHITESPACE = " \t\r\n\f\v"
_ASCII_DIGITS = frozenset("0123456789")
_IDENTIFIER_START = frozenset(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_$"
)
_IDENTIFIER_CONTINUE = _IDENTIFIER_START | frozenset("0123456789")
_ESCAPES = {
    '"': '"',
    "'": "'",
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
    "n": "\n",
    "r": "\r",
    "t": "\t",
}


def parse_js_literal(text: str) -> Any:
    """Parse data-only JavaScript literal syntax without evaluating code."""

    if not isinstance(text, str):
        raise ImportError("JS literal input must be text")
    parser = _Parser(text)
    value = parser.parse_value(depth=0)
    parser.skip_whitespace()
    if not parser.at_end:
        parser.fail("unexpected trailing syntax")
    return value


@dataclass
class _Parser:
    text: str
    cursor: int = 0

    @property
    def at_end(self) -> bool:
        return self.cursor >= len(self.text)

    def fail(self, message: str) -> None:
        raise ImportError(f"invalid JS literal at offset {self.cursor}: {message}")

    def peek(self) -> str:
        return "" if self.at_end else self.text[self.cursor]

    def skip_whitespace(self) -> None:
        while not self.at_end and self.text[self.cursor] in _WHITESPACE:
            self.cursor += 1

    def parse_value(self, *, depth: int) -> Any:
        self.skip_whitespace()
        char = self.peek()
        if not char:
            self.fail("expected a value")
        if char in "\"'":
            return self.parse_string()
        if char == "[":
            return self.parse_array(depth=depth + 1)
        if char == "{":
            return self.parse_object(depth=depth + 1)
        if char == "-" or char in _ASCII_DIGITS:
            return self.parse_integer()
        if char in _IDENTIFIER_START:
            identifier = self.parse_identifier()
            if identifier == "true":
                return True
            if identifier == "false":
                return False
            if identifier == "null":
                return None
            self.fail(f"unsupported identifier {identifier!r}")
        self.fail("unsupported syntax")

    def parse_string(self) -> str:
        quote = self.peek()
        self.cursor += 1
        value: list[str] = []
        while not self.at_end:
            char = self.text[self.cursor]
            self.cursor += 1
            if char == quote:
                return "".join(value)
            if char == "\\":
                if self.at_end:
                    self.fail("unterminated escape")
                escape = self.text[self.cursor]
                self.cursor += 1
                if escape == "u":
                    digits = self.text[self.cursor : self.cursor + 4]
                    if len(digits) != 4 or any(
                        item not in "0123456789abcdefABCDEF" for item in digits
                    ):
                        self.fail("invalid Unicode escape")
                    value.append(chr(int(digits, 16)))
                    self.cursor += 4
                    continue
                if escape not in _ESCAPES:
                    self.fail("unsupported string escape")
                value.append(_ESCAPES[escape])
                continue
            if ord(char) < 0x20:
                self.fail("unescaped control character in string")
            value.append(char)
        self.fail("unterminated string")

    def parse_identifier(self) -> str:
        start = self.cursor
        if self.peek() not in _IDENTIFIER_START:
            self.fail("expected identifier")
        self.cursor += 1
        while not self.at_end and self.text[self.cursor] in _IDENTIFIER_CONTINUE:
            self.cursor += 1
        return self.text[start : self.cursor]

    def parse_integer(self) -> int:
        start = self.cursor
        if self.peek() == "-":
            self.cursor += 1
            if self.peek() not in _ASCII_DIGITS:
                self.fail("expected integer digits")
        if self.peek() == "0":
            self.cursor += 1
            if self.peek() in _ASCII_DIGITS:
                self.fail("leading zero in integer")
        else:
            if self.peek() not in _ASCII_DIGITS:
                self.fail("expected integer")
            while self.peek() in _ASCII_DIGITS:
                self.cursor += 1
        digit_count = self.cursor - start - (self.text[start] == "-")
        if digit_count > _MAX_INTEGER_DIGITS:
            self.fail("integer exceeds 128 digits")
        try:
            return int(self.text[start : self.cursor])
        except ValueError as error:
            raise ImportError("invalid JS integer") from error

    def parse_array(self, *, depth: int) -> list[Any]:
        self._check_depth(depth)
        self.cursor += 1
        values: list[Any] = []
        self.skip_whitespace()
        if self.peek() == "]":
            self.cursor += 1
            return values
        while True:
            values.append(self.parse_value(depth=depth))
            self.skip_whitespace()
            if self.peek() == "]":
                self.cursor += 1
                return values
            if self.peek() != ",":
                self.fail("expected ',' or ']'")
            self.cursor += 1

    def parse_object(self, *, depth: int) -> dict[str, Any]:
        self._check_depth(depth)
        self.cursor += 1
        values: dict[str, Any] = {}
        self.skip_whitespace()
        if self.peek() == "}":
            self.cursor += 1
            return values
        while True:
            self.skip_whitespace()
            key = (
                self.parse_string()
                if self.peek() in "\"'"
                else self.parse_identifier()
            )
            if key in values:
                self.fail(f"duplicate object key {key!r}")
            self.skip_whitespace()
            if self.peek() != ":":
                self.fail("expected ':' after object key")
            self.cursor += 1
            values[key] = self.parse_value(depth=depth)
            self.skip_whitespace()
            if self.peek() == "}":
                self.cursor += 1
                return values
            if self.peek() != ",":
                self.fail("expected ',' or '}'")
            self.cursor += 1

    def _check_depth(self, depth: int) -> None:
        if depth > _MAX_CONTAINER_DEPTH:
            self.fail("container depth exceeds 32")
