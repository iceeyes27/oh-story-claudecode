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
import shutil
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
metric = _fixtures.metric


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

    def _reset_project(self, *, last_chapter: int = 0) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.project = Path(self.temporary.name) / "候选测试书"
        self.project.mkdir()
        # 候选目录在书根，刻意不放 正文/ 下（避免写后 hook 把候选认成正式章节）。
        self.candidate_dir = self.project / "候选"
        self.candidate_dir.mkdir(parents=True)
        (self.project / "正文").mkdir()
        # 初始化追踪状态（last_committed_chapter=0, state_revision=0）。
        self._tracking("init", initial_document(last_chapter=last_chapter))
        for chapter in range(1, last_chapter + 1):
            first = chr(0x4E00 + chapter * 2)
            second = chr(0x4E00 + chapter * 2 + 1)
            path = self.project / "正文" / f"第{chapter:03d}章_{first}{second}.md"
            path.write_text(f"# 第{chapter}章 {first}{second}\n本章事实{first}{second}。\n", encoding="utf-8")

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

    # 触发 check-ai-patterns finding 的短句（reverse-not-is + negation-parade）。
    TOXIC = "他想要的是尊严，而不是金钱。他知道，这世上没有光，没有声音，没有温度。"
    # scan_gate 真正会 blocking 的样本（check-degeneration.js 的 meta-leak 工程词泄漏）。
    # TOXIC 那组 AI 句式当前全是 advisory，`--fail-on=blocking` 对它永不触发，不能用来测门禁。
    GATE_BLOCKING = "他站在门口。细纲要求他必须离开。"

    @staticmethod
    def _canonical_sha(value: object) -> str:
        payload = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _reader_paths(self, prose: Path) -> list[Path]:
        accepted = sorted(
            (path for path in (self.project / "正文").glob("第*章*.md") if path.is_file()),
            key=lambda path: path.name,
        )
        paths = [*accepted, prose]
        known = self.project / "正文/_已知实体.txt"
        if known.is_file():
            paths.append(known)
        return paths

    def _prose_files(self, prose: Path) -> tuple[list[dict[str, str]], str]:
        entries = []
        rows = []
        for path in self._reader_paths(prose):
            relative = path.relative_to(self.project).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            entries.append({"path": relative, "sha256": digest})
            rows.append(f"{relative}\0{digest}")
        set_digest = hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()
        return entries, set_digest

    def _rc_report(self, prose: Path) -> dict:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in self._reader_paths(prose):
                shutil.copy2(path, root / path.name)
            completed = subprocess.run(
                ["node", str(ROOT / "skills/_shared/scripts/check-first-mention.js"), str(root), "--json"],
                text=True, capture_output=True, check=False, encoding="utf-8",
            )
        self.assertIn(completed.returncode, (0, 1), completed.stderr)
        return json.loads(completed.stdout)

    def _arc_report(self, ledger: dict) -> dict:
        path = Path(self.temporary.name) / f"ledger-{os.urandom(4).hex()}.json"
        path.write_text(json.dumps(ledger, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            ["node", str(ROOT / "skills/_shared/scripts/arc-ledger.js"), str(path), "--json", "--window=15"],
            text=True, capture_output=True, check=False, encoding="utf-8",
        )
        self.assertIn(completed.returncode, (0, 1), completed.stderr)
        return json.loads(completed.stdout)

    def _logic_checks(self, chapter: int, prose: Path, *, ledger: dict | None = None) -> dict:
        candidate_sha = hashlib.sha256(prose.read_bytes()).hexdigest()
        prose_files, set_sha = self._prose_files(prose)
        anchor = prose.read_text(encoding="utf-8-sig").splitlines()[0]
        base = {
            "status": "pass",
            "findings": [],
            "evidence": [{"path": prose.relative_to(self.project).as_posix(), "anchor": anchor}],
            "candidate_sha256": candidate_sha,
            "prose_files": prose_files,
            "prose_set_sha256": set_sha,
        }
        report = self._rc_report(prose)
        checks = {
            receipt_id: {**base, "run_id": f"test-{receipt_id}-{chapter}"}
            for receipt_id in ("rc-01", "rc-02", "rc-03")
        }
        checks["rc-01"]["result_sha256"] = self._canonical_sha(report)
        if chapter == 15:
            ledger = ledger or {
                "book": "候选测试书",
                "window": 15,
                "chapters": [
                    {"num": number, "opens": [], "closes": [], "mainAdvance": True}
                    for number in range(1, 16)
                ],
            }
            ledger_sha = self._canonical_sha(ledger)
            arc_report = self._arc_report(ledger)
            checks["arc-01"] = {
                **base,
                "run_id": "test-arc-01-15",
                "ledger": ledger,
                "ledger_sha256": ledger_sha,
            }
            checks["arc-02"] = {
                "run_id": "test-arc-02-15",
                "status": "pass" if not arc_report["blocking"] else "blocking",
                "findings": [],
                "evidence": [{"anchor": "ledger threshold"}],
                "candidate_sha256": candidate_sha,
                "ledger_sha256": ledger_sha,
                "result_sha256": self._canonical_sha(arc_report),
            }
        return checks

    def _transaction_path(self, chapter: int) -> Path:
        return self.candidate_dir / f"第{chapter:03d}章_追踪事务.json"

    def _mutate_binding(self, chapter: int, mutate) -> None:
        path = self._transaction_path(chapter)
        document = json.loads(path.read_text(encoding="utf-8"))
        mutate(document["candidate_binding"])
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def make_candidate(
        self,
        chapter: int,
        *,
        with_transaction: bool = True,
        tx_overrides: dict | None = None,
        body: str | None = None,
        ledger: dict | None = None,
        title: str | None = None,
    ) -> Path:
        title = title or ("测试章名" if chapter == 1 else f"暗门{chapter}")
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
            f"# 第{chapter}章细纲\n"
            "- 情节点：本章完成一次可验证推进。\n"
            "- 目标情绪：紧张\n"
            "- 主角目标/关键选择：核验物证并决定是否上报\n"
            f"- 结尾拍ID/类型：EB-01-{chapter:03d}；choice；主角带走物证\n"
            f"- 期待ID/类型：EX-01-{chapter:03d}；open_question；物证指向谁\n"
            f"- 读者验收预期：must_know=[物证在场]；may_believe=[只是笔误]；must_not_know=[终局真凶]；open_ids=[EX-01-{chapter:03d}]\n"
            "- 前因：开篇无前因\n"
            "- 后果指向：本章推进可被后续章节使用\n"
            "- 读者已知：已知现场；尚不知真凶\n",
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
                "schema_version": 2,
                "quality_profile": "fanqie-long-v2",
                "prose": {"path": f"候选/{prose.name}", "sha256": digest(prose)},
                "outline": {"path": f"大纲/{outline.name}", "sha256": digest(outline)},
                "skeleton": {"path": f"骨架/{skeleton.name}", "sha256": digest(skeleton)},
                "coverage": [{"id": "O1", "evidence": evidence}],
                "logic_checks": self._logic_checks(chapter, prose, ledger=ledger),
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

    def test_candidate_workflow_documents_v2_logic_contract(self) -> None:
        workflow = (ROOT / "skills/story-write/references/candidate-workflow.md").read_text(encoding="utf-8")
        binding = (ROOT / "skills/story-write/references/candidate-logic-binding.md").read_text(encoding="utf-8")
        self.assertIn("candidate_binding` v2", workflow)
        self.assertIn("fanqie-long-v2", workflow)
        for receipt_id in ("rc-01", "rc-02", "rc-03", "arc-01", "arc-02"):
            self.assertIn(receipt_id, binding)
        self.assertIn("第 3、5、10、14、16 章", binding)
        self.assertIn("blocking-approved", binding)

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

    def test_promote_treats_style_pattern_as_review_finding(self) -> None:
        prose = self.make_candidate(1, body=f"# 第1章\n{self.TOXIC}\n")
        scan = subprocess.run(
            [
                "node",
                str(ROOT / "skills/_shared/scripts/check-ai-patterns.js"),
                "--check",
                "--fail-on=blocking",
                str(prose),
            ],
            text=True,
            capture_output=True,
            check=False,
            encoding="utf-8",
        )
        self.assertEqual(scan.returncode, 0)
        self.assertIn("reverse-not-is", scan.stdout)
        self._candidate(["promote", "--chapter", "1"])
        self.assertEqual(self.final_files(), ["第001章_测试章名.md"])
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_promote_quality_gate_fails_when_node_is_unavailable(self) -> None:
        self.make_candidate(1)
        env = os.environ.copy()
        env["PATH"] = ""
        result = self._candidate(["promote", "--chapter", "1"], expect=2, env=env)
        self.assertIn("未找到 node", result.stderr)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)

    def test_promote_no_scan_bypasses_ai_gate_only(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n{self.GATE_BLOCKING}\n")
        self._candidate(["promote", "--chapter", "1", "--no-scan", "--reason", "作者确认本章为引用体"])
        self.assertEqual(self.final_files(), ["第001章_测试章名.md"])
        self.assertEqual(self.read_state()["state_revision"], 1)

    def test_promote_no_scan_requires_reason(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n{self.GATE_BLOCKING}\n")
        result = self._candidate(["promote", "--chapter", "1", "--no-scan"], expect=2)
        self.assertIn("--no-scan 必须同时给出 --reason", result.stderr)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)

    def test_promote_records_scan_skip_reason(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n{self.GATE_BLOCKING}\n")
        self._candidate(["promote", "--chapter", "1", "--no-scan", "--reason", "作者确认本章为引用体"])
        journals = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (self.candidate_dir / "_历史").iterdir()
            if path.name.startswith("采用事务-")
        ]
        self.assertTrue(journals)
        self.assertEqual(journals[0]["scan_skip"]["reason"], "作者确认本章为引用体")

    def test_promote_ignores_in_prose_exemption_marker(self) -> None:
        # 正文里的 `<!-- 去味:跳过 -->` 由写正文的一方产出，不得用来关掉检查自己的门。
        # 作者要豁免走 CLI 的 --no-scan --reason，留痕可审计。
        self.make_candidate(1, body=f"# 第1章\n<!-- 去味:跳过 -->\n{self.GATE_BLOCKING}\n")
        result = self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertIn("候选未通过采用前确定性检查", result.stderr)
        self.assertEqual(self.final_files(), [])
        self.assertEqual(self.read_state()["state_revision"], 0)

    def test_promote_honors_explicit_terse_title_profile(self) -> None:
        settings = self.project / "设定"
        settings.mkdir()
        (settings / "题材定位.md").write_text("# 题材定位\n- 标题档位：terse\n", encoding="utf-8")
        self.make_candidate(1, title="这是一个很长的测试标题")
        result = self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertIn("章节标题未通过", result.stderr)

    def test_promote_rejects_v1_binding_with_regeneration_message(self) -> None:
        self.make_candidate(1)
        self._mutate_binding(1, lambda binding: binding.update({
            "schema_version": 1, "quality_profile": "fanqie-long-v1",
        }))
        result = self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertIn("v1", result.stderr)
        self.assertIn("重新生成", result.stderr)

    def test_promote_rejects_missing_or_unknown_logic_id(self) -> None:
        for case in ("missing", "unknown"):
            with self.subTest(case=case):
                if case == "unknown":
                    self.temporary.cleanup()
                    self._reset_project()
                self.make_candidate(1)
                if case == "missing":
                    self._mutate_binding(1, lambda binding: binding["logic_checks"].pop("rc-03"))
                else:
                    self._mutate_binding(1, lambda binding: binding["logic_checks"].update({
                        "rc-99": dict(binding["logic_checks"]["rc-03"])
                    }))
                result = self._candidate(["promote", "--chapter", "1"], expect=2)
                self.assertIn("logic_checks 必须精确包含", result.stderr)
                self.assertEqual(self.final_files(), [])

    def test_promote_rejects_duplicate_logic_id_in_json(self) -> None:
        self.make_candidate(1)
        path = self._transaction_path(1)
        text = path.read_text(encoding="utf-8")
        text = text.replace('"logic_checks": {', '"logic_checks": {"rc-01": {},', 1)
        path.write_text(text, encoding="utf-8")
        result = self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertIn("JSON 含重复键：rc-01", result.stderr)

    def test_promote_rejects_stale_reader_file_hash(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=1)
        self.make_candidate(2)
        accepted = next((self.project / "正文").glob("第001章_*.md"))
        accepted.write_text(accepted.read_text(encoding="utf-8") + "正文后来改变。\n", encoding="utf-8")
        result = self._candidate(["promote", "--chapter", "2"], expect=2)
        self.assertIn("prose_files", result.stderr)
        self.assertIn("sha256 已过期", result.stderr)

    def test_promote_rejects_empty_or_unbound_semantic_evidence(self) -> None:
        for case in ("empty", "outside-prose", "missing-anchor"):
            with self.subTest(case=case):
                if case != "empty":
                    self.temporary.cleanup()
                    self._reset_project()
                self.make_candidate(1)

                def invalidate(binding):
                    receipt = binding["logic_checks"]["rc-02"]
                    if case == "empty":
                        receipt["evidence"] = []
                    elif case == "outside-prose":
                        receipt["evidence"] = [{
                            "path": "大纲/细纲_第001章.md",
                            "anchor": "第1章细纲",
                        }]
                    else:
                        receipt["evidence"][0]["anchor"] = "正文中不存在的证据锚点"

                self._mutate_binding(1, invalidate)
                result = self._candidate(["promote", "--chapter", "1"], expect=2)
                self.assertIn("rc-02.evidence", result.stderr)
                self.assertEqual(self.final_files(), [])

    def test_promote_reruns_rc01_even_with_no_scan(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=2)
        first = next((self.project / "正文").glob("第001章_*.md"))
        first.write_text(first.read_text(encoding="utf-8") + "九幽阁忽然亮了。\n", encoding="utf-8")
        self.make_candidate(3, body="# 第3章\n九幽阁再次亮起。\n")
        result = self._candidate(["promote", "--chapter", "3", "--no-scan", "--reason", "回归测试"], expect=2)
        self.assertIn("rc-01 复验发现 blocking", result.stderr)
        self.assertEqual(self.final_files(), sorted(path.name for path in (self.project / "正文").glob("*.md")))

    def test_chapter_14_and_16_do_not_require_arc_receipts(self) -> None:
        for chapter in (14, 16):
            with self.subTest(chapter=chapter):
                self.temporary.cleanup()
                self._reset_project(last_chapter=chapter - 1)
                self.make_candidate(chapter)
                document = json.loads(self._transaction_path(chapter).read_text(encoding="utf-8"))
                self.assertEqual(set(document["candidate_binding"]["logic_checks"]), {"rc-01", "rc-02", "rc-03"})
                self._candidate(["promote", "--chapter", str(chapter)])
                self.assertEqual(self.read_state()["last_committed_chapter"], chapter)

    @staticmethod
    def _blocking_ledger() -> dict:
        return {
            "book": "候选测试书",
            "window": 15,
            "chapters": [
                {
                    "num": number,
                    "opens": [{"id": f"Q{number}", "q": f"问题{number}"}],
                    "closes": [],
                    "mainAdvance": False,
                }
                for number in range(1, 16)
            ],
        }

    def test_chapter_15_requires_ledger_and_valid_arc02(self) -> None:
        for case in ("missing", "invalid"):
            with self.subTest(case=case):
                self.temporary.cleanup()
                self._reset_project(last_chapter=14)
                self.make_candidate(15)
                if case == "missing":
                    self._mutate_binding(15, lambda binding: binding["logic_checks"]["arc-01"].pop("ledger"))
                else:
                    def invalidate(binding):
                        ledger = binding["logic_checks"]["arc-01"]["ledger"]
                        ledger["chapters"][0]["closes"] = ["NOT-OPEN"]
                        digest = self._canonical_sha(ledger)
                        binding["logic_checks"]["arc-01"]["ledger_sha256"] = digest
                        binding["logic_checks"]["arc-02"]["ledger_sha256"] = digest
                    self._mutate_binding(15, invalidate)
                result = self._candidate(["promote", "--chapter", "15"], expect=2)
                self.assertIn("arc-01.ledger" if case == "missing" else "arc-02 开篇阈值检查", result.stderr)
                self.assertEqual(self.read_state()["last_committed_chapter"], 14)

    def test_arc02_blocking_requires_exact_author_approval(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=14)
        self.make_candidate(15, ledger=self._blocking_ledger())
        result = self._candidate(["promote", "--chapter", "15"], expect=2)
        self.assertIn("缺少作者批准", result.stderr)

        def approve(binding):
            arc02 = binding["logic_checks"]["arc-02"]
            arc02["status"] = "blocking-approved"
            arc02["override"] = {
                "approved_by_author": True,
                "result_sha256": arc02["result_sha256"],
                "reason": "作者确认本书为高悬念开篇并接受当前收支。",
            }
        self._mutate_binding(15, approve)
        self._candidate(["promote", "--chapter", "15"])
        self.assertEqual(self.read_state()["last_committed_chapter"], 15)

    def test_no_scan_cannot_bypass_logic_receipts(self) -> None:
        self.make_candidate(1, body=f"# 第1章\n{self.TOXIC}\n")
        self._mutate_binding(1, lambda binding: binding["logic_checks"].pop("rc-02"))
        result = self._candidate(["promote", "--chapter", "1", "--no-scan", "--reason", "回归测试"], expect=2)
        self.assertIn("logic_checks 必须精确包含", result.stderr)
        self.assertEqual(self.final_files(), [])

    def test_promote_all_with_current_serial_candidate(self) -> None:
        self.make_candidate(1)
        results = json.loads(self._candidate(["promote", "--all"]).stdout)
        self.assertEqual([r["chapter"] for r in results], [1])
        self.assertEqual(self.read_state()["last_committed_chapter"], 1)
        self.assertEqual(self.final_files(), ["第001章_测试章名.md"])

    def test_promote_all_rejects_multiple_candidates_before_writes(self) -> None:
        self.make_candidate(1)
        self.make_candidate(2)
        result = self._candidate(["promote", "--all"], expect=2)
        self.assertIn("不支持多个候选", result.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.final_files(), [])
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").is_file())
        self.assertTrue((self.candidate_dir / "第002章_暗门2.md").is_file())

    def test_recover_rejects_changed_reader_view_before_move_or_tracking(self) -> None:
        for phase in ("prepared", "prose_moved"):
            with self.subTest(phase=phase):
                self.temporary.cleanup()
                self._reset_project(last_chapter=1)
                self.make_candidate(2)
                env = os.environ.copy()
                env["STORY_CANDIDATE_FAIL_AFTER"] = phase
                self._candidate(["promote", "--chapter", "2"], expect=97, env=env)
                accepted = next((self.project / "正文").glob("第001章_*.md"))
                accepted.write_text(accepted.read_text(encoding="utf-8") + "恢复前被修改。\n", encoding="utf-8")
                result = self._candidate(["recover", "--chapter", "2"], expect=2)
                self.assertIn("读者正文摘要已变化", result.stderr)
                self.assertEqual(self.read_state()["state_revision"], 0)
                if phase == "prepared":
                    self.assertTrue((self.candidate_dir / "第002章_暗门2.md").is_file())
                else:
                    self.assertTrue((self.project / "正文/第002章_暗门2.md").is_file())

    def test_recover_validates_transaction_digest_before_moving_prose(self) -> None:
        self.make_candidate(1)
        env = os.environ.copy()
        env["STORY_CANDIDATE_FAIL_AFTER"] = "prepared"
        self._candidate(["promote", "--chapter", "1"], expect=97, env=env)
        transaction_path = self._transaction_path(1)
        transaction_path.write_text(transaction_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        result = self._candidate(["recover", "--chapter", "1"], expect=2)
        self.assertIn("追踪事务摘要不一致", result.stderr)
        self.assertEqual(self.final_files(), [])
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").is_file())

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

    def _rewrite_outline(self, chapter: int, text: str) -> None:
        outline = self.project / "大纲" / f"细纲_第{chapter:03d}章.md"
        outline.write_text(text, encoding="utf-8")
        path = self._transaction_path(chapter)
        document = json.loads(path.read_text(encoding="utf-8"))
        document["candidate_binding"]["outline"]["sha256"] = hashlib.sha256(outline.read_bytes()).hexdigest()
        path.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")

    def test_check_passes_on_new_chapter_with_intent_fields(self) -> None:
        self.make_candidate(1)
        future_outline = self.project / "大纲" / "细纲_第002章.md"
        future_outline.write_text("# 第2章细纲\n- 前因：[待补充]\n", encoding="utf-8")
        state_path = self.project / "追踪" / "_tracking-state.json"
        before = (self.read_state()["state_revision"], state_path.stat().st_mtime_ns)
        result = json.loads(self._candidate(["check", "--chapter", "1"]).stdout)
        self.assertEqual(result["action"], "check")
        self.assertTrue(result["ok"])
        self.assertEqual(self.read_state()["state_revision"], before[0])
        self.assertEqual(state_path.stat().st_mtime_ns, before[1])
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").is_file())
        self.assertEqual(self.final_files(), [])

    def test_new_chapter_missing_intent_fields_is_blocked(self) -> None:
        self.make_candidate(1)
        self._rewrite_outline(1, "# 第1章细纲\n- 情节点：本章完成一次可验证推进。\n")
        blocked = self._candidate(["check", "--chapter", "1"], expect=1)
        self.assertIn("目标情绪", blocked.stderr)
        self.assertIn("结尾拍ID/类型", blocked.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.final_files(), [])
        self._candidate(["promote", "--chapter", "1"], expect=2)
        self.assertEqual(self.final_files(), [])

    def test_new_chapter_missing_causal_fields_is_blocked(self) -> None:
        self.make_candidate(1)
        outline = self.project / "大纲" / "细纲_第001章.md"
        text = "\n".join(
            line for line in outline.read_text(encoding="utf-8").splitlines()
            if not line.startswith(("- 前因：", "- 后果指向：", "- 读者已知："))
        ) + "\n"
        self._rewrite_outline(1, text)

        blocked = self._candidate(["check", "--chapter", "1"], expect=1)
        self.assertIn("细纲因果链未通过", blocked.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.final_files(), [])

    def test_new_chapter_invalid_emotion_value_is_blocked(self) -> None:
        self.make_candidate(1)
        outline = self.project / "大纲" / "细纲_第001章.md"
        text = outline.read_text(encoding="utf-8").replace("- 目标情绪：紧张", "- 目标情绪：家国泪目")
        self._rewrite_outline(1, text)

        blocked = self._candidate(["check", "--chapter", "1"], expect=1)
        self.assertIn("目标情绪取值不在闭合词表", blocked.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.final_files(), [])

    def test_new_chapter_undeclared_real_world_name_is_blocked(self) -> None:
        self.make_candidate(1, body="# 第1章\n他打开抖音查看视频。\n")

        blocked = self._candidate(["check", "--chapter", "1"], expect=1)
        self.assertIn("未声明的现实专名", blocked.stderr)
        self.assertIn("抖音", blocked.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(self.final_files(), [])

    def test_new_chapter_character_near_name_is_advisory(self) -> None:
        role_dir = self.project / "设定" / "角色"
        role_dir.mkdir(parents=True)
        (role_dir / "钟嘉嘉.md").write_text("name: 钟嘉嘉\n", encoding="utf-8")
        self.make_candidate(1, body="# 第1章\n钟嘉佳走进会议室。\n")

        completed = self._candidate(["check", "--chapter", "1"])
        self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertIn("专名漂移 advisory", completed.stderr)
        self.assertIn("钟嘉佳", completed.stderr)

    def test_settlement_phrase_without_metrics_change_is_blocked(self) -> None:
        self.make_candidate(1, body="# 第1章\n任务完成，粉丝突破100万。\n")

        blocked = self._candidate(["check", "--chapter", "1"], expect=1)
        self.assertIn("metrics 未变化", blocked.stderr)
        self.assertIn("粉丝突破", blocked.stderr)
        self.assertEqual(self.final_files(), [])

    def test_settlement_reason_explicitly_allows_unchanged_metrics(self) -> None:
        self.make_candidate(
            1,
            body="# 第1章\n他回看旧视频里的任务完成提示。\n",
            tx_overrides={"metrics_unchanged_reason": "仅回看旧提示，本章没有新结算"},
        )

        completed = self._candidate(["check", "--chapter", "1"])
        self.assertTrue(json.loads(completed.stdout)["ok"])

    def test_metrics_update_binds_value_and_source_then_promotes(self) -> None:
        self.make_candidate(
            1,
            body="# 第1章\n任务完成，粉丝突破100万。\n",
            tx_overrides={
                "metrics": {"抖手粉丝": metric("100万", 1, "粉丝突破100万")},
            },
        )

        checked = self._candidate(["check", "--chapter", "1"])
        self.assertTrue(json.loads(checked.stdout)["ok"])
        self._candidate(["promote", "--chapter", "1"])
        state = self.read_state()
        self.assertEqual(state["metrics"]["抖手粉丝"]["value"], "100万")
        context = (self.project / "追踪/上下文.md").read_text(encoding="utf-8")
        self.assertIn("关键数值：抖手粉丝 100万", context)
        self.assertEqual(sum(line.startswith("## ") for line in context.splitlines()), 7)

    def test_metrics_value_must_match_source_phrase(self) -> None:
        self.make_candidate(
            1,
            body="# 第1章\n任务完成，粉丝突破100万。\n",
            tx_overrides={
                "metrics": {"抖手粉丝": metric("200万", 1, "粉丝突破100万")},
            },
        )

        blocked = self._candidate(["check", "--chapter", "1"], expect=1)
        self.assertIn("与 source_phrase", blocked.stderr)
        self.assertEqual(self.final_files(), [])

    def test_metrics_cumulative_value_accepts_prose_delta(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=1)
        state_path = self.project / "追踪" / "_tracking-state.json"
        state = self.read_state()
        state["metrics"] = {"华国国运": metric("+10000", 1, "国运值+10000")}
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tracking = importlib.util.module_from_spec(importlib.util.spec_from_file_location("tracking_render", TRACKING_TOOL))
        assert tracking.__spec__ and tracking.__spec__.loader
        tracking.__spec__.loader.exec_module(tracking)
        (self.project / "追踪/上下文.md").write_text(tracking.render_context(tracking.normalize_state(state)), encoding="utf-8")
        self.make_candidate(
            2,
            body="# 第2章\n任务完成，国运值+20000。\n",
            tx_overrides={
                "metrics": {"华国国运": metric("+30000", 2, "国运值+20000")},
            },
        )

        completed = self._candidate(["check", "--chapter", "2"])
        self.assertTrue(json.loads(completed.stdout)["ok"])

    def test_four_same_emotion_distinct_events_check_and_promote(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=3)
        outline_dir = self.project / "大纲"
        outline_dir.mkdir(exist_ok=True)
        events = (
            "夜里仓库失火，守夜人喊醒邻居，大家搬出了粮袋。",
            "渡口只剩一条船，船主拒绝超载，两家人决定先送孩子。",
            "船桨断在河中，岸上的人拉紧绳索，把小船拖回浅滩。",
            "最后一个孩子迟迟没上岸，父亲沿着河滩找到他，背着他回村。",
        )
        for chapter, event in enumerate(events[:3], 1):
            (outline_dir / f"细纲_第{chapter:03d}章.md").write_text(
                f"- 情节点：{event}\n- 目标情绪：紧张\n",
                encoding="utf-8",
            )
            accepted = next((self.project / "正文").glob(f"第{chapter:03d}章_*.md"))
            accepted.write_text(f"# 第{chapter}章\n{event}\n", encoding="utf-8")
        prose = self.make_candidate(4, body=f"# 第4章\n{events[3]}\n")
        outline = outline_dir / "细纲_第004章.md"
        self._rewrite_outline(
            4,
            outline.read_text(encoding="utf-8").replace(
                "本章完成一次可验证推进。", "父亲在河滩找回落单的孩子，背着他回到村里。"
            ),
        )
        before = {
            path.relative_to(self.project): path.read_bytes()
            for path in self.project.rglob("*") if path.is_file()
        }

        checked = self._candidate(["check", "--chapter", "4"])
        self.assertTrue(json.loads(checked.stdout)["ok"])
        self.assertIn("目标情绪连排 advisory", checked.stderr)
        self.assertIn("第1–4章连续 4 章", checked.stderr)
        self.assertEqual(
            {path.relative_to(self.project): path.read_bytes()
             for path in self.project.rglob("*") if path.is_file()},
            before,
        )
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(len(self.final_files()), 3)
        promoted = self._candidate(["promote", "--chapter", "4"])
        self.assertEqual(json.loads(promoted.stdout)["action"], "promote")
        self.assertIn("目标情绪连排 advisory", promoted.stderr)
        self.assertFalse(prose.exists())
        self.assertEqual((self.project / "正文" / prose.name).read_bytes(), before[prose.relative_to(self.project)])
        self.assertEqual(self.read_state()["last_committed_chapter"], 4)
        self.assertEqual(self.read_state()["state_revision"], 1)
        run(TRACKING_TOOL, ["check", "--project", str(self.project)])

    def test_future_emotion_outline_does_not_extend_current_advisory(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=2)
        self.make_candidate(3)
        outline_dir = self.project / "大纲"
        for chapter in (1, 2, 4):
            (outline_dir / f"细纲_第{chapter:03d}章.md").write_text(
                "- 目标情绪：紧张\n", encoding="utf-8"
            )

        completed = self._candidate(["check", "--chapter", "3"])
        self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertIn("第1–3章连续 3 章", completed.stderr)
        self.assertNotIn("第1–4章", completed.stderr)
        self.assertEqual(self.read_state()["state_revision"], 0)

    def test_emotion_run_input_failure_still_rejects_before_writes(self) -> None:
        self.temporary.cleanup()
        self._reset_project(last_chapter=3)
        prose = self.make_candidate(4)
        # A directory with an outline filename is a deterministic unreadable input.
        (self.project / "大纲" / "细纲_第003章.md").mkdir()

        checked = self._candidate(["check", "--chapter", "4"], expect=1)
        self.assertIn("目标情绪连排检查无法执行", checked.stderr)
        promoted = self._candidate(["promote", "--chapter", "4"], expect=2)
        self.assertIn("目标情绪连排检查无法执行", promoted.stderr)
        self.assertTrue(prose.is_file())
        self.assertEqual(self.read_state()["state_revision"], 0)
        self.assertEqual(len(self.final_files()), 3)

    def test_historical_chapter_missing_intent_fields_is_advisory(self) -> None:
        self.make_candidate(1)
        self._rewrite_outline(1, "# 第1章细纲\n- 情节点：本章完成一次可验证推进。\n")
        state_path = self.project / "追踪" / "_tracking-state.json"
        state = self.read_state()
        state["imported_through_chapter"] = 1
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        completed = self._candidate(["check", "--chapter", "1"])
        checked = json.loads(completed.stdout)
        self.assertTrue(checked["ok"])
        self.assertIn("细纲因果 advisory", completed.stderr)
        self.assertEqual(self.read_state()["imported_through_chapter"], 1)
        self.assertTrue((self.candidate_dir / "第001章_测试章名.md").is_file())
        self.assertEqual(self.final_files(), [])

    def test_historical_chapter_real_world_name_is_advisory(self) -> None:
        self.make_candidate(1, body="# 第1章\n他打开抖音查看视频。\n")
        state_path = self.project / "追踪" / "_tracking-state.json"
        state = self.read_state()
        state["imported_through_chapter"] = 1
        state_path.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

        completed = self._candidate(["check", "--chapter", "1"])
        self.assertTrue(json.loads(completed.stdout)["ok"])
        self.assertIn("专名漂移 advisory", completed.stderr)
        self.assertIn("抖音", completed.stderr)
        self.assertEqual(self.final_files(), [])


class OrdinaryRevisionTests(unittest.TestCase):
    """Synthetic transaction fixtures: never represented as real reader feedback."""
    REVISION = ROOT / "skills/story-write/scripts/revision-commit.py"

    def setUp(self):
        self.fixture = CandidateCommitTests()
        self.fixture._reset_project(last_chapter=4)
        self.project = self.fixture.project
        self.original = sorted((self.project / "正文").glob("*.md"))[1]
        fill = "".join(chr(0x6000 + n) for n in range(2300))
        self.original.write_text("# 第2章 手套\n她把手套递给弟弟。\n" + fill + "。\n", encoding="utf-8")
        self.source = self.project / "候选/修订稿.md"
        self.source.write_text(self.original.read_text(encoding="utf-8").replace("她把手套递给弟弟。", "她将手套递给弟弟。"), encoding="utf-8")

    def tearDown(self):
        self.fixture.temporary.cleanup()

    def cli(self, *args, expect=0, env=None):
        return run(self.REVISION, [*args, "--project", str(self.project)], expect=expect, env=env)

    def prepare(self, kind="wording"):
        result = json.loads(self.cli("prepare", "--chapter", "2", "--candidate", str(self.source), "--kind", kind,
                                     "--summary", "synthetic test editing").stdout)
        self.operation = result["operation"]
        self.directory = Path(result["directory"])
        self.review_path = self.project / "test-review.json"
        review = json.loads((self.directory / "review-template.json").read_text(encoding="utf-8"))
        review.update(reviewer="synthetic test fixture", status="pass", facts_unchanged=kind != "facts",
                      original_anchor=(self.directory / "original.md").read_text(encoding="utf-8").splitlines()[1],
                      candidate_anchor=(self.directory / "candidate.md").read_text(encoding="utf-8").splitlines()[1])
        for row in review["context"]:
            row["anchor"] = (self.project / row["path"]).read_text(encoding="utf-8").splitlines()[-1]
            row["assessment"] = "synthetic unaffected context"
        self.review_path.write_text(json.dumps(review, ensure_ascii=False), encoding="utf-8")
        return result

    def action(self, name, *extra, expect=0, env=None):
        args = [name, "--operation", self.operation]
        if name != "recover":
            args.extend(["--review", str(self.review_path)])
        if name == "accept":
            args.extend(["--author-approval", "synthetic test authorization"])
        return self.cli(*args, *extra, expect=expect, env=env)

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def test_prepare_and_check_leave_adopted_prose_and_state_unchanged(self):
        old = self.original.read_bytes()
        state = (self.project / "追踪/_tracking-state.json").read_bytes()
        result = self.prepare()
        self.assertEqual(len(result["review_scope"]), 2)
        before = self.snapshot()
        self.assertTrue(json.loads(self.action("check").stdout)["ok"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.original.read_bytes(), old)
        self.assertEqual((self.project / "追踪/_tracking-state.json").read_bytes(), state)

    def test_wording_and_rhythm_preserve_tracking_facts_and_original(self):
        for kind in ("wording", "rhythm"):
            with self.subTest(kind=kind):
                if kind == "rhythm":
                    self.source.write_text(self.source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                before = self.fixture.read_state()
                old = self.original.read_bytes()
                self.prepare(kind)
                self.action("accept")
                after = self.fixture.read_state()
                self.assertEqual(after["state_revision"], before["state_revision"] + 1)
                after["state_revision"] = before["state_revision"]
                self.assertEqual(after, before)
                self.assertEqual((self.directory / "original.md").read_bytes(), old)
                self.assertEqual(self.original.read_bytes(), self.source.read_bytes())
                self.fixture._tracking("check")

    def test_fact_revision_requires_transaction_and_all_later_context(self):
        result = self.prepare("facts")
        self.assertEqual(len(result["review_scope"]), 3)
        self.assertIn("tracking transaction", self.action("check", expect=1).stderr)
        tx = transaction(2, mode="revision")
        tx["expected_state_revision"] = 0
        path = self.project / "test-transaction.json"
        path.write_text(json.dumps(tx, ensure_ascii=False), encoding="utf-8")
        self.action("check", "--transaction", str(path))
        self.action("accept", "--transaction", str(path))
        state = self.fixture.read_state()
        self.assertEqual(state["last_committed_chapter"], 4)
        self.assertEqual(state["state_revision"], 1)
        self.assertIn(tx["delta"]["result"], (self.project / "追踪/逐章记录/第002章.md").read_text(encoding="utf-8"))
        self.fixture._tracking("check")

    def test_fact_revision_cannot_omit_downstream_reading(self):
        self.prepare("facts")
        review = json.loads(self.review_path.read_text(encoding="utf-8"))
        review["context"].pop()
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        self.assertIn("bound context", self.action("check", expect=1).stderr)

    def test_wording_requires_explicit_unchanged_facts_review(self):
        self.prepare()
        review = json.loads(self.review_path.read_text(encoding="utf-8"))
        review["facts_unchanged"] = False
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        self.assertIn("unchanged story facts", self.action("check", expect=1).stderr)

    def test_stale_original_context_inventory_and_review_fail_before_writes(self):
        for change in ("original", "context", "inventory", "review", "candidate", "state"):
            with self.subTest(change=change):
                self.prepare()
                path = {"original": self.original,
                        "context": sorted((self.project / "正文").glob("*.md"))[0],
                        "inventory": self.project / "正文/第005章_后来.md",
                        "review": self.review_path,
                        "candidate": self.directory / "candidate.md",
                        "state": self.project / "追踪/_tracking-state.json"}[change]
                old = path.read_bytes() if path.exists() else None
                if change == "review":
                    data = json.loads(old)
                    data["candidate_sha256"] = "0" * 64
                    path.write_text(json.dumps(data), encoding="utf-8")
                else:
                    path.write_bytes((old or b"") + b"\nchanged")
                before = self.snapshot()
                self.action("accept", expect=2)
                self.assertEqual(self.snapshot(), before)
                if old is None:
                    path.unlink()
                else:
                    path.write_bytes(old)

    def test_faults_recover_idempotently_and_block_other_writers(self):
        for phase in ("prepared", "prose_written", "views_written", "state_written"):
            with self.subTest(phase=phase):
                if hasattr(self, "operation"):
                    self.source.write_text(self.source.read_text(encoding="utf-8") + "\n", encoding="utf-8")
                self.prepare()
                env = dict(os.environ, STORY_REVISION_FAIL_AFTER=phase)
                self.action("accept", expect=97, env=env)
                tx = transaction(5)
                tx["expected_state_revision"] = self.fixture.read_state()["state_revision"]
                self.assertIn("recover", self.fixture._tracking("commit", tx, expect=2).stderr)
                self.action("recover")
                before = self.snapshot()
                self.action("recover")
                self.assertEqual(before, self.snapshot())
                self.fixture._tracking("check")

    def test_recover_refuses_unrelated_edit(self):
        self.prepare()
        self.action("accept", expect=97, env=dict(os.environ, STORY_REVISION_FAIL_AFTER="prose_written"))
        self.original.write_text("Someone changed the manuscript", encoding="utf-8")
        before = self.snapshot()
        self.action("recover", expect=2)
        self.assertEqual(before, self.snapshot())

    def test_lifecycle_head_cannot_be_bypassed(self):
        self.prepare()
        path = self.project / ".story-quality/HEAD.json"
        path.parent.mkdir()
        path.write_text("{}", encoding="utf-8")
        self.assertIn("quality lifecycle", self.action("check", expect=1).stderr)
        self.assertIn("quality lifecycle", self.action("accept", expect=2).stderr)

    def test_symlink_parent_rejected(self):
        self.prepare()
        other = Path(self.fixture.temporary.name) / "outside"
        other.mkdir()
        (self.project / "候选/_历史").symlink_to(other, target_is_directory=True)
        self.assertIn("symlink", self.action("accept", expect=2).stderr)
        self.assertEqual(list(other.iterdir()), [])

    def test_volume_directories_and_restoring_original(self):
        volume = self.project / "正文/第一卷"
        volume.mkdir()
        moved = volume / self.original.name
        self.original.replace(moved)
        self.original = moved
        old = self.original.read_bytes()
        self.prepare()
        self.action("accept")
        self.source.write_bytes(old)
        self.prepare()
        review = json.loads(self.review_path.read_text(encoding="utf-8"))
        review.update(original_anchor="她将手套递给弟弟。", candidate_anchor="她把手套递给弟弟。")
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        self.action("accept")
        self.assertEqual(self.original.read_bytes(), old)
        self.assertEqual(self.fixture.read_state()["state_revision"], 2)

    def test_wording_can_refresh_evidence_without_changing_metric_value(self):
        state = self.fixture.read_state()
        state["metrics"] = {"手套归属": {"value": "弟弟", "as_of_chapter": 2, "source_phrase": "她把手套递给弟弟。"}}
        import sys
        sys.path.insert(0, str(self.REVISION.parent))
        spec = importlib.util.spec_from_file_location("source_refresh_tracking", TRACKING_TOOL)
        tracking = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tracking)
        tracking.write_views(self.project / "追踪", tracking.render_views(state))
        tracking.atomic_write_text(self.project / "追踪/_tracking-state.json", tracking.json_payload(state))
        self.prepare()
        self.assertIn("anchor disappeared", self.action("check", expect=1).stderr)
        review = json.loads(self.review_path.read_text(encoding="utf-8"))
        review["metric_source_updates"] = {"手套归属": "她将手套递给弟弟。"}
        self.review_path.write_text(json.dumps(review), encoding="utf-8")
        self.action("check")
        self.action("accept")
        actual = self.fixture.read_state()["metrics"]["手套归属"]
        self.assertEqual(actual, {"value": "弟弟", "as_of_chapter": 2, "source_phrase": "她将手套递给弟弟。"})


if __name__ == "__main__":
    if len(sys.argv) == 1:
        independent_spec = importlib.util.spec_from_file_location("revision_review_tests", ROOT / "scripts/test-revision-review.py")
        independent = importlib.util.module_from_spec(independent_spec)
        independent_spec.loader.exec_module(independent)
        for name, value in vars(independent).items():
            if isinstance(value, type) and issubclass(value, unittest.TestCase) and value is not unittest.TestCase:
                globals()[name] = value
        del name, value  # unittest must not discover the loop variable as a second class.
    unittest.main(verbosity=2)
