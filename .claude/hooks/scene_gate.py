#!/usr/bin/env python3
"""PreToolUse guard for file-writing tools. Shell/external editor writes are not intercepted.

Claude Code only treats exit 2 as a block; any other failure lets the write
through. Every error path therefore exits 2, and I/O never depends on the
locale (Chinese Windows defaults to GBK/cp950).
"""
import json
import os
from pathlib import Path
import sys

# Official file-writing tools; MultiEdit is kept for older Claude Code versions.
TOOLS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit'}


def report(message):
    data = ('【場景關卡】' + message + '\n').encode('utf-8', 'backslashreplace')
    try:
        sys.stderr.buffer.write(data)
        sys.stderr.buffer.flush()
    except Exception:
        pass


def main():
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
        from novel import check, Invalid
        # Claude Code sends raw UTF-8 JSON; strict decoding rejects anything else.
        data = json.loads(sys.stdin.buffer.read().decode('utf-8'))
        if not isinstance(data, dict):
            raise Invalid('Hook 輸入必須是物件')
        if data.get('tool_name') not in TOOLS:
            return 0
        root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or os.getcwd()).resolve()
        tool_input = data.get('tool_input')
        if not isinstance(tool_input, dict):
            raise Invalid('寫檔工具缺少有效 tool_input')
        # NotebookEdit names its target notebook_path.
        path = tool_input.get('file_path') or tool_input.get('notebook_path')
        if not path:
            raise Invalid('寫檔工具缺少 file_path 或 notebook_path')
        check(root, path)
        return 0
    except UnicodeDecodeError:
        report('Hook 輸入不是有效的 UTF-8')
        return 2
    except Exception as e:  # Strict gate: a failing hook must never let the write through.
        report(str(e) or type(e).__name__)
        return 2


if __name__ == '__main__':
    sys.exit(main())
