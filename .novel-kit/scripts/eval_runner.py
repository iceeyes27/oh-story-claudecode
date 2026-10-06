#!/usr/bin/env python3
"""有界、可恢复的独立评测执行器；不替代原始审阅和逐项判分。"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import threading
import time
import uuid


RUNNER_SCHEMA_VERSION = 4
HOSTS = ("codex", "claude")
CLAUDE_AGENT_TOOLS = {"Agent", "Task", "SendMessage", "TeamCreate", "TaskCreate"}
RUNNER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
_signal_scope_depth = 0
_signal_number = 0


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def report_present(output):
    try:
        return output.is_file() and bool(output.read_bytes().strip())
    except OSError:
        return False


def input_checks(job):
    result = {}
    for name, expected in job['input_hashes'].items():
        try:
            result[name] = digest(name) == expected
        except OSError:
            result[name] = False
    return result


@contextmanager
def signal_cleanup():
    """主线程安装临时处理器；每项只清理自己持有的 Popen 进程组。"""
    global _signal_scope_depth, _signal_number
    if threading.current_thread() is not threading.main_thread():
        if not _signal_scope_depth:
            raise RuntimeError('在线程中调用 execute 前，须在主线程进入 signal_cleanup()')
        yield
        return
    outermost = _signal_scope_depth == 0
    previous = {}
    if outermost:
        _signal_number = 0

        def request_stop(number, frame):
            # 处理器只设置标记，不在异步信号中等待锁或启动进程。
            global _signal_number
            _signal_number = number

        for number in (signal.SIGTERM, signal.SIGINT):
            previous[number] = signal.signal(number, request_stop)
    _signal_scope_depth += 1
    try:
        yield
    finally:
        _signal_scope_depth -= 1
        if outermost:
            for number, handler in previous.items():
                signal.signal(number, handler)
            if _signal_number:
                raise SystemExit(128 + _signal_number)


@contextmanager
def job_lock(path):
    """操作系统负责中断后释放锁；保留锁文件不代表仍被占用。"""
    with path.open('a+b') as stream:
        if os.name == 'nt':
            import msvcrt
            if stream.tell() == 0:
                stream.write(b'0')
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def receipt_matches(receipt, job, output, attempt):
    try:
        events = attempt / 'events.jsonl'
        opening_path = attempt / 'opening.json'
        opening = json.loads(opening_path.read_text(encoding='utf-8'))
        return (receipt['status'] == 'completed' and receipt['returncode'] == 0
                and receipt['turn_completed'] is True
                and receipt.get('nested_agent_calls') == 0
                and receipt['prompt'] == job['prompt']
                and receipt['input_hashes'] == job['input_hashes']
                and receipt['output'] == str(output)
                and opening['prompt'] == job['prompt']
                and opening['input_hashes'] == job['input_hashes']
                and opening['checks_before'] == {p: True for p in job['input_hashes']}
                and opening['output'] == str(output)
                and digest(opening_path) == receipt['opening_sha256']
                and receipt['checks_after'] == {p: True for p in job['input_hashes']}
                and report_present(output)
                and digest(output) == receipt['report_sha256']
                and digest(events) == receipt['events_sha256'])
    except (KeyError, OSError, TypeError, ValueError):
        return False


def nested_calls(events):
    """按事件编号去重，区分禁用请求与宿主实际出现的调用。"""
    found = {}
    agent_tools = {'spawn_agent', 'followup_task', 'send_message', 'wait_agent',
                   'interrupt_agent', 'list_agents', 'create_thread', 'fork_thread',
                   'send_message_to_thread', 'wait_threads'}
    for index, event in enumerate(events):
        item = event.get('item')
        if not isinstance(item, dict):
            continue
        kind = str(item.get('type', ''))
        tool = str(item.get('tool', item.get('name', 'unknown')))
        short_tool = tool.replace('__', '.').rsplit('.', 1)[-1]
        if kind.startswith('collab_') or (kind.endswith('tool_call') and short_tool in agent_tools):
            key = item.get('id') or 'event-' + str(index)
            found[key] = {'item_id': key, 'type': kind, 'tool': tool}
    return list(found.values())


def claude_binary(explicit=None):
    """优先显式路径或 PATH；桌面应用内置的 CLI 取最新版本目录。"""
    if explicit:
        return str(explicit)
    found = shutil.which('claude')
    if found:
        return found
    base = Path.home() / 'Library/Application Support/Claude/claude-code'
    candidates = sorted(base.glob('*/*/claude.app/Contents/MacOS/claude'),
                        key=lambda path: [int(x) if x.isdigit() else 0 for x in path.parts[-6].split('.')])
    if candidates:
        return str(candidates[-1])
    raise FileNotFoundError('找不到 claude 命令；用 --claude-bin 指定')


def claude_command(binary, root, model):
    """只开放读写所需工具；dontAsk 把未列入的一律拒绝，不会卡在授权提示。"""
    return [binary, '-p', '--output-format', 'stream-json', '--verbose', '--model', model,
            '--no-session-persistence', '--permission-mode', 'dontAsk',
            '--tools', 'Read,Write,Glob,Grep', '--allowedTools', 'Read', 'Write', 'Glob', 'Grep',
            '--disable-slash-commands', '--strict-mcp-config', '--add-dir', str(root)]


def claude_analysis(events, allowed, output):
    """从 stream-json 取完成标记、嵌套代理调用、越权读取和成本；返回字段并入结果。"""
    allowed = {str(Path(p).resolve()) for p in allowed} | {str(Path(output).resolve())}
    nested, outside, reads = {}, [], []
    init = next((e for e in events if e.get('type') == 'system' and e.get('subtype') == 'init'), {})
    final = next((e for e in reversed(events) if e.get('type') == 'result'), None)
    for index, event in enumerate(events):
        if event.get('type') != 'assistant':
            continue
        content = (event.get('message') or {}).get('content')
        for block in content if isinstance(content, list) else []:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            tool, args = str(block.get('name', 'unknown')), block.get('input') or {}
            if tool in CLAUDE_AGENT_TOOLS:
                key = block.get('id') or 'event-' + str(index)
                nested[key] = {'item_id': key, 'type': 'tool_use', 'tool': tool}
            target = args.get('file_path') or args.get('path')
            if tool in ('Read', 'Glob', 'Grep') and target:
                resolved = str(Path(target).resolve())
                reads.append({'tool': tool, 'path': target})
                # Read 只能读冻结输入；Glob/Grep 只记录，供事后核对读取范围。
                if tool == 'Read' and resolved not in allowed:
                    outside.append({'tool': tool, 'path': target})
    return {'turn_completed': bool(final) and final.get('is_error') is False and final.get('subtype') == 'success',
            'nested': list(nested.values()), 'outside_reads': outside, 'tool_reads': reads,
            'model_id': init.get('model', 'unknown'),
            'usage': {k: final.get(k) for k in ('num_turns', 'duration_ms', 'total_cost_usd', 'usage') if final and k in final}}


def terminate(process):
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        if os.name == 'nt':
            process.kill()
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        process.wait(timeout=5)
    finally:
        # 组长可能先退出，但它派生的子进程仍可能忽略 SIGTERM。
        if os.name != 'nt':
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def execute(job, root, evidence_dir, timeout=180, command=None, host='codex', model='opus', claude_bin=None):
    if host not in HOSTS:
        raise ValueError('host 只能是 ' + '／'.join(HOSTS))
    with signal_cleanup():
        return _locked_execute(job, root, evidence_dir, timeout, command, host, model, claude_bin)


def _locked_execute(job, root, evidence_dir, timeout, command, host, model, claude_bin):
    root, evidence_dir = Path(root).resolve(), Path(evidence_dir).resolve()
    job_id = job.get('id', '')
    if not job_id or '..' in job_id or job_id == '.' or any(c in job_id for c in '/\\\r\n'):
        raise ValueError('任务编号不得为空或包含路径分隔符')
    if timeout <= 0 or not isinstance(job.get('prompt'), str) or not job['prompt'].strip():
        raise ValueError('超时和提示无效')
    if not job.get('input_hashes') or set(job.get('allowed_inputs', [])) != set(job['input_hashes']):
        raise ValueError('实际输入与冻结哈希必须完整对应')
    output = Path(job['output']).resolve()
    output.relative_to(root)
    job_dir = evidence_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    # 锁跟随实际输出目标，不能随任务编号或证据目录分开。
    output_lock = output.with_name('.' + output.name + '.eval-runner.lock')
    try:
        with job_lock(output_lock), job_lock(job_dir / '.lock'):
            return _execute(job, root, job_dir, output, timeout, command, host, model, claude_bin)
    except BlockingIOError:
        return {'job_id': job_id, 'status': 'busy'}


def _execute(job, root, job_dir, output, timeout, command, host='codex', model='opus', claude_bin=None):
    attempt = job_dir / ('run-' + uuid.uuid4().hex)
    attempt.mkdir()
    checks = input_checks(job)
    metadata = {'job_id': job['id'], 'started_at': stamp(), 'engine': 'codex exec --ephemeral' if host == 'codex' else 'claude -p --no-session-persistence',
                'host': host,
                'runner_schema_version': RUNNER_SCHEMA_VERSION, 'runner_sha256': RUNNER_SHA256,
                'model_id': model if host == 'claude' else 'unknown', 'independent_context': True,
                'nested_agents_requested_disabled': True, 'memory_requested_disabled': True,
                'prompt': job['prompt'], 'input_hashes': job['input_hashes'],
                'output': str(output), 'checks_before': checks, 'timeout_seconds': timeout,
                'evidence_dir': str(attempt)}
    save(attempt / 'opening.json', metadata)
    metadata['opening_sha256'] = digest(attempt / 'opening.json')

    def finish(status, **fields):
        metadata.update(fields)
        metadata.update(status=status, finished_at=stamp())
        save(attempt / 'result.json', metadata)
        return metadata

    if _signal_number:
        return finish('interrupted', signal_number=_signal_number)
    if not all(checks.values()):
        return finish('input_drift')
    if output.exists():
        for candidate in sorted(job_dir.glob('run-*/result.json')):
            try:
                receipt = json.loads(candidate.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if receipt_matches(receipt, job, output, candidate.parent):
                return finish('resumed', verified_receipt=str(candidate),
                              report_sha256=digest(output), turn_completed=True, returncode=0,
                              nested_agent_calls=0, nested_agent_call_details=[])
        return finish('unverified_output', note='保留未通过凭据核验的已有报告。旧执行器缺开读记录哈希也须另行核验，不事后补造，不覆盖或冒认成功。')
    output.parent.mkdir(parents=True, exist_ok=True)
    if command:
        args, cwd = command, root
    elif host == 'claude':
        try:
            args = claude_command(claude_binary(claude_bin), root, model)
        except FileNotFoundError as error:
            return finish('execution_error', error=str(error))
        # 在证据目录运行，避免加载书稿的 CLAUDE.md、本地 Hook 与记忆，保持独立上下文。
        cwd = attempt
    else:
        args = ['codex', 'exec', '--ephemeral', '--json', '--sandbox', 'workspace-write',
                '--disable', 'multi_agent', '--disable', 'memories', '-C', str(root), '-']
        cwd = root
    timed_out = False
    try:
        with (attempt / 'events.jsonl').open('xb') as stdout, (attempt / 'stderr.log').open('xb') as stderr:
            process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr,
                                       cwd=cwd, start_new_session=os.name != 'nt')
            try:
                deadline = time.monotonic() + timeout
                payload = job['prompt'].encode('utf-8')
                while True:
                    if _signal_number:
                        terminate(process)
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        terminate(process)
                        break
                    try:
                        process.communicate(payload, timeout=min(remaining, 0.1))
                        break
                    except subprocess.TimeoutExpired:
                        payload = None
            except BaseException:
                terminate(process)
                raise
    except OSError as error:
        return finish('execution_error', error=str(error))
    events, malformed = [], 0
    for line in (attempt / 'events.jsonl').read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            value = json.loads(line)
            if isinstance(value, dict):
                events.append(value)
            else:
                malformed += 1
        except ValueError:
            malformed += 1
    after = input_checks(job)
    present = report_present(output)
    extra = {}
    if host == 'claude' and not command:
        analysis = claude_analysis(events, job['allowed_inputs'], output)
        completed, nested = analysis['turn_completed'], analysis['nested']
        extra = {'model_id': analysis['model_id'], 'outside_reads': analysis['outside_reads'],
                 'tool_reads': analysis['tool_reads'], 'usage': analysis['usage']}
    else:
        completed = any(e.get('type') == 'turn.completed' for e in events)
        nested = nested_calls(events)
    successful = (not _signal_number and not timed_out and process.returncode == 0 and completed and present
                  and all(after.values()) and not malformed and not nested and not extra.get('outside_reads'))
    return finish('interrupted' if _signal_number else 'completed' if successful else 'timeout' if timed_out else 'needs_review',
                  signal_number=_signal_number or None,
                  returncode=process.returncode, turn_completed=completed, checks_after=after,
                  report_exists=present, report_sha256=digest(output) if present else None,
                  events_sha256=digest(attempt / 'events.jsonl'), malformed_event_lines=malformed,
                  nested_agent_calls=len(nested), nested_agent_call_details=nested,
                  thread_ids=[e['thread_id'] for e in events if e.get('type') == 'thread.started' and 'thread_id' in e],
                  **extra)


def validate_task_targets(jobs):
    """在筛选或启动任何任务前拒绝重复编号和同一实际报告目标。"""
    identifiers, outputs = set(), {}
    for job in jobs:
        job_id = job['id']
        output = Path(job['output']).resolve()
        if job_id in identifiers:
            raise ValueError('重复任务编号：' + str(job_id))
        if output in outputs:
            raise ValueError('重复报告目标：' + str(output) + '；任务 ' + str(outputs[output]) + ' 与 ' + str(job_id))
        identifiers.add(job_id)
        outputs[output] = job_id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tasks', type=Path, required=True)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--evidence-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=180)
    parser.add_argument('--workers', type=int, choices=(1, 2, 3), default=3)
    parser.add_argument('--limit', type=int, default=3)
    parser.add_argument('--budget', type=float, default=600)
    parser.add_argument('--datasets', nargs='*')
    parser.add_argument('--skip', nargs='*', default=[])
    parser.add_argument('--host', choices=HOSTS, default='codex', help='codex 沿用 codex exec；claude 用 claude -p，写入成本与读取记录')
    parser.add_argument('--model', default='opus', help='仅 --host claude：模型别名或完整名称')
    parser.add_argument('--claude-bin', type=Path, default=None, help='仅 --host claude：claude 可执行文件；默认取 PATH 或桌面应用内置版本')
    args = parser.parse_args()
    if args.limit < 1 or args.budget <= 0:
        parser.error('limit 和 budget 必须为正数')
    jobs = json.loads(args.tasks.read_text(encoding='utf-8'))['jobs']
    try:
        validate_task_targets(jobs)
    except (KeyError, TypeError, ValueError) as error:
        parser.error(str(error))
    jobs = [j for j in jobs if j['id'] not in args.skip and (not args.datasets or j['dataset'] in args.datasets)]
    # 已有输出也经过凭据核验；调用者可明确 skip 历史已完成项。
    jobs = jobs[:args.limit]
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.budget
    ledger = args.evidence_dir / ('batch-' + uuid.uuid4().hex + '.jsonl')

    def run(job):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {'job_id': job['id'], 'status': 'budget_exhausted'}
        try:
            return execute(job, args.root, args.evidence_dir, min(args.timeout, remaining),
                           host=args.host, model=args.model, claude_bin=args.claude_bin)
        except Exception as error:
            return {'job_id': job['id'], 'status': 'execution_error', 'error': str(error)}

    results = []
    print(json.dumps({'scheduled': len(jobs), 'workers': args.workers, 'ledger': str(ledger)}, ensure_ascii=False), flush=True)
    with signal_cleanup(), ledger.open('x', encoding='utf-8') as stream, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            stream.write(json.dumps(result, ensure_ascii=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
            print(json.dumps({k: result[k] for k in ('job_id', 'status', 'evidence_dir') if k in result}, ensure_ascii=False), flush=True)
    return 0 if all(r['status'] in ('completed', 'resumed') for r in results) else 2


if __name__ == '__main__':
    raise SystemExit(main())
