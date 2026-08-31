#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/check-prose-policy.py"
SPEC = importlib.util.spec_from_file_location("prose_policy", PATH)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class ProsePolicyInventoryTests(unittest.TestCase):
    def test_repository_has_one_priority_and_no_known_global_conflict(self) -> None:
        result = module.inventory()
        self.assertTrue(result["priority_authority"])
        self.assertGreater(result["files_scanned"], 50)
        self.assertGreater(result["candidate_rules"], 100)
        self.assertEqual(result["violations"], [])
        self.assertTrue(result["ok"])

    def test_forbidden_patterns_cover_the_rejected_global_rules(self) -> None:
        samples = {
            "global-unresolved-ending": "每章结尾必须有至少一个未解的问题",
            "global-two-suspense-lines": "保证任何时刻都有至少两条悬念线在运行",
            "global-two-expectation-lines": "任何时刻保持至少两条期待线并行运行",
            "global-two-long-one-short": "确保读者脑中有三个好奇的东西：两长一短",
            "global-deceptive-mainline": "大结构是欺骗式的主线",
            "global-infinite-expectation": "一个勾着一个无限循环",
            "global-suspense-minimum": "过渡章至少要达到1级",
            "global-overfire": "宁过火，不平淡",
            "global-comma-long-default": "叙述默认写成逗号长句",
            "global-sentence-band": "逗号之间 8-12 字",
            "global-punctuation-zero": "正文无破折号",
            "global-emotion-show-only": "关键情绪节点无直接写愤怒，用身体反应替代",
            "global-emotion-action-only": "情绪通过动作落地",
            "global-psychology-count": "心理活动不超过2段",
            "global-body-part-question": "身体部位同一词是否超 5 次？",
            "global-punctuation-clean-question": "正文里的破折号是否已清理？",
            "global-new-concept-count": "设定量可控（一章不超 3 个新概念）",
            "global-filler-count": "同一个情绪写了 3 段以上",
            "global-opening-hook-count": "前三章有至少 2 个爽点",
            "global-rhythm-quota": "低压+过场合计不超约 15%",
            "global-section-payload-quota": "每章至少一个新信息炸点",
            "global-hook-schedule": "每 2-3 节留钩子",
            "global-dialogue-percentage": "对话占比 45-60%",
            "global-paragraph-sentence-quota": "每段不超过3句话",
            "global-emotion-score": "开头情绪强度 ≥7",
            "direct-body-before-review": "每章写完直接写入 正文/",
            "optional-per-chapter-review": "本章写作完成。如需一致性检查",
            "detector-style-blocking": "severity: 'blocking'",
        }
        for rule_id, text in samples.items():
            self.assertRegex(text, module.FORBIDDEN[rule_id])

    def test_p1_treatment_and_suspense_priority_remain_explicit(self) -> None:
        prose = (ROOT / "skills/story-write/references/prose-policy.md").read_text(encoding="utf-8")
        suspense = (ROOT / "skills/story-write/references/long-suspense.md").read_text(encoding="utf-8")
        workflow = (
            (ROOT / "skills/story-write/references/candidate-workflow.md").read_text(encoding="utf-8")
            + (ROOT / "skills/story-write/references/quality-p1.md").read_text(encoding="utf-8")
        )
        for marker in (
            "P0-control = C + 单稿",
            "P1-treatment = C + 因果预检 + 双遍正文",
            "Pass A：plain_direct",
            "Pass B：voice_restore",
            "explanation_bloat",
            "voice_loss",
        ):
            self.assertIn(marker, prose)
        self.assertIn("章节功能与当前人物的目标、已知依据、选择和结果可理解", suspense)
        self.assertIn("显式 P1 treatment", workflow)
        self.assertIn("open-treatment-run", workflow)
        self.assertNotIn("适当谜语人，避重就轻", suspense)
        self.assertNotIn("每一层都要有回应", suspense)


if __name__ == "__main__":
    unittest.main(verbosity=2)
