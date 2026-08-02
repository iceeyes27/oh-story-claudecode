#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List, Optional

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")


TITLE_RE = re.compile(r"^第\d+章\s+.+$")
TIME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})(?::\d{2})?$")
STATUS_SET = {"待发布", "审核中"}


def read_text(path_arg: Optional[str]) -> str:
    if path_arg:
        path = pathlib.Path(path_arg).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError("missing file: %s" % path)
        text = path.read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()

    text = text.strip()
    if text.startswith('"') and text.endswith('"'):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, str):
                return decoded
        except Exception:
            pass
    return text


def normalize_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def extract_entries(lines: List[str]) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []
    for idx, line in enumerate(lines):
        time_match = TIME_RE.match(line)
        if not time_match:
            continue

        title_idx = None
        for back in range(1, 8):
            if idx - back < 0:
                break
            candidate = lines[idx - back]
            if TITLE_RE.match(candidate):
                title_idx = idx - back
                break

        if title_idx is None:
            continue

        title = lines[title_idx]
        status = None
        for probe in range(title_idx + 1, idx):
            candidate = lines[probe]
            if candidate in STATUS_SET:
                status = candidate
                break

        if not status:
            continue

        entries.append(
            {
                "title": title,
                "status": status,
                "publish_time": "%s %s" % (time_match.group(1), time_match.group(2)),
            }
        )
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract pending/review chapter schedule times from Fanqie chapter-manage page text."
    )
    parser.add_argument(
        "input_file",
        nargs="?",
        help="Optional text file captured from Fanqie chapter-manage page. Reads stdin when omitted.",
    )
    parser.add_argument(
        "--field",
        choices=["times"],
        help="Print only a derived field.",
    )
    args = parser.parse_args()

    try:
        lines = normalize_lines(read_text(args.input_file))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    entries = extract_entries(lines)
    payload = {
        "count": len(entries),
        "entries": entries,
        "times": [item["publish_time"] for item in entries],
    }

    if args.field == "times":
        for item in payload["times"]:
            print(item)
        return 0

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
