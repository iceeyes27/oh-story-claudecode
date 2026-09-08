#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性工具：从范围内文件里剥掉 OpenCode 引用。

只处理形态规整的机械替换；剩余的按文件人工处理。每条规则都统计命中次数并打印，
命中 0 次不算错（不同文件覆盖的规则子集不同），但总命中为 0 会退非零码，
避免编码问题导致「静默什么都没改」。
"""
import pathlib
import sys

RULES = [
    # agent 查找链：去掉中间的 .opencode 一跳
    ("`.claude/agents/{agent}.md` → `.opencode/agents/{agent}.md` → `.codex/agents/{agent}.toml`",
     "`.claude/agents/{agent}.md` → `.codex/agents/{agent}.toml`"),
    ("；不存在时再检查 `.opencode/agents/`，再不存在时检查 `.codex/agents/`",
     "；不存在时再检查 `.codex/agents/`"),
    ("；不存在时再检查 `.opencode/agents/`，再不存在时检查 `.codex/agents/`）",
     "；不存在时再检查 `.codex/agents/`）"),
    ("`.claude/agents/story-explorer.md` → `.opencode/agents/` → `.codex/agents/`",
     "`.claude/agents/story-explorer.md` → `.codex/agents/`"),
    ("`.claude/agents/narrative-writer.md` → `.opencode/agents/` → `.codex/agents/`",
     "`.claude/agents/narrative-writer.md` → `.codex/agents/`"),
    ("`.claude/agents/consistency-checker.md` → `.opencode/agents/` → `.codex/agents/`",
     "`.claude/agents/consistency-checker.md` → `.codex/agents/`"),
    # 平台清单
    ("Claude Code / OpenCode / Codex / ZCode / OpenClaw", "Claude Code / Codex / ZCode / OpenClaw"),
    ("Claude Code / OpenCode / Codex / Google Antigravity / ZCode / OpenClaw / Reasonix",
     "Claude Code / Codex / Google Antigravity / ZCode / OpenClaw / Reasonix"),
    ("Claude Code / OpenCode / Codex", "Claude Code / Codex"),
    ("Claude / OpenCode / Codex", "Claude / Codex"),
    ("`.claude/skills/`、`.codex/skills/`、`.opencode/skills/`、`.zcode/skills/`",
     "`.claude/skills/`、`.codex/skills/`、`.zcode/skills/`"),
]


def main(paths: list[str]) -> int:
    totals = {old: 0 for old, _ in RULES}
    for name in paths:
        path = pathlib.Path(name)
        if not path.is_file():
            print(f"skip (missing): {name}", file=sys.stderr)
            continue
        text = original = path.read_text(encoding="utf-8")
        for old, new in RULES:
            hits = text.count(old)
            if hits:
                totals[old] += hits
                text = text.replace(old, new)
        if text != original:
            path.write_text(text, encoding="utf-8", newline="\n")
            print(f"rewrote: {name}")
    print()
    for old, count in totals.items():
        print(f"{count:>3}x  {old[:70]}")
    total = sum(totals.values())
    print(f"\ntotal replacements: {total}")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
