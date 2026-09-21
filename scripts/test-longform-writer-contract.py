#!/usr/bin/env python3
"""Local writer contract: author craft choices survive, required gates do not vanish."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parent.parent / 'skills/story-write/scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('local_writer', SCRIPTS / 'build_writer_prompt.py')
writer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(writer)


class LocalWriterContract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='local-writer-contract-')
        self.addCleanup(self.tmp.cleanup)
        self.book = Path(self.tmp.name)
        self.put('大纲/细纲_第001章.md', '### 第 1 章：测试\n- 单元ID/位置：U1\n- 目标情绪：明确选择\n')
        self.put('追踪/上下文.md', '\n'.join(f'## {h}\n无\n' for h in writer.STATE_SECTIONS))
        self.put('设定/题材定位.md', '- 主对标书：无\n')

    def put(self, name, text):
        file = self.book / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding='utf-8')
        return file

    def build(self, chapter=1):
        return subprocess.run([sys.executable, str(SCRIPTS / 'build_writer_prompt.py'), '--project', str(self.book), '--chapter', str(chapter)],
                              capture_output=True, text=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def test_one_sentence_style_and_old_digest(self):
        style = self.put('设定/文风.md', '采用有限全知，允许进入母女各自内心。')
        old = self.put('设定/_文风摘要.md', '旧规则：深度限知，不得进入他人内心。')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('custom_style=true', result.stdout)
        self.assertIn(str(style), result.stdout)
        self.assertNotIn(str(old), result.stdout)
        for stub in ['', '# 文风', '# 文风\n[待补充]', '# 文风\n<!-- 作者稍后填写 -->']:
            style.write_text(stub, encoding='utf-8')
            self.assertIn('custom_style=false', self.build().stdout)

    def test_optional_author_craft_optout_is_effective(self):
        self.put('设定/文风.md', '保留必要心理。\n| writing-craft.md | 停读 |\n| dialogue-mastery.md | 读（只看排版） |')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('本书停读清单（整行跳过、不判定不读取）：writing-craft.md', result.stdout)
        self.assertIn('dialogue-mastery.md（只看排版）', result.stdout)

    def test_core_and_glob_optouts_do_not_disable_required_protocols(self):
        self.put('设定/文风.md', '保留必要心理。\n| reader-first-writing.md | 停读 |\n| long-format.md | 停读 |\n| candidate-workflow.md | 停读 |\n| references/* | 停读 |')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('本书停读清单', result.stdout)
        self.assertIn('必读核心：reader-first-writing.md 与 long-format.md', result.stdout)
        self.assertNotIn('references/*', result.stdout)

    def test_no_benchmark_does_not_require_assets(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('未选择对标', result.stdout)
        self.assertIn('不要求先拆一本书', result.stdout)
        self.assertNotIn('走全量召回后填此槽', result.stdout)

    def test_selected_benchmark_damage_is_error(self):
        self.put('设定/题材定位.md', '- 主对标书：参考书\n')
        result = self.build()
        self.assertEqual(result.returncode, 2)
        self.assertIn('已选对标 参考书 资料缺失或无效', result.stderr)
        for relative in ['剧情/情绪模块.md', '剧情/节奏.md', '文风.md']:
            self.put('对标/参考书/' + relative, '本章可用的资料内容')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('走全量召回后填此槽', result.stdout)
        self.put('对标/参考书/剧情/节奏.md', '[待补充]')
        self.assertEqual(self.build().returncode, 2)

    def test_downgrade_cannot_hide_selected_benchmark_damage(self):
        self.put('设定/题材定位.md', '- 主对标书：参考书\n')
        self.put('设定/文风.md', '采用近距离第三人称，保留必要心理。')
        self.put('设定/题材正文提示卡.md', '重点写普通人的选择、关系与具体代价。')
        self.put('大纲/卷纲_第1卷.md', '### 剧情单元 U1\n> 作用域：单元级 U1\n- 章节范围：第1-3章\n- 单元情绪引擎：犹疑到决定\n- 单元节拍/章功能分配：第1章受阻，第2章选择，第3章承担\n')
        missing = self.build()
        self.assertEqual(missing.returncode, 2)
        self.assertIn('剧情/情绪模块.md', missing.stderr)
        self.assertIn('剧情/节奏.md', missing.stderr)

        self.put('对标/参考书/剧情/情绪模块.md', '可核查的情绪模块')
        self.put('对标/参考书/剧情/节奏.md', '可核查的节奏模块')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('召回降档：成立', result.stdout)

    def test_no_policy_does_not_write_review_state(self):
        self.assertEqual(self.build().returncode, 0)
        self.assertFalse((self.book / '.story-review').exists())

    def test_nested_previous_chapter_is_used_and_duplicates_block(self):
        self.put('大纲/细纲_第002章.md', '### 第 2 章：船钱\n- 单元ID/位置：U1\n- 目标情绪：承担代价\n')
        previous = self.put('正文/第一卷/第001章_船票.md', '# 第001章 船票\n上一章的收尾锚点。\n')
        result = self.build(2)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('上一章的收尾锚点', result.stdout)
        self.assertIn(previous.name, result.stdout)
        self.assertIn('# 第002章 船钱', result.stdout)

        self.put('正文/第1章_重复.md', '# 第1章 重复\n另一个版本。\n')
        ambiguous = self.build(2)
        self.assertEqual(ambiguous.returncode, 2)
        self.assertIn('同章文件歧义', ambiguous.stderr)


if __name__ == '__main__':
    unittest.main()
