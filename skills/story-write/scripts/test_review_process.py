"""Process engineering fixtures; their statements are not actual reading evidence."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import review_process as process


def write_ref(project, relative, value):
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": relative, "sha256": process.digest(path)}


def make_process(project, chapter, candidate, editor, readers, *, prefix="审核/process", change=None, reader_identity=None):
    """Reusable *synthetic test* fixture; mutates reader receipts to match calls."""
    candidate_path = candidate.relative_to(project).as_posix()
    reader_identity = reader_identity or readers[0]["reviewer_run_id"]
    files = []
    union = {item['path']: item for item in [*editor['context_files'], *(item for reader in readers for item in reader.get('prose_files', []))]}
    for item in union.values():
        path = project / item["path"]
        files.append({**item, "text": path.read_bytes().decode("utf-8")})
    evidence = [{"path": candidate_path, "anchor": candidate.read_text(encoding="utf-8-sig").rstrip().splitlines()[-1][:12]}]
    reports = {}
    for index, role in enumerate(("editor", "natural", "diagnostic")):
        dimensions = ("understanding", "engagement", "confusion", "skimming", "reward_expectation") if role == "natural" else (("accuracy", "clarity", "naturalness", "continuity") if role == "editor" else sorted(process.DIAGNOSTIC_AXES))
        report = dict(role=role, chapter=chapter, candidate_sha256=process.digest(candidate), run_id=prefix + "-" + role, reviewer_run_id=editor["reviewer_run_id"] if role == "editor" else reader_identity, started_order=index * 2, completed_order=index * 2 + 1, findings=[], observations={name: {"assessment": "Synthetic observation", "evidence": evidence} for name in dimensions})
        if role == "natural": report["reading_kind"] = "first_read"
        if role == "diagnostic": report["natural_report_sha256"] = reports["natural"]["sha256"]
        reports[role] = write_ref(project, prefix + "-" + role + ".json", report)
    record = dict(schema_version=1, policy_version=process.POLICY, chapter=chapter, candidate_path=candidate_path, candidate_sha256=process.digest(candidate), prose_files=files, reports=reports, change=change or {"kind": "none", "reason": "First reader version"}, dispositions=[])
    record['writer_run_id'] = editor['writer_run_id']
    for reader in readers:
        reader.update(reviewer_run_id=reader_identity, run_id=prefix + "-diagnostic", reading_kind="first_read")
    return write_ref(project, prefix + ".json", record)


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prose = self.root / "候选/第1章_门.md"
        self.prose.parent.mkdir()
        self.prose.write_text("她打开门。", encoding="utf-8")
        self.editor = dict(writer_run_id="writer", reviewer_run_id="editor", context_files=[{"path": "候选/第1章_门.md", "sha256": process.digest(self.prose)}])
        self.readers = [dict(reviewer_run_id="reader")]
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers)

    def validate(self):
        return process.validate(self.root, 1, self.prose, self.ref, editor=self.editor, readers=self.readers)

    def modify(self, fn):
        doc = process.read_reference(self.root, self.ref)
        fn(doc)
        self.ref = write_ref(self.root, self.ref["path"], doc)

    def test_success(self): self.assertEqual(self.validate()["status"], "VERIFIED")

    def test_fixture_keeps_evidence_with_trailing_blank_lines(self):
        self.prose.write_text("她打开门。\n\n", encoding="utf-8")
        self.editor["context_files"][0]["sha256"] = process.digest(self.prose)
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers)
        self.assertEqual(self.validate()["status"], "VERIFIED")
        record = process.read_reference(self.root, self.ref)
        for reference in record["reports"].values():
            report = process.read_reference(self.root, reference)
            for observation in report["observations"].values():
                self.assertEqual(observation["evidence"][0]["anchor"], "她打开门。")

    def test_stale_report(self):
        doc = process.read_reference(self.root, self.ref)
        (self.root / doc['reports']['natural']['path']).write_text('{}', encoding='utf-8')
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_reversed_order(self):
        def mutate(doc):
            report = process.read_reference(self.root, doc['reports']['natural'])
            report['completed_order'] = 4
            doc['reports']['natural'] = write_ref(self.root, doc['reports']['natural']['path'], report)
        self.modify(mutate)
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_unhandled_important(self):
        def mutate(doc):
            report = process.read_reference(self.root, doc['reports']['editor'])
            report['findings'] = [{'id': 'e1', 'important': True, 'impact': '具体影响', 'evidence': [{'path': '候选/第1章_门.md', 'anchor': '打开门'}]}]
            doc['reports']['editor'] = write_ref(self.root, doc['reports']['editor']['path'], report)
        self.modify(mutate)
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_current_candidate_changed(self):
        self.prose.write_text('她关门。', encoding='utf-8')
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_diagnostic_dispatched_before_natural_return_rejected(self):
        def mutate(doc):
            report = process.read_reference(self.root, doc['reports']['diagnostic'])
            report['started_order'] = 2
            doc['reports']['diagnostic'] = write_ref(self.root, doc['reports']['diagnostic']['path'], report)
        self.modify(mutate)
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_missing_editor_axis_rejected(self):
        def mutate(doc):
            report = process.read_reference(self.root, doc['reports']['editor'])
            report['observations'].pop('naturalness')
            doc['reports']['editor'] = write_ref(self.root, doc['reports']['editor']['path'], report)
        self.modify(mutate)
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_missing_diagnostic_question_rejected(self):
        def mutate(doc):
            report = process.read_reference(self.root, doc['reports']['diagnostic'])
            report['observations'].pop('causes')
            doc['reports']['diagnostic'] = write_ref(self.root, doc['reports']['diagnostic']['path'], report)
        self.modify(mutate)
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_reference_cannot_escape_project(self):
        self.modify(lambda doc: doc['reports']['natural'].update(path='../outside.json'))
        with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_minor_targeted_review_keeps_reader(self):
        old = self.ref
        self.prose.write_text('她打开门！', encoding='utf-8')
        self.editor['context_files'][0]['sha256'] = process.digest(self.prose)
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix='审核/minor', change={'kind': 'minor', 'reason': 'Punctuation only', 'previous': old})
        def mutate(doc):
            natural = process.read_reference(self.root, doc['reports']['natural'])
            natural['reading_kind'] = 'targeted_recheck'
            doc['reports']['natural'] = write_ref(self.root, doc['reports']['natural']['path'], natural)
            diagnostic = process.read_reference(self.root, doc['reports']['diagnostic'])
            diagnostic['natural_report_sha256'] = doc['reports']['natural']['sha256']
            doc['reports']['diagnostic'] = write_ref(self.root, doc['reports']['diagnostic']['path'], diagnostic)
        self.modify(mutate)
        self.readers[0]['reading_kind'] = 'targeted_recheck'
        self.assertEqual(self.validate()['status'], 'VERIFIED')

    def test_previous_important_opinion_cannot_disappear(self):
        def add(doc):
            report = process.read_reference(self.root, doc['reports']['editor'])
            report['findings'] = [{'id': 'keep', 'important': True, 'impact': 'Opening useful', 'evidence': [{'path': '候选/第1章_门.md', 'anchor': '打开门'}]}]
            doc['reports']['editor'] = write_ref(self.root, doc['reports']['editor']['path'], report)
            doc['dispositions'] = [{'finding_id': report['run_id'] + '/keep', 'decision': 'accepted', 'reason': 'Keep action', 'evidence': [{'path': '候选/第1章_门.md', 'anchor': '打开门'}]}]
        self.modify(add)
        self.validate()
        old = self.ref
        self.prose.write_text('她打开门，走出去。', encoding='utf-8')
        self.editor['context_files'][0]['sha256'] = process.digest(self.prose)
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix='审核/new', reader_identity='new-reader', change={'kind': 'substantial', 'reason': 'Changed ending', 'previous': old})
        with self.assertRaisesRegex(process.ReviewProcessError, 'source IDs'):
            self.validate()

    def test_unrelated_reader_context_is_not_silently_dropped(self):
        previous = self.root / '正文/第0章_前.md'
        previous.parent.mkdir()
        previous.write_text('他在门外。', encoding='utf-8')
        self.readers[0]['prose_files'] = [{'path': '正文/第0章_前.md', 'sha256': process.digest(previous)}]
        with self.assertRaises(process.ReviewProcessError): self.validate()
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers)
        self.assertEqual(self.validate()['status'], 'VERIFIED')

    def test_reader_a_b_a_cannot_claim_third_first_read(self):
        for index, identity in enumerate(('reader-b', 'reader')):
            old = self.ref
            self.prose.write_text(f'她第{index}次关门。', encoding='utf-8')
            self.editor['context_files'][0]['sha256'] = process.digest(self.prose)
            self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix=f'审核/version-{index}', reader_identity=identity, change={'kind': 'substantial', 'reason': 'Scene changed', 'previous': old})
            if index == 0:
                self.validate()
            else:
                with self.assertRaises(process.ReviewProcessError): self.validate()

    def test_previous_editor_cannot_become_fresh_reader(self):
        old = self.ref
        self.prose.write_text('她走出门。', encoding='utf-8')
        self.editor['context_files'][0]['sha256'] = process.digest(self.prose)
        self.editor['reviewer_run_id'] = 'new-editor'
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix='审核/changed-role', reader_identity='editor', change={'kind': 'substantial', 'reason': 'Changed scene', 'previous': old})
        with self.assertRaisesRegex(process.ReviewProcessError, 'new blind reader'):
            self.validate()

    def test_previous_writer_cannot_become_fresh_reader(self):
        old = self.ref
        self.prose.write_text('她走出门。', encoding='utf-8')
        self.editor['context_files'][0]['sha256'] = process.digest(self.prose)
        self.editor['writer_run_id'] = 'new-writer'
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix='审核/old-writer', reader_identity='writer', change={'kind': 'substantial', 'reason': 'Changed scene', 'previous': old})
        with self.assertRaisesRegex(process.ReviewProcessError, 'new blind reader'):
            self.validate()

    def test_substantial_needs_new_reader(self):
        previous = self.ref
        self.prose.write_text('她关门。', encoding='utf-8')
        self.editor['context_files'][0]['sha256'] = process.digest(self.prose)
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix='审核/revised', change={'kind': 'substantial', 'reason': 'Changed action', 'previous': previous})
        with self.assertRaises(process.ReviewProcessError): self.validate()
        self.ref = make_process(self.root, 1, self.prose, self.editor, self.readers, prefix='审核/revised', reader_identity='new-reader', change={'kind': 'substantial', 'reason': 'Changed action', 'previous': previous})
        self.assertEqual(self.validate()['status'], 'VERIFIED')


if __name__ == '__main__': unittest.main()
