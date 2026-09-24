import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_workflow as tw  # noqa: E402

# Borrow helpers without binding the TestCase here, or discovery would run it twice.
n, SCRIPT, W = tw.n, tw.SCRIPT, tw.Workflow.__dict__


def ids(result):
    return {h['id']: h['count'] for h in result['hints']}


class Scan(unittest.TestCase):
    setUp, write = W['setUp'], W['write']

    def run_scan(self, content, name='草稿/第001章/場景01.md'):
        self.write(name, content)
        return n.scan(self.root, [name])[0]

    def bans(self, *lines):
        self.write(n.BANS, '# 作者禁用詞\n\n```author-ban\n' + ''.join(x + '\n' for x in lines) + '```\n')

    def test_glyph_list_excludes_valid_simplified_characters(self):
        glyphs = n.traditional_glyphs()
        self.assertGreater(len(glyphs), 300)
        for ch in glyphs:
            with self.assertRaises(UnicodeEncodeError, msg=ch):
                ch.encode('gb2312')
            ch.encode('big5')
        for ch in '著乾於後瞭餘':
            self.assertNotIn(ch, glyphs)

    def test_rules_load(self):
        rules = n.hint_rules()
        self.assertGreaterEqual(len(rules), 25)
        self.assertTrue(all(r['scope'] in {'敘述', '全部'} for r in rules))

    def test_both_glyph_forms_hit(self):
        self.assertIn('AP02', ids(self.run_scan('他心头一沉。\n')))
        self.assertIn('AP02', ids(self.run_scan('他心頭一沉。\n')))
        self.assertIn('AP07', ids(self.run_scan('她心中涌起一股暖意。\n')))

    def test_narration_rules_skip_dialogue(self):
        self.assertNotIn('AP02', ids(self.run_scan('「我心头一沉，」他说。\n')))
        self.assertIn('AP02', ids(self.run_scan('「走吧。」他心头一沉。\n')))
        # An unclosed quote does not hide narration on the next paragraph.
        self.assertIn('AP02', ids(self.run_scan('「走吧\n他心头一沉。\n')))

    def test_density_threshold(self):
        self.assertNotIn('AP23', ids(self.run_scan('仿佛。' * 4)))
        self.assertEqual(ids(self.run_scan('仿佛。' * 5))['AP23'], 5)

    def test_minutes_not_mistaken_for_degree(self):
        self.assertNotIn('AP29', ids(self.run_scan('等了几分钟。' * 3)))
        self.assertEqual(ids(self.run_scan('带着几分笑意。' * 3))['AP29'], 3)

    def test_author_ban_matches_dialogue_and_needs_source(self):
        self.bans('命运 | 作者 2026-09-24：不要写命运')
        r = self.run_scan('「这就是命运。」\n')
        self.assertEqual([h['match'] for h in r['author']], ['命运'])
        self.bans('命运')
        with self.assertRaises(n.Invalid):
            self.run_scan('没有问题。\n')

    def test_broken_rules_rejected(self):
        for line in ['X1 | 套話 | 敘述 | 1 | (未闭合 | 说明', 'X1 | 套話 | 對白 | 1 | 词 | 说明', 'X1 | 套話 | 敘述 | 0 | 词 | 说明',
                     'X1 | 套話 | 敘述 | 1']:
            with tempfile.TemporaryDirectory() as d:
                p = Path(d) / 'p.md'
                p.write_text('```ai-pattern\n' + line + '\n```\n', encoding='utf-8')
                with patch.object(n, 'PATTERNS', p), self.assertRaises(n.Invalid, msg=line):
                    n.hint_rules()

    def test_glyph_check_follows_book_setting(self):
        self.assertEqual([g['char'] for g in self.run_scan('他們说。\n')['glyph']], ['們'])
        self.assertEqual(self.run_scan('他们说着话，乾坤未定，后来于是著书。\n')['glyph'], [])
        self.write('設定/設定.md', '- 正文字形：繁體\n')
        self.assertEqual(self.run_scan('他們說。\n')['glyph'], [])

    def test_directory_scan(self):
        self.write('草稿/第001章/場景01.md', '他心头一沉。')
        self.write('草稿/第001章/場景02.md', '无事。')
        self.assertEqual([f['path'] for f in n.scan(self.root, ['草稿'])], ['草稿/第001章/場景01.md', '草稿/第001章/場景02.md'])

    def test_cli_outputs_utf8_and_json(self):
        self.write('草稿/a.md', '他心头一沉。\n')
        r = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), 'scan', '草稿/a.md'], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('提示 AP02', r.stdout.decode('utf-8'))
        r = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), 'scan', '--json', '草稿/a.md'], capture_output=True)
        self.assertEqual(json.loads(r.stdout.decode('utf-8'))[0]['hints'][0]['id'], 'AP02')
        r = subprocess.run([sys.executable, str(SCRIPT), '--root', str(self.root), 'scan', '草稿/missing.md'], capture_output=True)
        self.assertEqual(r.returncode, 2)

    def test_reader_reviewer_required_for_new_prose(self):
        self.assertIn('reader-reviewer', n.REVIEWERS['完整'])
        self.assertIn('reader-reviewer', n.REVIEWERS['章節'])
        self.assertNotIn('reader-reviewer', n.REVIEWERS['文字'])


class PrepareGate(unittest.TestCase):
    setUp, write, plan, ready, scene_delivery = (W[k] for k in ('setUp', 'write', 'plan', 'ready', 'scene_delivery'))

    def journal(self, name):
        return json.loads((self.root / f'審閱/採用/{name}/journal.json').read_text(encoding='utf-8'))

    def test_author_ban_becomes_unresolved(self):
        self.write(n.BANS, '```author-ban\n正文 | 作者原话\n```\n')
        self.ready(); s = self.scene_delivery(); n.prepare(self.root, s)
        j = self.journal('s1')
        self.assertEqual(j['review']['unresolved'], ['作者禁詞：正文×1（草稿/第001章/場景01.md）'])
        self.assertEqual(j['scan']['草稿/第001章/場景01.md']['author'][0]['match'], '正文')
        with self.assertRaises(n.Invalid):
            n.accept(self.root, 's1', '通過')
        self.assertEqual(n.accept(self.root, 's1', '通過', override='作者：这里保留'), 'complete')

    def test_traditional_prose_becomes_unresolved(self):
        self.ready(); s = self.scene_delivery()
        self.write(n.scene_path(1, 1), '他們說')
        n.prepare(self.root, s)
        self.assertEqual(self.journal('s1')['review']['unresolved'], ['正文字形：簡體正文含繁體字 們×1、說×1（草稿/第001章/場景01.md）'])

    def test_clean_simplified_prose_passes(self):
        self.ready(); n.prepare(self.root, self.scene_delivery())
        self.assertEqual(self.journal('s1')['review']['unresolved'], [])
        self.assertEqual(n.accept(self.root, 's1', '通過'), 'complete')

    def test_ban_list_edit_invalidates_prepared_delivery(self):
        self.ready(); n.prepare(self.root, self.scene_delivery())
        self.write(n.BANS, '```author-ban\n新词 | 作者原话\n```\n')
        with self.assertRaises(n.Invalid):
            n.accept(self.root, 's1', '通過')


if __name__ == '__main__':
    unittest.main()
