#!/usr/bin/env python3
"""Independent ordinary-revision safety regressions using synthetic manuscripts.

These exercise real validators and transaction recovery, not literary quality.
Only the scanner return boundary is wrapped to simulate an external editor.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "skills/story-write/scripts/revision-commit.py"
sys.path.insert(0, str(TOOL.parent))

if sys.version_info < (3, 10):
    _orig_write_text = Path.write_text

    def _compat_write_text(self, data, encoding=None, errors=None, newline=None):
        if newline is not None:
            with self.open("w", encoding=encoding, errors=errors, newline=newline) as handle:
                return handle.write(data)
        return _orig_write_text(self, data, encoding=encoding, errors=errors)

    Path.write_text = _compat_write_text


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


revision = module("independent_revision_review", TOOL)
fixtures = module("independent_tracking_fixtures", ROOT / "scripts/test-tracking-commit.py")
from test_review_process import make_process


class RevisionReviewTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="revision-review-test-")
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name) / "book"
        (self.project / "正文").mkdir(parents=True)
        (self.project / "大纲").mkdir()
        # Unique CJK filler isolates persistence tests from repetition detectors.
        filler = "".join(chr(0x6000 + n) for n in range(2300))
        self.final = self.project / "正文/第001章_回执.md"
        # newline="\n" 是可移植性要求：生产侧 atomic_write_text 固定写 LF，而
        # write_text 默认 newline=None 在 Windows 上会写成 CRLF，使逐字节断言只在 POSIX 成立。
        self.final.write_text("# 第1章 回执\n她把回执递给弟弟。\n" + filler + "。\n", encoding="utf-8", newline="\n")
        self.source = Path(self.temporary.name) / "revised.md"
        self.source.write_text(self.final.read_text(encoding="utf-8").replace("她把回执", "她将回执"), encoding="utf-8", newline="\n")
        revision.tracking.initialize(self.project, fixtures.initial_document(last_chapter=1))

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.project.rglob("*") if p.is_file()}

    def prepare(self, kind="wording"):
        result = revision.prepare(self.project, 1, self.source, kind, "synthetic regression fixture")
        self.operation = result["operation"]
        self.directory, self.manifest = revision.load(self.project, self.operation)
        self.review = json.loads((self.directory / "review-template.json").read_text(encoding="utf-8"))
        original_anchor = (self.directory / "original.md").read_text(encoding="utf-8").splitlines()[1]
        candidate_anchor = (self.directory / "candidate.md").read_text(encoding="utf-8").splitlines()[1]
        self.review.update(status="pass", reviewer="synthetic fixture; no reader-quality claim",
                           facts_unchanged=kind != "facts",
                           original_anchor=original_anchor,
                           candidate_anchor=candidate_anchor)
        for row in self.review["context"]:
            row.update(anchor=(self.project / row["path"]).read_text(encoding="utf-8").splitlines()[-1],
                       assessment="synthetic context checked")
        path = (self.directory / "candidate.md").resolve().relative_to(self.project.resolve()).as_posix()
        prose_row = {"path": path, "sha256": self.manifest["candidate_sha256"]}
        self.review["editor_review"] = {
            "schema_version": 1, "policy_version": "independent-editor-v1", "source": "independent",
            "status": "PASS", "writer_run_id": "fixture-writer", "reviewer_run_id": "fixture-editor",
            "candidate_sha256": self.manifest["candidate_sha256"], "context_files": [prose_row],
            "passes": [{"kind": k, "files": [path], "assessment": "Synthetic pass evidence.",
                        "evidence": [{"path": path, "anchor": candidate_anchor}]}
                       for k in ("comprehension", "sentence")],
            "findings": [], "signoff": {"candidate_sha256": self.manifest["candidate_sha256"], "limitations": []},
        }
        self.review["reader_review"] = {
            "schema_version": 1, "status": "PASS", "source": "independent",
            "run_id": "fixture-reader-first-run",
            "chapter": 1, "candidate_path": path,
            "reviewer_run_id": "fixture-reader", "reading_kind": "first_read",
            "candidate_sha256": self.manifest["candidate_sha256"], "prose_files": [prose_row],
            "observations": {key: {"assessment": "Synthetic receipt; not actual reader feedback.",
                                    "evidence": [{"path": path, "anchor": candidate_anchor}]}
                             for key in ("understanding", "friction", "reward", "read_on")},
            "findings": [],
        }
        self.review["review_process"] = make_process(
            self.project, 1, self.directory / "candidate.md", self.review["editor_review"],
            [self.review["reader_review"]], prefix="审核/revision-fixture")
        self.review_path = Path(self.temporary.name) / "review.json"
        self.review_path.write_text(json.dumps(self.review, ensure_ascii=False), encoding="utf-8")
        self.journal = self.project / f"候选/_历史/修订事务-{self.operation}.json"
        return result

    def accept(self, transaction=None):
        self.review_path.write_text(json.dumps(self.review, ensure_ascii=False), encoding="utf-8")
        return revision.accept(self.project, self.operation, self.review, transaction, "synthetic test adoption")

    def interrupted_accept(self, phase, transaction=None):
        args = [sys.executable, str(TOOL), "accept", "--project", str(self.project),
                "--operation", self.operation, "--review", str(self.review_path),
                "--author-approval", "synthetic test adoption"]
        if transaction is not None:
            tx_path = Path(self.temporary.name) / "transaction.json"
            tx_path.write_text(json.dumps(transaction, ensure_ascii=False), encoding="utf-8")
            args.extend(["--transaction", str(tx_path)])
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                                env=dict(os.environ, STORY_REVISION_FAIL_AFTER=phase, PYTHONDONTWRITEBYTECODE="1"))
        self.assertEqual(result.returncode, 97, result.stdout + result.stderr)

    def recover(self):
        with revision.project_lock(self.project):
            return revision.recover_locked(self.project, self.operation)

    def metrics_case(self, value):
        original = self.final.read_text(encoding="utf-8").replace("她把回执递给弟弟。", "余额为200元。")
        self.final.write_text(original, encoding="utf-8", newline="\n")
        self.source.write_text(original.replace("余额为200元。", "余额为100元。"), encoding="utf-8", newline="\n")
        self.prepare("facts")
        tx = fixtures.transaction(1, mode="revision")
        tx["expected_state_revision"] = 0
        tx["metrics"] = {"余额": fixtures.metric(value, 1, "余额为100元。")}
        return tx

    def source_refresh_case(self, kind="wording", *, revised="账上还有200元。", metric_chapter=1):
        original = self.final.read_text(encoding="utf-8").replace("她把回执递给弟弟。", "余额为200元。")
        self.final.write_text(original, encoding="utf-8", newline="\n")
        self.source.write_text(original.replace("余额为200元。", revised), encoding="utf-8", newline="\n")
        state = revision.tracking.check_project(self.project)
        if metric_chapter > 1:
            (self.project / "正文/第002章_余款.md").write_text("# 第2章 余款\n余额为200元。\n", encoding="utf-8", newline="\n")
            tx = fixtures.transaction(2)
            tx["expected_state_revision"] = state["state_revision"]
            revision.tracking.apply_transaction(self.project, tx)
            state = revision.tracking.check_project(self.project)
        state["metrics"] = {"余额": fixtures.metric("200元", metric_chapter, "余额为200元。")}
        revision.tracking.write_views(self.project / "追踪", revision.tracking.render_views(state))
        revision.tracking.atomic_write_text(self.project / revision.STATE, revision.tracking.json_payload(state))
        self.prepare(kind)
        self.review["metric_source_updates"] = {"余额": revised}

    def assert_refresh_rejected(self, message, transaction=None):
        before = self.snapshot()
        with self.assertRaisesRegex(revision.Error, message):
            revision.check(self.project, self.operation, self.review, transaction)
        with self.assertRaisesRegex(revision.Error, message):
            self.accept(transaction)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.journal.exists())

    def test_source_refresh_cannot_hide_numeric_fact_change(self):
        for kind in ("wording", "rhythm"):
            for amount in (100, 0):
                with self.subTest(kind=kind, amount=amount):
                    self.source_refresh_case(kind, revised=f"余额为{amount}元。")
                    self.assert_refresh_rejected("不一致")

    def test_source_refresh_preserves_nonnumeric_value_and_chapter_for_both_kinds(self):
        for kind, anchor in (("wording", "她将回执递给弟弟。"), ("rhythm", "回执被她递给弟弟。")):
            with self.subTest(kind=kind):
                original_anchor = self.final.read_text(encoding="utf-8").splitlines()[1]
                self.source.write_text(self.final.read_text(encoding="utf-8").replace(original_anchor, anchor), encoding="utf-8", newline="\n")
                state = revision.tracking.check_project(self.project)
                state["metrics"] = {"回执归属": fixtures.metric("弟弟", 1, original_anchor)}
                revision.tracking.write_views(self.project / "追踪", revision.tracking.render_views(state))
                revision.tracking.atomic_write_text(self.project / revision.STATE, revision.tracking.json_payload(state))
                self.prepare(kind)
                self.review["metric_source_updates"] = {"回执归属": anchor}
                before = self.snapshot()
                self.assertTrue(revision.check(self.project, self.operation, self.review, None)["ok"])
                self.assertEqual(before, self.snapshot())
                self.accept()
                state["state_revision"] += 1
                state["metrics"]["回执归属"]["source_phrase"] = anchor
                self.assertEqual(revision.tracking.check_project(self.project), state)
                self.assertEqual(self.final.read_bytes(), self.source.read_bytes())

    def test_source_refresh_rejects_unknown_metric_record_injection_and_missing_anchor(self):
        self.source_refresh_case()
        for updates, message in (
            ({"新增余额": "账上还有200元。"}, "fact recorded in the revised chapter"),
            ({"余额": {"value": "100元", "as_of_chapter": 2, "source_phrase": "账上还有200元。"}}, "cannot be located"),
            ({"余额": "候选正文没有这句话。"}, "cannot be located"),
            ({"余额": "  "}, "cannot be located"),
            ([], "must be a mapping"),
        ):
            with self.subTest(updates=updates):
                self.review["metric_source_updates"] = updates
                self.assert_refresh_rejected(message)

    def test_source_refresh_cannot_change_other_chapter_metric(self):
        self.source_refresh_case(metric_chapter=2)
        self.assert_refresh_rejected("fact recorded in the revised chapter")

    def test_source_refresh_still_requires_unchanged_facts_and_forbids_transaction(self):
        self.source_refresh_case("rhythm")
        for facts_unchanged in (False, None, "true"):
            with self.subTest(facts_unchanged=facts_unchanged):
                self.review["facts_unchanged"] = facts_unchanged
                self.assert_refresh_rejected("unchanged story facts")
        self.review["facts_unchanged"] = True
        self.assert_refresh_rejected("cannot silently change tracking facts", fixtures.transaction(1, mode="revision"))

    def test_metric_value_must_match_revised_prose_before_any_write(self):
        tx = self.metrics_case("9999元")
        before = self.snapshot()
        with self.assertRaisesRegex(revision.Error, "不一致"):
            revision.check(self.project, self.operation, self.review, tx)
        with self.assertRaisesRegex(revision.Error, "不一致"):
            self.accept(tx)
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.journal.exists())

    def test_valid_metric_revision_updates_single_tracking_authority(self):
        tx = self.metrics_case("100元")
        self.accept(tx)
        state = revision.tracking.check_project(self.project)
        self.assertEqual(state["metrics"]["余额"]["value"], "100元")
        self.assertEqual(state["state_revision"], 1)
        self.assertEqual(self.final.read_bytes(), self.source.read_bytes())
        for name, rendered in revision.tracking.render_views(state).items():
            self.assertEqual((self.project / "追踪" / name).read_text(encoding="utf-8"), rendered)
        self.assertFalse((self.project / ".story-quality/HEAD.json").exists())
        before = self.snapshot()
        self.recover()
        self.assertEqual(before, self.snapshot())

    def test_check_is_read_only_including_mtimes_and_creates_no_journal(self):
        self.prepare()
        before = self.snapshot()
        self.assertTrue(revision.check(self.project, self.operation, self.review, None)["ok"])
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.journal.exists())

    def test_padded_next_outline_is_bound_and_stale_outline_blocks_without_writes(self):
        outline = self.project / "大纲/细纲_第002章.md"
        outline.write_text("# 后续安排\n弟弟带回执去取钥匙。\n", encoding="utf-8")
        self.assertIn("大纲/细纲_第002章.md", self.prepare()["review_scope"])
        revision.check(self.project, self.operation, self.review, None)
        outline.write_text("# 后续安排\n弟弟烧掉了回执。\n", encoding="utf-8")
        before = self.snapshot()
        with self.assertRaisesRegex(revision.Error, "context changed"):
            self.accept()
        self.assertEqual(before, self.snapshot())
        self.assertFalse(self.journal.exists())

    def test_duplicate_padded_and_unpadded_next_outline_is_rejected(self):
        for name in ("细纲_第2章.md", "细纲_第002章.md"):
            (self.project / "大纲" / name).write_text("弟弟取回钥匙。", encoding="utf-8")
        with self.assertRaisesRegex(revision.Error, "duplicate next chapter outline"):
            self.prepare()
        self.assertFalse((self.project / "候选/_修订").exists())

    def assert_post_scan_mutation_rejected(self, relative):
        self.prepare()
        target = self.project / relative if relative else self.directory / "candidate.md"
        external_bytes = target.read_bytes() + b"\nexternal edit\n"
        real_scan = revision.candidate.scan_gate
        before = self.snapshot()

        def edited(*args, **kwargs):
            result = real_scan(*args, **kwargs)
            target.write_bytes(external_bytes)
            return result

        with mock.patch.object(revision.candidate, "scan_gate", side_effect=edited):
            with self.assertRaises((revision.Error, revision.tracking.TrackingError)):
                self.accept()
        self.assertFalse(self.journal.exists(), "reject before persisting a blocking transaction")
        after = self.snapshot()
        name = target.relative_to(self.project).as_posix()
        self.assertEqual(after[name][0], external_bytes)
        before.pop(name)
        after.pop(name)
        self.assertEqual(before, after, "only the simulated external edit may change the project")

    def test_frozen_candidate_mutation_during_scan_rejects_before_journal(self):
        self.assert_post_scan_mutation_rejected(None)

    def test_adopted_prose_mutation_during_scan_rejects_before_journal(self):
        self.assert_post_scan_mutation_rejected("正文/第001章_回执.md")

    def test_tracking_state_mutation_during_scan_rejects_before_journal(self):
        self.assert_post_scan_mutation_rejected(revision.STATE)

    def test_derived_view_mutation_during_scan_rejects_before_journal(self):
        view = next(iter(revision.tracking.render_views(revision.tracking.check_project(self.project))))
        self.assert_post_scan_mutation_rejected(f"追踪/{view}")

    def test_prepared_abort_keeps_originals_and_unblocks_new_proposal_even_if_candidate_damaged(self):
        self.prepare()
        original = self.final.read_bytes()
        state = (self.project / revision.STATE).read_bytes()
        self.interrupted_accept("prepared")
        (self.directory / "candidate.md").write_text("damaged frozen proposal", encoding="utf-8")
        revision.abort(self.project, self.operation, "synthetic cancellation")
        self.assertEqual(self.final.read_bytes(), original)
        self.assertEqual((self.project / revision.STATE).read_bytes(), state)
        self.assertEqual(json.loads(self.journal.read_text(encoding="utf-8"))["phase"], "aborted")
        revision.assert_no_unfinished_adoption(self.project)
        self.source.write_text(self.source.read_text(encoding="utf-8") + "\n", encoding="utf-8", newline="\n")
        self.prepare()

    def test_prepared_abort_refuses_any_transaction_output_changed_by_external_editor(self):
        self.prepare()
        self.interrupted_accept("prepared")
        for target in (self.final, self.project / revision.STATE):
            with self.subTest(target=target.name):
                old = target.read_bytes()
                target.write_bytes(old + b"\nexternal edit")
                before = self.snapshot()
                with self.assertRaisesRegex(revision.Error, "projections already changed"):
                    revision.abort(self.project, self.operation, "synthetic cancellation")
                self.assertEqual(before, self.snapshot())
                target.write_bytes(old)
        self.recover()
        self.assertEqual(revision.tracking.check_project(self.project)["state_revision"], 1)

    def test_abort_refuses_started_transaction_and_recovery_finishes(self):
        self.prepare()
        self.interrupted_accept("prose_written")
        before = self.snapshot()
        with self.assertRaisesRegex(revision.Error, "unstarted prepared"):
            revision.abort(self.project, self.operation, "synthetic cancellation")
        self.assertEqual(before, self.snapshot())
        self.recover()
        revision.tracking.check_project(self.project)

    def test_revised_body_invalidates_only_its_wordcount_certificate(self):
        (self.project / "大纲/细纲_第001章.md").write_text("字数目标：2500\n字数口径：visible_chars_v1\n", encoding="utf-8")
        state = revision.tracking.check_project(self.project)
        state["wordcount_records"]["1"] = revision.tracking.wordcount_core.build_project_wordcount_record(
            self.project, 1, resolution="within_user_band")
        revision.tracking.write_views(self.project / "追踪", revision.tracking.render_views(state))
        revision.tracking.atomic_write_text(self.project / revision.STATE, revision.tracking.json_payload(state))
        self.prepare()
        self.accept()
        after = revision.tracking.check_project(self.project)
        self.assertEqual(after["wordcount_records"], {})
        expected = dict(state, state_revision=1, wordcount_records={})
        self.assertEqual(after, expected)

    def test_tracking_snapshot_excludes_runtime_lock_files(self):
        """快照必须跳过 追踪/ 下的运行时锁文件，且这一点在每个平台都可验。

        回归背景：build_changes 在 project_lock 内运行。Windows 的 msvcrt 是强制
        锁，读活动锁文件抛 PermissionError [Errno 13]；POSIX 的 flock 是劝告锁，
        读得通。所以「漏掉排除」在 macOS/Linux 上完全无症状，只在 Windows 上炸。
        本用例直接断言排除集生效，不依赖平台锁语义。
        """
        tracking_root = self.project / "追踪"
        real = tracking_root / "逐章记录" / "第001章.md"
        real.parent.mkdir(parents=True, exist_ok=True)
        real.write_text("真实追踪内容。\n", encoding="utf-8", newline="\n")
        for name in revision.TRACKING_RUNTIME_FILES:
            (tracking_root / name).write_bytes(b"runtime lock residue")

        snapshot = revision.tracking_snapshot(self.project)

        self.assertIn("追踪/逐章记录/第001章.md", snapshot)
        for name in revision.TRACKING_RUNTIME_FILES:
            relative = (tracking_root / name).relative_to(self.project).as_posix()
            self.assertNotIn(relative, snapshot)
            # 排除只影响快照口径，不得顺手动了磁盘上的文件。
            self.assertTrue((tracking_root / name).is_file())


class IndependentRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="independent-revision-")
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "book"
        self.final = self.project / "正文/第1卷/第001章_回执.md"
        self.final.parent.mkdir(parents=True)
        text = "# 第1章 回执\n她把回执递给弟弟。\n" + "".join(chr(0x6000+n) for n in range(2300)) + "。\n"
        self.final.write_bytes(text.encode())
        source = Path(self.temp.name) / "revision.md"
        source.write_bytes(text.replace("她把回执", "她将回执").encode())
        revision.tracking.initialize(self.project, {
            "schema_version": 1, "book_title": "工程测试", "last_chapter": 1,
            "context": {"position": {"volume": "第一卷", "volume_start_chapter": 1,
                                      "story_time": "当天", "scene": "柜台"},
                        "long_term_constraints": [], "active_character_names": [], "continuity_risks": [],
                        "recent_chapters": [{"chapter": 1, "summary": "递交回执。"}],
                        "next_chapter_commitments": ["等待答复。"]},
            "character_snapshots": {}, "foreshadow": [], "timeline_events": [],
        })
        result = revision.prepare(self.project, 1, source, "wording", "synthetic wording change")
        self.operation = result["operation"]
        self.directory, self.manifest = revision.load(self.project, self.operation)
        self.review = json.loads((self.directory / "review-template.json").read_text(encoding="utf-8"))
        self.review.update(status="pass", reviewer="continuity-fixture", facts_unchanged=True,
                           original_anchor="她把回执递给弟弟。", candidate_anchor="她将回执递给弟弟。")
        path = (self.directory / "candidate.md").relative_to(self.project).as_posix()
        self.prose_row = {"path": path, "sha256": self.manifest["candidate_sha256"]}
        self.review["editor_review"] = {
            "schema_version": 1, "policy_version": "independent-editor-v1", "source": "independent",
            "status": "PASS", "writer_run_id": "fixture-writer", "reviewer_run_id": "fixture-editor",
            "candidate_sha256": self.manifest["candidate_sha256"], "context_files": [self.prose_row],
            "passes": [{"kind": kind, "files": [path], "assessment": "Synthetic pass evidence.",
                        "evidence": [{"path": path, "anchor": "她将回执递给弟弟。"}]}
                       for kind in ("comprehension", "sentence")],
            "findings": [], "signoff": {"candidate_sha256": self.manifest["candidate_sha256"], "limitations": []},
        }
        self.review["reader_review"] = {
            "schema_version": 1, "status": "PASS", "source": "independent",
            "run_id": "fixture-reader-first-run",
            "chapter": 1, "candidate_path": path,
            "reviewer_run_id": "fixture-reader", "reading_kind": "first_read",
            "candidate_sha256": self.manifest["candidate_sha256"], "prose_files": [self.prose_row],
            "observations": {key: {"assessment": "Synthetic receipt; not actual reader feedback.",
                                    "evidence": [{"path": path, "anchor": "她将回执递给弟弟。"}]}
                             for key in ("understanding", "friction", "reward", "read_on")},
            "findings": [],
        }
        self.review["review_process"] = make_process(
            self.project, 1, self.directory / "candidate.md", self.review["editor_review"],
            [self.review["reader_review"]], prefix="审核/revision-fixture")

    def snapshot(self):
        return {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob("*") if p.is_file()}

    def check(self):
        return revision.check(self.project, self.operation, self.review, None)

    def test_public_check_is_read_only_with_both_reviews(self):
        before = self.snapshot()
        self.assertTrue(self.check()["ok"])
        self.assertEqual(before, self.snapshot())

    def test_missing_either_review_blocks_without_writes(self):
        for name in ("reader_review", "editor_review"):
            with self.subTest(name=name):
                original = self.review.pop(name)
                before = self.snapshot()
                with self.assertRaises(revision.Error):
                    self.check()
                self.assertEqual(before, self.snapshot())
                self.review[name] = original

    def test_reader_cannot_be_writer_or_editor(self):
        for identity in ("fixture-writer", "fixture-editor"):
            self.review["reader_review"]["reviewer_run_id"] = identity
            with self.assertRaisesRegex(revision.Error, "writer or editor"):
                self.check()

    def test_future_prose_cannot_enter_reader_view(self):
        row = {"path": "正文/第002章_明天.md", "sha256": "a"*64}
        self.review["reader_review"]["prose_files"].append(row)
        with self.assertRaisesRegex(revision.Error, "exclude future"):
            self.check()

    def test_self_review_cannot_pass(self):
        self.review["editor_review"]["source"] = "self_check"
        with self.assertRaisesRegex(revision.Error, "self check"):
            self.check()

    def test_reader_observations_require_real_anchors(self):
        self.review["reader_review"]["observations"]["friction"]["evidence"][0]["anchor"] = "not in manuscript"
        with self.assertRaisesRegex(revision.Error, "cannot be located"):
            self.check()

    def test_targeted_recheck_requires_initial_read_id(self):
        self.review["reader_review"]["reading_kind"] = "targeted_recheck"
        with self.assertRaises(revision.Error):
            self.check()
        initial = copy.deepcopy(self.review["reader_review"])
        initial.update(reading_kind="first_read", run_id="actual-earlier-run-fixture")
        record = self.directory / "first-read.json"
        record.write_text(json.dumps(initial), encoding="utf-8")
        self.review["reader_review"].update(first_read_run_id=initial["run_id"],
            first_read_candidate_sha256=initial["candidate_sha256"],
            first_read={"path": record.relative_to(self.project).as_posix(), "sha256": revision.candidate.sha256_file(record)})
        # This test targets the original reader-reference contract. Process-level
        # minor/substantial history is tested separately by test_review_process.
        revision.valid_reader_review(self.project, self.directory, self.manifest, self.review)
        record.write_text("{}", encoding="utf-8")
        with self.assertRaises(revision.Error):
            self.check()

    def test_critical_uncertainty_is_not_pass(self):
        self.review["reader_review"]["findings"] = [{"severity": "uncertain", "critical": True}]
        with self.assertRaisesRegex(revision.Error, "critical reader"):
            self.check()

    def test_process_required_without_side_effects(self):
        self.review.pop("review_process")
        before = self.snapshot()
        with self.assertRaisesRegex(revision.Error, "review_process"):
            self.check()
        self.assertEqual(before, self.snapshot())

    def test_process_report_mutation_during_scan_blocks_accept(self):
        process_path = self.project / self.review["review_process"]["path"]
        gate = revision.candidate.scan_gate
        def mutate(*args, **kwargs):
            result = gate(*args, **kwargs)
            process_path.write_text("{}", encoding="utf-8")
            return result
        before = self.final.read_bytes()
        with mock.patch.object(revision.candidate, "scan_gate", side_effect=mutate):
            with self.assertRaisesRegex(revision.Error, "stale reference"):
                revision.accept(self.project, self.operation, self.review, None, "synthetic approval")
        self.assertEqual(before, self.final.read_bytes())
        self.assertFalse((self.project / f"候选/_历史/修订事务-{self.operation}.json").exists())

    def test_recovery_rejects_changed_process_report(self):
        review_path = Path(self.temp.name) / "review.json"
        review_path.write_text(json.dumps(self.review, ensure_ascii=False), encoding="utf-8")
        run = subprocess.run([sys.executable, str(TOOL), "accept", "--project", str(self.project),
                              "--operation", self.operation, "--review", str(review_path),
                              "--author-approval", "synthetic approval"], capture_output=True,
                             text=True, encoding="utf-8", env={**os.environ, "STORY_REVISION_FAIL_AFTER": "prepared"})
        self.assertEqual(run.returncode, 97, run.stderr + run.stdout)
        path = self.project / self.review["review_process"]["path"]
        path.write_text("{}", encoding="utf-8")
        before = self.snapshot()
        with revision.project_lock(self.project):
            with self.assertRaisesRegex(revision.Error, "stale reference"):
                revision.recover_locked(self.project, self.operation)
        self.assertEqual(before, self.snapshot())

    def test_changed_candidate_rejects_old_receipts(self):
        (self.directory / "candidate.md").write_bytes(b"changed")
        with self.assertRaisesRegex(revision.Error, "frozen revision changed"):
            self.check()

    def test_scanner_time_external_edit_is_rejected(self):
        original_gate = revision.candidate.scan_gate
        def mutate(*args, **kwargs):
            value = original_gate(*args, **kwargs)
            self.final.write_bytes(self.final.read_bytes() + b"\nExternal change")
            return value
        with mock.patch.object(revision.candidate, "scan_gate", side_effect=mutate):
            with self.assertRaises(revision.Error):
                revision.accept(self.project, self.operation, self.review, None, "synthetic approval")
        self.assertFalse((self.project / f"候选/_历史/修订事务-{self.operation}.json").exists())

    def test_check_rejects_candidate_changed_during_scan(self):
        gate = revision.candidate.scan_gate
        def mutate(*args, **kwargs):
            result = gate(*args, **kwargs)
            path = self.directory / "candidate.md"
            path.write_bytes(path.read_bytes() + b"\nexternal change")
            return result
        with mock.patch.object(revision.candidate, "scan_gate", side_effect=mutate):
            with self.assertRaisesRegex(revision.Error, "frozen revision changed"):
                self.check()

    def test_reader_cannot_only_quote_previous_chapter(self):
        manifest = copy.deepcopy(self.manifest)
        manifest["chapter"] = 2
        reader = self.review["reader_review"]
        reader["chapter"] = 2
        previous = self.final.relative_to(self.project).as_posix()
        reader["prose_files"].append({"path": previous, "sha256": revision.candidate.sha256_file(self.final)})
        for observation in reader["observations"].values():
            observation["evidence"] = [{"path": previous, "anchor": "她把回执递给弟弟。"}]
        with self.assertRaisesRegex(revision.Error, "current candidate evidence"):
            revision.valid_reader_review(self.project, self.directory, manifest, self.review)

    def test_recovery_revalidates_review_and_is_idempotent(self):
        for phase in ("prepared", "prose_written"):
            with self.subTest(phase=phase):
                # Each phase uses a fresh project; successful recovery advances state.
                if phase == "prose_written":
                    self.setUp()
                review_path = Path(self.temp.name) / "review.json"
                review_path.write_text(json.dumps(self.review, ensure_ascii=False), encoding="utf-8")
                run = subprocess.run([sys.executable, str(TOOL), "accept", "--project", str(self.project),
                                      "--operation", self.operation, "--review", str(review_path),
                                      "--author-approval", "synthetic approval"],
                                     capture_output=True, text=True, encoding="utf-8",
                                     env={**os.environ, "STORY_REVISION_FAIL_AFTER": phase, "PYTHONDONTWRITEBYTECODE": "1"})
                self.assertEqual(run.returncode, 97, run.stderr + run.stdout)
                with revision.project_lock(self.project):
                    result = revision.recover_locked(self.project, self.operation)
                self.assertEqual(result["editor_status"], "PASS")
                before = self.snapshot()
                with revision.project_lock(self.project):
                    self.assertTrue(revision.recover_locked(self.project, self.operation)["adopted"])
                self.assertEqual(before, self.snapshot())


if __name__ == "__main__":
    unittest.main(verbosity=2)
