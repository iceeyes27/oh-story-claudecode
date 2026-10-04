"""Quality regression samples: format and evidence integrity (no model calls)."""
import json
from pathlib import Path
import unittest

EVAL = Path(__file__).resolve().parents[1]/'.novel-kit/eval'
SEVERITIES = {'S1', 'S2', 'S3', 'S4'}
LAYERS = {'L1', 'L2', 'L3', 'L4', 'L5'}


class EvalSamples(unittest.TestCase):
    def keys(self):
        return sorted((EVAL/'答案').glob('*.json'))

    def test_every_sample_has_answer_key(self):
        samples = {p.name for p in (EVAL/'样本').iterdir() if p.is_dir()}
        answers = {p.stem for p in self.keys()}
        self.assertTrue(samples)
        self.assertEqual(samples, answers)

    def test_answer_keys_are_well_formed(self):
        for path in self.keys():
            with self.subTest(sample=path.stem):
                key = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(key['id'], path.stem)
                self.assertTrue(key['审阅者'])
                ids = [item['id'] for item in key['应抓']]
                self.assertEqual(len(ids), len(set(ids)))
                for item in key['应抓']:
                    self.assertTrue(item['id'].startswith(path.stem + '-'))
                    self.assertIn(item['层'], LAYERS)
                    self.assertIn(item['预期严重度'], SEVERITIES)
                    self.assertIn(item['位置'], {'正文', '前文'})
                    self.assertTrue(item['说明'])
                if key['组'] == 'K':
                    self.assertEqual(key['S1S2上限'], 0)
                    self.assertTrue(all(i['预期严重度'] in {'S3', 'S4'} for i in key['应抓']))

    def test_evidence_is_verbatim(self):
        for path in self.keys():
            key = json.loads(path.read_text(encoding='utf-8'))
            folder = EVAL/'样本'/path.stem
            texts = {'正文': (folder/'正文.md').read_text(encoding='utf-8')}
            if (folder/'前文.md').exists():
                texts['前文'] = (folder/'前文.md').read_text(encoding='utf-8')
            for item in key['应抓']:
                with self.subTest(item=item['id']):
                    self.assertIn(item['证据'], texts[item['位置']])
            for kept in key['不应报']:
                with self.subTest(sample=path.stem, kept=kept['证据']):
                    self.assertIn(kept['证据'], texts['正文'])

    def test_sample_text_carries_no_answers(self):
        for folder in (EVAL/'样本').iterdir():
            for name in ('正文.md', '前文.md'):
                file = folder/name
                if file.exists():
                    with self.subTest(file=str(file.relative_to(EVAL))):
                        text = file.read_text(encoding='utf-8')
                        for marker in ('S1', 'S2', '应抓', '答案', '【'):
                            self.assertNotIn(marker, text)


if __name__ == '__main__':
    unittest.main()
