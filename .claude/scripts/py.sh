#!/bin/sh
# 以 UTF-8 I/O 執行 Python 3.9+，不依賴直譯器叫 python3。
# 依序探測 python3 → python → py -3；版本探測會排除 Windows 的
# Microsoft Store 佔位程式（退出 49）與 Python 2。都不可用時退出 127。
# 用法：bash .claude/scripts/py.sh .claude/scripts/novel.py <命令> …
probe='import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
export PYTHONUTF8 PYTHONIOENCODING

if python3 -c "$probe" </dev/null >/dev/null 2>&1; then exec python3 "$@"; fi
if python -c "$probe" </dev/null >/dev/null 2>&1; then exec python "$@"; fi
if py -3 -c "$probe" </dev/null >/dev/null 2>&1; then exec py -3 "$@"; fi

echo '【Python】找不到可用的 Python 3.9+（已依序嘗試 python3、python、py -3）。請安裝 Python 3.9 以上，並確認其中一個命令可在 PATH 中執行。' >&2
exit 127
