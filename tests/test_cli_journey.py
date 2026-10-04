"""Exercise the documented launcher and CLI in a disposable book, without model claims."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from test_hook_encoding import BASH

KIT = Path(__file__).resolve().parents[1]


class CliJourney(unittest.TestCase):
    def test_scene_chapter_author_edit_and_revision_finish(self):
        with tempfile.TemporaryDirectory(prefix='novel-cli-') as tmp:
            root = Path(tmp).resolve()
            for folder in ('scripts', 'hooks'):
                shutil.copytree(KIT/'.novel-kit'/folder, root/'.novel-kit'/folder,
                                ignore=shutil.ignore_patterns('__pycache__'))
            for name in ('novel', 'novel.cmd', 'novel.py'):
                shutil.copy2(KIT/name, root/name)
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))

            def write(path, content):
                p = root/path; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding='utf-8')

            def cli(*args, code=0):
                if os.name == 'nt':
                    command = ['cmd.exe', '/d', '/c', str(root/'novel.cmd'), *args]
                else:
                    command = ['/bin/sh', str(root/'novel'), *args]
                r = subprocess.run(command,
                                   cwd=root, env=env, capture_output=True, text=True, encoding='utf-8')
                self.assertEqual(r.returncode, code, (args, r.stdout, r.stderr))
                return r

            def delivery(name, kind, pairs, mode, **extra):
                body = '隔离测试交付；不代表真人或模型审核通过\n\n'
                for source, _ in pairs:
                    body += '<!-- novel-candidate:' + source + ' -->\n'
                    body += (root/source).read_text(encoding='utf-8')
                    body += '\n<!-- /novel-candidate -->\n'
                write('審閱/'+name+'.md', body)
                spec = {'id': name, 'kind': kind, 'delivery': '審閱/'+name+'.md',
                        'files': [{'source': src, 'target': dst} for src, dst in pairs],
                        'review': {'mode': mode, 'completed': [], 'unresolved': ['隔離測試未執行模型審閱']}, **extra}
                path = '審閱/'+name+'.json'
                write(path, json.dumps(spec, ensure_ascii=False))
                return path

            def prepare(path, code=0):
                cli('review-start', path, code=code)
                if code == 0:
                    cli('prepare', path)

            def accept(name):
                cli('accept', name, '--approval', '隔離測試模擬採用', '--override', '僅測試機制，不代表真人授權')

            write('追蹤/場景狀態.md', '| 章 | 場景 | 狀態 | 備註 |\n|---|---|---|---|\n')
            write('追蹤/追蹤.md', '開書前')
            write('大綱/細綱/第001章.md', '- 狀態：已確認\n## 場景01 測試\n')
            scene = '草稿/第001章/場景01.md'; chapter = '正文/第001章.md'
            cli('confirm-plan', '1'); cli('begin', '1', '1')
            cli('check', scene); cli('check', chapter, code=2)
            write(scene, '第一場測試正文')
            spec = delivery('scene', 'scene', [(scene, scene)], '完整', chapter=1, scene=1)
            prepare(spec); cli('check', scene, code=2); accept('scene')
            cli('begin', '1', '0')
            write('草稿/第001章/整章候選.md', '整章測試正文'); write('審閱/追蹤候選.md', '第一章完成')
            pairs = [('草稿/第001章/整章候選.md', chapter)]
            missing = delivery('missing', 'chapter', pairs, '章節', chapter=1)
            prepare(missing, code=2)
            self.assertFalse((root/chapter).exists())
            pairs.append(('審閱/追蹤候選.md', '追蹤/追蹤.md'))
            prepare(delivery('chapter', 'chapter', pairs, '章節', chapter=1)); accept('chapter')
            self.assertEqual((root/'追蹤/追蹤.md').read_text(encoding='utf-8'), '第一章完成')

            cli('revision-start', 'fix', chapter)
            candidate = '審閱/修訂/fix/候選.md'; write(candidate, '初次修訂候選')
            prepare(delivery('old', 'revision', [(candidate, chapter)], '文字', revision='fix'))
            write(chapter, '作者在修訂中自行更改的版本')
            cli('revision-refresh', 'fix', chapter, '--reason', '隔離測試作者手改')
            cli('accept', 'old', '--approval', '隔離測試', '--override', '隔離測試', code=2)
            write('大綱/細綱/第002章.md', '- 狀態：已確認\n## 場景01 測試\n')
            cli('confirm-plan', '2', code=2)
            write(candidate, (root/chapter).read_text(encoding='utf-8'))
            prepare(delivery('new', 'revision', [(candidate, chapter)], '文字', revision='fix')); accept('new')
            cli('confirm-plan', '2', code=2)
            write('審閱/追蹤候選.md', '作者手改後的事實已同步')
            prepare(delivery('finish', 'revision-finish',
                                   [('審閱/追蹤候選.md', '追蹤/追蹤.md')], '文字', revision='fix'))
            accept('finish'); cli('confirm-plan', '2'); cli('begin', '2', '1')
            self.assertEqual((root/chapter).read_text(encoding='utf-8'), '作者在修訂中自行更改的版本')
            self.assertEqual((root/'追蹤/追蹤.md').read_text(encoding='utf-8'), '作者手改後的事實已同步')
            task = json.loads((root/'審閱/修訂/fix/任務.json').read_text(encoding='utf-8'))
            self.assertEqual(task['status'], 'complete')
            self.assertEqual(len(task['targets'][0]['baseline_history']), 1)


if __name__ == '__main__':
    unittest.main()
