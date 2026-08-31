#!/usr/bin/env python3
"""check-outline-causal.py — 细纲跨章因果字段校验（读者逻辑层）

现有细纲字段全是情绪营销与结构字段，没有一个记录「本章为什么发生」。因果链从
细纲阶段就没有落点，成稿自然接不上（读者反馈：逻辑不通）。本脚本校验每章细纲的
三个因果字段，并在最便宜的位置（写正文前）拦截因果断裂。

三字段（见 story-outline.md 细纲必填项）：
  - 前因      ：本章由此前哪一章的什么已发生事实驱动；开篇写「开篇无前因」
  - 后果指向  ：本章产生的、后续章节会用到的结果/伏笔/承诺
  - 读者已知  ：进入本章时读者手上应有/尚无的关键信息

严重度分级（稳健性关键）：
  - 前因指向未来章 / 不存在的章  = blocking（逻辑错误）
  - 字段缺失 / 占位              = 默认 advisory；--strict 时 blocking
  - 有 _tracking-state.json 且前因指向尚未成稿的章 = advisory（软提示）

退出码：0 无 blocking / 1 有 blocking / 2 参数或读取错误
用法： python check-outline-causal.py <书目录> [--json] [--strict] [--from=N] [--to=N]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Windows 默认 locale（cp936）会让管道输出与调用方的 utf-8 解码不匹配，强制 utf-8 输出
for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8")
        except Exception:
            pass

FIELDS = ("前因", "后果指向", "读者已知")
PLACEHOLDER = re.compile(r"^(待补充|待定|TBD|tbd|___+|\.\.\.|—+|-+)?$")
CH_NO = re.compile(r"第\s*(\d+)\s*章")
OPENING = re.compile(r"开篇无前因|无前因|首章|开篇章")
GENERIC_EVENT = re.compile(r"^(ok|OK|上一章|前文|已有事件|某事|这件事|事件|情节|结果)$")


def find_book(root: Path) -> Path | None:
    if not root.exists():
        return None
    if (root / "大纲").is_dir():
        return root
    # 允许直接传 大纲 目录
    if root.name == "大纲":
        return root.parent
    return root


def outline_dir(book: Path) -> Path:
    d = book / "大纲"
    return d if d.is_dir() else book


def chapter_no(fn: str) -> int | None:
    m = re.search(r"细纲_第(\d+)章", fn)
    return int(m.group(1)) if m else None


def extract_field(text: str, field: str) -> str | None:
    """返回 `- 前因：VALUE` 的 VALUE；不存在返回 None。"""
    for line in text.splitlines():
        m = re.match(r"^\s*-\s*" + re.escape(field) + r"\s*[：:]\s*(.*)$", line)
        if m:
            return m.group(1).strip()
    return None


def load_tracking_last_chapter(book: Path) -> int | None:
    p = book / "追踪" / "_tracking-state.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None
    for key in ("last_committed_chapter", "current_chapter", "chapter"):
        v = data.get(key)
        if isinstance(v, int):
            return v
    return None


def normalized_text(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z一-龥]", "", value)


def event_anchor_exists(book: Path, source_outline: Path, source_chapter: int, event: str) -> bool:
    event = event.strip(" ：:")
    if len(normalized_text(event)) < 4 or GENERIC_EVENT.fullmatch(event):
        return False
    sources = [source_outline]
    body = book / "正文"
    if body.is_dir():
        sources.extend(body.glob(f"第{source_chapter:03d}章_*.md"))
        sources.extend(body.glob(f"第{source_chapter}章_*.md"))
    records = book / "追踪" / "逐章记录"
    if records.is_dir():
        sources.extend(records.glob(f"第{source_chapter:03d}章.md"))
        sources.extend(records.glob(f"第{source_chapter}章.md"))
    corpus_parts = []
    for source in sources:
        try:
            corpus_parts.append(source.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError):
            continue
    corpus = normalized_text("\n".join(corpus_parts))
    needle = normalized_text(event)
    if needle and needle in corpus:
        return True
    tokens = [
        token for token in re.findall(r"[0-9A-Za-z一-龥]{2,}", event)
        if normalized_text(token) not in {"主角", "本章", "上一章", "已经", "发生", "事情", "结果"}
    ]
    strong = [normalized_text(token) for token in tokens if len(normalized_text(token)) >= 4]
    return any(token in corpus for token in strong)


def analyze(book: Path, *, strict: bool = False, start: int | None = None, end: int | None = None):
    od = outline_dir(book)
    outlines = sorted(od.glob("细纲_第*.md"), key=lambda p: chapter_no(p.name) or 0)
    existing = {chapter_no(p.name) for p in outlines if chapter_no(p.name)}
    by_chapter = {chapter_no(p.name): p for p in outlines if chapter_no(p.name)}
    last_committed = load_tracking_last_chapter(book)

    findings = []
    for p in outlines:
        num = chapter_no(p.name)
        if num is None:
            continue
        if start is not None and num < start:
            continue
        if end is not None and num > end:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception as exc:
            findings.append({"chapter": num, "severity": "advisory", "code": "read-error",
                             "msg": f"读取失败：{exc}"})
            continue
        # 旧项目默认 advisory；新写作路径 --strict 阻断。
        for field in FIELDS:
            val = extract_field(text, field)
            if val is None:
                findings.append({"chapter": num, "severity": "blocking" if strict else "advisory", "code": "missing-field",
                                 "msg": f"缺少「{field}」因果字段（建议补建）"})
            elif PLACEHOLDER.match(val):
                findings.append({"chapter": num, "severity": "blocking" if strict else "advisory", "code": "placeholder-field",
                                 "msg": f"「{field}」是占位，未实填"})
        # 前因章号逻辑 → blocking
        cause = extract_field(text, "前因")
        if cause and not PLACEHOLDER.match(cause) and not OPENING.search(cause):
            m = CH_NO.search(cause)
            if not m:
                findings.append({"chapter": num, "severity": "blocking" if strict else "advisory", "code": "cause-no-chapter",
                                 "msg": "「前因」未指向具体章号（建议写「第N章：事件」或「开篇无前因」）"})
            else:
                cnum = int(m.group(1))
                if cnum >= num:
                    findings.append({"chapter": num, "severity": "blocking", "code": "cause-future",
                                     "msg": f"「前因」指向第{cnum}章，不早于本章第{num}章（不能拿未来/本章当前因）"})
                elif cnum < 1 or (existing and cnum not in existing):
                    findings.append({"chapter": num, "severity": "blocking", "code": "cause-missing",
                                     "msg": f"「前因」指向第{cnum}章，但该章细纲不存在"})
                elif last_committed is not None and cnum > last_committed:
                    findings.append({"chapter": num, "severity": "blocking" if strict else "advisory", "code": "cause-uncommitted",
                                     "msg": f"「前因」指向第{cnum}章，但追踪显示只成稿到第{last_committed}章（该前因或尚未真正发生）"})
                else:
                    event = cause[m.end():].lstrip(" ：:")
                    source = by_chapter.get(cnum)
                    if strict and (source is None or not event_anchor_exists(book, source, cnum, event)):
                        findings.append({"chapter": num, "severity": "blocking", "code": "cause-event-missing",
                                         "msg": f"「前因」事件在第{cnum}章正文/细纲/追踪记录中找不到具体锚点：{event or '（未填写事件）'}"})
    selected_count = sum(
        1 for p in outlines
        if (start is None or (chapter_no(p.name) or 0) >= start)
        and (end is None or (chapter_no(p.name) or 0) <= end)
    )
    return findings, selected_count


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    json_mode = "--json" in argv
    strict = "--strict" in argv
    def number_option(prefix):
        raw = next((a[len(prefix):] for a in argv if a.startswith(prefix)), None)
        try:
            return int(raw) if raw is not None else None
        except ValueError:
            return -1
    start = number_option("--from=")
    end = number_option("--to=")
    if not args:
        print("用法: python check-outline-causal.py <书目录> [--json] [--strict] [--from=N] [--to=N]", file=sys.stderr)
        return 2
    if start == -1 or end == -1 or (start is not None and start < 1) or (end is not None and end < 1) or (start and end and start > end):
        print("参数错误：--from/--to 必须是正整数且 from <= to", file=sys.stderr)
        return 2
    book = find_book(Path(args[0]))
    if book is None or not outline_dir(book).exists():
        print(f"读取错误：找不到大纲目录 {args[0]}", file=sys.stderr)
        return 2
    findings, n = analyze(book, strict=strict, start=start, end=end)
    if n == 0:
        print(f"读取错误：{book}/大纲 下没有「细纲_第N章.md」", file=sys.stderr)
        return 2
    blocking = [f for f in findings if f["severity"] == "blocking"]
    if json_mode:
        print(json.dumps({"outlines": n, "blocking": len(blocking), "findings": findings},
                         ensure_ascii=False, indent=2))
    else:
        print(f"细纲因果字段检查 · 共 {n} 章，findings {len(findings)}（blocking {len(blocking)}）")
        print("—" * 60)
        for f in sorted(findings, key=lambda x: (x["severity"] != "blocking", x["chapter"])):
            tag = "[blocking]" if f["severity"] == "blocking" else "[advisory]"
            print(f"{tag} 第{f['chapter']}章 · {f['msg']}")
        print("—" * 60)
        print("blocking = 因果逻辑错误；默认缺字段为 advisory，--strict 时缺字段、占位和悬空事件也 blocking。")
    return 1 if blocking else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
