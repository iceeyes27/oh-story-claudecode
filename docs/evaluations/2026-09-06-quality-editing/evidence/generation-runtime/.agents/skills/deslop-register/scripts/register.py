#!/usr/bin/env python3
"""Register phrases and regexes in this installed bundle's shared word list.

Usage: register.py {phrase|syna|antithesis|dangling-identity|body-shell|scan|list} <value>

The scanner reads the shared word list at runtime, so a registration needs no
JavaScript edit.
"""
import os
import sys
import subprocess
import argparse
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILLS_ROOT.parent
BANNED_WORDS = SKILLS_ROOT / "_shared" / "references" / "banned-words.md"
SCANNER = SKILLS_ROOT / "_shared" / "scripts" / "check-ai-patterns.js"
EXPR_HEADING = "### 表情类"         # header preceding the 表情类 list line
SYNA_HEADING = "## 通感隐喻"         # section header for synesthetic regexes
ANTIT_HEADING = "## 对仗反义俏皮话"   # section header for antithetical aphorism regexes
DANGLING_IDENTITY_HEADING = "## 双端悬空的“的”字身份跳转句"
BODY_SHELL_HEADING = "## 空壳式人体失真比喻"


def banned_copies():
    return [BANNED_WORDS] if BANNED_WORDS.is_file() else []


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
        t = p.read_text(encoding="utf-8")
        if phrase in t:
            skipped += 1
            continue
        lines = t.split("\n")
        idx = _expr_line_index(lines)
        if idx == -1:
            lines.append(phrase)
        else:
            lines[idx] = lines[idx].rstrip() + "、" + phrase
        p.write_text("\n".join(lines), encoding="utf-8")
        updated += 1
    print(f"phrase '{phrase}': updated={updated} skipped(already)={skipped} (copies={len(copies)})")


def add_regex_rule(command_name, regex_line, heading, error_example, create_heading):
    regex_line = regex_line.strip()
    if not (regex_line.startswith("/") and regex_line.endswith("/")):
        print(f"ERROR: {command_name} rule must be a /regex/ line (e.g. {error_example})")
        sys.exit(1)
    copies = banned_copies()
    updated = skipped = 0
    for p in copies:
        t = p.read_text(encoding="utf-8")
        if regex_line in t:
            skipped += 1
            continue
        lines = t.split("\n")
        out, in_sec, inserted, heading_seen = [], False, False, False
        for l in lines:
            if l.startswith(heading):
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
            out.append(create_heading)
            out.append(regex_line)
        elif in_sec and not inserted:
            out.append(regex_line)
        p.write_text("\n".join(out), encoding="utf-8")
        updated += 1
    print(f"{command_name} {regex_line}: updated={updated} skipped(already)={skipped} (copies={len(copies)})")


def add_syna(regex_line):
    add_regex_rule(
        "syna",
        regex_line,
        SYNA_HEADING,
        "/那股.../",
        SYNA_HEADING + "（感官词抽象化情绪/局势，出现即改）",
    )


def add_antithesis(regex_line):
    add_regex_rule(
        "antithesis",
        regex_line,
        ANTIT_HEADING,
        "/([一-鿿]{1,3})[，,]([^，。]{0,8})不\\1/",
        ANTIT_HEADING + "（工整对称反义金句，出现即改）",
    )


def add_dangling_identity(regex_line):
    add_regex_rule(
        "dangling-identity",
        regex_line,
        DANGLING_IDENTITY_HEADING,
        "/醒来的[，,]成了他/",
        DANGLING_IDENTITY_HEADING + "（主语与身份指代同时悬空，出现即改）",
    )


def add_body_shell(regex_line):
    add_regex_rule(
        "body-shell",
        regex_line,
        BODY_SHELL_HEADING,
        "/像被抽走了骨头，只剩一层皮撑着/",
        BODY_SHELL_HEADING + "（骨架被抽走＋皮壳支撑，出现即改）",
    )


def scan(book_dir):
    node = os.environ.get("NODE_BIN") or "node"
    if not SCANNER.is_file():
        print("ERROR: scanner not found at", SCANNER)
        sys.exit(1)
    source = Path(book_dir)
    files = sorted(str(path) for path in source.rglob("*.md"))
    if not files:
        print("ERROR: no .md files found under", book_dir)
        sys.exit(1)
    cmd = [node, str(SCANNER), "--check"] + files
    res = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = res.stdout + res.stderr
    for kind in ["banned-word-exact", "banned-word-syna", "banned-word-antithesis", "banned-word-dangling-identity", "banned-word-body-shell"]:
        print(f"{kind}: {out.count(kind)}")
    return res.returncode


def main():
    ap = argparse.ArgumentParser(description="deslop-register helper")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("phrase")
    p1.add_argument("value")
    p2 = sub.add_parser("syna")
    p2.add_argument("value")
    p4 = sub.add_parser("antithesis")
    p4.add_argument("value")
    p5 = sub.add_parser("dangling-identity")
    p5.add_argument("value")
    p6 = sub.add_parser("body-shell")
    p6.add_argument("value")
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
    elif args.cmd == "dangling-identity":
        add_dangling_identity(args.value)
    elif args.cmd == "body-shell":
        add_body_shell(args.value)
    elif args.cmd == "scan":
        return scan(args.book_dir)
    elif args.cmd == "list":
        copies = banned_copies()
        print(f"banned-words.md copies found: {len(copies)}")
        for c in copies:
            print("  ", c)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
