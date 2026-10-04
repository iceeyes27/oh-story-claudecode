"""评测证据的冻结、显式判分与完整性；不调用模型。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / '.novel-kit/scripts/eval_evidence.py'
spec = importlib.util.spec_from_file_location('eval_evidence', MODULE)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


class EvalEvidence(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.body = self.root / '正文.md'
        self.body.write_text('第一行\n第二行\n第三行\n', encoding='utf-8')
        self.answer = self.root / '答案.json'
        self.answer.write_text(json.dumps({
            'id': 'A01', '组': 'A', '审阅者': ['copy-editor'],
            '应抓': [{'id': 'A01-1', '预期严重度': 'S2'},
                     {'id': 'A01-2', '预期严重度': 'S3'}],
            '不应报': [{'证据': '保护原文', '理由': '角色声线'}],
        }, ensure_ascii=False), encoding='utf-8')
        self.config = {
            'schema_version': 1,
            'inputs': [
                {'id': 'body', 'path': '正文.md', 'kind': 'prose',
                 'range': {'start_line': 2, 'end_line': 3}},
                {'id': 'answer', 'path': '答案.json', 'kind': 'answer',
                 'audience': 'coordinator'},
            ],
            'runs': [self.make_run('r1', 1), self.make_run('r2', 2)],
        }
        self.destination = self.root / '新证据'

    @staticmethod
    def make_run(run_id, attempt, phase='review'):
        return {'id': run_id, 'sample': 'A01', 'role': 'copy-editor',
                'attempt': attempt, 'phase': phase, 'context': ['body'],
                'prompt': '只读冻结正文，不读答案。', 'independent_context': True,
                'output': 'outputs/' + run_id + '.md'}

    def freeze(self):
        path = self.root / '配置.json'
        path.write_text(json.dumps(self.config, ensure_ascii=False), encoding='utf-8')
        return e.freeze(path, self.destination)

    def output(self, run_id, value='检出一；检出二；保护项误报；额外问题。'):
        path = self.destination / 'outputs' / (run_id + '.md')
        path.write_text(value, encoding='utf-8')

    @staticmethod
    def row(issue_id, detected, severity=None, evidence=''):
        return {'issue_id': issue_id, 'detected': detected, 'severity': severity,
                'evidence': evidence, 'reason': '模型逐项对照原始报告。'}

    def judgments(self, first=None, second=None):
        runs = []
        for run_id, values in [('r1', first), ('r2', second)]:
            runs.append({'run_id': run_id, 'execution_date': '2026-10-02',
                         'issues': values if values is not None else [
                             self.row('A01-1', True, 'S3', '检出一'),
                             self.row('A01-2', False)],
                         'protected': [{'protected_id': 'A01-protected-1',
                                        'reported': False, 'evidence': '',
                                        'reason': '未在报告中列为问题。'}],
                         'extra_findings': []})
        return {'schema_version': 1, 'quality_judgment_source': 'model_comparison',
                'runs': runs, 'repairs': []}

    def score(self, table=None, name='评分'):
        path = self.root / '逐项判分.json'
        path.write_text(json.dumps(table or self.judgments(), ensure_ascii=False), encoding='utf-8')
        return e.score(self.destination, path, name)

    def prepare(self):
        self.freeze()
        self.output('r1')
        self.output('r2')

    def test_freeze_keeps_actual_range_unknown_model_and_readonly_inputs(self):
        manifest = self.freeze()
        item = manifest['inputs'][0]
        self.assertEqual(item['range'], {'start_line': 2, 'end_line': 3})
        self.assertEqual((self.destination / item['snapshot']).read_text(encoding='utf-8'), '第二行\n第三行\n')
        self.assertEqual(manifest['runs'][0]['model'], 'unknown')
        self.assertEqual(manifest['runs'][0]['context'], ['body'])
        self.assertTrue(manifest['created_at'].endswith('Z'))
        self.assertEqual((self.destination / item['snapshot']).stat().st_mode & 0o222, 0)

    def test_freeze_never_overwrites_existing_directory(self):
        self.freeze()
        old = (self.destination / 'manifest.json').read_bytes()
        with self.assertRaises(e.Invalid):
            self.freeze()
        self.assertEqual(old, (self.destination / 'manifest.json').read_bytes())

    def test_freeze_collision_does_not_delete_another_process_directory(self):
        original = Path.mkdir

        def racing_mkdir(path, *args, **kwargs):
            if path.resolve() == self.destination.resolve():
                original(path, parents=True, exist_ok=False)
                (path / '另一进程.txt').write_text('其他进程的记录', encoding='utf-8')
                raise FileExistsError('另一进程已创建目标')
            return original(path, *args, **kwargs)

        with patch.object(Path, 'mkdir', racing_mkdir):
            with self.assertRaises(FileExistsError):
                self.freeze()
        self.assertTrue((self.destination / '另一进程.txt').is_file(), '另一进程的记录应保留')
        self.assertEqual((self.destination / '另一进程.txt').read_text(encoding='utf-8'), '其他进程的记录')

    def test_verify_detects_source_and_snapshot_drift(self):
        manifest = self.freeze()
        self.body.write_text('来源已修改', encoding='utf-8')
        report = e.verify(self.destination)
        self.assertFalse(report['ok'])
        self.assertTrue(any(x['kind'] == 'source_drift' for x in report['problems']))
        snap = self.destination / manifest['inputs'][0]['snapshot']
        snap.chmod(0o644)
        snap.write_text('快照被修改', encoding='utf-8')
        self.assertTrue(any(x['kind'] == 'snapshot_drift' for x in e.verify(self.destination)['problems']))

    def test_verify_checks_declared_output_range_and_missing_outputs(self):
        self.freeze()
        self.assertTrue(e.verify(self.destination)['ok'])
        self.assertEqual(len(e.verify(self.destination)['missing_outputs']), 2)
        self.assertFalse(e.verify(self.destination, require_outputs=True)['ok'])
        self.output('未声明')
        self.assertFalse(e.verify(self.destination)['ok'])

    def test_known_runner_locks_allow_scoring_and_preserve_files(self):
        self.config['scope'] = 'review_only'
        self.prepare()
        locks = []
        for run_id, content in [('r1', b''), ('r2', b'0')]:
            lock = self.destination / 'outputs' / ('.' + run_id + '.md.eval-runner.lock')
            lock.write_bytes(content)
            locks.append((lock, content, lock.stat().st_ino))
        self.assertTrue(e.verify(self.destination, require_outputs=True)['ok'])
        report = self.score()
        self.assertTrue(report['evidence_complete'], report['missing'])
        self.assertEqual(set(report['output_hashes']), {'outputs/r1.md', 'outputs/r2.md'})
        self.assertEqual(report['quality_acceptance'], 'not_determined')
        self.assertTrue(e.verify(self.destination, require_outputs=True)['ok'])
        for lock, content, inode in locks:
            self.assertEqual(lock.read_bytes(), content)
            self.assertEqual(lock.stat().st_ino, inode, '核验和评分不得删除或重建锁文件')

    def test_runner_locks_do_not_satisfy_missing_outputs(self):
        self.config['scope'] = 'review_only'
        self.freeze()
        for run_id, content in [('r1', b''), ('r2', b'0')]:
            (self.destination / 'outputs' / ('.' + run_id + '.md.eval-runner.lock')).write_bytes(content)
        self.assertTrue(e.verify(self.destination)['ok'])
        integrity = e.verify(self.destination, require_outputs=True)
        self.assertFalse(integrity['ok'])
        self.assertEqual(set(integrity['missing_outputs']), {'outputs/r1.md', 'outputs/r2.md'})
        report = self.score()
        self.assertFalse(report['evidence_complete'])
        self.assertEqual(report['output_hashes'], {})
        self.assertIn('缺失输出：outputs/r1.md', report['missing'])
        self.assertIn('缺失输出：outputs/r2.md', report['missing'])

    def test_unknown_locks_and_extra_reports_still_block_scoring(self):
        self.prepare()
        for name in ['.unknown.md.eval-runner.lock', 'r1.md.eval-runner.lock', '额外报告.md']:
            with self.subTest(name=name):
                extra = self.destination / 'outputs' / name
                extra.write_bytes(b'')
                self.addCleanup(extra.unlink, missing_ok=True)
                report = e.verify(self.destination)
                self.assertFalse(report['ok'])
                self.assertIn({'kind': 'unexpected_output', 'path': 'outputs/' + name}, report['problems'])
                with self.assertRaises(e.Invalid):
                    self.score()
                extra.unlink()

    def test_runner_locks_require_exact_supported_contents(self):
        self.prepare()
        lock = self.destination / 'outputs/.r1.md.eval-runner.lock'
        for content in [b'x', b'\x1a', b'00', '伪装为锁的报告正文'.encode('utf-8')]:
            with self.subTest(content=content):
                lock.write_bytes(content)
                report = e.verify(self.destination)
                self.assertFalse(report['ok'])
                self.assertIn({'kind': 'unexpected_output', 'path': 'outputs/.r1.md.eval-runner.lock'},
                              report['problems'])
                with self.assertRaises(e.Invalid):
                    self.score()

    def test_runner_lock_symlinks_and_directories_are_rejected(self):
        self.prepare()
        lock = self.destination / 'outputs/.r1.md.eval-runner.lock'
        target = self.root / '空文件'
        target.write_bytes(b'')
        for destination in [target, self.root / '不存在的文件']:
            with self.subTest(target=destination.name):
                try:
                    lock.symlink_to(destination)
                except OSError as exc:
                    self.skipTest('当前环境不支持创建符号链接：' + str(exc))
                self.assertIn({'kind': 'unexpected_output', 'path': 'outputs/.r1.md.eval-runner.lock'},
                              e.verify(self.destination)['problems'])
                lock.unlink()
        lock.mkdir()
        self.assertIn({'kind': 'unexpected_output', 'path': 'outputs/.r1.md.eval-runner.lock'},
                      e.verify(self.destination)['problems'])

    def test_runner_lock_name_is_bound_to_exact_declared_parent(self):
        self.config['runs'][0]['output'] = 'outputs/分组/r1.md'
        self.freeze()
        self.output('r2')
        output = self.destination / 'outputs/分组/r1.md'
        output.write_text('检出一', encoding='utf-8')
        output.with_name('.r1.md.eval-runner.lock').write_bytes(b'')
        self.assertTrue(e.verify(self.destination, require_outputs=True)['ok'])
        wrong_parent = self.destination / 'outputs/.r1.md.eval-runner.lock'
        wrong_parent.write_bytes(b'')
        self.assertIn({'kind': 'unexpected_output', 'path': 'outputs/.r1.md.eval-runner.lock'},
                      e.verify(self.destination)['problems'])

    def test_output_directory_symlink_cannot_grant_lock_exception(self):
        self.config['runs'][0]['output'] = 'outputs/分组/r1.md'
        self.freeze()
        directory = self.destination / 'outputs/分组'
        directory.rmdir()
        target = self.root / '实际分组'
        target.mkdir()
        (target / '.r1.md.eval-runner.lock').write_bytes(b'')
        try:
            directory.symlink_to(target, target_is_directory=True)
        except OSError as exc:
            self.skipTest('当前环境不支持创建符号链接：' + str(exc))
        with self.assertRaises(e.Invalid):
            e.verify(self.destination)

    def test_declared_lock_shaped_report_remains_hash_checked(self):
        self.config['runs'][1]['output'] = 'outputs/.r1.md.eval-runner.lock'
        self.freeze()
        self.output('r1')
        report_path = self.destination / 'outputs/.r1.md.eval-runner.lock'
        report_path.write_text('检出一', encoding='utf-8')
        self.assertTrue(e.verify(self.destination, require_outputs=True)['ok'])
        score = self.score()
        self.assertIn('outputs/.r1.md.eval-runner.lock', score['output_hashes'])
        report_path.write_bytes(b'')
        report = e.verify(self.destination)
        self.assertFalse(report['ok'])
        self.assertTrue(any(x['kind'] == 'scored_output_drift'
                            and x['path'] == 'outputs/.r1.md.eval-runner.lock' for x in report['problems']))

    def test_runner_lock_replacement_during_open_is_rejected(self):
        self.prepare()
        lock = (self.destination / 'outputs/.r1.md.eval-runner.lock').resolve()
        lock.write_bytes(b'')
        replacement = self.root / '替换锁'
        replacement.write_bytes(b'')
        original_open = e.os.open

        def replacing_open(path, flags, *args, **kwargs):
            if path == lock:
                replacement.replace(lock)
            return original_open(path, flags, *args, **kwargs)

        with patch.object(e.os, 'open', replacing_open):
            report = e.verify(self.destination)
        self.assertIn({'kind': 'unexpected_output', 'path': 'outputs/.r1.md.eval-runner.lock'},
                      report['problems'])

    def test_output_escape_and_answer_context_are_rejected_before_writing(self):
        self.config['runs'][0]['output'] = '../覆盖.md'
        with self.assertRaises(e.Invalid):
            self.freeze()
        self.assertFalse(self.destination.exists())
        self.config['runs'][0]['output'] = 'outputs/r1.md'
        self.config['runs'][0]['context'].append('answer')
        with self.assertRaises(e.Invalid):
            self.freeze()
        self.assertFalse(self.destination.exists())

    def test_each_attempt_is_separate_from_supplemental_union(self):
        self.prepare()
        first = [self.row('A01-1', True, 'S3', '检出一'), self.row('A01-2', False)]
        second = [self.row('A01-1', False), self.row('A01-2', True, 'S2', '检出二')]
        report = self.score(self.judgments(first, second))
        self.assertEqual([x['detected']['rate'] for x in report['attempts']], [0.5, 0.5])
        self.assertEqual(report['unions'][0]['detected']['rate'], 1.0)
        self.assertEqual(report['attempts'][0]['severity_attainment']['rate'], 0.0)
        self.assertEqual(report['unions'][0]['severity_attainment']['rate'], 0.0)

    def test_two_run_consistency_is_explicit_not_union_success(self):
        self.prepare()
        first = [self.row('A01-1', True, 'S3', '检出一'), self.row('A01-2', False)]
        second = [self.row('A01-1', True, 'S2', '检出一'), self.row('A01-2', True, 'S4', '检出二')]
        report = self.score(self.judgments(first, second))
        consistency = report['consistency'][0]
        self.assertEqual(consistency['detection_agreement']['rate'], 0.5)
        self.assertEqual(consistency['severity_agreement']['rate'], 0.0)
        self.assertEqual(consistency['positive_overlap']['rate'], 0.5)

    def test_missing_rows_do_not_become_clean_or_complete(self):
        self.prepare()
        table = self.judgments()
        table['runs'][1]['issues'].pop()
        table['runs'][0].pop('extra_findings')
        report = self.score(table)
        self.assertFalse(report['evidence_complete'])
        self.assertIsNone(report['runs'][1]['detected']['rate'])
        self.assertTrue(any('A01-2' in x for x in report['missing']))
        self.assertEqual(report['quality_acceptance'], 'not_determined')
        summary = (self.destination / 'scores/评分.md').read_text(encoding='utf-8')
        self.assertIn('模型对照', summary)
        self.assertIn('不代表作者亲自核验', summary)
        self.assertIn('缺失', summary)

    def test_zero_denominator_is_not_perfect_score(self):
        self.answer.write_text(json.dumps({'id': 'A01', '组': 'K', '应抓': [], '不应报': []}), encoding='utf-8')
        self.prepare()
        table = self.judgments([], [])
        for run in table['runs']:
            run['protected'] = []
            run['extra_findings'] = [{'id': 'extra-1', 'severity': 'S2',
                                      'evidence': '额外问题', 'reason': '答案外问题。',
                                      'false_positive': True}]
        report = self.score(table)
        self.assertIsNone(report['attempts'][0]['detected']['rate'])
        self.assertEqual(report['runs'][0]['false_positives']['control_s1_s2'], 1)
        self.assertEqual(report['unions'][0]['false_positives']['control_s1_s2'], 1)

    def test_protection_and_false_positives_remain_separate(self):
        self.prepare()
        table = self.judgments()
        table['runs'][0]['protected'][0].update(reported=True, evidence='保护项误报')
        report = self.score(table)
        self.assertEqual(report['runs'][0]['false_positives']['protected_reported'], 1)
        self.assertEqual(report['runs'][1]['false_positives']['protected_reported'], 0)
        self.assertEqual(report['unions'][0]['false_positives']['protected_reported'], 1)

    def test_unbacked_and_duplicate_judgments_are_rejected(self):
        self.prepare()
        table = self.judgments()
        table['runs'][0]['issues'][0]['evidence'] = '报告里没有的引用'
        with self.assertRaises(e.Invalid):
            self.score(table)
        table = self.judgments()
        table['runs'][0]['issues'].append(dict(table['runs'][0]['issues'][0]))
        with self.assertRaises(e.Invalid):
            self.score(table)
        self.assertFalse((self.destination / 'scores/评分.json').exists())

    def test_score_never_overwrites_and_verify_binds_raw_outputs(self):
        self.prepare()
        self.score()
        with self.assertRaises(e.Invalid):
            self.score()
        self.output('r1', '修改后的原始报告')
        report = e.verify(self.destination)
        self.assertFalse(report['ok'])
        self.assertTrue(any(x['kind'] == 'scored_output_drift' for x in report['problems']))

    def test_human_attribution_is_not_invented(self):
        self.prepare()
        table = self.judgments()
        table['quality_judgment_source'] = 'human'
        with self.assertRaises(e.Invalid):
            self.score(table)

    def test_repair_missing_is_listed_even_when_review_tables_complete(self):
        self.prepare()
        report = self.score()
        self.assertFalse(report['evidence_complete'])
        self.assertTrue(any('修正' in x for x in report['missing']))

    def test_review_only_scope_can_complete_without_claiming_quality_pass(self):
        self.config['scope'] = 'review_only'
        self.prepare()
        report = self.score()
        self.assertTrue(report['evidence_complete'], report['missing'])
        self.assertEqual(report['scope'], 'review_only')
        self.assertEqual(report['quality_acceptance'], 'not_determined')

    def test_complete_repair_evidence_still_does_not_claim_quality_pass(self):
        self.config['runs'] += [self.make_run('fix', 1, 'repair'), self.make_run('fix-review', 1, 'repair_review')]
        self.prepare()
        self.output('fix', '修正副本，保留保护原文。')
        self.output('fix-review', '复审确认一；复审确认二；保护项保留。')
        table = self.judgments()
        table['repairs'] = [{
            'sample': 'A01', 'repair_run_id': 'fix', 'review_run_id': 'fix-review',
            'execution_date': '2026-10-02',
            'issues': [{'issue_id': 'A01-1', 'resolved': True, 'evidence': '复审确认一', 'reason': '模型对照修后报告。'}],
            'new_errors': [],
            'protected': [{'protected_id': 'A01-protected-1', 'changed': False,
                           'evidence': '保护项保留', 'reason': '模型对照修正副本与原文。'}],
        }]
        report = self.score(table)
        self.assertTrue(report['evidence_complete'], report['missing'])
        self.assertEqual(report['repairs'][0]['resolved']['rate'], 1.0)
        self.assertEqual(report['repairs'][0]['protected_changed'], 0)
        self.assertEqual(report['quality_acceptance'], 'not_determined')


if __name__ == '__main__':
    unittest.main()
