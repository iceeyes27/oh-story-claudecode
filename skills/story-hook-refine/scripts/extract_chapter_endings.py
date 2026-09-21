#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_chapter_endings.py — 批量提取指定范围的章末段落（只报告，不要求修改钩子）

用法：
  python .agents/skills/story-hook-refine/scripts/extract_chapter_endings.py [--dir 正文根] [--from N] [--to N] [--words 词表文件] [--lines N]

行为：
  1. 解析当前书：--dir 未指定时读项目根 `.active-book`（去掉换行），拼 `{书名}/正文`；
     找不到或该书正文不存在 → 明确报错退出（不静默默认）。
  2. 严格识别章节文件：只收文件名匹配 `^第(\\d+)章_` 的 .md/.txt；**跳过正文根下任何
     `.claude/`、`_已知实体.txt`、agent-memory 等非章节文件**（不进入遍历，不猜测）。
  3. 完整性校验（任一失败即报错退出，不静默继续）：
     - 重号：两个文件解析到同一章节号 → 报两文件路径
     - 缺号：目标区间内有编号无文件（按区间起点为 1 或 --from 计算）→ 列缺失号
     - 读取失败：打开/解码失败 → 报文件与异常
  4. 提取每章最后一段（默认 1 段，--lines 可调）；带 --words 时只输出命中词表的章末。
  5. 输出：<章节号>\t<文件名>\t<章末段前 120 字…>；汇总行写到 stderr。

退出码：0 正常；1 参数/识别/完整性错误；2 文件读取错误。
"""
from __future__ import annotations

import argparse
import os
import re
import sys


CHAPTER_RE = re.compile(r"^第(\d+)章_")


def parse_args():
    ap = argparse.ArgumentParser(description="提取每章最后一段，可带词表过滤")
    ap.add_argument("--dir", default=None,
                    help="正文根目录（相对或绝对）；缺省时读 .active-book 解析当前书")
    ap.add_argument("--from", dest="from_n", type=int, default=None,
                    help="起始章节号（含）")
    ap.add_argument("--to", dest="to_n", type=int, default=None,
                    help="结束章节号（含）")
    ap.add_argument("--words", default=None,
                    help="口号词表文件路径；给出则只输出命中词表的章末")
    ap.add_argument("--lines", type=int, default=1,
                    help="提取最后 N 段，默认 1")
    return ap.parse_args()


def resolve_root(explicit: str | None) -> str:
    """--dir 优先；否则读 .active-book 解析当前书正文根。解析失败即报错。"""
    if explicit:
        return explicit
    active = ".active-book"
    if os.path.isfile(active):
        with open(active, encoding="utf-8") as f:
            book = f.read().strip()
        cand = os.path.join(book, "正文")
        if os.path.isdir(cand):
            return cand
        sys.stderr.write(f"[error] .active-book 指向 {book}，但其 正文/ 目录不存在\n")
        sys.exit(1)
    sys.stderr.write(
        "[error] 未指定 --dir 且 .active-book 不可用；请显式传 --dir 或先确认当前书\n")
    sys.exit(1)


def collect_chapters(root: str, from_n: int | None, to_n: int | None):
    """只收「第N章_」命名文件；返回 {num: path}。重号/缺号/读取失败在此校验。"""
    chapters: dict[int, str] = {}
    errors: list[str] = []

    for dirpath, _dirnames, filenames in os.walk(root):
        # 跳过正文根下的隐藏/工具目录（.claude、.git 等），避免扫描非章节文件
        rel = os.path.relpath(dirpath, root)
        if rel != "." and (rel.startswith(".") or os.path.sep + "." in os.path.sep + rel):
            continue
        for fn in filenames:
            m = CHAPTER_RE.match(fn)
            if not m:
                continue  # 非「第N章_」格式：_已知实体.txt、MEMORY.md 等一律忽略
            num = int(m.group(1))
            if from_n is not None and num < from_n:
                continue
            if to_n is not None and num > to_n:
                continue
            full = os.path.join(dirpath, fn)
            if num in chapters:
                errors.append(f"重号 {num}: {chapters[num]} 与 {full}")
            else:
                chapters[num] = full

    if errors:
        sys.stderr.write("[error] 章节文件校验失败：\n  " + "\n  ".join(errors) + "\n")
        sys.exit(1)

    # 缺号校验：区间从 min(from_n 或 1) 到 max(to_n 或最大号)，逐个查
    lo = from_n if from_n is not None else 1
    hi = to_n if to_n is not None else (max(chapters) if chapters else lo - 1)
    missing = [n for n in range(lo, hi + 1) if n not in chapters]
    if missing:
        sys.stderr.write(
            f"[error] 缺号 {len(missing)} 个（{lo}-{hi}）：{missing[:20]}{'…' if len(missing) > 20 else ''}\n")
        sys.exit(1)

    return chapters


def read_endings(chapters: dict[int, str], lines: int):
    """读取每章最后 N 段；返回 [(num, basename, ending)]，读取失败即终止。"""
    result = []
    for num in sorted(chapters):
        fp = chapters[num]
        try:
            with open(fp, encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            sys.stderr.write(f"[error] 读取失败 {fp}: {e}\n")
            sys.exit(2)
        paras = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
        if not paras:
            sys.stderr.write(f"[warn] {fp} 无正文段落\n")
            continue
        ending = "".join(paras[-lines:])
        result.append((num, os.path.basename(fp), ending))
    return result


def main():
    args = parse_args()
    root = resolve_root(args.dir)
    if not os.path.isdir(root):
        sys.stderr.write(f"[error] 正文目录不存在: {root}\n")
        return 1

    chapters = collect_chapters(root, args.from_n, args.to_n)

    words = None
    if args.words:
        with open(args.words, encoding="utf-8") as f:
            words = [w.strip() for w in f.read().splitlines() if w.strip()]

    entries = read_endings(chapters, args.lines)
    hits = 0
    for num, fn, ending in entries:
        short = ending.replace("\n", "").strip()
        if len(short) > 120:
            short = short[:120] + "…"
        if words:
            if any(w in ending for w in words):
                hits += 1
                print(f"{num}\t{fn}\t{short}")
        else:
            print(f"{num}\t{fn}\t{short}")

    if words:
        sys.stderr.write(f"[summary] 区间内章节 {len(entries)}，命中词表章末 {hits}\n")
    else:
        sys.stderr.write(f"[summary] 区间内章节 {len(entries)}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
