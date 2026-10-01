"""Agent payload, adapter ownership and native launcher integration contracts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT/'.novel-kit/scripts'))
import adapters
from novel import Invalid


class PortableBook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='novel portable-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()/'中文 空間'
        self.root.mkdir()
        for name in ('.novel-kit', '.agents'):
            shutil.copytree(KIT/name, self.root/name,
                            ignore=shutil.ignore_patterns('__pycache__', 'adapters.json', 'adapter-backups'))
        for name in ('novel', 'novel.cmd', 'novel.py', 'AGENTS.md', 'CLAUDE.md'):
            shutil.copy2(KIT/name, self.root/name)
        self.env = {k: v for k, v in os.environ.items() if k not in {'CLAUDE_PROJECT_DIR', 'NOVEL_KIT_ROOT'}}

    def put(self, name, text):
        path = self.root/name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def hook(self, command, cwd=None):
        payload = {'tool_name':'apply_patch', 'cwd':str(cwd or self.root), 'tool_input':{'command':command}}
        return subprocess.run([sys.executable, str(self.root/'.novel-kit/hooks/scene_gate.py')],
                              input=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                              env=self.env, capture_output=True)


class PatchGuard(PortableBook):
    def test_multiple_files_and_move_source_destination_are_all_checked(self):
        cases = [
            ('*** Add File: 設定/new.md\n+設定', 0),
            ('*** Add File: 設定/new.md\n+x\n*** Add File: 正文/第001章.md\n+正文', 2),
            ('*** Delete File: 正文/第001章.md', 2),
            ('*** Update File: 設定/a.md\n*** Move to: 正文/第001章.md\n@@\n-old\n+new', 2),
            ('*** Update File: 正文/第001章.md\n*** Move to: 設定/a.md\n@@\n-old\n+new', 2),
            ('*** Update File: 設定/a.md\n*** Move to: 設定/b.md\n@@\n-old\n+new', 0),
            ('*** Add File: 審閱/採用/fake/journal.json\n+{}', 2),
            ('*** Add File: 草稿/第001章/場景01.md\n+無細綱', 2),
        ]
        for body, expected in cases:
            r = self.hook('*** Begin Patch\n'+body+'\n*** End Patch')
            self.assertEqual(r.returncode, expected, r.stderr.decode('utf-8', 'replace'))

    def test_relative_paths_use_tool_cwd_not_project_root(self):
        nested = self.root/'正文'; nested.mkdir()
        r = self.hook('*** Begin Patch\n*** Add File: 第001章.md\n+x\n*** End Patch', cwd=nested)
        self.assertEqual(r.returncode, 2)
        allowed = self.root/'設定'; allowed.mkdir()
        self.assertEqual(self.hook('*** Begin Patch\n*** Add File: a.md\n+x\n*** End Patch', cwd=allowed).returncode, 0)

    def test_bad_patch_is_denied_and_patch_like_prose_does_not_add_targets(self):
        for command in (None, {}, '', 'not a patch', '*** Begin Patch\n*** End Patch',
                        '*** Begin Patch\n*** Move to: 設定/a.md\n*** End Patch',
                        '*** Begin Patch\n*** Unknown File: 設定/a.md\n+x\n*** End Patch'):
            self.assertEqual(self.hook(command).returncode, 2)
        self.assertEqual(self.hook('*** Begin Patch\n*** Add File: 設定/a.md\n+*** Delete File: 正文/x.md\n*** End Patch').returncode, 0)


class AdapterOwnership(PortableBook):
    def test_setup_check_and_doctor_for_both_agents(self):
        self.assertTrue(adapters.synchronize(self.root, {'claude','codex'}))
        self.assertEqual(adapters.synchronize(self.root, {'claude','codex'}, check=True), [])
        self.assertEqual(adapters.synchronize(self.root, {'claude','codex'}), [])
        self.assertEqual(adapters.doctor(self.root, {'claude','codex'}), 0)
        self.assertFalse((self.root/'正文/novel-kit-doctor.md').exists())
        self.assertFalse((self.root/'設定/novel-kit-doctor.md').exists())
        for path in (self.root/'.codex/agents').glob('*.toml'):
            text = path.read_text(encoding='utf-8')
            self.assertNotIn('\nmodel =', text)
            if sys.version_info >= (3, 11):
                import tomllib
                data = tomllib.loads(text)
                self.assertEqual(data['name'], path.stem)
                self.assertTrue(data['developer_instructions'])

    def test_custom_adapters_are_not_overwritten_and_replacement_is_backed_up(self):
        path = self.put('.claude/skills/revise/SKILL.md', '作者自訂版本')
        with self.assertRaises(Invalid): adapters.synchronize(self.root, {'claude'})
        self.assertEqual(path.read_text(encoding='utf-8'), '作者自訂版本')
        self.assertFalse((self.root/'.claude/skills/new-book/SKILL.md').exists())
        adapters.synchronize(self.root, {'claude'}, replace=True)
        backups = list((self.root/'.novel-kit/adapter-backups').glob('*/.claude/skills/revise/SKILL.md'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding='utf-8'), '作者自訂版本')

    def test_shared_source_changes_propagate_but_local_edit_conflicts(self):
        adapters.synchronize(self.root, {'claude','codex'})
        source = self.root/'.novel-kit/roles/copy-editor.md'
        source.write_text(source.read_text(encoding='utf-8')+'\n新增審閱要求\n', encoding='utf-8')
        changed = adapters.synchronize(self.root, {'claude','codex'}, check=True)
        self.assertIn('.claude/agents/copy-editor.md', changed)
        self.assertIn('.codex/agents/copy-editor.toml', changed)
        adapters.synchronize(self.root, {'claude','codex'})
        local = self.put('.codex/agents/copy-editor.toml', '使用者自訂模型')
        with self.assertRaises(Invalid): adapters.synchronize(self.root, {'codex'})
        self.assertEqual(local.read_text(encoding='utf-8'), '使用者自訂模型')

    def test_foreign_settings_and_hooks_are_preserved(self):
        original = {'permissions':{'allow':['Read']}, 'hooks':{'PreToolUse':[
            {'matcher':'Bash','hooks':[{'type':'command','command':'echo own-check'}]}]}}
        path = self.put('.claude/settings.local.json', json.dumps(original))
        adapters.synchronize(self.root, {'claude'}, replace=True)
        actual = json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(actual['permissions'], original['permissions'])
        self.assertEqual(actual['hooks']['PreToolUse'][0], original['hooks']['PreToolUse'][0])
        self.assertEqual(len(actual['hooks']['PreToolUse']), 2)

    def test_unknown_symlink_target_and_missing_sources_fail_closed(self):
        folder = self.root/'.codex'; folder.mkdir()
        try: (folder/'agents').symlink_to(self.root, target_is_directory=True)
        except OSError: self.skipTest('無法建立符號連結')
        with self.assertRaises(Invalid): adapters.synchronize(self.root, {'codex'})
        (folder/'agents').unlink()
        (self.root/'.agents/skills/revise/SKILL.md').unlink()
        with self.assertRaises(Invalid): adapters.synchronize(self.root, {'codex'})

    def test_generic_mode_does_not_install_other_agent_configuration(self):
        self.assertEqual(adapters.synchronize(self.root, set()), [])
        self.assertEqual(adapters.doctor(self.root, set()), 0)
        self.assertFalse((self.root/'.codex').exists())
        self.assertFalse((self.root/'.claude').exists())

    def test_windows_hook_configuration_handles_space_and_apostrophe_paths(self):
        import base64
        root = Path("C:/書稿/O'Brien story")
        item = adapters.hook_config(root, 'claude', 'windows')['hooks'][0]
        self.assertEqual(item['command'], 'powershell.exe')
        script = base64.b64decode(item['args'][-1]).decode('utf-16le')
        self.assertIn("O''Brien story", script)
        self.assertNotIn('ExecutionPolicy', script)
        codex = adapters.hook_config(root, 'codex', 'windows')['hooks'][0]
        self.assertEqual(codex['commandWindows'].split(), [item['command'], *item['args']])


@unittest.skipUnless(os.name == 'nt', '原生 Windows cmd.exe 啟動器')
class WindowsLauncher(PortableBook):
    def cmd(self, relative, args=(), payload=None, env=None):
        return subprocess.run(['cmd.exe','/d','/c',str(self.root/relative),*args],
                              input=payload, capture_output=True, env=env or self.env, cwd=self.root)

    def test_native_python_hook_and_cli_without_git_bash(self):
        # Only Python and Windows system utilities are available; no Git Bash needed.
        env = dict(self.env, PATH=os.pathsep.join([str(Path(sys.executable).parent), str(Path(os.environ['SystemRoot'])/'System32')]))
        result = self.cmd('novel.cmd', ['--help'], env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        for tool, data in [('Write', {'file_path':str(self.root/'正文/第001章.md')}),
                           ('apply_patch', {'command':'*** Begin Patch\n*** Add File: 正文/第001章.md\n+x\n*** End Patch'})]:
            payload = json.dumps({'tool_name':tool,'cwd':str(self.root),'tool_input':data}, ensure_ascii=False).encode('utf-8')
            result = self.cmd('.novel-kit/hooks/scene_gate.cmd', payload=payload, env=env)
            self.assertEqual(result.returncode, 2, result.stderr)

    def test_missing_python_blocks_hook(self):
        empty = self.root/'empty'; empty.mkdir()
        env = dict(self.env, PATH=str(empty))
        result = self.cmd('.novel-kit/hooks/scene_gate.cmd', payload=b'{}', env=env)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
