# python3-shim.sh — source 本文件后，脚本里既有的裸 `python3` 调用在 Windows 上也能跑。
#
# python.org 安装后，Windows 的 `python3` 会落到 Microsoft Store 占位程序并以 exit 49
# 静默失败（见 scripts/check-python-invocation.sh 与 issue #121）。技能文档里禁止裸调
# python3，但仓库自身的 CI 脚本历史上大量使用；逐处改写既啰嗦又容易误伤 heredoc 和断言
# 里的字面量。这里改为定义一个同名 shell 函数覆盖 PATH 查找——shell 函数优先于外部命令，
# 命令替换与进程替换同属当前 shell 也能继承。
#
# 用法（在 set -euo pipefail 与 REPO_ROOT 之后）：
#   . "$REPO_ROOT/scripts/python3-shim.sh"

if ! python3 -c "" >/dev/null 2>&1; then
  if python -c "" >/dev/null 2>&1; then
    python3() { python "$@"; }
  elif py -3 -c "" >/dev/null 2>&1; then
    python3() { py -3 "$@"; }
  else
    echo "FAIL: Python 3 is required (tried python3, python, and py)" >&2
    exit 1
  fi
fi
