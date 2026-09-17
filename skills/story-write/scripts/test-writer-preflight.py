"""Public writer entrypoints: author style and benchmark applicability."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT=Path(__file__).with_name('build_writer_prompt.py')
class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.book=Path(self.temp.name)
        self.put('设定/题材定位.md','- 主对标书：无\n')
        self.put('设定/文风.md','用短句，保留必要的直接心理。')
        self.put('设定/题材正文提示卡.md','写普通人的选择与关系。')
        self.put('大纲/细纲_第001章.md','### 第 1 章：船票\n- 单元ID/位置：U1；第1拍\n- 目标情绪：决定帮忙\n')
        self.put('大纲/卷纲_第1卷.md','### 剧情单元 U1\n> 作用域：单元级 U1\n- 章节范围：第1-3章\n- 单元情绪引擎：犹疑到决定\n- 单元节拍/章功能分配：第1章借船，第2章运货，第3章归还\n')
        self.put('追踪/上下文.md','\n'.join('## '+h+'\n无' for h in ['当前位置','长期约束','核心角色状态','活跃伏笔','近三章速记','下一章承诺','连贯性风险']))
    def put(self,name,text):
        p=self.book/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');return p
    def build(self):
        return subprocess.run([sys.executable,str(SCRIPT),'--project',str(self.book),'--chapter','1'],capture_output=True,text=True)
    def test_one_sentence_style_is_authority_over_stale_digest(self):
        self.put('设定/_文风摘要.md','过期摘要，不许写心理。')
        result=self.build();self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('custom_style=true',result.stdout);self.assertNotIn('_文风摘要.md',result.stdout)
    def test_optional_opt_out_cannot_disable_core_or_evidence_gate(self):
        self.put('设定/文风.md','用短句，保留心理。\n| long-suspense.md | 停读 |\n| reader-first-writing.md | 停读 |\n| long-format.md | 停读 |\n| agent-quality.md | 停读 |\n| references/* | 停读 |')
        result=self.build();self.assertEqual(result.returncode,0,result.stderr)
        optout=next(line for line in result.stdout.splitlines() if line.startswith('本书停读清单'))
        self.assertIn('long-suspense.md',optout)
        for name in ['reader-first-writing.md','long-format.md','agent-quality.md','references/*']:self.assertNotIn(name,optout)
        self.assertIn('不能豁免格式、事实、采用或阅读证据门禁',result.stdout)
    def test_no_benchmark_or_custom_style_does_not_force_benchmark(self):
        (self.book/'设定/文风.md').unlink()
        result=self.build();self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('未选择对标',result.stdout);self.assertIn('不走对标全量召回',result.stdout)
    def test_selected_broken_assets_fail_then_repair(self):
        self.put('设定/题材定位.md','- 主对标书：样例书\n')
        (self.book/'设定/文风.md').unlink()
        result=self.build();self.assertEqual(result.returncode,2);self.assertIn('已选对标',result.stderr)
        for name in ['剧情/情绪模块.md','剧情/节奏.md','文风.md']:self.put('对标/样例书/'+name,'完整的示例资料。')
        result=self.build();self.assertEqual(result.returncode,0,result.stderr)
    def test_duplicate_outline_is_explicit_error(self):
        self.put('大纲/细纲_第1章_另稿.md','### 第 1 章：船票\n')
        result=self.build();self.assertEqual(result.returncode,2);self.assertIn('歧义',result.stderr)
    def test_scene_view_mode_hides_budgets_and_keeps_obligations(self):
        self.put('大纲/细纲_第001章.md','### 第 1 章：船票\n## 章节蓝图\n- 核心事件：借船\n- 单元ID/位置：U1；第1拍\n- 目标情绪：决定帮忙\n- 本章禁止提前释放：船主的身份\n'
            '### 因果链\n- 前因：开篇无前因\n### 情节细化\n| # | 情节点（谁做了什么） | 功能标签 | 分辨率 | 目标字数 | 执行边界 |\n|---|---|---|---|---|---|\n'
            '| 1 | 主角去码头找船 | 铺垫 | 密 | 250-320 | 禁：不揭船主。放：允许砍价 |\n\n目标字数合计：下限2200字（章目标2500，范围2200-2800）\n')
        full=self.build();self.assertEqual(full.returncode,0,full.stderr)
        self.assertIn('细纲文件（动笔前完整读到 EOF）',full.stdout)
        result=subprocess.run([sys.executable,str(SCRIPT),'--project',str(self.book),'--chapter','1','--packet-mode','scene-view','--candidate-tag','B'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        out=result.stdout
        self.assertNotIn('细纲文件（动笔前完整读到 EOF）',out)
        self.assertIn('——— 首要目标',out);self.assertIn('——— 场景视图',out)
        self.assertIn('主角去码头找船｜禁：不揭船主。放：允许砍价',out)
        self.assertNotIn('250-320',out);self.assertNotIn('目标字数合计',out);self.assertNotIn('单元ID/位置',out)
        self.assertIn('禁止提前释放：船主的身份',out)
        self.assertIn('第001章_船票_B.md',out)
        self.assertIn('状态卡不适用于本章',out)
        self.assertIn('材料包模式：scene-view',out)
        self.assertIn('全章一次成文',out);self.assertIn('≤10 行申报',out)
    def test_invalid_existing_reading_policy_cannot_be_legacy(self):
        self.put('.story-review/longform-v1.json','null')
        result=self.build();self.assertEqual(result.returncode,2);self.assertIn('连读写前门',result.stderr)
if __name__=='__main__':unittest.main()
