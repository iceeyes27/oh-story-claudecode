#!/usr/bin/env python3
"""Regression tests for the deterministic author-voice profile tool."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills" / "story-write" / "scripts" / "author_voice_profile.py"
START = b"<!-- author-voice:machine:start -->"
END = b"<!-- author-voice:machine:end -->"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def make_project(root: Path, *, newline: str = "\n") -> tuple[Path, Path]:
    project = root / "中文书名"
    style = project / "设定" / "文风.md"
    author_before = "# 本书文风\n\n## 作者规则\n- 对话不要解释已知信息。\n\n"
    author_after = "\n## 作者补充\n- 保留有功能的停顿。\n"
    content = author_before + START.decode() + "\n" + END.decode() + author_after
    write(style, content.replace("\n", newline))
    return project, style


def add_adopted_prose(project: Path) -> None:
    write(
        project / "正文" / "第001章_起风.md",
        "# 第一章 起风\n\n雨沿着旧窗框往下流，陈默把账本放在桌上。\n\n“你数过没有？”\n\n“三遍。”他把手收回口袋。\n",
    )
    write(
        project / "正文" / "卷一" / "第002章-一封信.md",
        "# 第二章 一封信\n\n信封没有落款。\n\n她没拆，先看了一眼门外的脚印，又把灯芯压低了些。\n\n“明天再说。”\n",
    )


def run(project: Path, command: str, *extra: str) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(TOOL), command, "--project", str(project), "--json", *extra],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=environment,
        check=False,
    )


def output_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    source = result.stdout if result.stdout.strip() else result.stderr
    try:
        value = json.loads(source)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"output is not JSON: stdout={result.stdout!r} stderr={result.stderr!r}") from exc
    require(isinstance(value, dict), "output must be a JSON object")
    return value


def marker_regions(data: bytes) -> tuple[bytes, bytes, bytes]:
    start = data.index(START)
    end = data.index(END)
    return data[:start], data[start + len(START):end], data[end + len(END):]


def test_update_scope_preservation_and_idempotence(root: Path) -> None:
    project, style = make_project(root / "main", newline="\r\n")
    add_adopted_prose(project)
    write(project / "候选" / "第003章_不得采样.md", "候选秘密句。\n")
    write(project / "骨架" / "第004章_不得采样.md", "骨架秘密句。\n")
    write(project / "对标" / "参考书" / "第005章.md", "对标秘密句。\n")
    write(project / "正文" / "候选" / "第006章.md", "内嵌候选秘密句。\n")
    write(project / "正文" / "归档" / "第007章.md", "归档秘密句。\n")
    before = style.read_bytes()
    before_prefix, _, before_suffix = marker_regions(before)

    result = run(project, "update")
    payload = output_json(result)
    require(result.returncode == 0, f"update failed: {result.stderr}")
    require(payload["status"] == "updated", "first update must report updated")
    require(payload["sample_count"] == 2, "only adopted chapters may be sampled")
    require(payload["chapter_from"] == 1 and payload["chapter_to"] == 2, "sample range is wrong")
    after = style.read_bytes()
    after_prefix, machine, after_suffix = marker_regions(after)
    require(after_prefix == before_prefix, "bytes before the machine marker changed")
    require(after_suffix == before_suffix, "bytes after the machine marker changed")
    require(b"\r\n" in machine, "target CRLF convention was not preserved in machine region")
    decoded = machine.decode("utf-8")
    require("机器声纹分析" in decoded, "machine profile heading is missing")
    require("候选秘密句" not in decoded and "对标秘密句" not in decoded, "excluded prose leaked into profile")
    require("归档秘密句" not in decoded and "内嵌候选秘密句" not in decoded, "excluded body subtree leaked into profile")

    second = run(project, "update")
    second_payload = output_json(second)
    require(second.returncode == 0 and second_payload["status"] == "up_to_date", "second update must be idempotent")
    require(style.read_bytes() == after, "idempotent update rewrote content")

    check = run(project, "check")
    require(check.returncode == 0 and output_json(check)["status"] == "up_to_date", "fresh profile must pass check")


def test_check_and_dry_run_are_read_only(root: Path) -> None:
    project, style = make_project(root / "readonly")
    add_adopted_prose(project)
    first = run(project, "update")
    require(first.returncode == 0, "fixture update failed")
    write(project / "正文" / "第001章_起风.md", "# 第一章\n\n改过的正文。\n")
    before = style.read_bytes()

    check = run(project, "check")
    require(check.returncode == 1 and output_json(check)["status"] == "stale", "stale check must exit 1")
    require(style.read_bytes() == before, "check modified the style file")
    dry_run = run(project, "update", "--dry-run")
    dry_payload = output_json(dry_run)
    require(dry_run.returncode == 0 and dry_payload["status"] == "would_update", "dry-run status is wrong")
    require(dry_payload["dry_run"] is True, "dry-run flag is missing")
    require(style.read_bytes() == before, "dry-run modified the style file")


def assert_rejected_without_change(project: Path, style: Path, expected: str) -> None:
    before = style.read_bytes() if style.exists() and style.is_file() else None
    result = run(project, "update")
    payload = output_json(result)
    require(result.returncode == 2, f"expected safety failure, got {result.returncode}: {result.stdout} {result.stderr}")
    require(payload["status"] == "error" and expected in str(payload["error"]), f"missing error fragment: {expected}")
    if before is not None:
        require(style.read_bytes() == before, "rejected update changed the style file")


def test_marker_failures_are_non_destructive(root: Path) -> None:
    missing_project, missing_style = make_project(root / "missing-marker")
    add_adopted_prose(missing_project)
    write(missing_style, "# 文风\n\n作者区。\n")
    assert_rejected_without_change(missing_project, missing_style, "开始标记")

    duplicate_project, duplicate_style = make_project(root / "duplicate-marker")
    add_adopted_prose(duplicate_project)
    data = duplicate_style.read_bytes().replace(END, START + b"\n" + END)
    duplicate_style.write_bytes(data)
    assert_rejected_without_change(duplicate_project, duplicate_style, "开始标记")

    reversed_project, reversed_style = make_project(root / "reversed-marker")
    add_adopted_prose(reversed_project)
    write(reversed_style, "# 文风\n" + END.decode() + "\n" + START.decode() + "\n")
    assert_rejected_without_change(reversed_project, reversed_style, "顺序损坏")


def test_empty_invalid_and_duplicate_samples(root: Path) -> None:
    empty_project, empty_style = make_project(root / "empty")
    (empty_project / "正文").mkdir(parents=True)
    assert_rejected_without_change(empty_project, empty_style, "没有可采样")

    blank_project, blank_style = make_project(root / "blank")
    write(blank_project / "正文" / "第001章_空.md", "# 只有标题\n")
    assert_rejected_without_change(blank_project, blank_style, "没有可分析的正文")

    invalid_project, invalid_style = make_project(root / "invalid-utf8")
    invalid_path = invalid_project / "正文" / "第001章_损坏.md"
    invalid_path.parent.mkdir(parents=True)
    invalid_path.write_bytes(b"\xff\xfe\x00")
    assert_rejected_without_change(invalid_project, invalid_style, "UTF-8")

    duplicate_project, duplicate_style = make_project(root / "duplicate")
    write(duplicate_project / "正文" / "卷一" / "第001章_A.md", "A正文。\n")
    write(duplicate_project / "正文" / "卷二" / "第1章_B.md", "B正文。\n")
    assert_rejected_without_change(duplicate_project, duplicate_style, "重复章号")


def create_symlink(link: Path, target: Path, *, directory: bool = False) -> bool:
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, link, target_is_directory=directory)
        return True
    except (OSError, NotImplementedError):
        return False


def test_symlink_escape_is_rejected(root: Path) -> bool:
    project, style = make_project(root / "sample-link")
    write(project / "正文" / "第001章_合法.md", "合法正文。\n")
    outside = root / "outside.md"
    write(outside, "外部文本不得读取。\n")
    link = project / "正文" / "第002章_链接.md"
    if not create_symlink(link, outside):
        return False
    assert_rejected_without_change(project, style, "符号链接")

    style_project, style_path = make_project(root / "style-link")
    add_adopted_prose(style_project)
    external_style = root / "external-style.md"
    external_style.write_bytes(style_path.read_bytes())
    style_path.unlink()
    if not create_symlink(style_path, external_style):
        return False
    before = external_style.read_bytes()
    result = run(style_project, "update")
    require(result.returncode == 2 and "符号链接" in str(output_json(result)["error"]), "style symlink must be rejected")
    require(external_style.read_bytes() == before, "style symlink target was modified")
    return True


def test_short_evidence_and_digest_change(root: Path) -> None:
    project, style = make_project(root / "evidence")
    long_sentence = "他把很长很长的一段话从头说到尾，中间没有停下，因为他知道门外的人正在等最后那个答案。"
    write(project / "正文" / "第001章_长句.md", f"# 第一章\n\n{long_sentence}\n\n“走吗？”\n")
    first = run(project, "update")
    first_payload = output_json(first)
    require(first.returncode == 0, "evidence fixture update failed")
    machine = marker_regions(style.read_bytes())[1].decode("utf-8")
    evidence_lines = [line for line in machine.splitlines() if " — 「" in line]
    require(evidence_lines, "short evidence lines are missing")
    for line in evidence_lines:
        snippet = line.split("「", 1)[1].rsplit("」", 1)[0]
        require(len(snippet) <= 36, "evidence copied more than the short limit")

    write(project / "正文" / "第001章_长句.md", f"# 第一章\n\n{long_sentence}\n\n“现在就走。”\n")
    stale = run(project, "check")
    stale_payload = output_json(stale)
    require(stale.returncode == 1, "changed adopted prose must stale the profile")
    require(stale_payload["sample_sha256"] != first_payload["sample_sha256"], "sample digest did not change")


def main() -> int:
    tests = [
        test_update_scope_preservation_and_idempotence,
        test_check_and_dry_run_are_read_only,
        test_marker_failures_are_non_destructive,
        test_empty_invalid_and_duplicate_samples,
        test_short_evidence_and_digest_change,
    ]
    passed = 0
    with tempfile.TemporaryDirectory(prefix="author-voice-profile-") as temporary:
        root = Path(temporary)
        for test in tests:
            test(root)
            passed += 1
            print(f"PASS: {test.__name__}")
        symlink_ran = test_symlink_escape_is_rejected(root)
        if symlink_ran:
            passed += 1
            print("PASS: test_symlink_escape_is_rejected")
        else:
            print("note: symbolic-link creation is unavailable; symlink scenario not executed")
    print(f"author voice profile tests: {passed}/{len(tests) + (1 if symlink_ran else 0)} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
