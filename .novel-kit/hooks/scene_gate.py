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
TOOLS = {'Write', 'Edit', 'MultiEdit', 'NotebookEdit', 'apply_patch'}


def patch_paths(command):
    """Inspect every add/update/delete and both sides of a move before any patch runs."""
    from novel import require
    require(isinstance(command, str), 'apply_patch 缺少文字 command')
    lines = command.strip().splitlines()
    require(len(lines) >= 3 and lines[0] == '*** Begin Patch' and lines[-1] == '*** End Patch', '無法解析 apply_patch 邊界')
    paths, operation = [], None
    for line in lines[1:-1]:
        matched = False
        for label in ('Add File', 'Update File', 'Delete File', 'Move to'):
            prefix = '*** '+label+': '
            if line.startswith(prefix):
                require(label != 'Move to' or operation == 'Update File', 'Move to 必須接在 Update File 後')
                path = line[len(prefix):]
                require(bool(path.strip()), '補丁路徑不可空白')
                paths.append(path)
                operation = label
                matched = True
                break
        if matched:
            continue
        require(operation is not None and (line.startswith((' ', '+', '-', '@@')) or line == '*** End of File' or line == ''), '無法解析補丁內容')
    require(paths, '補丁未列出目標')
    return paths


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
        root = Path(os.environ.get('NOVEL_KIT_ROOT') or os.environ.get('CLAUDE_PROJECT_DIR') or Path(__file__).resolve().parents[2]).resolve()
        tool_input = data.get('tool_input')
        if not isinstance(tool_input, dict):
            raise Invalid('寫檔工具缺少有效 tool_input')
        if data['tool_name'] == 'apply_patch':
            paths = patch_paths(tool_input.get('command'))
        else:
            path = tool_input.get('file_path') or tool_input.get('notebook_path')
            if not path:
                raise Invalid('寫檔工具缺少 file_path 或 notebook_path')
            paths = [path]
        cwd = Path(data.get('cwd') or root)
        if not cwd.is_absolute():
            raise Invalid('Hook cwd 必須為絕對路徑')
        for path in paths:
            if not isinstance(path, str):
                raise Invalid('寫檔路徑必須是字串')
            target = Path(path)
            check(root, str(target if target.is_absolute() else cwd / target))
        return 0
    except UnicodeDecodeError:
        report('Hook 輸入不是有效的 UTF-8')
        return 2
    except Exception as e:  # Strict gate: a failing hook must never let the write through.
        report(str(e) or type(e).__name__)
        return 2


if __name__ == '__main__':
    sys.exit(main())
