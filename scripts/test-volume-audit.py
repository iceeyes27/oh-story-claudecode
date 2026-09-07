#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test-volume-audit.py - 卷级生命周期健康度审计脚本单元与集成测试"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "story-write" / "scripts" / "volume-audit.py"


class TestVolumeAudit(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="test-vol-audit-"))

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def run_tool(self, args, expected_code=0):
        cmd = [sys.executable, str(SCRIPT)] + args
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        self.assertEqual(res.returncode, expected_code, f"expected {expected_code}, got {res.returncode}\nstdout={res.stdout}\nstderr={res.stderr}")
        return res

    def test_missing_volume_outline(self):
        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=1)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "FAIL")
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("Volume_Outline_Missing", codes)

    def test_missing_conflict(self):
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text("# 卷纲·第一卷\n\n章节范围：第 1–30 章\n\n无实质矛盾", encoding="utf-8")

        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=1)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "FAIL")
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("Volume_Contract_Missing_Conflict", codes)

    def test_valid_volume_pass_and_write(self):
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text(
            "# 卷纲·第一卷\n\n章节范围：第 1–30 章\n\n## 核心矛盾\n\n主矛盾：对抗反派\n\n下一卷新周期规划...",
            encoding="utf-8"
        )
        prose_dir = self.temp_dir / "正文"
        prose_dir.mkdir(parents=True)
        (prose_dir / "第001章_开端.md").write_text("# 第001章\n\n正文开始。", encoding="utf-8")

        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--write", "--json"], expected_code=0)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "PASS")
        self.assertTrue(data["metrics"]["outline_found"])
        self.assertEqual(data["metrics"]["existing_chapters_in_range"], 1)

        # Verify report written
        report_file = self.temp_dir / "追踪" / "稳定性审计" / "卷_1_生命周期审计.md"
        self.assertTrue(report_file.is_file())
        report_text = report_file.read_text(encoding="utf-8")
        self.assertIn("卷级生命周期健康度审计报告：第 1 卷", report_text)
        self.assertIn("Gate: PASS", report_text)

    def test_inflation_signal_detection(self):
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text(
            "# 卷纲·第一卷\n\n章节范围：第 1–30 章\n\n## 核心矛盾\n\n主矛盾：搞钱\n\n下一卷新周期规划...",
            encoding="utf-8"
        )
        prose_dir = self.temp_dir / "正文"
        prose_dir.mkdir(parents=True)
        (prose_dir / "第001章_开端.md").write_text("# 第001章\n\n他的身价超过百亿万亿，战力暴涨万倍。", encoding="utf-8")

        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=0)
        data = json.loads(res.stdout)
        self.assertEqual(data["status"], "PASS")
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("Power_Economic_Inflation_Signal", codes)

        # Strict mode should fail
        strict_res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--strict", "--json"], expected_code=1)
        strict_data = json.loads(strict_res.stdout)
        self.assertEqual(strict_data["status"], "FAIL")

    def test_prose_mention_is_not_a_conflict_declaration(self):
        """正文里提到「核心冲突」不算声明，必须是标题行或字段行。

        回归：旧正则的 `##` 只绑在第一个分支上，行文中随口提一句
        「核心冲突」就能骗过 Volume_Contract_Missing_Conflict。
        """
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text(
            "# 卷纲·第一卷\n\n章节范围：第 1–30 章\n\n本卷要围绕核心冲突展开，读者才有代入。",
            encoding="utf-8"
        )
        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=1)
        data = json.loads(res.stdout)
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("Volume_Contract_Missing_Conflict", codes)

    def test_field_line_conflict_declaration_is_accepted(self):
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text(
            "# 卷纲·第一卷\n\n章节范围：第 1–30 章\n\n- **核心冲突**：主角与门主争夺矿脉\n\n下一卷新周期规划...",
            encoding="utf-8"
        )
        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=0)
        data = json.loads(res.stdout)
        codes = [f["code"] for f in data["findings"]]
        self.assertNotIn("Volume_Contract_Missing_Conflict", codes)

    def test_prose_range_phrase_is_not_treated_as_chapter_range(self):
        """卷纲里的行文（如「每 3~5 章一个爽点」）不得被当成章节范围。

        回归：旧实现的宽松回退正则会把该行解析成 [3, 5]，导致审计只统计
        第 3~5 章、通胀扫描只覆盖 3 章，且不触发 Volume_Range_Unclear，
        给作者一份看似正常、口径全错的换卷报告。
        """
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text(
            "# 卷纲·第一卷\n\n## 核心矛盾\n\n主矛盾：对抗反派\n\n"
            "## 节奏\n\n每 3~5 章一个爽点循环，保持追读。\n\n下一卷新周期规划...",
            encoding="utf-8"
        )
        prose_dir = self.temp_dir / "正文"
        prose_dir.mkdir(parents=True)
        for i in range(1, 9):
            (prose_dir / f"第{i:03d}章_测试.md").write_text(f"# 第{i:03d}章\n\n正文。", encoding="utf-8")

        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=0)
        data = json.loads(res.stdout)
        self.assertEqual(data["metrics"]["chapter_range"], [None, None])
        self.assertEqual(data["metrics"]["existing_chapters_in_range"], 8)
        codes = [f["code"] for f in data["findings"]]
        self.assertIn("Volume_Range_Unclear", codes)

    def test_line_only_chapter_range_is_accepted(self):
        outline_dir = self.temp_dir / "大纲"
        outline_dir.mkdir(parents=True)
        (outline_dir / "卷纲_第1卷.md").write_text(
            "# 卷纲·第一卷\n\n- 第1-20章\n\n## 核心矛盾\n\n主矛盾：对抗反派\n\n下一卷新周期规划...",
            encoding="utf-8"
        )
        prose_dir = self.temp_dir / "正文"
        prose_dir.mkdir(parents=True)
        for i in (1, 5, 25):
            (prose_dir / f"第{i:03d}章_测试.md").write_text(f"# 第{i:03d}章\n\n正文。", encoding="utf-8")

        res = self.run_tool(["--project", str(self.temp_dir), "--volume", "1", "--json"], expected_code=0)
        data = json.loads(res.stdout)
        self.assertEqual(data["metrics"]["chapter_range"], [1, 20])
        self.assertEqual(data["metrics"]["existing_chapters_in_range"], 2)
        codes = [f["code"] for f in data["findings"]]
        self.assertNotIn("Volume_Range_Unclear", codes)

    def test_invalid_arguments(self):
        # Nonexistent dir
        self.run_tool(["--project", str(self.temp_dir / "nonexistent"), "--volume", "1"], expected_code=2)
        # Invalid volume
        self.run_tool(["--project", str(self.temp_dir), "--volume", "invalid"], expected_code=2)


if __name__ == "__main__":
    unittest.main()
