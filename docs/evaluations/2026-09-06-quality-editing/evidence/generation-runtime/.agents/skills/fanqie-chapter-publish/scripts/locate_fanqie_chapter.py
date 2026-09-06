#!/usr/bin/env python3
import argparse
import json
import pathlib
import re
import sys
from typing import Dict, List, Tuple

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

SKIP_DIR_PARTS = {"归档", "备份", "回收站"}


def normalize_no(raw: str) -> int:
    match = re.search(r"(\d+)", raw)
    if not match:
        raise ValueError("chapter number must contain digits")
    return int(match.group(1))


def chapter_pattern(chapter_no: int) -> re.Pattern:
    return re.compile(r"第0*%d章.*\.md$" % chapter_no)


def collect_candidates(root: pathlib.Path, chapter_no: int) -> List[pathlib.Path]:
    pattern = chapter_pattern(chapter_no)
    candidates = []
    for path in root.rglob("*.md"):
        if "正文" not in path.parts:
            continue
        if SKIP_DIR_PARTS & set(path.parts):
            continue
        if pattern.search(path.name):
            candidates.append(path)
    return sorted(candidates)


def render(root: pathlib.Path, chapter_no: int, candidates: List[pathlib.Path]) -> Dict[str, object]:
    rel_candidates = [str(path.relative_to(root)) for path in candidates]
    if not rel_candidates:
        return {
            "status": "not_found",
            "chapter_no": chapter_no,
            "root": str(root),
            "candidates": [],
        }
    if len(rel_candidates) == 1:
        return {
            "status": "unique",
            "chapter_no": chapter_no,
            "root": str(root),
            "path": rel_candidates[0],
            "candidates": rel_candidates,
        }
    return {
        "status": "multiple",
        "chapter_no": chapter_no,
        "root": str(root),
        "candidates": rel_candidates,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Locate a local chapter markdown file by 第NN章 under a project root."
    )
    parser.add_argument("chapter_no", help="Chapter number, for example 52 or 第52章")
    parser.add_argument(
        "--root",
        default=".",
        help="Project root to search from. Defaults to current directory.",
    )
    parser.add_argument(
        "--field",
        choices=["status", "path"],
        help="Print only one field.",
    )
    args = parser.parse_args()

    root = pathlib.Path(args.root).expanduser().resolve()
    if not root.exists():
        print("missing root: %s" % root, file=sys.stderr)
        return 1

    try:
        chapter_no = normalize_no(args.chapter_no)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    payload = render(root, chapter_no, collect_candidates(root, chapter_no))

    if args.field:
        if args.field == "path":
            if payload["status"] != "unique":
                print("chapter path is not unique", file=sys.stderr)
                return 1
            print(payload["path"])
        else:
            print(payload["status"])
        return 0

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
