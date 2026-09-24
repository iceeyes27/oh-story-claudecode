"""Locale-independent guard: text I/O must name its encoding.

Windows zh-TW/zh-CN default locales are not UTF-8; a bare read_text(), open()
or subprocess text=True silently depends on them. The AST scan catches such
regressions on any platform, including UTF-8 macOS/Linux.
"""
import ast
from pathlib import Path
import unittest

KIT = Path(__file__).resolve().parents[1]
FILES = [KIT / '.claude/scripts/novel.py', KIT / '.claude/hooks/scene_gate.py', *sorted((KIT / 'tests').glob('*.py'))]
SUBPROCESS_TEXT = {'run', 'check_output', 'Popen', 'call', 'check_call'}


def const(node):
    return node.value if isinstance(node, ast.Constant) else None


def problem(node):
    f = node.func
    name = f.attr if isinstance(f, ast.Attribute) else f.id if isinstance(f, ast.Name) else None
    kw = {k.arg: k.value for k in node.keywords}
    if 'encoding' in kw:
        return None
    if name in {'read_text', 'write_text'}:
        return name + '() 未指定 encoding'
    if name == 'open':
        owner = f.value.id if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) else None
        if owner == 'os':
            return None  # os.open works on bytes/file descriptors.
        pos = 1 if isinstance(f, ast.Name) or owner == 'io' else 0  # open(path, mode) vs Path.open(mode)
        mode = kw.get('mode', node.args[pos] if len(node.args) > pos else None)
        mode = 'r' if mode is None else const(mode)
        if isinstance(mode, str) and 'b' in mode:
            return None
        return 'open() 文字模式未指定 encoding'
    if name in SUBPROCESS_TEXT and any(const(kw.get(k)) is True for k in ('text', 'universal_newlines')):
        return name + '(text=True) 未指定 encoding'
    return None


class EncodingGuard(unittest.TestCase):
    def test_text_io_names_encoding(self):
        found = []
        for path in FILES:
            tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
            for node in ast.walk(tree):
                msg = problem(node) if isinstance(node, ast.Call) else None
                if msg:
                    found.append(f'{path.relative_to(KIT).as_posix()}:{node.lineno}: {msg}')
        self.assertEqual(found, [], '\n'.join(found))

    def test_guard_detects_bare_calls(self):
        bad = ["p.read_text()", "p.write_text('x')", "open('a')", "open('a', 'w')", "p.open()",
               "io.open('a', 'r')", "subprocess.run(['x'], text=True)"]
        good = ["p.read_text(encoding='utf-8')", "open('a', 'rb')", "p.open('a+b')", "os.open('a', 1)",
                "subprocess.run(['x'], input=b'')", "subprocess.run(['x'], text=True, encoding='utf-8')"]
        for src in bad:
            self.assertIsNotNone(problem(ast.parse(src).body[0].value), src)
        for src in good:
            self.assertIsNone(problem(ast.parse(src).body[0].value), src)


if __name__ == '__main__':
    unittest.main()
