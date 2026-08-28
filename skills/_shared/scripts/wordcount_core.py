#!/usr/bin/env python3
"""Deterministic visible-character counting for long-form chapter gates."""

from __future__ import annotations

import re


METRIC = "visible_chars_v1"
FANQIE_MIN = 2200
FANQIE_MAX = 2800

_FRONTMATTER_KEY = re.compile(r"^[A-Za-z_\u3400-\u9FFF][^:\n]{0,80}:[ \t]*(?:.*)$")
_ATX_HEADING = re.compile(r"^[\t ]{0,3}#{1,6}[\t ]+\S")


def normalize_newlines(value: str) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n")


def visible_body(value: str) -> str:
    text = normalize_newlines(value).lstrip("\ufeff")
    lines = text.split("\n")
    if lines and lines[0] == "---":
        closing = next((index for index in range(1, min(len(lines), 201)) if lines[index] in {"---", "..."}), -1)
        if closing >= 2 and any(_FRONTMATTER_KEY.match(line) for line in lines[1:closing]):
            lines = lines[closing + 1 :]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _ATX_HEADING.match(lines[0]):
        lines.pop(0)
    return "\n".join(lines)


def count_visible_chars(value: str) -> int:
    return sum(not character.isspace() for character in visible_body(value))


def fanqie_length(value: str) -> dict[str, int | str]:
    actual = count_visible_chars(value)
    status = "pass" if FANQIE_MIN <= actual <= FANQIE_MAX else ("under" if actual < FANQIE_MIN else "over")
    return {"metric": METRIC, "min": FANQIE_MIN, "max": FANQIE_MAX, "actual": actual, "status": status}
