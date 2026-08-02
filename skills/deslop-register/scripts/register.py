#!/usr/bin/env python3
"""deslop-register helper.

Syncs banned phrases / synesthetic regexes across the project's framework copies
of banned-words.md, and runs the deslop scanner over a book directory.

Usage:
  python3 register.py phrase "短语"        # append phrase to 表情类 line in all banned-words.md copies
  python3 register.py syna  "/正则/"        # append /regex/ to the 通感隐喻 section
  python3 register.py antithesis "/正则/"   # append /regex/ to the 对仗反义俏皮话 section
  python3 register.py scan   "<book_dir>"   # run check-ai-patterns.js on all .md under book_dir
  python3 register.py list                  # show how many banned-words.md copies exist

The scanner is read at runtime by check-ai-patterns.js, so registering a phrase or
regex in banned-words.md is enough — no .js edit needed.
"""
import os
import sys
import glob
import subprocess
import argparse

ROOT = os.getcwd()
FRAMEWORKS = [".workbuddy", ".codex", ".claude", ".agents"]
BANNED_REL = [
    "story-deslop/references/banned-words.md",
    "story-long-write/references/banned-words.md",
    "story-short-write/references/banned-words.md",
    "story-short-analyze/references/banned-words.md",
    "story-review/references/banned-words.md",
    "story-setup/references/agent-references/banned-words.md",
]
EXPR_HEADING = "### 表情类"         # header preceding the 表情类 list line
SYNA_HEADING = "## 通感隐喻"         # section header for synesthetic regexes
ANTIT_HEADING = "## 对仗反义俏皮话"   # section header for antithetical aphorism regexes


def banned_copies():
    out = []
    for fw in FRAMEWORKS:
        for rel in BANNED_REL:
            p = os.path.join(ROOT, fw, "skills", rel)
            if os.path.isfile(p):
                out.append(p)
    return out


def _expr_line_index(lines):
    """Index of the 表情类 list line. Anchor on the '### 表情类' heading, then the
    next non-empty line. Fallback: a plain line containing both 眼中闪过 and 嘴角勾起
    that is not a table row (some copies keep a table with those words in a cell)."""
    for i, l in enumerate(lines):
        if l.strip().startswith(EXPR_HEADING):
            for j in range(i + 1, len(lines)):
                if lines[j].strip():
                    return j
            break
    for i, l in enumerate(lines):
        if "眼中闪过" in l and "嘴角勾起" in l and not l.lstrip().startswith("|"):
            return i
    return -1


def add_phrase(phrase):
    phrase = phrase.strip().strip("、")
    copies = banned_copies()
    updated = skipped = 0
    for p in copies:
        t = open(p, encoding="utf-8").read()
        if phrase in t:
            skipped += 1
            continue
        lines = t.split("\n")
        idx = _expr_line_index(lines)
        if idx == -1:
            lines.append(phrase)
        else:
            lines[idx] = lines[idx].rstrip() + "、" + phrase
        open(p, "w", encoding="utf-8").write("\n".join(lines))
        updated += 1
    print(f"phrase '{phrase}': updated={updated} skipped(already)={skipped} (copies={len(copies)})")


def add_syna(regex_line):
    regex_line = regex_line.strip()
    if not (regex_line.startswith("/") and regex_line.endswith("/")):
        print("ERROR: synesthetic rule must be a /regex/ line (e.g. /那股.../ )")
        sys.exit(1)
    copies = banned_copies()
    updated = skipped = 0
    for p in copies:
        t = open(p, encoding="utf-8").read()
        if regex_line in t:
            skipped += 1
            continue
        lines = t.split("\n")
        out, in_sec, inserted = [], False, False
        for l in lines:
            if l.startswith(SYNA_HEADING):
                in_sec = True
                out.append(l)
                continue
            if in_sec and l.startswith("## "):
                if not inserted:
                    out.append(regex_line)
                    inserted = True
                in_sec = False
                out.append(l)
                continue
            out.append(l)
        if in_sec and not inserted:
            out.append(regex_line)
        open(p, "w", encoding="utf-8").write("\n".join(out))
        updated += 1
    print(f"syna {regex_line}: updated={updated} skipped(already)={skipped} (copies={len(copies)})")


def add_antithesis(regex_line):
    regex_line = regex_line.strip()
    if not (regex_line.startswith("/") and regex_line.endswith("/")):
        print("ERROR: antithesis rule must be a /regex/ line (e.g. /([一-鿿]{1,3})[，,]([^，。]{0,8})不\\1/ )")
        sys.exit(1)
    copies = banned_copies()
    updated = skipped = 0
    for p in copies:
        t = open(p, encoding="utf-8").read()
        if regex_line in t:
            skipped += 1
            continue
        lines = t.split("\n")
        out, in_sec, inserted, heading_seen = [], False, False, False
        for l in lines:
            if l.startswith(ANTIT_HEADING):
                heading_seen = True
                in_sec = True
                out.append(l)
                continue
            if in_sec and l.startswith("## "):
                if not inserted:
                    out.append(regex_line)
                    inserted = True
                in_sec = False
                out.append(l)
                continue
            out.append(l)
        if not heading_seen:
            if out and out[-1].strip():
                out.append("")
            out.append(ANTIT_HEADING + "（工整对称反义金句，出现即改）")
            out.append(regex_line)
        elif in_sec and not inserted:
            out.append(regex_line)
        open(p, "w", encoding="utf-8").write("\n".join(out))
        updated += 1
    print(f"antithesis {regex_line}: updated={updated} skipped(already)={skipped} (copies={len(copies)})")


def scan(book_dir):
    node = os.environ.get("NODE_BIN") or "node"
    scanner = os.path.join(ROOT, ".workbuddy", "skills", "story-deslop",
                           "scripts", "check-ai-patterns.js")
    if not os.path.isfile(scanner):
        print("ERROR: scanner not found at", scanner)
        sys.exit(1)
    files = sorted(glob.glob(os.path.join(book_dir, "**", "*.md"), recursive=True))
    if not files:
        files = sorted(glob.glob(os.path.join(book_dir, "*.md")))
    if not files:
        print("ERROR: no .md files found under", book_dir)
        sys.exit(1)
    cmd = [node, scanner, "--check"] + files
    res = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    out = res.stdout + res.stderr
    for kind in ["banned-word-exact", "banned-word-syna", "banned-word-antithesis"]:
        print(f"{kind}: {out.count(kind)}")
    return out


def main():
    ap = argparse.ArgumentParser(description="deslop-register helper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("phrase")
    p1.add_argument("value")
    p2 = sub.add_parser("syna")
    p2.add_argument("value")
    p4 = sub.add_parser("antithesis")
    p4.add_argument("value")
    p3 = sub.add_parser("scan")
    p3.add_argument("book_dir")
    sub.add_parser("list")
    args = ap.parse_args()

    if args.cmd == "phrase":
        add_phrase(args.value)
    elif args.cmd == "syna":
        add_syna(args.value)
    elif args.cmd == "antithesis":
        add_antithesis(args.value)
    elif args.cmd == "scan":
        scan(args.book_dir)
    elif args.cmd == "list":
        copies = banned_copies()
        print(f"banned-words.md copies found: {len(copies)}")
        for c in copies:
            print("  ", c)


if __name__ == "__main__":
    main()
