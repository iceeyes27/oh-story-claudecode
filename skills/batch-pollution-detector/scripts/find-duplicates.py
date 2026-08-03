#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨文件重复长句检测：定位脚本批量插入的复读污染。
用法: <Python 3 解释器> find-duplicates.py <文件或目录> [--min-len 18] [--min-count 2]
只报告，不改文。"""
import sys, os, glob, re
from collections import defaultdict

def get_files(path):
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "*.md")))
    return [path]

def split_sentences(text):
    # 按句号/问号/叹号/分号切句（保留对话引号内也切，因为复读句常在引号内）
    parts = re.split(r'[。！？；\n]', text)
    return [p.strip() for p in parts if p.strip()]

def main():
    if len(sys.argv) < 2:
        print("用法: <Python 3 解释器> find-duplicates.py <文件或目录> [--min-len 18] [--min-count 2]")
        sys.exit(1)
    path = sys.argv[1]
    min_len = 18
    min_count = 2
    if "--min-len" in sys.argv:
        min_len = int(sys.argv[sys.argv.index("--min-len")+1])
    if "--min-count" in sys.argv:
        min_count = int(sys.argv[sys.argv.index("--min-count")+1])

    files = get_files(path)
    if not files:
        print("未找到文件"); sys.exit(0)

    counter = defaultdict(list)  # sentence -> [(file, line)]
    for f in files:
        try:
            lines = open(f, encoding="utf-8").read().splitlines()
        except Exception as e:
            print(f"读取失败 {f}: {e}"); continue
        for i, line in enumerate(lines, 1):
            for sent in split_sentences(line):
                if len(sent) >= min_len:
                    counter[sent].append((os.path.basename(f), i))

    flagged = 0
    for sent, locs in sorted(counter.items(), key=lambda x: -len(x[1])):
        if len(locs) >= min_count:
            flagged += 1
            files_list = ", ".join(f"{f}:{l}" for f, l in locs)
            print(f"×{len(locs)} | {sent}")
            print(f"    出现: {files_list}")
    print(f"\n共 {flagged} 句重复 (阈值: ≥{min_len}字, ≥{min_count}次)")

if __name__ == "__main__":
    main()
