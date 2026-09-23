#!/usr/bin/env python3
"""PreToolUse guard for Write/Edit. Shell/external editor writes are not intercepted."""
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from novel import check, Invalid


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            raise Invalid('Hook 輸入必須是物件')
        if data.get('tool_name') not in {'Write', 'Edit'}:
            return 0
        root = Path(os.environ.get('CLAUDE_PROJECT_DIR') or data.get('cwd') or os.getcwd()).resolve()
        tool_input = data.get('tool_input')
        if not isinstance(tool_input, dict):
            raise Invalid('Write/Edit 缺少有效 tool_input')
        path = tool_input.get('file_path')
        if not path:
            raise Invalid('Write/Edit 缺少 file_path')
        check(root, path)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as e:
        print('【場景關卡】' + str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
