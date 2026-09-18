"""Synthetic transaction tests, not literary quality or human reading evidence."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
TOOL = Path(__file__).with_name("revision-commit.py")
sys.path.insert(0, str(TOOL.parent))
spec = importlib.util.spec_from_file_location("revision_review_test", TOOL)
revision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revision)
from test_review_process import make_process


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
    unittest.main()
