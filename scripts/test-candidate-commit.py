#!/usr/bin/env python3
"""候选系统脚本 candidate-commit.py 的行为回归测试。

复用 test-tracking-commit.py 的合法事务构造器，验证核心不变式：
- 候选存在时正稿与 _tracking-state.json 不动（追踪只在 promote 推进）。
- promote 幂等安全：追踪回放失败时正文移回候选、状态不变、可重跑。
- reject/rewrite 只归档，不碰正稿与追踪。
"""

from __future__ import annotations

import importlib.util
import hashlib
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


def run(
    tool: Path,
    args: list[str],
    *,
    expect: int = 0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        [sys.executable, str(tool), *args],
        text=True,
        capture_output=True,
        check=False,
        encoding="utf-8",
        env=env,
    )
    assert completed.returncode == expect, (
        f"expected {expect} got {completed.returncode}\nSTDOUT:{completed.stdout}\nSTDERR:{completed.stderr}"
    )
    return completed


class CandidateCommitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._reset_project()

    def _reset_project(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "候选测试书"
        self.project.mkdir()
        # 候选目录在书根，刻意不放 正文/ 下（避免写后 hook 把候选认成正式章节）。
        self.candidate_dir = self.project / "候选"
        self.candidate_dir.mkdir(parents=True)
        (self.project / "正文").mkdir()
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

    def _candidate(
        self,
        args: list[str],
        *,
        expect: int = 0,
        env: dict[str, str] | None = None,
    ):
        return run(
            TOOL,
            [*args, "--project", str(self.project)] if "--project" not in args else args,
            expect=expect,
            env=env,
        )

    def read_state(self) -> dict:
        return json.loads((self.project / "追踪/_tracking-state.json").read_text(encoding="utf-8"))

    # 触发 check-ai-patterns blocking 的短句（reverse-not-is + negation-parade）。
    TOXIC = "他想要的是尊严，而不是金钱。他知道，这世上没有光，没有声音，没有温度。"

    def make_candidate(
        self,
        chapter: int,
        *,
        with_transaction: bool = True,
        tx_overrides: dict | None = None,
        body: str | None = None,
    ) -> Path:
        title = "测试章名" if chapter == 1 else f"暗门{chapter}"
        prose = self.candidate_dir / f"第{chapter:03d}章_{title}.md"
        prefix = body if body is not None else f"# 第{chapter}章\n"
        visible = "".join(prefix.split())
        fill_length = max(0, 2300 - len(visible))
        fill = "".join(chr(0x6000 + ((chapter * 2500 + index) % 7000)) for index in range(fill_length))
        content = prefix + fill + "。\n"
        prose.write_text(content, encoding="utf-8")
        outline_dir = self.project / "大纲"
        skeleton_dir = self.project / "骨架"
        outline_dir.mkdir(exist_ok=True)
        skeleton_dir.mkdir(exist_ok=True)
        outline = outline_dir / f"细纲_第{chapter:03d}章.md"
        outline.write_text(
            f"# 第{chapter}章细纲\n- 情节点：本章完成一次可验证推进。\n",
            encoding="utf-8",
        )
        skeleton = skeleton_dir / f"第{chapter:03d}章_{title}.md"
        skeleton.write_text(
            f"# 第{chapter}章 {title}\n\n"
            "## 章节契约\n"
            f"- 来源细纲：大纲/{outline.name}\n"
            "- 最终正文字数目标：2400\n"
            "- 目标情绪：紧张\n- 读者获得：关键进展\n- 禁止提前释放：后续真相\n"
            "- 开场动作：人物进入现场\n- 章尾钩子：发现新物证\n\n"
            "## 细纲覆盖\n- [x] O1 本章推进 -> 场景 1\n\n"
            "## 场景 1\n- 时空与人物：现场与主角\n- 场景目标：核验物证\n- 阻力：资料缺失\n"
            "- 动作链：进入现场并核验\n- 结果变化：获得线索\n- 情绪转折：从怀疑到确认\n"
            "- 信息/伏笔：物证编号\n- 台词意图与潜台词：试探责任人\n- 正文字数预算：800\n\n"
            "## 场景 2\n- 时空与人物：办公室与主角\n- 场景目标：追查来源\n- 阻力：权限受限\n"
            "- 动作链：提交申请并复核\n- 结果变化：锁定范围\n- 情绪转折：从受阻到突破\n"
            "- 信息/伏笔：访问记录\n- 台词意图与潜台词：逼问时间点\n- 正文字数预算：800\n\n"
            "## 场景 3\n- 时空与人物：走廊与主角\n- 场景目标：确认结论\n- 阻力：对方回避\n"
            "- 动作链：展示证据并追问\n- 结果变化：出现新冲突\n- 情绪转折：从确定到警觉\n"
            "- 信息/伏笔：异常签名\n- 台词意图与潜台词：迫使对方表态\n- 正文字数预算：800\n\n"
            "## 扩写约束\n- 人物声线：克制直接\n- 事实红线：不新增无来源事实\n- 允许自由发挥：动作细节\n",
            encoding="utf-8",
        )
        if with_transaction:
            doc = transaction(chapter)
            doc["expected_state_revision"] = self.read_state()["state_revision"]
            if tx_overrides:
                doc.update(tx_overrides)
            evidence = content.splitlines()[-1][:8]
            digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
            doc["candidate_binding"] = {
                "schema_version": 1,
                "quality_profile": "fanqie-long-v1",
                "prose": {"path": f"候选/{prose.name}", "sha256": digest(prose)},
                "outline": {"path": f"大纲/{outline.name}", "sha256": digest(outline)},
                "skeleton": {"path": f"骨架/{skeleton.name}", "sha256": digest(skeleton)},
                "coverage": [{"id": "O1", "evidence": evidence}],
            }
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

    def test_promote_rejects_stale_expected_revision_before_writes(self) -> None:
        self.make_candidate(1, tx_overrides={"expected_state_revision": 99})
        self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.final_files(), [])
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").exists())

    def test_promote_missing_transaction_aborts(self) -> None:
        self.make_candidate(1, with_transaction=False)
        self._candidate(["promote", "--chapter", "1"], expect=2)
        # 正稿与追踪不受影响，候选正文仍在原处。
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").exists())

    def test_promote_rolls_back_on_tracking_failure(self) -> None:
        # 破坏事务（删掉 delta）应在任何移动前被预演拒绝，修复后可重跑。
        prose = self.make_candidate(1)
        transaction_path = self.candidate_dir / "第001章_追踪事务.json"
        original = json.loads(transaction_path.read_text(encoding="utf-8"))
        broken = dict(original)
        del broken["delta"]
        transaction_path.write_text(
            json.dumps(broken, ensure_ascii=False), encoding="utf-8"
        )
        self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertTrue(prose.exists(), "追踪预演失败后候选正文必须保持原处")

        # 修好事务后重跑同一 promote 成功。
        transaction_path.write_text(json.dumps(original, ensure_ascii=False), encoding="utf-8")
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

    def test_promote_quality_gate_blocks_toxic(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n{self.TOXIC}\n")
        self._candidate(["promote", "--chapter", "1"], expect=2)
        # 未过质量门：正稿与追踪不变，候选仍在原处。
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").exists())

    def test_promote_quality_gate_fails_when_node_is_unavailable(self) -> None:
        self.make_candidate(1)
        env = os.environ.copy()
        env["PATH"] = ""
        result = self._candidate(["promote", "--chapter", "1"], expect=2, env=env)
        self.assertIn("未找到 node", result.stderr)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)

    def test_promote_no_scan_bypasses_gate(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n{self.TOXIC}\n")
        self._candidate(["promote", "--chapter", "1", "--no-scan"])
        self.assertEqual(self.final_files(), ["第001章_测试章名.md"])
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_promote_exemption_marker_bypasses_gate(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n<!-- 去味:跳过 -->\n{self.TOXIC}\n")
        self._candidate(["promote", "--chapter", "1"])
        self.assertEqual(self.final_files(), ["第001章_测试章名.md"])
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_promote_all_in_order(self) -> None:
        self.make_candidate(1)
        self.make_candidate(2, tx_overrides={"expected_state_revision": 1})
        results = json.loads(self._candidate(["promote", "--all"]).stdout)
        self.assertEqual([r["chapter"] for r in results], [1, 2])
        self.assertEqual(self.read_state()["last_committed_chapter"], 2)
        self.assertEqual(sorted(self.final_files()), ["第001章_测试章名.md", "第002章_暗门2.md"])

    def test_recover_is_idempotent_after_each_persisted_phase(self) -> None:
        for index, phase in enumerate(("prepared", "prose_moved", "tracking_committed")):
            with self.subTest(phase=phase):
                if index:
                    self.temporary.cleanup()
                    self._reset_project()
                self.make_candidate(1)
                env = os.environ.copy()
                env["STORY_CANDIDATE_FAIL_AFTER"] = phase
                self._candidate(["promote", "--chapter", "1"], expect=97, env=env)
                first = json.loads(self._candidate(["recover", "--chapter", "1"]).stdout)
                second = json.loads(self._candidate(["recover", "--chapter", "1"]).stdout)
                self.assertEqual(first[0]["state_revision"], 1)
                self.assertEqual(second[0]["state_revision"], 1)
                self.assertEqual(self.read_state()["state_revision"], 1)
                self.assertEqual(self.final_files(), ["第001章_测试章名.md"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
