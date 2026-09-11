#!/usr/bin/env python3
"""Register phrases and regexes in this installed bundle's shared word list.

Usage: register.py {phrase|syna|antithesis|expository|dangling-identity|body-shell|scan|list} <value>

The scanner reads the shared word list at runtime, so a registration needs no
JavaScript edit.
"""
import os
import sys
import subprocess
import argparse
import json
import re
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = SKILLS_ROOT.parent
BANNED_WORDS = SKILLS_ROOT / "_shared" / "references" / "banned-words.md"
SCANNER = SKILLS_ROOT / "_shared" / "scripts" / "check-ai-patterns.js"
SYNA_HEADING = "## 通感隐喻"         # section header for synesthetic regexes
ANTIT_HEADING = "## 对仗反义俏皮话"   # section header for antithetical aphorism regexes
EXPOSITORY_HEADING = "## 说明文式感官对仗"  # section header for expository sensory-contrast regexes
DANGLING_IDENTITY_HEADING = "## 双端悬空的“的”字身份跳转句"
BODY_SHELL_HEADING = "## 空壳式人体失真比喻"


def banned_copies():
    return [BANNED_WORDS] if BANNED_WORDS.is_file() else []


def add_phrase(phrase):
    phrase = phrase.strip().strip("、")
    if not phrase or re.search(r"[\r\n（）()、]", phrase):
        raise ValueError("phrase must be one nonempty literal without annotations")
    copies = banned_copies()
    updated = skipped = 0
    for p in copies:
        t = p.read_text(encoding="utf-8")
        fences = list(re.finditer(r"^```story-rules\r?\n([\s\S]*?)^```[ \t]*$", t, re.M))
        if len(fences) != 1:
            raise ValueError("expected exactly one story-rules data fence")
        fence = fences[0]
        data = json.loads(fence.group(1))
        if (data.get("schema_version") != 1 or data.get("source") != "system"
                or data.get("scope") != "narration" or not isinstance(data.get("contextual"), list)):
            raise ValueError("invalid shared rule data")
        if phrase in data["contextual"]:
            skipped += 1
            continue
        data["contextual"].append(phrase)
        payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        p.write_text(t[:fence.start(1)] + payload + t[fence.end(1):], encoding="utf-8")
        updated += 1
    print(f"phrase '{phrase}': updated={updated} skipped(already)={skipped} (copies={len(copies)})")


def add_regex_rule(command_name, regex_line, heading, error_example, create_heading):
    regex_line = regex_line.strip()
    if not (regex_line.startswith("/") and regex_line.endswith("/")) or re.search(r"[\r\n]", regex_line):
        print(f"ERROR: {command_name} rule must be a /regex/ line (e.g. {error_example})")
        sys.exit(1)
    # Validate with the same regex engine as the scanner before changing rules.
    subprocess.run([os.environ.get("NODE_BIN") or "node", "-e",
                    "const r = new RegExp(process.argv[1]); if (r.test('')) process.exit(1);",
                    "--", regex_line[1:-1]], check=True, capture_output=True)
    copies = banned_copies()
    updated = skipped = 0
    for p in copies:
        t = p.read_text(encoding="utf-8")
        lines = t.split("\n")
        sections = []
        for start, line in enumerate(lines):
            if not line.startswith(heading):
                continue
            end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
            fences = [i for i in range(start + 1, end) if lines[i].strip() == "```story-regex"]
            if fences:
                sections.append((end, fences))
        if not any(line.startswith(heading) for line in lines):
            lines.extend(["", create_heading, "", "```story-regex", regex_line, "```", ""])
        else:
            if len(sections) != 1:
                raise ValueError("expected a section with story-regex data in " + heading)
            end, fences = sections[0]
            blocks = []
            for opening in fences:
                closing = next((i for i in range(opening + 1, end) if lines[i].strip() == "```"), None)
                if closing is None or any(opening < other < closing for other in fences):
                    raise ValueError("unclosed or nested story-regex fence in " + heading)
                blocks.append((opening, closing))
            if any(regex_line == lines[i].strip() for opening, closing in blocks
                   for i in range(opening + 1, closing)):
                skipped += 1
                continue
            lines.insert(blocks[0][1], regex_line)
        p.write_text("\n".join(lines), encoding="utf-8")
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


def add_expository(regex_line):
    add_regex_rule(
        "expository",
        regex_line,
        EXPOSITORY_HEADING,
        "/还在眼前…，…闻到的却是…/",
        EXPOSITORY_HEADING + "（记忆残留＋“却是”现实对照，出现即改）",
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
    for kind in ["banned-word-exact", "banned-word-syna", "banned-word-antithesis", "banned-word-expository-contrast", "banned-word-dangling-identity", "banned-word-body-shell"]:
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
    p4b = sub.add_parser("expository")
    p4b.add_argument("value")
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
    elif args.cmd == "expository":
        add_expository(args.value)
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
