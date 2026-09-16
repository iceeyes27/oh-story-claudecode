#!/usr/bin/env python3
"""Real volume CLI regression: coverage is independent of file placement."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).with_name("volume-audit.py")

class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.book = Path(self.temp.name)
        (self.book / "大纲").mkdir()
        (self.book / "大纲/卷纲_第1卷.md").write_text("# 第一卷\n章节范围：第1–3章\n## 核心矛盾\n争回船票。下一卷继续。", encoding="utf-8")
    def prose(self, name, text="战力提升百倍"):
        p = self.book / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p
    def run_audit(self, *args):
        result = subprocess.run([sys.executable, str(SCRIPT), "--project", str(self.book), "--volume", "1", "--json", *args], capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return json.loads(result.stdout)
    def codes(self, result):
        return {f["code"] for f in result["findings"]}
    def test_shared_directory_contract(self):
        fixture = json.loads(SCRIPT.with_name("chapter-inventory-fixtures.json").read_text())
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                for filename in case["files"]: self.prose(filename)
                result = self.run_audit()
                self.assertEqual(result["status"], "PASS")
                self.assertEqual(result["metrics"]["existing_chapters_in_range"], len(case["chapters"]))
                self.assertEqual(result["metrics"]["expected_chapters"], case["chapters"])

    def test_nested_and_excluded_files(self):
        for n in range(1, 4):
            self.prose(f"正文/第一卷/第{n:03}章_船票.md")
        for folder in ("候选", "_历史", "_原稿_备份", ".agent"):
            self.prose(f"正文/{folder}/第1章_副本.md")
        result = self.run_audit()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metrics"]["existing_chapters_in_range"], 3)
        self.assertEqual(result["metrics"]["inflation_risk_signals"], 3)
    def test_full_volume_missing_vs_future(self):
        self.prose("正文/第1章.md")
        self.assertIn("Prose_Chapter_Missing", self.codes(self.run_audit()))
        result = self.run_audit("--through-chapter", "1")
        self.assertEqual(result["metrics"]["future_chapters"], [2, 3])
        self.assertEqual(result["status"], "PASS")
    def test_duplicates_do_not_silently_choose(self):
        self.prose("正文/第1章.md")
        self.prose("正文/第一卷/第001章_船票.md")
        self.assertIn("Prose_Chapter_Duplicate", self.codes(self.run_audit("--through-chapter", "1")))
    def test_candidate_completes_volume_but_not_duplicate(self):
        for n in (1, 2): self.prose(f"正文/第{n}章.md")
        candidate = self.prose("候选/第3章_出发.md")
        self.assertEqual(self.run_audit("--candidate", str(candidate))["status"], "PASS")
        self.prose("正文/第3章.md")
        self.assertIn("Prose_Chapter_Duplicate", self.codes(self.run_audit("--candidate", str(candidate))))
    def test_candidate_alias_has_same_audit_digest(self):
        for n in (1, 2): self.prose(f"正文/第{n}章.md")
        candidate = self.prose("候选/第3章_出发.md")
        alias = self.book / "candidate-alias"
        alias.symlink_to(self.book / "候选", target_is_directory=True)
        actual = self.run_audit("--candidate", str(candidate))
        alternate = self.run_audit("--candidate", str(alias / candidate.name))
        self.assertEqual(actual, alternate)

    def tracking(self, **fields):
        self.prose("追踪/_tracking-state.json", json.dumps(fields))
    def test_declared_gap_and_adopted_missing(self):
        self.prose("正文/第1章.md")
        self.prose("正文/第3章.md")
        self.tracking(last_committed_chapter=3, chapter_gaps=[dict(start_chapter=2, end_chapter=2, declared_at_chapter=3, reason="作者确认跳号")])
        result = self.run_audit()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["metrics"]["excluded_chapters"], [2])
        (self.book / "正文/第3章.md").unlink()
        self.assertIn("Prose_Chapter_Missing", self.codes(self.run_audit("--through-chapter", "1")))
    def test_bad_gap_and_reversed_range_cannot_pass(self):
        for n in range(1, 4): self.prose(f"正文/第{n}章.md")
        self.tracking(last_committed_chapter=3, imported_through_chapter=2, chapter_gaps=[dict(start_chapter=2, end_chapter=2, declared_at_chapter=3, reason="invalid imported gap")])
        self.assertIn("Prose_Tracking_Invalid", self.codes(self.run_audit()))
        (self.book / "追踪/_tracking-state.json").unlink()
        (self.book / "大纲/卷纲_第1卷.md").write_text("章节范围：第3–1章\n## 核心矛盾\n争回船票。", encoding="utf-8")
        self.assertIn("Prose_Coverage_Unknown", self.codes(self.run_audit()))

    def test_corrupt_tracking_not_ignored(self):
        self.prose("正文/第1章.md")
        self.prose("追踪/_tracking-state.json", "{")
        self.assertIn("Prose_Tracking_Invalid", self.codes(self.run_audit("--through-chapter", "1")))

if __name__ == "__main__": unittest.main()
