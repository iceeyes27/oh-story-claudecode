#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_extract_chapter_endings.py — story-hook-refine 脚本回归测试

运行：
  python .agents/skills/story-hook-refine/scripts/test_extract_chapter_endings.py

覆盖：
  1. 严格识别：非「第N章_」文件（_已知实体.txt、.claude/MEMORY.md、project_f1-*.md）被忽略，
     不再产生假阳性章节号（历史 bug：f1 被解析成第 1 章造成重号）。
  2. 重号检测：同名「第N章_」两个文件 → 报错退出（exit 1）。
  3. 缺号检测：区间缺号 → 报错退出（exit 1）。
  4. 读取失败：损坏文件 → 报错退出（exit 2）。
  5. .active-book 解析：临时目录写 .active-book → 自动解析到 {书}/正文。
  6. --words 过滤：只输出命中词表的章末。

全部通过打印 PASS；任一失败打印 FAIL 并退出码 1。
"""
import os
import subprocess
import sys
import tempfile

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "extract_chapter_endings.py")


def run(args, cwd):
    return subprocess.run([sys.executable, SCRIPT, *args],
                          capture_output=True, text=True, cwd=cwd)


def make_tree(root, files):
    """files: {relpath: content}"""
    for rel, content in files.items():
        full = os.path.join(root, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)


def test_strict_identification():
    """杂文件不产生章节号；重号/缺号可被捕获。"""
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "书", "正文")
        make_tree(root, {
            "第001章_七天.md": "正文一。\n\n章末一。",
            "第002章_三千盾.md": "正文二。\n\n章末二。",
            "_已知实体.txt": "不是章节",
            ".claude/agent-memory/story-architect/project_f1-signature-cup.md": "f1 不应被解析",
        })
        r = run(["--dir", root], cwd=td)
        # 只应输出 001/002 两行 + stderr summary
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        assert len(lines) == 2, f"期望 2 章，实际 {len(lines)}: {lines}"
        assert all(l.startswith(("1\t", "2\t")) for l in lines), lines
        print("  PASS 严格识别：杂文件被忽略，无假阳性")


def test_duplicate_detection():
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "书", "正文")
        make_tree(root, {
            "第001章_七天.md": "a",
            "第001章_重复.md": "b",
        })
        r = run(["--dir", root], cwd=td)
        assert r.returncode == 1, f"重号应退出 1，实际 {r.returncode}"
        assert "重号" in (r.stderr + r.stdout), r.stderr
        print("  PASS 重号检测")


def test_missing_detection():
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "书", "正文")
        make_tree(root, {"第001章_a.md": "a", "第003章_c.md": "c"})
        r = run(["--dir", root, "--from", "1", "--to", "3"], cwd=td)
        assert r.returncode == 1, f"缺号应退出 1，实际 {r.returncode}"
        assert "缺号" in (r.stderr + r.stdout), r.stderr
        print("  PASS 缺号检测")


def test_read_failure():
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "书", "正文")
        make_tree(root, {"第001章_a.md": "a"})
        bad = os.path.join(root, "第002章_b.md")
        with open(bad, "wb") as f:
            f.write(b"\xff\xfe\x00\x01")  # 非法 utf-8
        r = run(["--dir", root], cwd=td)
        assert r.returncode == 2, f"读取失败应退出 2，实际 {r.returncode}"
        assert "读取失败" in (r.stderr + r.stdout), r.stderr
        print("  PASS 读取失败检测")


def test_active_book_resolution():
    with tempfile.TemporaryDirectory() as td:
        book = os.path.join(td, "我的书")
        make_tree(os.path.join(book, "正文"), {"第001章_x.md": "正文。\n\n末。"})
        with open(os.path.join(td, ".active-book"), "w", encoding="utf-8") as f:
            f.write("我的书")
        r = run([], cwd=td)
        assert r.returncode == 0, r.stderr
        assert r.stdout.splitlines()[0].startswith("1\t"), r.stdout
        print("  PASS .active-book 解析")


def test_words_filter():
    with tempfile.TemporaryDirectory() as td:
        root = os.path.join(td, "书", "正文")
        make_tree(root, {
            "第001章_a.md": "正文。\n\n他望向远方，整片天地都在脚下铺开。",
            "第002章_b.md": "正文。\n\n他数完钱，把字据收进怀里。",
        })
        words = os.path.join(td, "words.txt")
        with open(words, "w", encoding="utf-8") as f:
            f.write("天地\n")
        r = run(["--dir", root, "--words", words], cwd=td)
        lines = r.stdout.splitlines()
        assert len(lines) == 1 and lines[0].startswith("1\t"), lines
        print("  PASS 词表过滤")


def main():
    tests = [test_strict_identification, test_duplicate_detection,
             test_missing_detection, test_read_failure,
             test_active_book_resolution, test_words_filter]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__} (异常): {e}")
    if failed:
        print(f"\n{len(tests) - failed}/{len(tests)} 通过")
        return 1
    print(f"\n全部 {len(tests)} 项测试通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
