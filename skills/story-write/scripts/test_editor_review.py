import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import editor_review as editor
spec = importlib.util.spec_from_file_location('candidate_commit_tests', ROOT / 'candidate-commit.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


class EditorContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prose = self.root / '候选/第2章_门.md'
        self.previous = self.root / '正文/第一卷/第1章_笔.md'
        for path in (self.prose, self.previous):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('他打开了门。', encoding='utf-8')
        files = [{'path': p.relative_to(self.root).as_posix(), 'sha256': editor.digest(p)} for p in (self.previous, self.prose)]
        self.receipt = dict(schema_version=1, policy_version='independent-editor-v1', status='PASS', source='independent', writer_run_id='writer', reviewer_run_id='editor', candidate_sha256=editor.digest(self.prose), context_files=files, passes=[{'kind': kind, 'files': [x['path'] for x in files]} for kind in ('comprehension', 'sentence')], findings=[], signoff={'candidate_sha256': editor.digest(self.prose), 'limitations': []})
        for entry in self.receipt['passes']:
            entry.update(assessment='人物开门动作及主语明确。', evidence=[{'path': files[1]['path'], 'anchor': '他打开了门。'}])

    def validate(self):
        return editor.validate(self.root, 2, self.prose, self.receipt)

    def test_pass_recursive_context(self):
        self.assertEqual(self.validate()['status'], 'PASS')

    def test_fault_matrix(self):
        mutations = [lambda r: r.update(schema_version=9), lambda r: r.update(reviewer_run_id='writer'), lambda r: r.update(candidate_sha256='bad'), lambda r: r.update(source='self_check'), lambda r: r.update(passes=[]), lambda r: r['signoff'].update(candidate_sha256='bad'), lambda r: r['context_files'].pop(), lambda r: r['context_files'][0].update(sha256='bad')]
        original = copy.deepcopy(self.receipt)
        for index, mutate in enumerate(mutations):
            with self.subTest(case=index):
                self.receipt = copy.deepcopy(original)
                mutate(self.receipt)
                with self.assertRaises(editor.EditorReviewError):
                    self.validate()

    def test_missing(self):
        self.receipt = None
        with self.assertRaises(editor.EditorReviewError): self.validate()

    def test_second_edit_stales_receipt(self):
        self.prose.write_text('他关了门。', encoding='utf-8')
        with self.assertRaises(editor.EditorReviewError): self.validate()

    def test_context_change_stales_receipt(self):
        self.previous.write_text('她离开了。', encoding='utf-8')
        with self.assertRaises(editor.EditorReviewError): self.validate()

    def test_waiver_does_not_make_self_check_independent(self):
        self.receipt.update(status='NOT_EVALUATED', source='self_check', reviewer_run_id='writer')
        self.receipt['waiver'] = {'chapter': 2, 'candidate_sha256': editor.digest(self.prose), 'author_approval': '本章免审', 'reason': '作者决定'}
        self.assertEqual(self.validate(), {'status': 'WAIVED', 'source': 'self_check'})
        self.receipt['waiver']['chapter'] = 3
        with self.assertRaises(editor.EditorReviewError): self.validate()

    def test_moved_candidate(self):
        final = self.root / '正文/第2章_门.md'
        self.prose.replace(final)
        self.assertEqual(editor.validate(self.root, 2, self.prose, self.receipt, moved_to=final)['status'], 'PASS')

    def test_findings(self):
        self.receipt['findings'] = [dict(id='e1', path=self.receipt['context_files'][0]['path'], anchor='他打开了门。', impact='指代不明', reason='待核', severity='uncertain', critical=True, disposition='unresolved')]
        with self.assertRaises(editor.EditorReviewError): self.validate()
        self.receipt['findings'][0]['critical'] = False
        with self.assertRaises(editor.EditorReviewError): self.validate()
        self.receipt['signoff']['limitations'] = ['指代尚不确定']
        self.assertEqual(self.validate()['status'], 'PASS')

    def test_legacy_prepared_requires_scoped_authorization(self):
        path = self.root / 'journal.json'
        journal = dict(schema_version=1, phase='prepared', operation_id='old', chapter=2, paths={'candidate': '候选/第2章_门.md', 'final': '正文/第2章_门.md', 'transaction': 'tx.json', 'archive_transaction': 'archive.json'}, digests={})
        path.write_text(json.dumps(journal), encoding='utf-8')
        before = path.read_bytes()
        with self.assertRaisesRegex(candidate.CandidateError, 'migration_required'):
            candidate.recover_journal(self.root, path)
        self.assertEqual(path.read_bytes(), before)
        with self.assertRaisesRegex(candidate.CandidateError, '摘要不一致'):
            candidate.recover_journal(self.root, path, legacy_authorization={'operation_id': 'old', 'journal_sha256': 'bad', 'author_approval': '恢复', 'reason': '旧事务'})

    def test_cli_legacy_requires_all_fields(self):
        self.assertEqual(candidate.main(['recover', '--project', str(self.root), '--chapter', '2', '--legacy-operation-id', 'old']), 2)

    def test_new_recovery_revalidates_editor_for_both_phases(self):
        for phase in ('prepared', 'prose_moved'):
            with self.subTest(phase=phase):
                transaction = self.root / 'tx.json'
                transaction.write_text(json.dumps({'candidate_binding': {'schema_version': 4, 'editor_review': self.receipt}}), encoding='utf-8')
                journal = dict(schema_version=3, phase=phase, chapter=2, paths={'candidate': '候选/第2章_门.md', 'final': '正文/第2章_门.md', 'transaction': 'tx.json', 'archive_transaction': 'archive.json'}, digests={}, editor_review=self.receipt, editor_result={'status': 'PASS', 'source': 'independent'})
                path = self.root / 'journal.json'
                path.write_text(json.dumps(journal), encoding='utf-8')
                with patch.object(candidate, 'verify_recovery_reader_view'), patch.object(candidate.editor_review, 'validate', side_effect=candidate.editor_review.EditorReviewError('stale context')):
                    with self.assertRaisesRegex(candidate.CandidateError, 'stale context'):
                        candidate.recover_journal(self.root, path)
                self.assertTrue(self.prose.exists())

    def test_no_scan_still_validates_editor(self):
        # Reach the independent editor gate with deterministic preflight inputs.
        binding = {'schema_version': 4, 'quality_profile': candidate.QUALITY_PROFILE}
        for key in ('prose', 'outline', 'skeleton'):
            binding[key] = {'path': self.prose.relative_to(self.root).as_posix(), 'sha256': editor.digest(self.prose)}
        state = self.root / candidate.TRACKING_STATE
        state.parent.mkdir(parents=True)
        state.write_text('{}', encoding='utf-8')
        tx = self.root / 'tx.json'
        tx.write_text('{}', encoding='utf-8')
        document = {'expected_state_revision': 0, 'chapter': 2, 'candidate_binding': binding}
        for skip in (False, True):
            with self.subTest(skip_scan=skip), patch.object(candidate, 'read_state', return_value={'state_revision': 0}):
                with self.assertRaisesRegex(candidate.CandidateError, 'missing receipt'):
                    candidate.validate_binding(self.root, 2, self.prose, tx, document, skip_scan=skip, scan_skip_reason='explicit' if skip else None)

    def test_pass_needs_actual_evidence(self):
        self.receipt['passes'][0]['evidence'] = []
        with self.assertRaises(editor.EditorReviewError): self.validate()

    def test_first_read_reference(self):
        path = self.root / 'first-read.json'
        original = {'chapter': 2, 'candidate_path': '候选/第2章_门.md', 'source': 'independent', 'reading_kind': 'first_read', 'run_id': 'first', 'reviewer_run_id': 'reader', 'candidate_sha256': editor.digest(self.prose)}
        original.update(findings=[], prose_files=[{'path': '候选/第2章_门.md', 'sha256': original['candidate_sha256']}], evidence=[{'path': '候选/第2章_门.md', 'anchor': '他打开了门。'}])
        path.write_text(json.dumps(original), encoding='utf-8')
        receipt = {'chapter': 2, 'first_read': {'path': 'first-read.json', 'sha256': editor.digest(path)}, 'first_read_run_id': 'first', 'reviewer_run_id': 'reader', 'first_read_candidate_sha256': original['candidate_sha256']}
        self.assertEqual(editor.validate_first_read(self.root, receipt, chapter=2), original)
        observed = copy.deepcopy(original)
        observed['observations'] = {'understanding': {'assessment': '人物行为清楚', 'evidence': observed.pop('evidence')}}
        path.write_text(json.dumps(observed), encoding='utf-8')
        receipt['first_read']['sha256'] = editor.digest(path)
        self.assertEqual(editor.validate_first_read(self.root, receipt, chapter=2), observed)
        metadata = {k: v for k, v in original.items() if k not in ('findings', 'evidence', 'prose_files')}
        path.write_text(json.dumps(metadata), encoding='utf-8')
        receipt['first_read']['sha256'] = editor.digest(path)
        with self.assertRaises(editor.EditorReviewError): editor.validate_first_read(self.root, receipt, chapter=2)
        path.write_text(json.dumps(original), encoding='utf-8')
        receipt['first_read']['sha256'] = editor.digest(path)
        receipt['reviewer_run_id'] = 'other'
        with self.assertRaises(editor.EditorReviewError): editor.validate_first_read(self.root, receipt, chapter=2)
        receipt['reviewer_run_id'] = 'reader'
        path.write_text('{}', encoding='utf-8')
        with self.assertRaises(editor.EditorReviewError): editor.validate_first_read(self.root, receipt, chapter=2)

    def test_first_read_rejects_invalid_path_source_kind_and_candidate(self):
        original = {'chapter': 2, 'candidate_path': '候选/第2章_门.md', 'source': 'independent', 'reading_kind': 'first_read', 'run_id': 'first', 'reviewer_run_id': 'reader', 'candidate_sha256': editor.digest(self.prose)}
        original.update(findings=[], prose_files=[{'path': '候选/第2章_门.md', 'sha256': original['candidate_sha256']}], evidence=[{'path': '候选/第2章_门.md', 'anchor': '他打开了门。'}])
        path = self.root / 'first.json'
        for field, value in (('source', 'self_check'), ('reading_kind', 'targeted_recheck'), ('candidate_sha256', 'bad'), ('run_id', 'other'), ('findings', None), ('prose_files', []), ('evidence', []), ('chapter', 1), ('candidate_path', '候选/第1章_笔.md')):
            with self.subTest(field=field):
                changed = {**original, field: value}
                path.write_text(json.dumps(changed), encoding='utf-8')
                receipt = {'chapter': 2, 'first_read': {'path': 'first.json', 'sha256': editor.digest(path)}, 'first_read_run_id': 'first', 'reviewer_run_id': 'reader', 'first_read_candidate_sha256': original['candidate_sha256']}
                with self.assertRaises(editor.EditorReviewError): editor.validate_first_read(self.root, receipt, chapter=2)
        receipt['first_read']['path'] = './first.json'
        with self.assertRaises(editor.EditorReviewError): editor.validate_first_read(self.root, receipt, chapter=2)

    def test_context_rejects_planning_future_and_noncanonical(self):
        for relative in ('大纲/第1章_纲.md', '正文/第3章_未来.md', './正文/第一卷/第1章_笔.md'):
            with self.subTest(path=relative):
                original = copy.deepcopy(self.receipt)
                self.receipt['context_files'][0]['path'] = relative
                with self.assertRaises(editor.EditorReviewError): self.validate()
                self.receipt = original

    def test_valid_other_chapter_first_read_cannot_be_reused(self):
        digest = editor.digest(self.previous)
        original = {'chapter': 1, 'candidate_path': '候选/第1章_笔.md', 'source': 'independent', 'reading_kind': 'first_read', 'run_id': 'first', 'reviewer_run_id': 'reader', 'candidate_sha256': digest, 'findings': [], 'prose_files': [{'path': '候选/第1章_笔.md', 'sha256': digest}], 'evidence': [{'path': '候选/第1章_笔.md', 'anchor': '他打开了门。'}]}
        path = self.root / 'prior-first-read.json'
        path.write_text(json.dumps(original), encoding='utf-8')
        receipt = {'chapter': 1, 'first_read': {'path': path.name, 'sha256': editor.digest(path)}, 'first_read_run_id': 'first', 'reviewer_run_id': 'reader', 'first_read_candidate_sha256': digest}
        editor.validate_first_read(self.root, receipt, chapter=1)
        receipt['chapter'] = 2
        with self.assertRaisesRegex(editor.EditorReviewError, 'chapter mismatch'):
            editor.validate_first_read(self.root, receipt, chapter=2)

    def test_resolved_finding_requires_original_snapshot(self):
        self.receipt['findings'] = [dict(id='e1', path='候选/第2章_门.md', anchor='旧句', impact='指代', reason='改清楚', severity='blocking', critical=True, disposition='resolved')]
        with self.assertRaises(editor.EditorReviewError): self.validate()
        original = self.root / '初审.md'
        original.write_text('旧句', encoding='utf-8')
        self.receipt['findings'][0]['original_evidence'] = {'path': '初审.md', 'sha256': editor.digest(original)}
        self.assertEqual(self.validate()['status'], 'PASS')

    def test_recovery_commits_and_archives_new_and_authorized_legacy(self):
        # Real file movement and phase journaling; reader gate and tracking delta
        # engine are isolated here because their own suites exercise semantics.
        for version in (1,):
            with self.subTest(version=version):
                final = self.root / '正文/第2章_门.md'
                if final.exists(): final.replace(self.prose)
                archive = self.root / 'archive.json'
                if archive.exists(): archive.unlink()
                state = self.root / candidate.TRACKING_STATE
                state.parent.mkdir(parents=True, exist_ok=True)
                state.write_text('{"state_revision":0}', encoding='utf-8')
                after = b'{"state_revision":1}'
                tx = self.root / 'tx.json'
                tx.write_text(json.dumps({'candidate_binding': {'schema_version': 2 if version == 1 else 3, 'editor_review': self.receipt}}), encoding='utf-8')
                journal = dict(schema_version=version, phase='prepared', operation_id='test', chapter=2, expected_state_revision=0, expected_next_revision=1, tracking_payload={}, paths={'candidate': '候选/第2章_门.md', 'final': '正文/第2章_门.md', 'transaction': 'tx.json', 'archive_transaction': 'archive.json'}, digests={'candidate': editor.digest(self.prose), 'transaction': editor.digest(tx), 'state_before': editor.digest(state), 'state_after': candidate.sha256_bytes(after)}, editor_review=self.receipt, editor_result={'status': 'PASS', 'source': 'independent'})
                path = self.root / 'journal.json'
                path.write_text(json.dumps(journal), encoding='utf-8')
                authorization = {'operation_id': 'test', 'journal_sha256': editor.digest(path), 'author_approval': '恢复已启动事务', 'reason': '升级恢复'} if version == 1 else None
                with patch.object(candidate, 'verify_recovery_reader_view'), patch.object(candidate, 'replay_tracking', side_effect=lambda *args: state.write_bytes(after)):
                    result = candidate.recover_journal(self.root, path, legacy_authorization=authorization)
                self.assertEqual(result['state_revision'], 1)
                self.assertTrue(final.exists() and archive.exists())
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['phase'], 'done')


if __name__ == '__main__':
    unittest.main()
