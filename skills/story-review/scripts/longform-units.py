#!/usr/bin/env python3
"""Read unit boundaries using the canonical outline parser, without writing views."""
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from outline_view import parse, CH_RANGE


def units(book):
    result = []
    for file in sorted((book / "大纲").glob("卷纲*.md")):
        if file.is_symlink():
            raise ValueError(f"卷纲不能是符号链接：{file.name}")
        _, sections = parse(file.read_text(encoding="utf-8-sig"))
        for section in sections:
            if "剧情单元" not in section.title or section.status == "已退役" or section.kind == "批次底稿":
                continue
            if not section.unit:
                raise ValueError(f"剧情单元缺稳定 ID：{file.name}:{section.start + 1}")
            spans = [CH_RANGE.search(line.replace("**", "")) for line in section.lines]
            spans = [tuple(map(int, match.groups())) for match in spans if match]
            if len(set(spans)) != 1 or not spans or not 1 <= spans[0][0] <= spans[0][1]:
                raise ValueError(f"单元缺明确唯一章节范围：{section.unit}")
            result.append({"id": section.unit, "source": file.relative_to(book).as_posix(),
                           "from": spans[0][0], "to": spans[0][1]})
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(units(Path(sys.argv[1]).resolve()), ensure_ascii=False))
    except (ValueError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
