"""用临时假执行器验证评测调度；不调用真实模型。"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


MODULE = Path(__file__).resolve().parents[1] / '.novel-kit/scripts/eval_runner.py'
spec = importlib.util.spec_from_file_location('eval_runner', MODULE)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


FAKE_CODEX = r'''
import json
import os
from pathlib import Path
import subprocess
import sys
import time

prompt = sys.stdin.read()
job = json.loads(prompt)
Path(job['invocation']).write_text(prompt, encoding='utf-8')
Path(job['arguments']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
print(json.dumps({'type': 'thread.started', 'thread_id': 'fake-thread'}), flush=True)
mode = job.get('mode', 'success')
if mode == 'delayed_report':
    time.sleep(1)
if mode == 'nested':
    item = {'id': 'nested-1', 'type': 'collab_tool_call', 'tool': 'wait'}
    print(json.dumps({'type': 'item.started', 'item': item}), flush=True)
    print(json.dumps({'type': 'item.completed', 'item': item}), flush=True)
if mode == 'timeout':
    if job.get('marker'):
        code = 'import signal, time; from pathlib import Path; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(1.5); Path(' + repr(job['marker']) + ').write_text("未终止的子进程", encoding="utf-8")'
        subprocess.Popen([sys.executable, '-c', code])
    time.sleep(30)
if mode == 'drift':
    Path(job['input']).write_text('执行中修改输入', encoding='utf-8')
if mode != 'no_report':
    Path(job['output']).write_text(' ' if mode == 'empty' else '独立审阅报告。', encoding='utf-8')
if mode != 'no_completion':
    print(json.dumps({'type': 'turn.completed'}), flush=True)
sys.exit(7 if mode == 'nonzero' else 0)
'''


FAKE_CLAUDE = r'''
import json
from pathlib import Path
import sys

job = json.loads(sys.stdin.read())
Path(job['arguments']).write_text(json.dumps(sys.argv[1:]), encoding='utf-8')
mode = job.get('mode', 'success')
print(json.dumps({'type': 'system', 'subtype': 'init', 'model': 'claude-fake-1', 'tools': ['Read', 'Write']}), flush=True)


def tool(name, **args):
    block = {'type': 'tool_use', 'id': 'tu-' + name + str(len(args)), 'name': name, 'input': args}
    print(json.dumps({'type': 'assistant', 'message': {'content': [block]}}), flush=True)


tool('Read', file_path=job['input'])
if mode == 'outside_read':
    tool('Read', file_path=job['other'])
if mode == 'nested':
    tool('Agent', prompt='x')
Path(job['output']).write_text('独立审阅报告。', encoding='utf-8')
if mode == 'auth':
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': True, 'result': 'Not logged in'}), flush=True)
else:
    print(json.dumps({'type': 'result', 'subtype': 'success', 'is_error': False, 'num_turns': 3,
                      'total_cost_usd': 0.25, 'duration_ms': 1200, 'usage': {'input_tokens': 10}}), flush=True)
'''


@unittest.skipUnless(os.name == 'posix', '假执行器使用 POSIX 可执行脚本')
class EvalRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / '执行证据'
        self.evidence.mkdir()
        self.input = self.root / '输入.md'
        self.input.write_text('原始冻结正文。', encoding='utf-8')
        self.output = self.root / '报告.md'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        fake = self.bin / 'codex'
        fake.write_text('#!' + sys.executable + '\n' + FAKE_CODEX, encoding='utf-8')
        fake.chmod(0o755)
        self.env = patch.dict(os.environ, {'PATH': str(self.bin) + os.pathsep + os.environ.get('PATH', '')})
        self.env.start()
        self.addCleanup(self.env.stop)

    def job(self, mode='success'):
        control = {'output': str(self.output), 'input': str(self.input),
                   'invocation': str(self.root / '已启动.txt'),
                   'arguments': str(self.root / '参数.json'),
                   'marker': str(self.root / '残留子进程.txt'), 'mode': mode}
        return {'id': 'A01_修后_copy-editor_1', 'dataset': 'regression',
                'prompt': json.dumps(control, ensure_ascii=False),
                'output': str(self.output), 'allowed_inputs': [str(self.input)],
                'input_hashes': {str(self.input): hashlib.sha256(self.input.read_bytes()).hexdigest()}}

    def execute(self, job=None, timeout=3):
        return r.execute(job or self.job(), self.root, self.evidence, timeout=timeout)

    def start_direct(self, job, evidence=None):
        task = self.root / ('独立任务-' + job['id'] + '.json')
        task.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
        code = ('import importlib.util,json,sys; from pathlib import Path; '
                's=importlib.util.spec_from_file_location("runner",sys.argv[1]); '
                'm=importlib.util.module_from_spec(s); s.loader.exec_module(m); '
                'print(json.dumps(m.execute(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")),'
                'sys.argv[3],sys.argv[4],timeout=20),ensure_ascii=False))')
        return subprocess.Popen([sys.executable, '-c', code, str(MODULE), str(task),
                                 str(self.root), str(evidence or self.evidence)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')

    def wait_for_invocation(self):
        deadline = time.monotonic() + 3
        while not (self.root / '已启动.txt').exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.root / '已启动.txt').exists(), '假执行器未及时启动')

    def assert_not_completed(self, result):
        self.assertNotIn(result['status'], ('completed', 'resumed', '完成', '已验证完成', '已验证恢复'))

    def test_success_and_resume_preserve_report_and_exact_prompt(self):
        job = self.job()
        first = self.execute(job)
        self.assertTrue(first['turn_completed'], first)
        self.assertEqual(first['returncode'], 0, first)
        original = self.output.read_bytes()
        prompt = self.root / '已启动.txt'
        self.assertEqual(prompt.read_text(encoding='utf-8'), job['prompt'])
        started = prompt.stat().st_mtime_ns
        second = self.execute(job)
        self.assertEqual(prompt.stat().st_mtime_ns, started, second)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertIn(second['status'], ('resumed', '完成', '已验证完成', '已验证恢复', 'completed'))
        arguments = json.loads((self.root / '参数.json').read_text(encoding='utf-8'))
        self.assertIn('--ephemeral', arguments)
        self.assertIn('multi_agent', arguments)
        self.assertIn('memories', arguments)
        self.assertNotIn('--model', arguments)
        self.assertNotIn('resume', arguments)

    def test_bad_input_never_launches(self):
        job = self.job()
        self.input.write_text('输入已漂移。', encoding='utf-8')
        result = self.execute(job)
        self.assert_not_completed(result)
        self.assertFalse((self.root / '已启动.txt').exists())
        self.assertFalse(self.output.exists())

    def test_missing_input_is_recorded_without_launch(self):
        job = self.job()
        self.input.unlink()
        result = self.execute(job)
        self.assert_not_completed(result)
        self.assertFalse((self.root / '已启动.txt').exists())

    def test_existing_output_without_credential_is_preserved(self):
        self.output.write_text('未知来源旧报告。', encoding='utf-8')
        result = self.execute()
        self.assert_not_completed(result)
        self.assertEqual(self.output.read_text(encoding='utf-8'), '未知来源旧报告。')
        self.assertFalse((self.root / '已启动.txt').exists())

    def test_changed_report_cannot_resume(self):
        job = self.job()
        self.execute(job)
        self.output.write_text('报告已被手改。', encoding='utf-8')
        result = self.execute(job)
        self.assert_not_completed(result)
        self.assertEqual(self.output.read_text(encoding='utf-8'), '报告已被手改。')

    def test_changed_prompt_cannot_reuse_other_report(self):
        job = self.job()
        self.execute(job)
        job['prompt'] += ' '
        self.assert_not_completed(self.execute(job))

    def test_changed_opening_or_events_cannot_resume(self):
        for name in ('opening.json', 'events.jsonl'):
            with self.subTest(name=name):
                self.output.unlink(missing_ok=True)
                first = self.execute()
                path = Path(first['evidence_dir']) / name
                path.write_text(path.read_text(encoding='utf-8') + '\n', encoding='utf-8')
                self.assert_not_completed(self.execute())

    def test_legacy_receipt_is_preserved_as_unverified(self):
        first = self.execute()
        receipt = Path(first['evidence_dir']) / 'result.json'
        value = json.loads(receipt.read_text(encoding='utf-8'))
        value.pop('opening_sha256')
        receipt.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        original = receipt.read_bytes()
        self.assertEqual(self.execute()['status'], 'unverified_output')
        self.assertEqual(receipt.read_bytes(), original)

    def test_job_id_rejects_path_components(self):
        for job_id in ('../逃逸', 'a/b', 'a\\b', 'a..b', '.'):
            with self.subTest(job_id=job_id):
                job = self.job()
                job['id'] = job_id
                with self.assertRaises(ValueError):
                    self.execute(job)

    def test_opening_records_loaded_runner_version(self):
        result = self.execute()
        opening = json.loads((Path(result['evidence_dir']) / 'opening.json').read_text(encoding='utf-8'))
        self.assertEqual(opening['runner_schema_version'], r.RUNNER_SCHEMA_VERSION)
        self.assertEqual(opening['runner_sha256'], r.RUNNER_SHA256)

    def test_nested_call_is_observed_and_blocks_completion(self):
        result = self.execute(self.job('nested'))
        self.assertEqual(result['status'], 'needs_review')
        self.assertTrue(result['nested_agents_requested_disabled'])
        self.assertNotIn('nested_agents_enabled', result)
        self.assertEqual(result['nested_agent_calls'], 1)
        self.assertEqual(result['nested_agent_call_details'][0]['tool'], 'wait')

    def test_thread_tool_calls_are_counted(self):
        items = [{'type': 'item.completed', 'item': {'id': 'x', 'type': 'mcp_tool_call',
                  'tool': 'mcp__codex_app__create_thread'}}]
        self.assertEqual(len(r.nested_calls(items)), 1)

    def test_completion_requires_exit_event_and_nonempty_report(self):
        for mode in ('nonzero', 'no_completion', 'no_report', 'empty', 'drift'):
            with self.subTest(mode=mode):
                self.output.unlink(missing_ok=True)
                self.input.write_text('原始冻结正文。', encoding='utf-8')
                self.assert_not_completed(self.execute(self.job(mode)))

    def test_timeout_terminates_process_group(self):
        started = time.monotonic()
        result = self.execute(self.job('timeout'), timeout=0.3)
        self.assert_not_completed(result)
        self.assertLess(time.monotonic() - started, 6)
        time.sleep(1.6)
        self.assertFalse((self.root / '残留子进程.txt').exists(), '超时后子进程仍写入标记')

    def test_retry_uses_distinct_evidence_without_overwrite(self):
        job = self.job('no_report')
        self.execute(job)
        before = {p: p.read_bytes() for p in self.evidence.rglob('*') if p.is_file() and p.suffix != '.jsonl'}
        self.execute(job)
        after = {p: p.read_bytes() for p in self.evidence.rglob('*') if p.is_file() and p.suffix != '.jsonl'}
        self.assertGreater(len(after), len(before))
        for path, content in before.items():
            self.assertEqual(after[path], content, str(path))

    def test_cli_budget_and_unique_durable_batch_ledgers(self):
        first = self.job('timeout')
        second = dict(first, id='第二项', output=str(self.root / '第二份报告.md'))
        tasks = self.root / '任务.json'
        tasks.write_text(json.dumps({'jobs': [first, second]}, ensure_ascii=False), encoding='utf-8')
        command = [sys.executable, str(MODULE), '--tasks', str(tasks), '--root', str(self.root),
                   '--evidence-dir', str(self.evidence), '--workers', '1', '--limit', '2',
                   '--timeout', '20', '--budget', '0.2']
        for _ in range(2):
            process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=6)
            self.assertEqual(process.returncode, 2, process.stderr)
        ledgers = list(self.evidence.glob('batch-*.jsonl'))
        self.assertEqual(len(ledgers), 2)
        for ledger in ledgers:
            rows = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()]
            self.assertEqual([row['status'] for row in rows], ['timeout', 'budget_exhausted'])

    def test_sigterm_cleans_cli_and_direct_execute_without_killing_other_processes(self):
        for mode in ('cli', 'direct'):
            with self.subTest(mode=mode):
                (self.root / '已启动.txt').unlink(missing_ok=True)
                self.output.unlink(missing_ok=True)
                job = self.job('delayed_report')
                if mode == 'cli':
                    tasks = self.root / '信号任务.json'
                    tasks.write_text(json.dumps({'jobs': [job]}, ensure_ascii=False), encoding='utf-8')
                    process = subprocess.Popen([sys.executable, str(MODULE), '--tasks', str(tasks),
                                                '--root', str(self.root), '--evidence-dir', str(self.evidence)],
                                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
                else:
                    process = self.start_direct(job)
                outside = self.root / ('非本任务-' + mode + '.txt')
                unrelated = subprocess.Popen([sys.executable, '-c',
                    'import time; from pathlib import Path; time.sleep(0.7); Path(' + repr(str(outside)) + ').write_text("完成", encoding="utf-8")'])
                try:
                    self.wait_for_invocation()
                    process.send_signal(signal.SIGTERM)
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 128 + signal.SIGTERM, (stdout, stderr))
                    unrelated.wait(timeout=3)
                    time.sleep(0.5)
                    self.assertFalse(self.output.exists(), '主进程退出后模型子进程仍写报告')
                    self.assertTrue(outside.exists(), '其他任务的进程被误杀')
                    receipts = [json.loads(p.read_text(encoding='utf-8')) for p in self.evidence.rglob('result.json')]
                    self.assertTrue(any(x['status'] == 'interrupted' for x in receipts))
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=3)
                    if unrelated.poll() is None:
                        unrelated.kill()
                        unrelated.wait(timeout=3)

    def test_same_output_is_locked_across_job_ids_evidence_dirs_and_symlink_alias(self):
        first = self.start_direct(self.job('delayed_report'))
        try:
            self.wait_for_invocation()
            alias = self.root / '路径别名'
            alias.symlink_to(self.root, target_is_directory=True)
            second = dict(self.job(), id='另一个任务', output=str(alias / self.output.name))
            result = r.execute(second, self.root, self.root / '另一证据目录', timeout=3)
            self.assertEqual(result['status'], 'busy')
            stdout, stderr = first.communicate(timeout=4)
            self.assertEqual(first.returncode, 0, stderr)
            self.assertEqual(json.loads(stdout)['status'], 'completed')
            original = self.output.read_bytes()
            again = r.execute(second, self.root, self.root / '另一证据目录', timeout=3)
            self.assertEqual(again['status'], 'unverified_output')
            self.assertEqual(self.output.read_bytes(), original)
        finally:
            if first.poll() is None:
                first.terminate()
                first.communicate(timeout=5)

    def test_cli_rejects_duplicate_ids_and_outputs_before_limit_or_launch(self):
        first = self.job()
        for duplicate in (dict(first, output=str(self.root / '不同输出.md')),
                          dict(first, id='不同编号', output=str(self.root / '子目录/../报告.md'))):
            with self.subTest(duplicate=duplicate['id']):
                tasks = self.root / '重复任务.json'
                tasks.write_text(json.dumps({'jobs': [first, duplicate]}, ensure_ascii=False), encoding='utf-8')
                process = subprocess.run([sys.executable, str(MODULE), '--tasks', str(tasks),
                                          '--root', str(self.root), '--evidence-dir', str(self.evidence),
                                          '--limit', '1'], capture_output=True, text=True, encoding='utf-8', timeout=3)
                self.assertEqual(process.returncode, 2)
                self.assertIn('重复', process.stderr)
                self.assertFalse((self.root / '已启动.txt').exists())
                self.assertFalse(list(self.evidence.glob('batch-*.jsonl')))

    def test_external_thread_execution_requires_main_signal_scope_and_restores_handlers(self):
        original = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        with ThreadPoolExecutor(max_workers=1) as pool:
            with self.assertRaises(RuntimeError):
                pool.submit(self.execute).result()
        self.assertFalse((self.root / '已启动.txt').exists())
        with r.signal_cleanup(), ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(self.execute).result()
        self.assertEqual(result['status'], 'completed')
        self.assertEqual({s: signal.getsignal(s) for s in original}, original)


if __name__ == '__main__':
    unittest.main()


@unittest.skipUnless(os.name == 'posix', '假执行器使用 POSIX 可执行脚本')
class EvalRunnerClaudeHost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.evidence = self.root / '执行证据'
        self.input = self.root / '输入.md'
        self.input.write_text('冻结正文。', encoding='utf-8')
        self.other = self.root / '答案.md'
        self.other.write_text('不得读取。', encoding='utf-8')
        self.output = self.root / '报告.md'
        bin_dir = self.root / 'bin'
        bin_dir.mkdir()
        fake = bin_dir / 'claude'
        fake.write_text('#!' + sys.executable + '\n' + FAKE_CLAUDE, encoding='utf-8')
        fake.chmod(0o755)
        env = patch.dict(os.environ, {'PATH': str(bin_dir) + os.pathsep + os.environ.get('PATH', '')})
        env.start()
        self.addCleanup(env.stop)

    def job(self, mode='success'):
        control = {'output': str(self.output), 'input': str(self.input), 'other': str(self.other),
                   'arguments': str(self.root / '参数.json'), 'mode': mode}
        return {'id': 'C01_V3_1', 'dataset': 'v3', 'prompt': json.dumps(control, ensure_ascii=False),
                'output': str(self.output), 'allowed_inputs': [str(self.input)],
                'input_hashes': {str(self.input): hashlib.sha256(self.input.read_bytes()).hexdigest()}}

    def execute(self, job):
        return r.execute(job, self.root, self.evidence, timeout=5, host='claude', model='fake-model')

    def test_success_records_model_cost_and_reads_then_resumes(self):
        job = self.job()
        first = self.execute(job)
        self.assertEqual(first['status'], 'completed', first)
        self.assertEqual(first['host'], 'claude')
        self.assertEqual(first['model_id'], 'claude-fake-1')
        self.assertEqual(first['usage']['total_cost_usd'], 0.25)
        self.assertEqual([x['tool'] for x in first['tool_reads']], ['Read'])
        arguments = json.loads((self.root / '参数.json').read_text(encoding='utf-8'))
        self.assertEqual(arguments[arguments.index('--model') + 1], 'fake-model')
        self.assertEqual(arguments[arguments.index('--tools') + 1], 'Read,Write,Glob,Grep')
        self.assertIn('--no-session-persistence', arguments)
        self.assertEqual(arguments[arguments.index('--permission-mode') + 1], 'dontAsk')
        self.assertNotIn('Bash', ' '.join(arguments))
        (self.root / '参数.json').unlink()
        second = self.execute(job)
        self.assertEqual(second['status'], 'resumed', second)
        self.assertFalse((self.root / '参数.json').exists(), '已完成项不应再次启动模型')

    def test_login_failure_is_not_completed_even_if_report_exists(self):
        result = self.execute(self.job('auth'))
        self.assertEqual(result['status'], 'needs_review', result)
        self.assertFalse(result['turn_completed'])

    def test_read_outside_frozen_inputs_blocks_completion(self):
        result = self.execute(self.job('outside_read'))
        self.assertEqual(result['status'], 'needs_review', result)
        self.assertEqual([x['path'] for x in result['outside_reads']], [str(self.other)])

    def test_nested_agent_call_blocks_completion(self):
        result = self.execute(self.job('nested'))
        self.assertEqual(result['status'], 'needs_review', result)
        self.assertEqual(result['nested_agent_calls'], 1)

    def test_unknown_host_is_rejected(self):
        with self.assertRaises(ValueError):
            r.execute(self.job(), self.root, self.evidence, host='other')
