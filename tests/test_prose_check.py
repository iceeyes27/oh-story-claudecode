"""Deterministic degeneration check: each fingerprint fires, genre devices and human prose stay clean."""
from pathlib import Path
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT/'.novel-kit/scripts'))
import novel  # noqa: E402
import prose_check  # noqa: E402


def kinds(text):
    return [(f['severity'], f['type']) for f in prose_check.scan(text)]


class ProseCheck(unittest.TestCase):
    def test_clean_scene_has_no_findings(self):
        text = ('# 场景03\n\n雨点砸在破木顶上，噼里啪啦地响。\n\n'
                '“走吧。”他说。\n\n他闭上眼，静候天明。\n')
        self.assertEqual(kinds(text), [])

    def test_adjacent_and_long_sentence_repetition(self):
        line = '他把那只铁皮盒子塞回床底，又用旧报纸盖了两层。'
        self.assertIn(('blocking', 'verbatim-repeat'), kinds(line + '\n\n' + line + '\n'))
        looped = '\n\n'.join(['她说完转身就走。', line, '窗外起风了。', line, '灯灭了。', line, '天亮了。'])
        self.assertEqual(kinds(looped).count(('blocking', 'verbatim-repeat')), 1)

    def test_quoted_refrain_is_a_genre_device(self):
        chant = '“赫奇帕奇！赫奇帕奇！赫奇帕奇必胜！”'
        self.assertEqual(kinds('\n\n'.join([chant] * 4) + '\n'), [])

    def test_truncation_needs_closing_punctuation(self):
        self.assertIn(('blocking', 'truncated'), kinds('他伸手去推那扇门，门后\n'))
        for ending in ('他推开门。', '“走。”', '门开了……', '她问：“谁？”'):
            with self.subTest(ending=ending):
                self.assertNotIn(('blocking', 'truncated'), kinds(ending + '\n'))

    def test_placeholders_and_refusals(self):
        for text in ('（此处省略打斗过程）\n\n他赢了。', '作为AI语言模型，我无法继续。',
                     '他推开门。\n\n未完待续。', '我无法继续写这个场景。', '他推开门�。'):
            with self.subTest(text=text):
                self.assertIn(('blocking', 'placeholder-leak'), kinds(text + '\n'))

    def test_in_story_speech_and_first_person_are_not_refusals(self):
        for text in ('“作为AI，我会保护你。”机器人说。', '“对不起，我无法答应你。”',
                     '我不能写信给他，信会被拆开。', '她说这是人工智能时代的产物。'):
            with self.subTest(text=text):
                self.assertEqual(kinds(text + '\n'), [])

    def test_pipeline_terms_block_but_quoted_or_structural_words_advise(self):
        self.assertIn(('blocking', 'meta-leak'), kinds('按细纲，他此刻该去找校长。\n'))
        self.assertIn(('blocking', 'meta-leak'), kinds('他的出口状态是疲惫。\n'))
        self.assertEqual(kinds('“这段细纲还得改。”编辑说。\n'), [('advisory', 'meta-leak')])
        self.assertEqual(kinds('《预言家日报》的读者来信堆满了桌子。\n'), [('advisory', 'meta-leak')])

    def test_creation_guidance_leak_is_blocking_but_in_story_quote_is_advisory(self):
        for term in ('创作护栏', '創作護欄'):
            with self.subTest(term=term):
                self.assertIn(('blocking', 'meta-leak'), kinds('按照' + term + '，他该停在这里。\n'))
                self.assertEqual(kinds('“我给这份编辑笔记起名叫' + term + '。”她说。\n'),
                                 [('advisory', 'meta-leak')])

    def test_headings_fences_and_front_matter_are_skipped(self):
        text = ('---\ntitle: 场景\n---\n### 第1章 开机密码\n\n```\n细纲 TODO\n```\n\n'
                '雨停了。\n')
        self.assertEqual(kinds(text), [])

    def test_cli_is_read_only_and_exit_code_tracks_blocking(self):
        with tempfile.TemporaryDirectory(prefix='novel-prose-') as tmp:
            root = Path(tmp).resolve()
            draft = root/'草稿/第001章/場景01.md'
            draft.parent.mkdir(parents=True)
            draft.write_text('《预言家日报》的读者来信堆满了桌子。\n', encoding='utf-8')
            self.assertEqual(novel.main(['--root', str(root), 'prose-check', '草稿/第001章/場景01.md']), 0)
            draft.write_text('按细纲，他走了\n', encoding='utf-8')
            before = draft.read_bytes()
            self.assertEqual(novel.main(['--root', str(root), 'prose-check', '--json', '草稿/第001章/場景01.md']), 1)
            self.assertEqual(draft.read_bytes(), before)
            self.assertFalse((root/'.novel-kit').exists())
            self.assertEqual(novel.main(['--root', str(root), 'prose-check', '../outside.md']), 2)

    def test_eval_samples_stay_clean(self):
        # Author-approved and sample prose must never trip a blocking fingerprint.
        for path in sorted((KIT/'.novel-kit/eval/样本').glob('*/*.md')):
            with self.subTest(path=path.parent.name + '/' + path.name):
                blocking = [f for f in prose_check.scan(path.read_text(encoding='utf-8')) if f['severity'] == 'blocking']
                self.assertEqual(blocking, [])


if __name__ == '__main__':
    unittest.main()
