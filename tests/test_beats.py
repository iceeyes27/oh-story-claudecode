"""Beat splitting and per-sentence coverage: boundaries tile the prose, every sentence needs a verdict."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

KIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KIT/'.novel-kit/scripts'))
import beats  # noqa: E402
import novel  # noqa: E402

SCENE = ('# 场景01\n\n雨点砸在破木顶上，噼里啪啦地响。\n\n陈放睁开眼。指尖刚一抬起，他就僵住了。\n\n'
         '“走吧。”他说。\n\n门开了……\n')
# Prose lines: 3, 5, 7, 9.


class Split(unittest.TestCase):
    def test_numbers_sentences_per_beat(self):
        out = beats.split(SCENE, [{'start_line': 1, 'end_line': 5, 'label': '醒来'},
                                  {'start_line': 6, 'end_line': 9, 'label': '出门'}])
        self.assertEqual([s['id'] for s in out[0]['sentences']], ['1-01', '1-02', '1-03'])
        self.assertEqual([s['text'] for s in out[1]['sentences']], ['“走吧。”', '他说。', '门开了……'])
        self.assertEqual(out[0]['sentences'][1]['line'], 5)

    def test_numbered_text_keeps_paragraphs_and_original_spacing(self):
        text = '# x\n\n“这孩子从小把钱攥得紧。” 亚瑟乐呵呵摸着脑袋。\n\n玛莎愣住。她没说话。\n'
        out = beats.split(text, [{'start_line': 1, 'end_line': 5, 'label': '饭桌'}])
        self.assertEqual(out[0]['sentences'][1], {'id': '1-02', 'line': 3, 'text': '亚瑟乐呵呵摸着脑袋。', 'lead': ' '})
        self.assertNotIn('lead', out[0]['sentences'][2])
        md = beats.numbered_markdown('t', out)
        self.assertIn('\n[1-01]“这孩子从小把钱攥得紧。” [1-02]亚瑟乐呵呵摸着脑袋。\n\n[1-03]玛莎愣住。[1-04]她没说话。\n', md)

    def test_unterminated_line_is_one_sentence(self):
        self.assertEqual(beats.sentences('震得天花板落下一层轻灰：'), ['震得天花板落下一层轻灰：'])
        self.assertEqual(beats.sentences('她问：“谁？”他没答。'), ['她问：“谁？”', '他没答。'])

    def test_rejects_gap_overlap_tail_and_unnamed_beats(self):
        cases = [
            [{'start_line': 1, 'end_line': 3, 'label': 'a'}, {'start_line': 7, 'end_line': 9, 'label': 'b'}],
            [{'start_line': 1, 'end_line': 5, 'label': 'a'}, {'start_line': 5, 'end_line': 9, 'label': 'b'}],
            [{'start_line': 1, 'end_line': 7, 'label': 'a'}],
            [{'start_line': 1, 'end_line': 9, 'label': ' '}],
            [{'start_line': 1, 'end_line': 99, 'label': 'a'}],
            [],
        ]
        for spec in cases:
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                beats.split(SCENE, spec)


class Coverage(unittest.TestCase):
    def setUp(self):
        self.numbered = {'beats': beats.split(SCENE, [{'start_line': 1, 'end_line': 5, 'label': '醒来'},
                                                      {'start_line': 6, 'end_line': 9, 'label': '出门'}])}

    def test_every_sentence_needs_a_verdict_line(self):
        report = '| 1-01 | 通过 |\n| 1-02 | 问题 CE-1 |\n1-03 提到但没结论\n'
        self.assertEqual(beats.coverage(self.numbered, report, [1]), ['1-03'])
        self.assertEqual(beats.coverage(self.numbered, report + '| 1-03 | 待核 |\n', [1]), [])
        self.assertEqual(beats.coverage(self.numbered, report, None), ['1-03', '2-01', '2-02', '2-03'])

    def test_ids_inside_numbers_do_not_count(self):
        self.assertEqual(beats.coverage(self.numbered, '11-01 通过；1-012 通过；21-01 通过', [1]), ['1-01', '1-02', '1-03'])

    def test_per_beat_mode(self):
        self.assertEqual(beats.coverage(self.numbered, '第1幕：通过\n第 2 幕 待核', None, per_beat=True), [])
        self.assertEqual(beats.coverage(self.numbered, '第1幕：通过\n第2幕没写', None, per_beat=True), ['第2幕'])

    def test_unknown_beat_number(self):
        with self.assertRaises(ValueError):
            beats.coverage(self.numbered, '', [3])


class Remap(unittest.TestCase):
    def test_split_merge_and_unchanged_sentences(self):
        spec = [{'start_line': 1, 'end_line': 5, 'label': '醒来'}, {'start_line': 6, 'end_line': 9, 'label': '出门'}]
        old = {'beats': beats.split(SCENE, spec)}
        revised = SCENE.replace('陈放睁开眼。', '陈放睁开眼，翻了个身。').replace('门开了……', '门开了。风灌进来。')
        rows = beats.remap(old, {'beats': beats.split(revised, spec)})
        self.assertIn(('1-01', '1-01', '未改'), rows)
        self.assertIn(('1-02', '1-02', '改写'), rows)
        self.assertIn(('2-03', '2-03', '改写'), rows)
        self.assertIn((None, '2-04', '新增'), rows)
        merged = SCENE.replace('陈放睁开眼。指尖刚一抬起，他就僵住了。', '陈放睁开眼，指尖刚一抬起就僵住了。')
        rows = beats.remap(old, {'beats': beats.split(merged, spec)})
        self.assertIn(('1-03', None, '删除'), rows)
        self.assertIn('| 1-03 | — | 删除 |', beats.remap_markdown(rows))


class Cli(unittest.TestCase):
    def test_split_then_coverage_and_staleness(self):
        with tempfile.TemporaryDirectory(prefix='novel-beats-') as tmp:
            root = Path(tmp).resolve()
            draft = root/'草稿/第001章/場景01.md'
            draft.parent.mkdir(parents=True); draft.write_text(SCENE, encoding='utf-8')
            spec = root/'審閱/第001章/場景01_分幕.json'
            spec.parent.mkdir(parents=True)
            spec.write_text(json.dumps({'target': '草稿/第001章/場景01.md', 'beats': [
                {'start_line': 1, 'end_line': 5, 'label': '醒来'}, {'start_line': 6, 'end_line': 9, 'label': '出门'}]},
                ensure_ascii=False), encoding='utf-8')
            run = lambda *a: novel.main(['--root', str(root), *a])
            self.assertEqual(run('beat-split', '審閱/第001章/場景01_分幕.json'), 0)
            numbered = '審閱/第001章/場景01_分幕_编号.json'
            self.assertIn('[1-02]陈放睁开眼。[1-03]指尖刚一抬起', (root/'審閱/第001章/場景01_分幕_编号.md').read_text(encoding='utf-8'))
            report = root/'審閱/第001章/报告.md'
            report.write_text('1-01 通过\n1-02 通过\n', encoding='utf-8')
            self.assertEqual(run('beat-coverage', numbered, '審閱/第001章/报告.md', '--beat', '1'), 1)
            report.write_text('1-01 通过\n1-02 通过\n1-03 问题\n', encoding='utf-8')
            self.assertEqual(run('beat-coverage', numbered, '審閱/第001章/报告.md', '--beat', '1'), 0)
            draft.write_text(SCENE.replace('僵住', '愣住'), encoding='utf-8')
            self.assertEqual(run('beat-coverage', numbered, '審閱/第001章/报告.md', '--beat', '1'), 2)


if __name__ == '__main__':
    unittest.main()
