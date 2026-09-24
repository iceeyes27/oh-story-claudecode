"""Hook behaviour under non-UTF-8 locales, a broken python3 and no Python.

Claude Code sends the hook payload as raw UTF-8 JSON (non-ASCII unescaped), so
these tests feed bytes, never json.dumps() default ASCII escapes.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
SCRIPT = KIT / '.claude/scripts/novel.py'
spec = importlib.util.spec_from_file_location('novel', SCRIPT)
n = importlib.util.module_from_spec(spec); spec.loader.exec_module(n)
HOOK = KIT / '.claude/hooks/scene_gate.py'
SETTINGS = KIT / '.claude/settings.json'


def find_bash():
    override = os.environ.get('NOVEL_KIT_TEST_BASH')
    if override:
        return override
    found = shutil.which('bash')
    if os.name == 'nt':
        if found and 'system32' in found.lower():
            found = None  # System32\bash.exe is the WSL launcher, not Git Bash.
        git = shutil.which('git')
        if not found and git:
            base = Path(git).resolve().parents[1]
            found = next((str(p) for p in (base / 'bin/bash.exe', base / 'usr/bin/bash.exe') if p.exists()), None)
    return found


BASH = find_bash()


def posix(path):
    return str(path).replace('\\', '/')


class Book(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='novel-hook-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve() / '書稿'
        self.root.mkdir()
        self.write(n.STATE, n.table({}))
        # Chapter 1 confirmed with two scenes; chapter 2 only a draft outline.
        self.plan(1, confirmed=True); n.confirm_plan(self.root, 1)
        self.plan(2, confirmed=False)

    def write(self, path, content):
        p = self.root / path; p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        return p

    def plan(self, ch, confirmed):
        self.write(f'大綱/細綱/第{ch:03d}章.md', '- 狀態：' + ('已確認' if confirmed else '草案') + '\n## 場景01 甲\n## 場景02 乙\n')

    def payload(self, path, tool='Write', raw=False, key='file_path', **extra):
        path = str(path)
        # raw: pass the path verbatim (relative, other-OS forms). Python 3.13 on Windows
        # no longer treats '/c/…' as absolute, so do not rely on os.path.isabs for those.
        target = path if raw or os.path.isabs(path) else str(self.root / path)
        data = {'session_id': 'x', 'cwd': str(self.root), 'hook_event_name': 'PreToolUse', 'tool_name': tool,
                'tool_input': {key: target, 'content': '內容 "引號" \\ 反斜線'}, **extra}
        return json.dumps(data, ensure_ascii=False).encode('utf-8')

    def outside(self):
        return Path(self.tmp.name).resolve() / '別的專案/正文/第001章.md'

    def scope_cases(self):
        """(payload, expected exit) shared by the Python gate and the no-Python fallback."""
        owned = ['追蹤/場景狀態.md', '追蹤/場景狀態.MD', '審閱/採用/s1/journal.json',
                 '審閱/修訂/fix/任務.json', '審閱/修訂/fix/任務.Json', '導入/清單.json', '導入/清單.JSON']
        return ([(self.payload(p), 2) for p in owned] +
                [(self.payload(self.outside()), 0), (self.payload('設定/設定.md'), 0),
                 (self.payload('審閱/修訂/fix/候選.md'), 0), (self.payload('追蹤/追蹤.md'), 0),
                 (self.payload('正文/第001章.md', tool='MultiEdit'), 2),
                 (self.payload('正文/第001章.ipynb', tool='NotebookEdit', key='notebook_path'), 2),
                 (self.payload('設定/筆記.ipynb', tool='NotebookEdit', key='notebook_path'), 0),
                 (self.payload(self.outside(), tool='NotebookEdit', key='notebook_path'), 0)])

    def env(self, **extra):
        # PYTHONIOENCODING forces non-UTF-8 stdio on every platform. PYTHONUTF8 is unset
        # (the Windows default) rather than 0: forcing 0 under POSIX LC_ALL=C would also
        # make os.environ ASCII, a different problem the launcher already avoids.
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root), PYTHONIOENCODING='gbk')
        env.pop('PYTHONUTF8', None)
        env.update(extra)
        return env


class PythonHook(Book):
    """Direct Python entry: stdio forced to GBK like zh-CN Windows."""

    def run_hook(self, data, io='gbk'):
        return subprocess.run([sys.executable, str(HOOK)], input=data, capture_output=True,
                              env=self.env(PYTHONIOENCODING=io))

    def test_utf8_bytes_are_decoded_regardless_of_locale(self):
        cases = [('正文/第001章.md', 2), ('草稿/第002章/場景01.md', 2), ('草稿/第001章/場景02.md', 2),
                 ('草稿/第001章/場景01.md', 0), ('設定/設定.md', 0)]
        # gbk: strict decode error; latin-1/surrogateescape: silent mojibake that used to bypass the gate.
        for io in ['gbk', 'gbk:surrogateescape', 'latin-1']:
            for tool in ['Write', 'Edit']:
                for path, code in cases:
                    r = self.run_hook(self.payload(path, tool), io)
                    self.assertEqual(r.returncode, code, (io, tool, path, r.stderr.decode('utf-8', 'replace')))
        r = self.run_hook(self.payload('正文/第001章.md'))
        self.assertIn('正式正文', r.stderr.decode('utf-8'))

    def test_scope_outside_tool_owned_and_notebook(self):
        for data, code in self.scope_cases():
            r = self.run_hook(data)
            self.assertEqual(r.returncode, code, (data.decode('utf-8'), r.stderr.decode('utf-8', 'replace')))
        r = self.run_hook(self.payload('追蹤/場景狀態.md'))
        self.assertIn('novel.py 維護', r.stderr.decode('utf-8'))

    def test_invalid_utf8_is_rejected(self):
        gbk = json.dumps({'tool_name': 'Write', 'tool_input': {'file_path': str(self.root / '設定/設定.md')}},
                         ensure_ascii=False).encode('gbk')
        with self.assertRaises(UnicodeDecodeError):
            gbk.decode('utf-8')
        for data in [gbk, b'{"tool_name":"Write","tool_input":{"file_path":"\xe6\xad"}}']:
            r = self.run_hook(data)
            self.assertEqual(r.returncode, 2, r.stderr.decode('utf-8', 'replace'))
            r.stderr.decode('utf-8')  # message itself stays valid UTF-8


@unittest.skipUnless(BASH, 'bash 不可用')
class Launcher(Book):
    """The command in settings.json, with python3 broken or Python missing."""

    def setUp(self):
        super().setUp()
        shutil.copytree(KIT / '.claude', self.root / '.claude', ignore=shutil.ignore_patterns('__pycache__'))
        self.bin = Path(self.tmp.name) / 'bin'; self.bin.mkdir()
        self.empty = Path(self.tmp.name) / 'empty'; self.empty.mkdir()

    def fake(self, name, body):
        p = self.bin / name
        p.write_bytes(('#!/bin/sh\n' + body + '\n').encode('utf-8')); p.chmod(0o755)

    def fake_store_stub(self):
        # Microsoft Store python3 placeholder: prints a hint and exits 49.
        self.fake('python3', 'echo "Python was not found" >&2\nexit 49')
        self.fake('python', f'exec "{posix(sys.executable)}" "$@"')

    def command(self):
        hooks = json.loads(SETTINGS.read_text(encoding='utf-8'))['hooks']['PreToolUse']
        self.assertEqual(hooks[0]['matcher'], 'Write|Edit|MultiEdit|NotebookEdit')
        return hooks[0]['hooks'][0]['command']

    def run_settings(self, data, path_dirs):
        path = os.pathsep.join([*map(str, path_dirs), os.path.dirname(BASH), os.environ.get('PATH', '')])
        return subprocess.run([BASH, '-c', self.command()], input=data, capture_output=True,
                              env=self.env(PATH=path))

    def run_no_python(self, data, root=None):
        # Hook script invoked directly with a PATH that has no interpreter at all.
        env = self.env(PATH=str(self.empty))
        if root is not None:
            env['CLAUDE_PROJECT_DIR'] = root
        return subprocess.run([BASH, str(self.root / '.claude/hooks/scene_gate.sh')], input=data,
                              capture_output=True, env=env)

    def test_settings_uses_bash_launcher(self):
        self.assertEqual(self.command(), 'bash "$CLAUDE_PROJECT_DIR/.claude/hooks/scene_gate.sh"')

    def test_store_stub_python3_is_skipped(self):
        self.fake_store_stub()
        cases = [('正文/第001章.md', 2), ('草稿/第002章/場景01.md', 2), ('草稿/第001章/場景02.md', 2),
                 ('草稿/第001章/場景01.md', 0), ('設定/設定.md', 0)]
        for path, code in cases:
            r = self.run_settings(self.payload(path), [self.bin])
            self.assertEqual(r.returncode, code, (path, r.stderr.decode('utf-8', 'replace')))

    def test_store_stub_scope_through_settings(self):
        self.fake_store_stub()
        for data, code in self.scope_cases():
            r = self.run_settings(data, [self.bin])
            self.assertEqual(r.returncode, code, (data.decode('utf-8'), r.stderr.decode('utf-8', 'replace')))

    def test_launcher_exports_utf8(self):
        self.fake_store_stub()
        code = 'import os,sys; print(os.environ["PYTHONUTF8"], os.environ["PYTHONIOENCODING"], sys.stdout.encoding, sys.version_info >= (3, 9))'
        path = os.pathsep.join([str(self.bin), os.environ.get('PATH', '')])
        r = subprocess.run([BASH, str(KIT / '.claude/scripts/py.sh'), '-c', code], capture_output=True,
                           env=self.env(PATH=path))
        self.assertEqual(r.returncode, 0, r.stderr.decode('utf-8', 'replace'))
        self.assertEqual(r.stdout.decode('utf-8').split(), ['1', 'utf-8', 'utf-8', 'True'])

    def test_launcher_without_python_exits_127(self):
        r = subprocess.run([BASH, str(KIT / '.claude/scripts/py.sh'), '-c', 'pass'], capture_output=True,
                           env=self.env(PATH=str(self.empty)))
        self.assertEqual(r.returncode, 127)
        self.assertIn('Python 3.9', r.stderr.decode('utf-8'))

    def test_unexpected_python_failure_blocks(self):
        # Passes the version probe, then crashes: must not become a non-blocking error.
        self.fake('python3', 'case "$1" in -c) exit 0;; esac\nexit 1')
        r = self.run_settings(self.payload('設定/設定.md'), [self.bin])
        self.assertEqual(r.returncode, 2)

    def test_no_python_blocks_protected_paths_only(self):
        for path in ['正文/第001章.md', '草稿/第001章/場景01.md', '導入/原稿/book.txt']:
            r = self.run_no_python(self.payload(path))
            self.assertEqual(r.returncode, 2, path)
            self.assertIn('Python 3.9', r.stderr.decode('utf-8'))
        outside = Path(self.tmp.name) / '別的專案/正文/第001章.md'
        for path in ['設定/設定.md', str(outside)]:
            r = self.run_no_python(self.payload(path))
            self.assertEqual(r.returncode, 0, (path, r.stderr.decode('utf-8', 'replace')))
        r = self.run_no_python(self.payload('正文/x.md', tool='Read'))
        self.assertEqual(r.returncode, 0)

    def test_no_python_scope_outside_tool_owned_and_notebook(self):
        for data, code in self.scope_cases():
            r = self.run_no_python(data)
            self.assertEqual(r.returncode, code, (data.decode('utf-8'), r.stderr.decode('utf-8', 'replace')))
        r = self.run_no_python(self.payload('導入/清單.json'))
        self.assertIn('novel.py 維護', r.stderr.decode('utf-8'))
        r = self.run_no_python(self.payload('正文/x.ipynb', tool='NotebookEdit', key='path'))
        self.assertEqual(r.returncode, 2)

    def test_no_python_alias_back_into_project_blocks(self):
        # Identity check ([[ -ef ]]) catches outside-looking paths that reach the book.
        link = Path(self.tmp.name) / 'alias'
        try:
            link.symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest('無法建立符號連結')
        for path in [link / '正文/第001章.md', link / '設定/設定.md']:
            r = self.run_no_python(self.payload(path))
            self.assertEqual(r.returncode, 2, (path, r.stderr.decode('utf-8', 'replace')))

    def test_no_python_relative_and_windows_paths(self):
        cases = [('C:\\book', 'C:\\book\\正文\\第001章.md', 2), ('C:\\book', 'c:/book/草稿/第001章/場景01.md', 2),
                 ('C:\\book', 'C:\\book\\設定\\設定.md', 0), ('C:/book', '/c/book/正文/第001章.md', 2),
                 ('C:\\book', 'D:\\other\\正文\\第001章.md', 0), ('/srv/book', '/srv/book2/正文/a.md', 0),
                 ('/srv/book', '正文/第001章.md', 2), ('/srv/book', './草稿/x.md', 2), ('/srv/book', '設定/x.md', 0),
                 ('C:\\book', '\\\\?\\C:\\book\\正文\\第001章.md', 2),
                 ('C:\\book', 'C:\\book\\正文.\\第001章.md', 2),
                 ('C:\\book', 'C:\\book\\正文 \\第001章.md', 2),
                 ('C:\\book', 'C:\\book\\導入\\原稿.\\a.txt', 2),
                 ('C:\\book', 'D:正文\\第001章.md', 2),
                 ('C:\\book', 'C:\\book\\追蹤\\場景狀態.MD', 2), ('C:\\book', 'c:/BOOK/導入/清單.json', 2),
                 ('C:\\book', 'C:\\book\\追蹤\\場景狀態.md::$DATA', 2),
                 ('C:\\book', 'C:\\book\\導入\\清單.json.', 2),
                 ('C:\\book', '\\\\localhost\\C$\\book\\正文\\第001章.md', 2),
                 ('\\\\srv\\share\\book', '\\\\srv\\share\\book\\設定\\x.md', 0),
                 ('\\\\srv\\share\\book', '\\\\srv\\share\\other\\x.md', 0),
                 ('\\\\srv\\share\\book', '\\\\srv\\share\\book\\正文\\第001章.md', 2),
                 ('/srv/book', '/srv/book/追蹤/場景狀態.md', 2), ('/srv/book', '/srv/other/追蹤/場景狀態.md', 0)]
        for root, path, code in cases:
            r = self.run_no_python(self.payload(path, raw=True), root=root)
            self.assertEqual(r.returncode, code, (root, path, r.stderr.decode('utf-8', 'replace')))

    def test_no_python_unparseable_input_blocks(self):
        ascii_escaped = json.dumps({'tool_name': 'Write', 'tool_input': {'file_path': str(self.root / '設定/x.md')}}).encode('utf-8')
        for data in [b'', b'{', b'{"tool_name":"Write","tool_input":{}}', ascii_escaped,
                     self.payload(str(self.root) + '/設定/../正文/第001章.md')]:
            r = self.run_no_python(data)
            self.assertEqual(r.returncode, 2, data)


if __name__ == '__main__':
    unittest.main()
