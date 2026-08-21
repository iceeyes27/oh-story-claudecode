#!/usr/bin/env python3
"""候选系统脚本 candidate-commit.py 的行为回归测试。

复用 test-tracking-commit.py 的合法事务构造器，验证核心不变式：
- 候选存在时正稿与 _tracking-state.json 不动（追踪只在 promote 推进）。
- promote 幂等安全：追踪回放失败时正文移回候选、状态不变、可重跑。
- reject/rewrite 只归档，不碰正稿与追踪。
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/story-write/scripts/candidate-commit.py"
TRACKING_TOOL = ROOT / "skills/story-write/scripts/tracking_commit.py"

# 借用追踪测试里的合法文档构造器，避免重复维护事务形状。
_spec = importlib.util.spec_from_file_location(
    "tracking_test_fixtures", ROOT / "scripts/test-tracking-commit.py"
)
assert _spec and _spec.loader
_fixtures = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_fixtures)
initial_document = _fixtures.initial_document
transaction = _fixtures.transaction


def run(tool: Path, args: list[str], *, expect: int = 0) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(tool), *args],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
    )
    assert completed.returncode == expect, (
        f"expected {expect} got {completed.returncode}\nSTDOUT:{completed.stdout}\nSTDERR:{completed.stderr}"
    )
    return completed


class CandidateCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "候选测试书"
        self.project.mkdir()
        self.candidate_dir = self.project / "正文" / "候选"
        self.candidate_dir.mkdir(parents=True)
        # 初始化追踪状态（last_committed_chapter=0, state_revision=0）。
        self._tracking("init", initial_document(last_chapter=0))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    # ---- helpers ----
    def _tracking(self, command: str, document: dict | None = None, *, expect: int = 0):
        args = [command, "--project", str(self.project)]
        if document is not None:
            path = Path(self.temporary.name) / f"{command}-{os.urandom(4).hex()}.json"
            path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
            args.extend(["--input", str(path)])
        return run(TRACKING_TOOL, args, expect=expect)

    def _candidate(self, args: list[str], *, expect: int = 0):
        return run(TOOL, [*args, "--project", str(self.project)] if "--project" not in args else args, expect=expect)

    def read_state(self) -> dict:
        return json.loads((self.project / "追踪/_tracking-state.json").read_text(encoding="utf-8"))

    def make_candidate(self, chapter: int, *, with_transaction: bool = True, tx_overrides: dict | None = None) -> Path:
        prose = self.candidate_dir / f"第{chapter:03d}章_测试章名.md"
        prose.write_text(f"# 第{chapter}章\n候选正文内容。\n", encoding="utf-8")
        if with_transaction:
            doc = transaction(chapter)
            if tx_overrides:
                doc.update(tx_overrides)
            (self.candidate_dir / f"第{chapter:03d}章_追踪事务.json").write_text(
                json.dumps(doc, ensure_ascii=False), encoding="utf-8"
            )
        return prose

    def final_files(self) -> list[str]:
        body = self.project / "正文"
        return sorted(p.name for p in body.iterdir() if p.is_file() and p.suffix == ".md")

    def history_files(self) -> list[str]:
        history = self.candidate_dir / "_历史"
        return sorted(p.name for p in history.iterdir()) if history.is_dir() else []

    # ---- tests ----
    def test_candidate_does_not_touch_body_or_tracking(self) -> None:
        self.make_candidate(1)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.read_state()["last_committed_chapter"], 0)

    def test_promote_moves_prose_and_advances_tracking(self) -> None:
        self.make_candidate(1)
        result = json.loads(self._candidate(["promote", "--chapter", "1"]).stdout)
        self.assertEqual(result["action"], "promote")
        self.assertEqual(self.final_files(), ["第001章_测试章名.md"])
        self.assertEqual(self.read_state()["last_committed_chapter"], 1)
        self.assertEqual(self.read_state()["state_revision"], 1)
        # 候选正文与事务已清出候选目录（事务归档到 _历史）。
        self.assertFalse((self.candidate_dir / "第001章_测试章名.md").exists())
        self.assertFalse((self.candidate_dir / "第001章_追踪事务.json").exists())
        run(TRACKING_TOOL, ["check", "--project", str(self.project)])

    def test_promote_refreshes_stale_expected_revision(self) -> None:
        # 候选事务里烤入过期 revision，promote 应刷新为当前值后成功。
        self.make_candidate(1, tx_overrides={"expected_state_revision": 99})
        self._candidate(["promote", "--chapter", "1"])
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_promote_missing_transaction_aborts(self) -> None:
        self.make_candidate(1, with_transaction=False)
        self._candidate(["promote", "--chapter", "1"], expect=2)
        # 正稿与追踪不受影响，候选正文仍在原处。
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").exists())

    def test_promote_rolls_back_on_tracking_failure(self) -> None:
        # 破坏事务（删掉 delta）触发 tracking_commit 校验失败，验证正文移回、状态不变、可重跑。
        prose = self.make_candidate(1)
        broken = transaction(1)
        del broken["delta"]
        (self.candidate_dir / "第001章_追踪事务.json").write_text(
            json.dumps(broken, ensure_ascii=False), encoding="utf-8"
        )
        self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertTrue(prose.exists(), "追踪失败后候选正文必须移回原处以支持重跑")

        # 修好事务后重跑同一 promote 成功。
        (self.candidate_dir / "第001章_追踪事务.json").write_text(
            json.dumps(transaction(1), ensure_ascii=False), encoding="utf-8"
        )
        self._candidate(["promote", "--chapter", "1"])
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_promote_refuses_to_overwrite_final(self) -> None:
        self.make_candidate(1)
        self._candidate(["promote", "--chapter", "1"])
        # 再造一个同章候选，promote 应拒绝覆盖正稿。
        self.make_candidate(1)
        self._candidate(["promote", "--chapter", "1"], expect=2)

    def test_reject_archives_without_touching_body(self) -> None:
        self.make_candidate(1)
        result = json.loads(self._candidate(["reject", "--chapter", "1"]).stdout)
        self.assertEqual(result["action"], "reject")
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertFalse((self.candidate_dir / "第001章_测试章名.md").exists())
        history = self.history_files()
        self.assertTrue(any(name.startswith("第001章_测试章名") for name in history))
        self.assertTrue(any("追踪事务" in name for name in history))

    def test_rewrite_flag_marks_action(self) -> None:
        self.make_candidate(1)
        result = json.loads(self._candidate(["reject", "--chapter", "1", "--rewrite"]).stdout)
        self.assertEqual(result["action"], "rewrite")

    def test_list_reports_pending(self) -> None:
        self.make_candidate(1)
        self.make_candidate(2, with_transaction=False)
        entries = json.loads(self._candidate(["list"]).stdout)
        by_chapter = {e["chapter"]: e for e in entries}
        self.assertTrue(by_chapter[1]["has_transaction"])
        self.assertFalse(by_chapter[2]["has_transaction"])
        self.assertFalse(by_chapter[1]["final_exists"])

    def test_promote_all_in_order(self) -> None:
        self.make_candidate(1)
        self.make_candidate(2)
        results = json.loads(self._candidate(["promote", "--all"]).stdout)
        self.assertEqual([r["chapter"] for r in results], [1, 2])
        self.assertEqual(self.read_state()["last_committed_chapter"], 2)
        self.assertEqual(sorted(self.final_files()), ["第001章_测试章名.md", "第002章_测试章名.md"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
