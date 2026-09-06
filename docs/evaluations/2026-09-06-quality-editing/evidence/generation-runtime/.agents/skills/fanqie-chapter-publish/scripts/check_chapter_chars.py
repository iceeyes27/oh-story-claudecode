#!/usr/bin/env python3
"""Scan chapter markdown files and report those below a character-count threshold.

Default threshold is 1000 characters, matching the Fanqie platform floor: a
chapter with fewer than 1000 body characters cannot enter the publish settings.
The character-count algorithm mirrors extract_fanqie_chapter.py: strip BOM,
drop leading/trailing blank lines, drop the level-1 chapter heading, drop
empty lines, join with newlines, and take len().

Exit code is non-zero when any chapter is under the threshold, so it can be
used in batch gating.
"""
import argparse
import pathlib
import re
import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

HEADER_RE = re.compile(r"^\s*#{1,6}\s*第[一二三四五六七八九十百千万零〇\d]+章[：:\s]*(.*)\s*$")
FILENAME_RE = re.compile(r"第0*(\d+)章[_\s-]*(.+?)\.md$")
DEFAULT_MIN_CHARS = 1000


def normalize_lines(text: str) -> list:
    lines = [line.rstrip() for line in text.replace("\ufeff", "").splitlines()]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def chapter_no_from_path(path: pathlib.Path):
    m = FILENAME_RE.search(path.name)
    return int(m.group(1)) if m else None


def count_chars(path: pathlib.Path) -> int:
    raw = path.read_text(encoding="utf-8")
    lines = normalize_lines(raw)
    if lines:
        hm = HEADER_RE.match(lines[0])
        if hm:
            lines = lines[1:]
            while lines and not lines[0].strip():
                lines.pop(0)
    body_lines = [ln.strip() for ln in lines if ln.strip()]
    return len("\n".join(body_lines))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Scan chapter markdown files and report those below the Fanqie publish floor (default 1000 chars)."
    )
    ap.add_argument("--root", default=".", help="Project or book root directory")
    ap.add_argument("--min", type=int, default=DEFAULT_MIN_CHARS,
                    help="Minimum body char count; default 1000 (Fanqie floor)")
    ap.add_argument("--from", dest="from_no", type=int, default=None,
                    help="Only check chapters with number >= this")
    ap.add_argument("--to", dest="to_no", type=int, default=None,
                    help="Only check chapters with number <= this")
    args = ap.parse_args()

    root = pathlib.Path(args.root).expanduser().resolve()

    files = sorted(root.glob("正文/**/第*章*.md"), key=lambda p: p.name)
    if not files:
        files = sorted(root.rglob("第*章*.md"), key=lambda p: p.name)

    under = []
    checked = 0
    for f in files:
        no = chapter_no_from_path(f)
        if no is None:
            continue
        if args.from_no is not None and no < args.from_no:
            continue
        if args.to_no is not None and no > args.to_no:
            continue
        n = count_chars(f)
        checked += 1
        flag = "" if n >= args.min else "  <<< 不足"
        print(f"第{no}章  {n:>6} 字符  {f}{flag}")
        if n < args.min:
            under.append((no, n, f.name))

    print("-" * 48)
    print(f"扫描 {checked} 章，门槛 {args.min} 字符")
    if under:
        print(f"⚠️ 共 {len(under)} 章不足 {args.min} 字符：")
        for no, n, name in under:
            print(f"  第{no}章  仅 {n} 字符  ({name})")
        return 1
    print("✓ 全部达标")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
