"""Small strict parser for the generated Codex agent TOML subset.

The repository supports Python runtimes older than 3.11, where ``tomllib`` is
not available. Generated agent files intentionally use only basic strings,
multiline basic strings, and JSON-compatible arrays, so validating that subset
does not require an external dependency.
"""

from __future__ import annotations

import json
import re


KEY_RE = re.compile(r"([A-Za-z_][A-Za-z0-9_-]*)\s*=\s*")


def loads(text: str) -> dict[str, object]:
    values: dict[str, object] = {}
    position = 0
    length = len(text)
    decoder = json.JSONDecoder()
    while position < length:
        while position < length and text[position].isspace():
            position += 1
        if position >= length:
            break
        match = KEY_RE.match(text, position)
        if not match:
            raise ValueError(f"unsupported TOML syntax at offset {position}")
        key = match.group(1)
        if key in values:
            raise ValueError(f"duplicate TOML key: {key}")
        position = match.end()
        if text.startswith('"""', position):
            start = position + 3
            end = text.find('"""', start)
            if end < 0:
                raise ValueError(f"unterminated multiline string: {key}")
            raw = text[start:end]
            values[key] = raw.replace('\\"', '"').replace('\\\\', '\\').strip("\n")
            position = end + 3
        else:
            try:
                value, consumed = decoder.raw_decode(text[position:])
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid value for {key}: {error}") from error
            values[key] = value
            position += consumed
        if position < length and not text[position].isspace():
            raise ValueError(f"unexpected trailing content for {key}")
    return values
