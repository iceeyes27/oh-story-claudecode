#!/usr/bin/env python3
"""只冻结和计算显式评测证据，不调用模型，不判断小说质量。"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys


SCHEMA = 1
SEVERITIES = ('S1', 'S2', 'S3', 'S4')
PHASES = ('review', 'repair', 'repair_review')


class Invalid(ValueError):
    pass


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def dumps(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + '\n'


def load(path):
    try:
        value = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, UnicodeError, ValueError) as exc:
        raise Invalid('无法读取 JSON：' + str(path) + '；' + str(exc)) from exc
    if not isinstance(value, dict):
        raise Invalid('JSON 顶层必须是对象：' + str(path))
    return value


def identifier(value, label):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', value):
        raise Invalid(label + ' 必须只用字母、数字、点、下划线或连字符')
    if value in ('.', '..'):
        raise Invalid(label + ' 不得为目录跳转')
    return value


def required_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise Invalid(label + ' 必须是非空文本')
    return value


def list_field(value, label):
    if not isinstance(value, list):
        raise Invalid(label + ' 必须是列表')
    return value


def unique(items, field, label):
    result = {}
    for item in list_field(items, label):
        if not isinstance(item, dict):
            raise Invalid(label + ' 每项必须是对象')
        key = required_text(item.get(field), label + '.' + field)
        if key in result:
            raise Invalid(label + ' 重复：' + key)
        result[key] = item
    return result


def inside(root, relative, namespace=None):
    if not isinstance(relative, str) or '\\' in relative:
        raise Invalid('路径必须使用相对路径和 /')
    parts = PurePosixPath(relative)
    if parts.is_absolute() or '..' in parts.parts or not parts.parts:
        raise Invalid('路径越界：' + relative)
    if namespace and (len(parts.parts) < 2 or parts.parts[0] != namespace):
        raise Invalid('路径必须位于 ' + namespace + '/：' + relative)
    path = root / relative
    if any((root / Path(*parts.parts[:index])).is_symlink() for index in range(1, len(parts.parts) + 1)):
        raise Invalid('证据路径不得经过符号链接：' + relative)
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError as exc:
        raise Invalid('路径越界：' + relative) from exc
    return path


def readonly(path, data):
    with path.open('xb') as handle:
        handle.write(data)
    path.chmod(0o444)


def freeze(spec_path, destination):
    """新建独立证据目录；快照只读；存在的目录一律拒绝。"""
    spec_path = Path(spec_path).resolve()
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_symlink():
        raise Invalid('冻结目录已存在，不覆盖：' + str(destination))
    spec = load(spec_path)
    if spec.get('schema_version', SCHEMA) != SCHEMA:
        raise Invalid('不支持的配置版本')
    scope = spec.get('scope', 'full')
    if scope not in ('full', 'review_only'):
        raise Invalid('scope 只允许 full 或 review_only')
    inputs = unique(spec.get('inputs'), 'id', 'inputs')
    runs = unique(spec.get('runs'), 'id', 'runs')
    if not inputs or not runs:
        raise Invalid('inputs 和 runs 不能为空')
    frozen_inputs, contents = [], {}
    for item_id, item in inputs.items():
        identifier(item_id, 'input id')
        source = Path(required_text(item.get('path'), 'input path'))
        source = (spec_path.parent / source).resolve() if not source.is_absolute() else source.resolve()
        try:
            raw = source.read_bytes()
            lines = raw.decode('utf-8').splitlines(keepends=True)
        except (OSError, UnicodeError) as exc:
            raise Invalid('输入必须是可读 UTF-8 文件：' + str(source)) from exc
        selection = item.get('range')
        if selection is None:
            start, end = 1, len(lines)
        elif isinstance(selection, dict):
            start, end = selection.get('start_line'), selection.get('end_line')
            if type(start) is not int or type(end) is not int or start < 1 or end < start or end > len(lines):
                raise Invalid('输入行范围无效：' + item_id)
        else:
            raise Invalid('range 必须包含 start_line/end_line')
        selected = ''.join(lines[start - 1:end]).encode('utf-8')
        kind = required_text(item.get('kind'), 'input kind')
        audience = item.get('audience', 'reviewer')
        if audience not in ('reviewer', 'coordinator') or (kind == 'answer' and audience != 'coordinator'):
            raise Invalid('答案只允许 coordinator，audience 只能是 reviewer/coordinator')
        snapshot = 'inputs/' + item_id + source.suffix
        inside(destination, snapshot, 'inputs')
        frozen_inputs.append({'id': item_id, 'source_path': str(source), 'source_sha256': digest(raw),
                              'kind': kind, 'audience': audience,
                              'range': {'start_line': start, 'end_line': end},
                              'snapshot': snapshot, 'snapshot_sha256': digest(selected)})
        contents[snapshot] = selected
    frozen_runs, outputs = [], set()
    for run_id, run in runs.items():
        identifier(run_id, 'run id')
        output = required_text(run.get('output'), 'run output')
        inside(destination, output, 'outputs')
        if output in outputs:
            raise Invalid('输出路径重复：' + output)
        outputs.add(output)
        context = list_field(run.get('context'), 'run context')
        if not context or len(context) != len(set(context)):
            raise Invalid('context 必须非空且不得重复')
        for input_id in context:
            if input_id not in inputs or inputs[input_id].get('audience', 'reviewer') != 'reviewer':
                raise Invalid('context 含未声明或协调器专用输入：' + str(input_id))
        phase = run.get('phase', 'review')
        independent = run.get('independent_context')
        attempt = run.get('attempt')
        if phase not in PHASES or (type(independent) is not bool and independent != 'unknown'):
            raise Invalid('phase 或独立上下文标记无效：' + run_id)
        if type(attempt) is not int or attempt < 1:
            raise Invalid('attempt 必须是正整数：' + run_id)
        frozen_runs.append({'id': run_id, 'sample': required_text(run.get('sample'), 'sample'),
                            'role': required_text(run.get('role'), 'role'), 'attempt': attempt,
                            'phase': phase, 'context': context,
                            'prompt': required_text(run.get('prompt'), 'prompt'),
                            'independent_context': independent,
                            'model': run.get('model') or 'unknown', 'output': output})
    identities = [(r['sample'], r['role'], r['phase'], r['attempt']) for r in frozen_runs]
    if len(identities) != len(set(identities)):
        raise Invalid('样本、角色、阶段和次数的组合不得重复')
    manifest = {'schema_version': SCHEMA, 'kind': 'novel-kit-eval-freeze', 'created_at': now(),
                'label': spec.get('label', destination.name), 'scope': scope,
                'spec_source': str(spec_path), 'spec_sha256': digest(spec_path.read_bytes()),
                'inputs': frozen_inputs, 'runs': frozen_runs}
    created = False
    try:
        destination.mkdir(parents=True, exist_ok=False)
        created = True
        (destination / 'inputs').mkdir()
        (destination / 'outputs').mkdir()
        for relative, data in contents.items():
            readonly(destination / relative, data)
        for output in outputs:
            inside(destination, output, 'outputs').parent.mkdir(parents=True, exist_ok=True)
        readonly(destination / 'freeze-spec.json', spec_path.read_bytes())
        readonly(destination / 'manifest.json', dumps(manifest).encode('utf-8'))
    except Exception:
        # 仅清理由本次刚创建的目录，不接触任何已有目录。
        if created and destination.exists():
            shutil.rmtree(destination)
        raise
    return manifest


def manifest_at(root):
    manifest = load(root / 'manifest.json')
    if manifest.get('schema_version') != SCHEMA or manifest.get('kind') != 'novel-kit-eval-freeze':
        raise Invalid('不是受支持的冻结清单')
    return manifest


def runner_lock_placeholder(path):
    """兼容现有空锁和 Windows 单字节锁；不据此判断任务是否完成。"""
    def signature(metadata):
        return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_size,
                metadata.st_mtime_ns, metadata.st_ctime_ns)

    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size not in (0, 1):
            return False
        flags = (os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
                 | getattr(os, 'O_BINARY', 0))
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if signature(opened) != signature(before):
                return False
            content = os.read(descriptor, 2)
        finally:
            os.close(descriptor)
        after = path.lstat()
    except OSError:
        return False
    # 只核对扫描时可见状态；不保证核验后没有并发写入或路径替换。
    return signature(after) == signature(opened) and content in (b'', b'0')


def verify(evidence_dir, require_outputs=False):
    """核对完整源、实际快照及声明输出；不会修复或改写证据。"""
    root = Path(evidence_dir).resolve()
    manifest = manifest_at(root)
    problems, missing_outputs = [], []

    def check(path, expected, kind, label):
        try:
            current = digest(path.read_bytes())
        except OSError:
            current = None
        if current != expected:
            problems.append({'kind': kind, 'path': label, 'expected': expected, 'actual': current})

    check(Path(manifest['spec_source']), manifest['spec_sha256'], 'spec_drift', manifest['spec_source'])
    check(root / 'freeze-spec.json', manifest['spec_sha256'], 'spec_snapshot_drift', 'freeze-spec.json')
    for item in manifest['inputs']:
        check(Path(item['source_path']), item['source_sha256'], 'source_drift', item['source_path'])
        check(inside(root, item['snapshot'], 'inputs'), item['snapshot_sha256'], 'snapshot_drift', item['snapshot'])
    declared, declared_paths, runner_locks = set(), set(), set()
    for run in manifest['runs']:
        path = inside(root, run['output'], 'outputs')
        declared.add(run['output'])
        declared_paths.add(path)
        runner_locks.add(path.with_name('.' + path.name + '.eval-runner.lock'))
        if not path.is_file():
            missing_outputs.append(run['output'])
    if (root / 'outputs').exists():
        for path in (root / 'outputs').rglob('*'):
            relative = path.relative_to(root).as_posix()
            if path in runner_locks and path not in declared_paths:
                # 只排除已声明输出旁的合法普通锁文件；正式报告优先，保留互斥用的 inode。
                if runner_lock_placeholder(path):
                    continue
                problems.append({'kind': 'unexpected_output', 'path': relative})
                continue
            if path.is_file() or path.is_symlink():
                if relative not in declared or path.is_symlink():
                    problems.append({'kind': 'unexpected_output', 'path': relative})
    if (root / 'scores').exists():
        for path in sorted((root / 'scores').glob('*.json')):
            if path.name.endswith('.judgments.json'):
                continue
            saved = load(path)
            if saved.get('kind') != 'novel-kit-eval-score':
                problems.append({'kind': 'unexpected_score', 'path': path.relative_to(root).as_posix()})
                continue
            for relative, expected in saved.get('output_hashes', {}).items():
                check(inside(root, relative, 'outputs'), expected, 'scored_output_drift', relative)
            if saved.get('judgments_snapshot'):
                relative = saved['judgments_snapshot']
                check(inside(root, relative, 'scores'), saved['judgments_sha256'], 'judgments_drift', relative)
    return {'ok': not problems and (not require_outputs or not missing_outputs),
            'checked_at': now(), 'problems': problems, 'missing_outputs': missing_outputs}


def metric(numerator, denominator, missing=0):
    return {'numerator': numerator, 'denominator': denominator,
            'rate': numerator / denominator if denominator and not missing else None,
            'missing': missing}


def read_answers(root, manifest):
    answers = {}
    for item in manifest['inputs']:
        if item['kind'] != 'answer':
            continue
        answer = load(inside(root, item['snapshot'], 'inputs'))
        sample = required_text(answer.get('id'), '答案 id')
        if sample in answers:
            raise Invalid('冻结答案重复：' + sample)
        issues = unique(answer.get('应抓'), 'id', '应抓')
        for issue in issues.values():
            if issue.get('预期严重度') not in SEVERITIES:
                raise Invalid('预期严重度无效：' + issue['id'])
        protected = {}
        for index, item in enumerate(list_field(answer.get('不应报'), '不应报'), 1):
            protected_id = item.get('id') or sample + '-protected-' + str(index)
            if protected_id in protected:
                raise Invalid('保护项重复：' + protected_id)
            protected[protected_id] = item
        answers[sample] = {'issues': issues, 'protected': protected, 'group': answer.get('组')}
    return answers


def decision_rows(raw, key, expected, label, decision, report_text, missing):
    if raw is None:
        missing.append(label + '：缺失逐项判分表')
        rows = {}
    else:
        rows = unique(raw, key, label)
    if set(rows) - set(expected):
        raise Invalid(label + ' 含答案外编号：' + ', '.join(sorted(set(rows) - set(expected))))
    result = {}
    for item_id in expected:
        row = rows.get(item_id)
        if row is None or row.get(decision) is None:
            missing.append(label + '：缺失 ' + item_id)
            result[item_id] = None
            continue
        if type(row[decision]) is not bool:
            raise Invalid(label + ' 的 ' + decision + ' 必须为 true/false/null')
        required_text(row.get('reason'), label + ' reason')
        evidence = row.get('evidence', '')
        if not isinstance(evidence, str) or (row[decision] and not evidence):
            raise Invalid(label + ' 正向判断必须附原始报告证据')
        if evidence and report_text is not None and evidence not in report_text:
            raise Invalid(label + ' 证据不在原始报告中：' + item_id)
        if decision == 'detected':
            severity = row.get('severity')
            if (row[decision] and severity not in SEVERITIES) or (not row[decision] and severity is not None):
                raise Invalid(label + ' 严重度与检出标记不符：' + item_id)
        result[item_id] = row
    return result


def issue_metrics(answer, rows):
    issues = answer['issues']
    high = [i for i in issues if issues[i]['预期严重度'] in ('S1', 'S2')]
    return {
        'detected': metric(sum(bool(v and v['detected']) for v in rows.values()), len(issues),
                           sum(v is None for v in rows.values())),
        'severity_attainment': metric(sum(bool(rows.get(i) and rows[i].get('severity') in ('S1', 'S2')) for i in high),
                                      len(high), sum(rows.get(i) is None for i in high)),
    }


def combine_metrics(results, label):
    combined = dict(label)
    for field in ('detected', 'severity_attainment'):
        combined[field] = metric(sum(r[field]['numerator'] for r in results),
                                 sum(r[field]['denominator'] for r in results),
                                 sum(r[field]['missing'] for r in results))
    combined['false_positives'] = {key: sum(r['false_positives'][key] for r in results)
                                   for key in ('control_s1_s2', 'protected_reported', 'other_explicit', 'missing')}
    return combined


def display_metric(value):
    base = str(value['numerator']) + '/' + str(value['denominator'])
    if value['missing']:
        return base + '（缺失 ' + str(value['missing']) + ' 项，不计算率）'
    if not value['denominator']:
        return '不适用（分母为零）'
    return base + '（' + format(value['rate'], '.1%') + '）'


def summary(report):
    lines = ['# 评测证据汇总', '', '生成日期：' + report['created_at'], '',
             '声明验收范围：' + ('只评审阅' if report['scope'] == 'review_only' else '审阅与修正证据') + '。',
             '质量判断来源：模型对照，不代表作者亲自核验。工具只计算显式逐问题判分，不调用模型，不自动判断匹配。',
             '本汇总不宣称质量通过；L5 阅读体验、质量验收和正文采用仍由作者裁决。', '',
             '证据完整性：' + ('已收齐声明证据。' if report['evidence_complete'] else '未完成，存在缺失。'), '',
             '| 角色／次数 | 检出率 | S1/S2 定级达标率 | K组答案外S1/S2 | 保护项误报 | 其他显式误报 |',
             '|---|---|---|---|---|---|']
    for result in report['attempts']:
        fp = result['false_positives']
        lines.append('| ' + result['role'] + '／' + str(result['attempt']) + ' | ' + display_metric(result['detected'])
                     + ' | ' + display_metric(result['severity_attainment']) + ' | ' + str(fp['control_s1_s2'])
                     + ' | ' + str(fp['protected_reported']) + ' | ' + str(fp['other_explicit']) + ' |')
    lines += ['', '两次一致率按答案中的应抓问题逐项比较：检出判断相同含两次都未报；严重度一致要求未报或具体 S1–S4 完全相同。正向重合率为两次都检出／至少一次检出。', '']
    for result in report['consistency']:
        lines.append('- ' + result['role'] + '：检出一致 ' + display_metric(result['detection_agreement'])
                     + '；严重度一致 ' + display_metric(result['severity_agreement'])
                     + '；正向重合 ' + display_metric(result['positive_overlap']))
    lines += ['', '补充并集：同角色多次任一次检出，严重度取较严；并集不能代替逐次稳定性。', '']
    for result in report['unions']:
        fp = result['false_positives']
        lines.append('- ' + result['role'] + '：检出 ' + display_metric(result['detected'])
                     + '；定级达标 ' + display_metric(result['severity_attainment'])
                     + '；K组误报 ' + str(fp['control_s1_s2']) + '；保护项误报 ' + str(fp['protected_reported']))
    lines += ['', '修正效果与新错误、保护项误改单列：', '']
    for repair in report['repairs']:
        lines.append('- ' + repair['sample'] + '：原预期S1/S2问题解决 ' + display_metric(repair['resolved'])
                     + '；新增L1/L2问题 ' + str(repair['new_errors'])
                     + '（其中S1/S2 ' + str(repair['new_s1_s2_errors']) + '）；保护项误改 ' + str(repair['protected_changed']))
    if report['missing']:
        lines += ['', '缺失或未核验事项：', ''] + ['- ' + text for text in report['missing']]
    lines += ['', '每次原始报告、逐项判分、输出哈希和运行上下文见同名 JSON；当前数字只覆盖声明样本与执行，不能外推其他作品。', '']
    return '\n'.join(lines)


def score(evidence_dir, judgments_path, name='评分'):
    """消费协调器显式表；没有逐项判断时保留缺失，不把缺失算作未报。"""
    root = Path(evidence_dir).resolve()
    identifier(name, '评分名称') if name.isascii() else required_text(name, '评分名称')
    if '/' in name or '\\' in name or name in ('.', '..'):
        raise Invalid('评分名称不得含路径')
    targets = [inside(root, 'scores/' + name + suffix, 'scores') for suffix in ('.json', '.md', '.judgments.json')]
    if any(p.exists() or p.is_symlink() for p in targets):
        raise Invalid('评分文件已存在，不覆盖；请使用新名称')
    integrity = verify(root)
    if not integrity['ok']:
        raise Invalid('冻结来源、快照或输出范围已变化，先另开证据版本：' + dumps(integrity['problems']))
    manifest = manifest_at(root)
    table = load(judgments_path)
    if table.get('schema_version') != SCHEMA or table.get('quality_judgment_source') != 'model_comparison':
        raise Invalid('判分表必须显式标 schema_version=1、quality_judgment_source=model_comparison')
    answers = read_answers(root, manifest)
    declared = {r['id']: r for r in manifest['runs']}
    tables = unique(table.get('runs', []), 'run_id', 'runs 判分')
    if any(run_id not in declared or declared[run_id]['phase'] != 'review' for run_id in tables):
        raise Invalid('runs 判分只允许已声明的 review run_id')
    missing, results, judgments, output_hashes = [], [], {}, {}
    report_texts = {}
    for run in manifest['runs']:
        output = inside(root, run['output'], 'outputs')
        if output.is_file():
            raw = output.read_bytes()
            output_hashes[run['output']] = digest(raw)
            try:
                report_texts[run['id']] = raw.decode('utf-8')
            except UnicodeError as exc:
                raise Invalid('报告必须为 UTF-8：' + run['output']) from exc
        else:
            missing.append('缺失输出：' + run['output'])
            report_texts[run['id']] = None
        if run['phase'] in ('review', 'repair_review') and run['independent_context'] is not True:
            missing.append(run['id'] + '：未确认独立上下文')
        if run['phase'] != 'review':
            continue
        if run['sample'] not in answers:
            missing.append(run['id'] + '：缺失冻结答案 ' + run['sample'])
            continue
        answer = answers[run['sample']]
        raw_table = tables.get(run['id'], {})
        if not raw_table.get('execution_date'):
            missing.append(run['id'] + '：缺失实际执行日期')
        issue_rows = decision_rows(raw_table.get('issues'), 'issue_id', answer['issues'], run['id'] + ' 应抓',
                                   'detected', report_texts[run['id']], missing)
        protected_rows = decision_rows(raw_table.get('protected'), 'protected_id', answer['protected'],
                                       run['id'] + ' 保护项', 'reported', report_texts[run['id']], missing)
        extra = raw_table.get('extra_findings')
        if extra is None:
            missing.append(run['id'] + '：缺失答案外问题判分（无时也须填 []）')
            extra_rows = {}
        else:
            extra_rows = unique(extra, 'id', run['id'] + ' 答案外问题')
            for item in extra_rows.values():
                required_text(item.get('reason'), '答案外问题 reason')
                evidence = required_text(item.get('evidence'), '答案外问题 evidence')
                if item.get('severity') not in SEVERITIES or type(item.get('false_positive')) is not bool:
                    raise Invalid('答案外问题需显式严重度和 false_positive 布尔判断')
                if report_texts[run['id']] is not None and evidence not in report_texts[run['id']]:
                    raise Invalid('答案外问题证据不在原始报告')
        result = {'run_id': run['id'], 'sample': run['sample'], 'role': run['role'], 'attempt': run['attempt']}
        result.update(issue_metrics(answer, issue_rows))
        result['false_positives'] = {
            'control_s1_s2': sum(i['severity'] in ('S1', 'S2') for i in extra_rows.values()) if answer['group'] == 'K' else 0,
            'protected_reported': sum(bool(i and i['reported']) for i in protected_rows.values()),
            'other_explicit': sum(i['false_positive'] for i in extra_rows.values()) if answer['group'] != 'K' else 0,
            'missing': sum(i is None for i in protected_rows.values()) + (extra is None),
        }
        judgments[run['id']] = (issue_rows, protected_rows, extra_rows)
        results.append(result)
    attempts = []
    groups = defaultdict(list)
    by_role_sample = defaultdict(list)
    for result in results:
        groups[(result['role'], result['attempt'])].append(result)
        by_role_sample[(result['role'], result['sample'])].append(result)
    for (role, attempt), values in sorted(groups.items()):
        attempts.append(combine_metrics(values, {'role': role, 'attempt': attempt}))
    union_by_role, consistency_by_role = defaultdict(list), defaultdict(list)
    for (role, sample), values in sorted(by_role_sample.items()):
        values.sort(key=lambda r: r['attempt'])
        answer = answers[sample]
        union_rows, union_protected, union_extra = {}, {}, {}
        for item_id in answer['issues']:
            rows = [judgments[r['run_id']][0][item_id] for r in values]
            known = [r for r in rows if r and r['detected']]
            union_rows[item_id] = min(known, key=lambda r: SEVERITIES.index(r['severity'])) if known else (None if None in rows else {'detected': False, 'severity': None})
        for item_id in answer['protected']:
            rows = [judgments[r['run_id']][1][item_id] for r in values]
            union_protected[item_id] = any(r and r['reported'] for r in rows)
        for value in values:
            for item_id, item in judgments[value['run_id']][2].items():
                if item_id not in union_extra or SEVERITIES.index(item['severity']) < SEVERITIES.index(union_extra[item_id]['severity']):
                    union_extra[item_id] = item
        union = issue_metrics(answer, union_rows)
        # 并集有已检出的已知项仍保留缺失标记，不隐藏不完整执行。
        union['detected']['missing'] = sum(any(judgments[v['run_id']][0][i] is None for v in values) for i in answer['issues'])
        union['severity_attainment']['missing'] = sum(any(judgments[v['run_id']][0][i] is None for v in values) for i in answer['issues'] if answer['issues'][i]['预期严重度'] in ('S1', 'S2'))
        for field in ('detected', 'severity_attainment'):
            union[field] = metric(union[field]['numerator'], union[field]['denominator'], union[field]['missing'])
        union['false_positives'] = {'control_s1_s2': sum(i['severity'] in ('S1', 'S2') for i in union_extra.values()) if answer['group'] == 'K' else 0,
                                    'protected_reported': sum(union_protected.values()),
                                    'other_explicit': sum(i['false_positive'] for i in union_extra.values()) if answer['group'] != 'K' else 0,
                                    'missing': sum(r['false_positives']['missing'] for r in values)}
        union_by_role[role].append(union)
        if len(values) < 2:
            if role == 'copy-editor':
                missing.append(sample + '／copy-editor：缺失第二次独立执行，一致率不可计算')
            continue
        first, second = [judgments[v['run_id']][0] for v in values[:2]]
        unknown = sum(first[i] is None or second[i] is None for i in answer['issues'])
        valid = [i for i in answer['issues'] if first[i] is not None and second[i] is not None]
        consistency_by_role[role].append({
            'detection_agreement': metric(sum(first[i]['detected'] == second[i]['detected'] for i in valid), len(answer['issues']), unknown),
            'severity_agreement': metric(sum(first[i].get('severity') == second[i].get('severity') for i in valid), len(answer['issues']), unknown),
            'positive_overlap': metric(sum(first[i]['detected'] and second[i]['detected'] for i in valid),
                                       sum(first[i]['detected'] or second[i]['detected'] for i in valid), unknown),
        })
    consistency = []
    for role, values in sorted(consistency_by_role.items()):
        result = {'role': role, 'compared_attempts': '每样本前两次'}
        for field in ('detection_agreement', 'severity_agreement', 'positive_overlap'):
            result[field] = metric(sum(v[field]['numerator'] for v in values), sum(v[field]['denominator'] for v in values), sum(v[field]['missing'] for v in values))
        consistency.append(result)
    repairs = score_repairs(table, declared, answers, report_texts, missing) if manifest.get('scope', 'full') == 'full' else []
    if manifest.get('scope') == 'review_only' and table.get('repairs'):
        raise Invalid('review_only 范围不接收修正判分；请另开 full 证据')
    report = {'schema_version': SCHEMA, 'kind': 'novel-kit-eval-score', 'created_at': now(),
              'quality_judgment_source': 'model_comparison', 'quality_acceptance': 'not_determined',
              'scope': manifest.get('scope', 'full'),
              'evidence_complete': not missing, 'missing': missing, 'runs': results, 'attempts': attempts,
              'consistency': consistency,
              'unions': [combine_metrics(v, {'role': k, 'supplemental_only': True}) for k, v in sorted(union_by_role.items())],
              'repairs': repairs, 'output_hashes': output_hashes,
              'judgments_snapshot': 'scores/' + name + '.judgments.json',
              'judgments_sha256': digest(Path(judgments_path).read_bytes())}
    (root / 'scores').mkdir(exist_ok=True)
    readonly(targets[2], Path(judgments_path).read_bytes())
    readonly(targets[0], dumps(report).encode('utf-8'))
    readonly(targets[1], summary(report).encode('utf-8'))
    return report


def score_repairs(table, declared, answers, report_texts, missing):
    planned = [r for r in declared.values() if r['phase'] == 'repair']
    rereads = [r for r in declared.values() if r['phase'] == 'repair_review']
    raw = list_field(table.get('repairs', []), 'repairs')
    if not planned:
        missing.append('未声明修正副本运行，修正证据缺失')
    if not rereads:
        missing.append('未声明独立修后盲读运行，修后证据缺失')
    repairs, seen = [], set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise Invalid('修正判分每项必须为对象')
        repair_id, review_id = entry.get('repair_run_id'), entry.get('review_run_id')
        if repair_id in seen:
            raise Invalid('修正判分重复：' + str(repair_id))
        seen.add(repair_id)
        if repair_id not in declared or review_id not in declared or declared[repair_id]['phase'] != 'repair' or declared[review_id]['phase'] != 'repair_review':
            raise Invalid('修正判分需声明 repair 与 repair_review 运行')
        sample = entry.get('sample')
        if sample not in answers or declared[repair_id]['sample'] != sample or declared[review_id]['sample'] != sample:
            raise Invalid('修正判分样本与冻结声明不符')
        if not entry.get('execution_date'):
            missing.append(str(repair_id) + '：缺失修正对照日期')
        answer = answers[sample]
        expected = {i: v for i, v in answer['issues'].items() if v['预期严重度'] in ('S1', 'S2')}
        rows = decision_rows(entry.get('issues'), 'issue_id', expected, str(repair_id) + ' 修正结果',
                             'resolved', report_texts[review_id], missing)
        protected = decision_rows(entry.get('protected'), 'protected_id', answer['protected'],
                                  str(repair_id) + ' 保护项误改', 'changed', report_texts[review_id], missing)
        errors = entry.get('new_errors')
        if errors is None:
            missing.append(str(repair_id) + '：缺失新增L1/L2错误判分（无时须填 []）')
            errors = []
        errors = unique(errors, 'id', '修后新增错误')
        for error in errors.values():
            if error.get('layer') not in ('L1', 'L2') or error.get('severity') not in SEVERITIES:
                raise Invalid('修后新增错误需显式 L1/L2 和严重度')
            evidence = required_text(error.get('evidence'), '新增错误 evidence')
            required_text(error.get('reason'), '新增错误 reason')
            if report_texts[review_id] is not None and evidence not in report_texts[review_id]:
                raise Invalid('新增错误证据不在修后报告')
        repairs.append({'sample': sample, 'repair_run_id': repair_id, 'review_run_id': review_id,
                        'resolved': metric(sum(bool(r and r['resolved']) for r in rows.values()), len(expected), sum(r is None for r in rows.values())),
                        'new_errors': len(errors), 'new_s1_s2_errors': sum(r['severity'] in ('S1', 'S2') for r in errors.values()),
                        'protected_changed': sum(bool(r and r['changed']) for r in protected.values()),
                        'protected_missing': sum(r is None for r in protected.values())})
    for run in planned:
        if run['id'] not in seen:
            missing.append(run['id'] + '：缺失修正逐项判分')
    used_reviews = {r['review_run_id'] for r in repairs}
    for run in rereads:
        if run['id'] not in used_reviews:
            missing.append(run['id'] + '：缺失修后盲读对照判分')
    return repairs


def main(argv=None):
    parser = argparse.ArgumentParser(description='冻结、核对和计算显式评测证据；不自动认定质量通过。')
    sub = parser.add_subparsers(dest='command', required=True)
    command = sub.add_parser('freeze', help='只创建新的证据目录')
    command.add_argument('--spec', required=True)
    command.add_argument('--dest', required=True)
    command = sub.add_parser('verify', help='只核对证据')
    command.add_argument('directory')
    command.add_argument('--require-outputs', action='store_true')
    command = sub.add_parser('score', help='计算协调器逐项判分表')
    command.add_argument('directory')
    command.add_argument('--judgments', required=True)
    command.add_argument('--name', default='评分')
    args = parser.parse_args(argv)
    try:
        if args.command == 'freeze':
            result = freeze(args.spec, args.dest)
            print(dumps({'manifest': str(Path(args.dest).absolute() / 'manifest.json'), 'runs': len(result['runs'])}), end='')
            return 0
        if args.command == 'verify':
            result = verify(args.directory, args.require_outputs)
            print(dumps(result), end='')
            return 0 if result['ok'] else 1
        result = score(args.directory, args.judgments, args.name)
        print(dumps({'evidence_complete': result['evidence_complete'], 'quality_acceptance': result['quality_acceptance'],
                     'missing': result['missing'], 'summary': str(Path(args.directory).resolve() / 'scores' / (args.name + '.md'))}), end='')
        return 0
    except (Invalid, OSError) as exc:
        print('评测证据错误：' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
