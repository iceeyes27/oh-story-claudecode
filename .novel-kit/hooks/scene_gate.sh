#!/usr/bin/env bash
# PreToolUse 写工具关卡启动器（Write/Edit/MultiEdit/NotebookEdit/apply_patch）。
# Claude Code 只把退出 2 当作拦截，其他非零会放行写入；
# Python 关卡的任何意外退出一律映射为 2。
# 没有有效 Python 时无法可靠解析路径身份，匹配的写工具全部拦截。

case $0 in
  *[\\/]*) here=${0%[\\/]*} ;;
  *) here=. ;;
esac

# stdin 存在變數中轉交（不 export，避免大內容觸發 E2BIG）。
# 優先用 cat 整塊讀取：內建 read 在管道上逐位元組讀，大內容可慢到觸發 Hook 逾時而被放行。
# PATH 沒有 cat 時才退回 read（/dev/stdin 在 Windows 的 MSYS 環境不一定存在，不可依賴）。
if command -v cat >/dev/null 2>&1; then
  input=$(cat)
else
  IFS= read -r -d '' input || true
fi
printf '%s' "$input" | "${BASH:-bash}" "$here/../scripts/py.sh" "$here/scene_gate.py"
code=$?
case $code in
  0 | 2) exit "$code" ;;
  127) ;;
  *)
    printf '【场景关卡】关卡程序异常退出（退出码 %s），已拦截。\n' "$code" >&2
    exit 2
    ;;
esac

# 无有效 Python：只分辨工具名，不尝试用字符串判定路径是否安全。
# 先查写工具，避免嵌套的同名字段盖过宿主提供的写工具名。
write_tool_re='"tool_name"[[:space:]]*:[[:space:]]*"(Write|Edit|MultiEdit|NotebookEdit|apply_patch)"'
tool_name_re='"tool_name"[[:space:]]*:[[:space:]]*"[^"\\]*"'
if [[ ! $input =~ $write_tool_re && $input =~ $tool_name_re ]]; then
  exit 0
fi
printf '【场景关卡】找不到可用的 Python 3.9+，无法可靠核对写入目标，已拦截写工具。请修复 PATH 中的 python3、python 或 py -3，再运行 doctor 检查。\n' >&2
exit 2
