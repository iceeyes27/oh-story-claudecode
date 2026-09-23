#!/usr/bin/env python3
"""場景關卡：寫入新的場景草稿檔之前，檢查細綱與上一個場景的狀態。

由 Claude Code 的 PreToolUse hook 呼叫。只攔「新建」草稿/第NNN章/場景MM.md；
修改已存在的場景檔、寫入其他檔案一律放行。
exit 0 = 放行；exit 2 = 攔下（stderr 的訊息會回傳給 Claude）。
"""
import json
import os
import re
import sys

SCENE_RE = re.compile(r"草稿/第(\d+)章/場景(\d+)\.md$")


def block(msg):
    sys.stderr.buffer.write(("【場景關卡】" + msg + "\n").encode("utf-8"))
    sys.exit(2)


def load_rows(proj):
    path = os.path.join(proj, "追蹤", "場景狀態.md")
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            m = re.search(r"(\d+)", cells[0])
            if not m:
                continue  # 表頭或分隔線
            ch = int(m.group(1))
            unit = cells[1]
            sm = re.search(r"場景\s*0*(\d+)", unit)
            if sm:
                unit = int(sm.group(1))
            rows.append((ch, unit, cells[2]))
    return rows


def main():
    raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except ValueError:
        return 0
    if data.get("tool_name") != "Write":
        return 0

    file_path = (data.get("tool_input") or {}).get("file_path") or ""
    m = SCENE_RE.search(file_path.replace("\\", "/"))
    if not m:
        return 0

    proj = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    abs_path = file_path if os.path.isabs(file_path) else os.path.join(proj, file_path)
    if os.path.exists(abs_path):
        return 0  # 修改既有場景（修正、使用者要求修改）不攔

    ch, sc = int(m.group(1)), int(m.group(2))
    label = f"第{ch:03d}章 場景{sc:02d}"
    rows = load_rows(proj)

    revising = [r for r in rows if r[2] == "修訂中"]
    if revising:
        chs = "、".join(f"第{r[0]:03d}章" for r in revising)
        block(f"{chs} 正在修訂中。修訂完成前不得寫新場景。")

    if not os.path.exists(os.path.join(proj, "大綱", "細綱", f"第{ch:03d}章.md")):
        block(f"找不到 大綱/細綱/第{ch:03d}章.md。請先用 /plan-chapter 規劃並確認細綱。")

    status = {(r[0], r[1]): r[2] for r in rows}
    if (ch, sc) not in status:
        block(f"追蹤/場景狀態.md 沒有 {label}。細綱尚未經作者確認，或此場景不在細綱中。")

    pending = [r for r in rows if r[0] == ch and r[2] == "待審"]
    if pending:
        block(f"第{ch:03d}章有場景正在等作者審核，審核通過前不得寫新場景。")

    if sc > 1:
        prev = status.get((ch, sc - 1))
        if prev != "已通過":
            block(f"上一個場景（場景{sc - 1:02d}）狀態是「{prev or '未登記'}」，必須等作者回覆「通過」才能寫 {label}。")
    elif ch > 1:
        prev_rows = [r for r in rows if r[0] == ch - 1 and r[1] != "修訂"]
        if prev_rows:
            if status.get((ch - 1, "收尾")) != "已通過":
                block(f"第{ch - 1:03d}章的章節收尾尚未通過，不能開始第{ch:03d}章。")
        elif not os.path.exists(os.path.join(proj, "正文", f"第{ch - 1:03d}章.md")):
            block(f"找不到上一章 正文/第{ch - 1:03d}章.md，也沒有它的場景紀錄。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
