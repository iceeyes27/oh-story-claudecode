#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引号/括号平衡检查：删除污染句后验证标点是否失衡。
用法: python3 check-balance.py <文件或目录>
输出失衡文件列表。"""
import sys, os, glob

def get_files(path):
    if os.path.isdir(path):
        return sorted(glob.glob(os.path.join(path, "*.md")))
    return [path]

def main():
    if len(sys.argv) < 2:
        print("用法: python3 check-balance.py <文件或目录>")
        sys.exit(1)
    path = sys.argv[1]
    files = get_files(path)
    bad = 0
    for f in files:
        try:
            s = open(f, encoding="utf-8").read()
        except Exception as e:
            print(f"读取失败 {f}: {e}"); continue
        name = os.path.basename(f)
        issues = []
        for label, op, cl in [("中文双引号", "\u201c", "\u201d"),
                               ("中文单引号", "\u2018", "\u2019"),
                               ("ASCII双引号", '"', '"')]:
            o, c = s.count(op), s.count(cl)
            if o != c:
                issues.append(f"{label} 开{o} 闭{c}")
        if issues:
            bad += 1
            print(f"{name}: {'; '.join(issues)}")
    print(f"共 {bad} 个文件引号失衡" if bad else "全部引号平衡 ✓")

if __name__ == "__main__":
    main()
