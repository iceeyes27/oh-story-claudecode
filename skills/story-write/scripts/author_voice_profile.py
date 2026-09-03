#!/usr/bin/env python3
"""Build a deterministic author-voice profile from adopted chapter prose only."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA = "author-voice-profile/v1"
START_MARKER = b"<!-- author-voice:machine:start -->"
END_MARKER = b"<!-- author-voice:machine:end -->"
STYLE_RELATIVE = Path("设定") / "文风.md"
BODY_DIR = "正文"
EXCLUDED_DIRS = frozenset({"候选", "_历史", "骨架", "拆文库", "对标", "归档", "archive", "archives"})
CHAPTER_RE = re.compile(r"^第0*(\d+)章(?:[_\s-].*)?\.md$", re.IGNORECASE)
CONTENT_CHAR_RE = re.compile(r"[\u3400-\u9fffA-Za-z0-9]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？!?])")
MAX_EVIDENCE_CHARS = 36


class VoiceProfileError(RuntimeError):
    """An expected validation or filesystem boundary failure."""


@dataclass(frozen=True)
class Sample:
    chapter: int
    path: Path
    relative: str
    raw: bytes
    text: str


@dataclass(frozen=True)
class Sentence:
    sample: Sample
    line: int
    index: int
    text: str
    length: int


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VoiceProfileError(message)


def emit(value: object, *, as_json: bool, error: bool = False) -> None:
    if as_json:
        output = json.dumps(value, ensure_ascii=False, sort_keys=True)
    else:
        output = str(value)
    stream = sys.stderr if error else sys.stdout
    stream.flush()
    stream.buffer.write((output + "\n").encode("utf-8"))
    stream.buffer.flush()


def resolved_project(raw: Path) -> Path:
    try:
        project = raw.expanduser().resolve(strict=True)
    except OSError as exc:
        raise VoiceProfileError(f"书项目不可读：{raw}: {exc}") from exc
    require(project.is_dir(), f"书项目不是目录：{project}")
    return project


def require_in_root(root: Path, target: Path, label: str) -> None:
    try:
        target.resolve(strict=True).relative_to(root.resolve(strict=True))
    except (OSError, ValueError) as exc:
        raise VoiceProfileError(f"{label}越出书项目：{target}") from exc


def require_no_symlink_components(root: Path, target: Path, label: str) -> None:
    try:
        relative = target.absolute().relative_to(root.absolute())
    except ValueError as exc:
        raise VoiceProfileError(f"{label}越出书项目：{target}") from exc
    current = root
    for component in relative.parts:
        current = current / component
        require(not current.is_symlink(), f"{label}包含符号链接：{current}")


def read_utf8(path: Path, label: str) -> tuple[bytes, str]:
    try:
        raw = path.read_bytes()
        return raw, raw.decode("utf-8-sig")
    except (OSError, UnicodeError) as exc:
        raise VoiceProfileError(f"{label}不是可读的 UTF-8 文件：{path}: {exc}") from exc


def discover_samples(project: Path) -> list[Sample]:
    body = project / BODY_DIR
    require(body.exists(), f"正文目录不存在：{body}")
    require(body.is_dir(), f"正文路径不是目录：{body}")
    require_no_symlink_components(project, body, "正文目录")
    require_in_root(project, body, "正文目录")

    found: list[Sample] = []
    pending = [body]
    while pending:
        directory = pending.pop()
        try:
            entries = sorted(directory.iterdir(), key=lambda item: item.name)
        except OSError as exc:
            raise VoiceProfileError(f"无法枚举正文目录：{directory}: {exc}") from exc
        child_dirs: list[Path] = []
        for path in entries:
            require(not path.is_symlink(), f"正文样本路径不得使用符号链接：{path}")
            if path.is_dir():
                if path.name not in EXCLUDED_DIRS:
                    require_in_root(body, path, "正文子目录")
                    child_dirs.append(path)
                continue
            match = CHAPTER_RE.match(path.name)
            if not path.is_file() or match is None:
                continue
            require_in_root(body, path, "正文样本")
            raw, prose = read_utf8(path, "正文样本")
            found.append(
                Sample(
                    chapter=int(match.group(1)),
                    path=path,
                    relative=path.relative_to(project).as_posix(),
                    raw=raw,
                    text=prose,
                )
            )
        pending.extend(reversed(child_dirs))

    found.sort(key=lambda item: (item.chapter, item.relative))
    require(found, "正文目录中没有可采样的已采用章节")
    duplicates: dict[int, list[str]] = {}
    for sample in found:
        duplicates.setdefault(sample.chapter, []).append(sample.relative)
    repeated = {chapter: paths for chapter, paths in duplicates.items() if len(paths) > 1}
    require(not repeated, f"正文存在重复章号：{repeated}")
    return found


def sample_digest(samples: Iterable[Sample]) -> str:
    digest = hashlib.sha256()
    for sample in samples:
        relative = sample.relative.encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(sample.raw).to_bytes(8, "big"))
        digest.update(sample.raw)
    return digest.hexdigest()


def content_length(text: str) -> int:
    return len(CONTENT_CHAR_RE.findall(text))


def prose_lines(sample: Sample) -> list[tuple[int, str]]:
    rows: list[tuple[int, str]] = []
    in_comment = False
    for number, raw_line in enumerate(sample.text.splitlines(), start=1):
        line = raw_line.strip()
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if line.startswith("<!--"):
            if "-->" not in line:
                in_comment = True
            continue
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^(?:>|[-*+]\s+|\d+[.)]\s+)", "", line).strip()
        if content_length(line):
            rows.append((number, line))
    return rows


def sentence_rows(sample: Sample, lines: list[tuple[int, str]]) -> list[Sentence]:
    result: list[Sentence] = []
    for line_number, line in lines:
        for index, raw in enumerate(SENTENCE_SPLIT_RE.split(line)):
            sentence = raw.strip()
            length = content_length(sentence)
            if length:
                result.append(Sentence(sample, line_number, index, sentence, length))
    return result


def percentile(values: list[int], numerator: int, denominator: int) -> int:
    require(values, "样本没有可分析的数值")
    ordered = sorted(values)
    index = ((len(ordered) - 1) * numerator) // denominator
    return ordered[index]


def ratio(numerator: int, denominator: int) -> str:
    return f"{(numerator * 100 / denominator) if denominator else 0:.1f}%"


def per_thousand(count: int, total: int) -> str:
    return f"{(count * 1000 / total) if total else 0:.1f}"


def evidence_snippet(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text).replace("`", "").strip()
    if len(normalized) <= MAX_EVIDENCE_CHARS:
        return normalized
    return normalized[: MAX_EVIDENCE_CHARS - 1] + "…"


def choose_evidence(sentences: list[Sentence], median_length: int) -> list[tuple[str, Sentence]]:
    chosen: list[tuple[str, Sentence]] = []
    used: set[tuple[str, int, int]] = set()

    def add(label: str, candidates: Iterable[Sentence]) -> None:
        for item in candidates:
            key = (item.sample.relative, item.line, item.index)
            if key not in used:
                used.add(key)
                chosen.append((label, item))
                return

    ordered = sorted(sentences, key=lambda item: (item.sample.chapter, item.sample.relative, item.line, item.index))
    representative = sorted(
        sentences,
        key=lambda item: (abs(item.length - median_length), item.sample.chapter, item.sample.relative, item.line, item.index),
    )
    add("中位句长", representative)
    add("对话节拍", (item for item in ordered if "“" in item.text or "「" in item.text))
    add("短句节拍", (item for item in ordered if item.length <= 12))
    return chosen[:3]


def render_profile(samples: list[Sample]) -> tuple[str, dict[str, object]]:
    paragraphs: list[tuple[Sample, int, str]] = []
    sentences: list[Sentence] = []
    joined_text: list[str] = []
    for sample in samples:
        lines = prose_lines(sample)
        paragraphs.extend((sample, number, text) for number, text in lines)
        sentences.extend(sentence_rows(sample, lines))
        joined_text.extend(text for _, text in lines)

    require(paragraphs, "已采用章节中没有可分析的正文")
    require(sentences, "已采用章节中没有可分析的句子")
    sentence_lengths = [item.length for item in sentences]
    paragraph_lengths = [content_length(text) for _, _, text in paragraphs]
    total_chars = sum(paragraph_lengths)
    require(total_chars > 0, "已采用章节中没有可分析的文字")
    median_sentence = percentile(sentence_lengths, 1, 2)
    short_sentences = sum(length <= 12 for length in sentence_lengths)
    medium_sentences = sum(13 <= length <= 28 for length in sentence_lengths)
    long_sentences = sum(length >= 29 for length in sentence_lengths)
    dialogue_paragraphs = sum(text.startswith(("“", "「", '"')) for _, _, text in paragraphs)
    punctuation_text = "".join(joined_text)
    digest = sample_digest(samples)
    evidence = choose_evidence(sentences, median_sentence)

    lines = [
        "## 机器声纹分析",
        "",
        f"- schema：`{SCHEMA}`",
        f"- 样本：{len(samples)} 章（第{samples[0].chapter}–{samples[-1].chapter}章），{total_chars} 个可计算文字",
        f"- 范围：`{samples[0].relative}` → `{samples[-1].relative}`",
        f"- 样本摘要：`sha256:{digest}`",
        "- 结论边界：仅为已采用正文的确定性统计，不代表文学质量或读者偏好提升。",
        "",
        "### 可复现统计",
        "",
        f"- 句长：P25 {percentile(sentence_lengths, 1, 4)}，中位 {median_sentence}，P75 {percentile(sentence_lengths, 3, 4)}。",
        f"- 句长带：短句≤12 {ratio(short_sentences, len(sentences))}，中句 13–28 {ratio(medium_sentences, len(sentences))}，长句≥29 {ratio(long_sentences, len(sentences))}。",
        f"- 段落：{len(paragraphs)} 段，中位 {percentile(paragraph_lengths, 1, 2)} 字，P75 {percentile(paragraph_lengths, 3, 4)} 字。",
        f"- 对话段：{ratio(dialogue_paragraphs, len(paragraphs))}（以引号开头的非空段落）。",
        "- 标点密度（每千个可计算文字）："
        + "，".join(
            f"{mark} {per_thousand(punctuation_text.count(mark), total_chars)}"
            for mark in ("。", "，", "？", "！", "；", "：", "、")
        )
        + "。",
        "",
        "### 短证据定位",
        "",
    ]
    for label, item in evidence:
        lines.append(f"- {label}：`{item.sample.relative}:{item.line}` — 「{evidence_snippet(item.text)}」")

    metrics: dict[str, object] = {
        "schema": SCHEMA,
        "sample_count": len(samples),
        "chapter_from": samples[0].chapter,
        "chapter_to": samples[-1].chapter,
        "sample_sha256": digest,
        "content_chars": total_chars,
        "sentence_count": len(sentences),
        "paragraph_count": len(paragraphs),
        "evidence_count": len(evidence),
    }
    return "\n".join(lines) + "\n", metrics


def style_document(project: Path) -> tuple[Path, bytes, bytes]:
    target = project / STYLE_RELATIVE
    require(target.exists(), f"文风文件不存在：{target}")
    require(target.is_file(), f"文风路径不是文件：{target}")
    require_no_symlink_components(project, target, "文风文件")
    require_in_root(project, target, "文风文件")
    try:
        data = target.read_bytes()
    except OSError as exc:
        raise VoiceProfileError(f"文风文件不可读：{target}: {exc}") from exc
    require(data.count(START_MARKER) == 1, "文风文件必须且只能有一个声纹机器区开始标记")
    require(data.count(END_MARKER) == 1, "文风文件必须且只能有一个声纹机器区结束标记")
    start = data.index(START_MARKER)
    end = data.index(END_MARKER)
    require(start < end, "声纹机器区标记顺序损坏")
    return target, data, b"\r\n" if b"\r\n" in data else b"\n"


def compose_document(data: bytes, newline: bytes, profile: str) -> bytes:
    start = data.index(START_MARKER)
    end = data.index(END_MARKER)
    profile_bytes = profile.encode("utf-8").replace(b"\n", newline).rstrip(b"\r\n")
    return data[:start] + START_MARKER + newline + profile_bytes + newline + data[end:]


def atomic_replace(path: Path, expected: bytes, replacement: bytes) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(replacement)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, mode)
            require(path.read_bytes() == expected, "文风文件在分析期间已变化，拒绝覆盖")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()
    except VoiceProfileError:
        raise
    except OSError as exc:
        raise VoiceProfileError(f"无法更新文风机器区：{path}: {exc}") from exc


def execute(args: argparse.Namespace) -> int:
    project = resolved_project(args.project)
    target, current, newline = style_document(project)
    samples = discover_samples(project)
    profile, metrics = render_profile(samples)
    expected = compose_document(current, newline, profile)
    changed = current != expected
    relative_target = target.relative_to(project).as_posix()

    if args.command == "check":
        status = "stale" if changed else "up_to_date"
        result = {"status": status, "changed": changed, "target": relative_target, **metrics}
        emit(result if args.json else f"{status}: {relative_target}", as_json=args.json)
        return 1 if changed else 0

    if args.dry_run:
        status = "would_update" if changed else "up_to_date"
    elif changed:
        atomic_replace(target, current, expected)
        status = "updated"
    else:
        status = "up_to_date"
    result = {"status": status, "changed": changed, "dry_run": bool(args.dry_run), "target": relative_target, **metrics}
    emit(result if args.json else f"{status}: {relative_target}", as_json=args.json)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="仅从已采用正文生成确定性作者声纹统计，保护文风文件的作者区。"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="只读检查机器区是否与已采用正文一致")
    update = commands.add_parser("update", help="仅更新文风文件的固定机器区")
    for command in (check, update):
        command.add_argument("--project", type=Path, required=True, help="书项目目录")
        command.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    update.add_argument("--dry-run", action="store_true", help="报告是否会变化，不写入文件")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return execute(args)
    except VoiceProfileError as exc:
        payload = {"status": "error", "error": str(exc)}
        emit(payload if getattr(args, "json", False) else f"ERROR: {exc}", as_json=getattr(args, "json", False), error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
