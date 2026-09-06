#!/bin/bash
# check-prose-after-write.sh — PostToolUse/PostToolUseFailure(Bash|Write|Edit|MultiEdit)
# 正文写入成功或失败后运行共享确定性检查。写后事件只能向 Claude 增加上下文，不能撤销
# 已经发生的文件写入；失败命令也可能已部分写入，因此 PostToolUseFailure 使用同一检查器。
#
# Bash 目标解析、正文判定和内容检查统一走 story_hook_core.js；本文件只负责 Claude Hook I/O。
# node 不可用时静默放行，session-start.sh 会报告运行依赖缺失。
set -euo pipefail
export LC_ALL=C

source "$(dirname "$0")/lib/common.sh"

HOOK_INPUT="${CLAUDE_TOOL_INPUT:-}"
if [ -z "$HOOK_INPUT" ] && [ ! -t 0 ]; then
  HOOK_INPUT="$(cat)"
fi
[ -n "$HOOK_INPUT" ] || exit 0

node -e "" >/dev/null 2>&1 || exit 0
CLI="$(dirname "$0")/story_hook_cli.js"
[ -f "$CLI" ] || exit 0
ROOT=$(project_root)

# prose-after-event 始终以 0 退出；有发现时输出合法 Claude hook JSON，
# 无发现、负载无效或目标不存在时保持静默。
printf '%s' "$HOOK_INPUT" | node "$CLI" prose-after-event "$ROOT" 2>/dev/null || true
exit 0
