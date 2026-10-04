"""每项启动全新临时Codex会话，保存实际事件；不代替独立报告或模型判分。"""
from pathlib import Path
import argparse
import concurrent.futures
import datetime
import hashlib
import json
import subprocess

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def execute(job, attempt):
    output = Path(job['output'])
    if output.exists():
        return {'job_id': job['id'], 'status': '已有报告未改'}
    checks = {p: digest(p) == h for p, h in job['input_hashes'].items()}
    if not all(checks.values()):
        return {'job_id': job['id'], 'status': '输入漂移', 'checks': checks}
    destination = BASE / 'CLI执行' / job['id'] / ('批次' + str(attempt))
    destination.mkdir(parents=True, exist_ok=False)
    metadata = {'job_id': job['id'], 'engine': 'codex exec --ephemeral',
                'independent_context': True, 'model_id': 'unknown',
                'nested_agents_enabled': False, 'memory_enabled': False,
                'started_at': utc(), 'prompt': job['prompt'], 'prompt_exact': True,
                'input_hashes': job['input_hashes'], 'checks': checks}
    (destination / '开读冻结.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    command = ['codex', 'exec', '--ephemeral', '--json', '--sandbox', 'workspace-write', '--disable', 'multi_agent', '--disable', 'memories', '-C', str(ROOT), '-']
    with (destination / 'events.jsonl').open('wb') as stdout, (destination / 'stderr.log').open('wb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stdout, stderr=stderr)
        try:
            process.communicate(job['prompt'].encode('utf-8'), timeout=600)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            returncode = 'timeout'
    events = []
    for line in (destination / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    metadata.update({'finished_at': utc(), 'returncode': returncode,
                     'thread_ids': [e['thread_id'] for e in events if e.get('type') == 'thread.started'],
                     'turn_completed': any(e.get('type') == 'turn.completed' for e in events),
                     'report_exists': output.is_file(),
                     'report_sha256': digest(output) if output.is_file() else None,
                     'checks_after': {p: digest(p) == h for p, h in job['input_hashes'].items()}})
    metadata['status'] = '完成' if returncode == 0 and metadata['turn_completed'] and metadata['report_exists'] and all(metadata['checks_after'].values()) else '待核'
    (destination / '执行结果.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return {k: metadata[k] for k in ['job_id', 'status', 'returncode', 'report_exists', 'turn_completed', 'report_sha256']}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tasks', type=Path, default=BASE / '审阅任务.json')
    parser.add_argument('--skip', nargs='*', default=[])
    parser.add_argument('--datasets', nargs='*')
    parser.add_argument('--workers', type=int, default=3, choices=[1, 2, 3])
    parser.add_argument('--reverse', action='store_true')
    parser.add_argument('--batch', type=int, default=2)
    args = parser.parse_args()
    jobs = json.loads(args.tasks.read_text(encoding='utf-8'))['jobs']
    jobs = [j for j in jobs if j['id'] not in args.skip and not Path(j['output']).exists()
            and (not args.datasets or j['dataset'] in args.datasets)]
    if args.reverse:
        jobs.reverse()
    print(json.dumps({'pending': len(jobs), 'workers': args.workers}, ensure_ascii=False), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(execute, j, args.batch): j for j in jobs}
        for future in concurrent.futures.as_completed(futures):
            job = futures[future]
            try:
                result = future.result()
            except Exception as error:
                result = {'job_id': job['id'], 'status': '执行器错误', 'error': str(error)}
            print(json.dumps(result, ensure_ascii=False), flush=True)
    print('本批调度结束；仍须核对原始报告、读取范围和逐项判分。', flush=True)

if __name__ == '__main__':
    main()
