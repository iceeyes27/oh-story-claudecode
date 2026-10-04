#!/usr/bin/env python3
"""Small, local workflow helpers. Markdown owns scene state; journals own recovery only."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

STATE = '追蹤/場景狀態.md'
STATES = {'未開始', '撰寫中', '自動審閱中', '待審', '已通過', '待復核'}
STATE_DISPLAY = {'未開始': '未开始', '撰寫中': '撰写中', '自動審閱中': '自动审阅中',
                 '待審': '待审', '已通過': '已通过', '待復核': '待复核'}
STATE_CANONICAL = {**{value: key for key, value in STATE_DISPLAY.items()}, **{key: key for key in STATES}}
SCENE = re.compile(r'草稿/第(\d{3,})章/場景(\d{2,})\.md')
CHAPTER = re.compile(r'正文/第(\d{3,})章\.md')
# Written only through atomic() by the commands below; re.I because Windows ignores extension case.
TOOL_OWNED = re.compile(r'追蹤/場景狀態\.md|審閱/採用/.+|審閱/修訂/[^/]+/任務\.json|導入/清單\.json', re.I)
REVIEWERS = {
    '完整': {'copy-editor', 'consistency-checker', 'character-reviewer', 'prose-reviewer', 'structure-reviewer'},
    '文字': {'copy-editor', 'consistency-checker'},
    '章節': {'copy-editor', 'consistency-checker', 'structure-reviewer'},
}


class Invalid(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def read(path):
    return path.read_bytes() if path.exists() else None


def text(path):
    # Never rely on the locale encoding (GBK/cp950 on Chinese Windows).
    return path.read_text(encoding='utf-8')


def load(path):
    return json.loads(text(path))


def dump(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.novel-tmp-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def inside(root, name):
    require(isinstance(name, str) and name and '\x00' not in name, '路徑不可空白')
    p = Path(name)
    p = p if p.is_absolute() else root / p
    require('..' not in p.parts, '不接受含 .. 的路徑')
    require(p != root and root in p.parents, '路徑必須位於專案內')
    # Reject symlink aliases even if they happen to resolve back inside the project.
    require(not any(x.is_symlink() for x in [p, *p.parents] if x != root and root in x.parents), '不接受符號連結路徑')
    require(p == p.resolve(), '路徑必須是專案內的標準路徑')
    return p


def outside(root, name):
    """True only for absolute paths verifiably outside the book (Claude Code memory, plans).

    The literal path, the resolved path and every existing ancestor's file identity must all
    miss root: 8.3 short names, junctions, symlinks, \\\\?\\ prefixes and case-insensitive
    filesystems can alias back into the book. UNC/device paths on another drive than root
    are never outside, since \\\\localhost\\C$ reaches local disks without a visible link.
    """
    if not isinstance(name, str) or not name or '\x00' in name:
        return False
    p = Path(name)
    if not p.is_absolute():
        return False
    if p.drive != root.drive and p.drive[:2] in {'\\\\', '//'}:
        return False
    try:
        real = p.resolve()
        key = root.stat()
    except (OSError, RuntimeError):
        return False
    if any(x == root or root in x.parents for x in (p, real)):
        return False
    for x in [p, *p.parents]:
        try:
            s = x.stat()
        except OSError:
            continue
        if (s.st_dev, s.st_ino) == (key.st_dev, key.st_ino):
            return False
    return True


def rel(root, path):
    return inside(root, str(path)).relative_to(root).as_posix()


def ident(value):
    require(bool(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', value)), '識別碼限英數、底線與連字號')
    return value


@contextmanager
def locked(root):
    # OS releases this lock on crashes; the empty lock file is intentionally persistent.
    with (root / '.novel-kit.lock').open('a+b') as f:
        if os.name == 'nt':
            import msvcrt
            if f.tell() == 0:
                f.write(b'0'); f.flush()
            f.seek(0)
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as e:
                raise Invalid('另一個工作流程正在執行') from e
        else:
            import fcntl
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as e:
                raise Invalid('另一個工作流程正在執行') from e
        try:
            yield
        finally:
            if os.name == 'nt':
                f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)


def rows(root):
    content = text(inside(root, STATE))
    result = {}
    for line in content.splitlines():
        if not line.strip().startswith('|'):
            continue
        cells = [x.strip() for x in line.strip().strip('|').split('|')]
        if cells[0] == '章' or all(re.fullmatch(r'[: -]+', c) for c in cells):
            continue
        require(len(cells) == 4, '場景狀態表必須是四欄')
        require(re.fullmatch(r'第\d{3,}章', cells[0]), '章號格式錯誤')
        require(cells[1] == '收尾' or re.fullmatch(r'(?:场景|場景)\d{2,}', cells[1]), '场景栏格式错误；旧修订列请迁移到修订任务')
        ch = int(cells[0][1:-1])
        sc = 0 if cells[1] == '收尾' else int(cells[1][2:])
        require(ch > 0 and (sc > 0 or cells[1] == '收尾'), '章與場景編號必須大於零')
        key = (ch, sc)
        require(key not in result, '場景狀態有重複列')
        require(cells[2] in STATE_CANONICAL, '场景状态值不合法：' + cells[2])
        meta = json.loads(cells[3]) if cells[3] else {}
        require(isinstance(meta, dict), '備註必須是工具產生的 JSON 物件')
        result[key] = {'status': STATE_CANONICAL[cells[2]], 'meta': meta}
    return result


def table(data):
    lines = ['# 场景状态', '', '> 状态由 novel.py 维护；备注包含确认与采用版本，请勿手改。', '', '| 章 | 场景 | 状态 | 备注 |', '|---|---|---|---|']
    for (ch, sc), row in sorted(data.items(), key=lambda x: (x[0][0], x[0][1] or 10**9)):
        unit = f'场景{sc:02d}' if sc else '收尾'
        meta = json.dumps(row['meta'], ensure_ascii=False, separators=(',', ':')).replace('|', '\\u007c')
        lines.append(f'| 第{ch:03d}章 | {unit} | {STATE_DISPLAY[row["status"]]} | {meta} |')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def scene_path(ch, sc):
    return f'草稿/第{ch:03d}章/場景{sc:02d}.md' if sc else f'正文/第{ch:03d}章.md'


def outline(root, ch):
    p = inside(root, f'大綱/細綱/第{ch:03d}章.md')
    content = text(p)
    statuses = re.findall(r'^- (?:状态|狀態)[：:]([^\r\n]*)$', content, re.M)
    require(len(statuses) == 1 and statuses[0].strip() in {'已确认', '已確認'}, '细纲须有唯一的已确认状态，重复或冲突标签不可使用')
    nums = [int(s) for s in re.findall(r'^## (?:场景|場景)(\d{2,})(?:\s|$)', content, re.M)]
    require(nums and nums == list(range(1, len(nums) + 1)), '细纲场景必须由 01 连续编号且不重复')
    return p, nums


def journals(root):
    return sorted((root / '審閱/採用').glob('*/journal.json'))


def idle(root):
    for p in journals(root):
        require(load(p)['status'] not in {'applying', 'reverting', 'withdrawing'}, '有中断操作，请先恢复 accept、rollback 或 withdraw：' + p.parent.name)


def tasks(root):
    return [(p, load(p)) for p in sorted((root / '審閱/修訂').glob('*/任務.json'))]


def no_revision(root):
    require(not any(t['status'] not in {'complete', 'cancelled'} for _, t in tasks(root)), '有未完成修訂；完成追蹤更新前不得續寫')


def verify_adopted(root, ch, sc, data):
    r = data.get((ch, sc))
    require(r and r['status'] == '已通過', f'第{ch:03d}章 {sc or "收尾"} 尚未採用')
    require(r['meta'].get('text') == digest(read(inside(root, scene_path(ch, sc)))) and r['meta'].get('text'), '已採用正文已變更，請先處理修訂')


def previous_chapter(root, ch, data):
    if ch == 1:
        return
    if any(c == ch - 1 for c, _ in data):
        verify_adopted(root, ch - 1, 0, data)
    else:
        p = root / '導入/清單.json'
        imports = load(p) if p.exists() else {}
        r = imports.get(str(ch - 1), {})
        require(r.get('text') and r['text'] == digest(read(inside(root, scene_path(ch - 1, 0)))), '上一章未採用或尚未確認導入')


def eligible(root, ch, sc, allow_pending=False):
    idle(root); no_revision(root)
    data = rows(root)
    p, nums = outline(root, ch)
    require(sc == 0 or sc in nums, '場景不在細綱中')
    r = data.get((ch, sc))
    require(r and r['meta'].get('outline') == digest(p.read_bytes()), '細綱版本已變更或尚未登記確認')
    allowed = {'未開始', '撰寫中', '自動審閱中'} | ({'待審'} if allow_pending else set())
    require(r['status'] in allowed, '此場景不可直接編輯；待審請先 reopen，已採用請用 revise')
    require(not any(x['status'] == '待復核' for x in data.values()), '有依賴待復核，請先完成修訂')
    require(not any(k != (ch, sc) and x['status'] in {'待審', '撰寫中', '自動審閱中'} for k, x in data.items()), '另一個場景或收尾尚未交付完成')
    previous_chapter(root, ch, data)
    for n in nums if sc == 0 else range(1, sc):
        verify_adopted(root, ch, n, data)
    return data


def check(root, name):
    if outside(root, name):
        return
    p = inside(root, name)
    name = rel(root, p)
    # Windows drops trailing dots/spaces and maps '::$DATA' to the main stream.
    require(not re.search(r':|[. ](/|$)', name), '路徑段不可含冒號或以點、空白結尾')
    if TOOL_OWNED.fullmatch(name):
        raise Invalid('此檔由 novel.py 維護，請改用對應命令（見 .novel-kit/workflows/adoption.md）')
    if name.startswith('正文/'):
        raise Invalid('正式正文只能經採用工具更新；請修改候選')
    if name.startswith('導入/原稿/') and p.exists():
        raise Invalid('導入原稿備份不可修改')
    m = SCENE.fullmatch(name)
    if m:
        eligible(root, int(m[1]), int(m[2]))
    elif re.fullmatch(r'草稿/第\d{3,}章/整章候選\.md', name):
        eligible(root, int(re.search(r'第(\d+)章', name)[1]), 0)
    elif name.startswith('草稿/'):
        raise Invalid('草稿路徑格式錯誤')


def confirm_plan(root, ch):
    idle(root); no_revision(root)
    data = rows(root)
    previous_chapter(root, ch, data)
    require(not any(r['status'] in {'待審', '撰寫中', '自動審閱中', '待復核'} for r in data.values()), '先處理目前待審或進行中的內容')
    p, nums = outline(root, ch)
    require(all(r['status'] == '未開始' for (c, _), r in data.items() if c == ch), '已有寫作內容，須完成修訂及相容性復核後才能重新確認細綱')
    data = {k: v for k, v in data.items() if k[0] != ch}
    for sc in [*nums, 0]:
        data[ch, sc] = {'status': '未開始', 'meta': {'outline': digest(p.read_bytes())}}
    atomic(root / STATE, table(data))


def begin(root, ch, sc, reopen=False):
    data = eligible(root, ch, sc, allow_pending=reopen)
    if reopen:
        require(data[ch, sc]['status'] == '待審', '只有待審交付可以 reopen')
    data[ch, sc]['status'] = '撰寫中'
    # An old prepared delivery can no longer match this state snapshot.
    data[ch, sc]['meta'].pop('delivery', None)
    data[ch, sc]['meta'].pop('review', None)
    atomic(root / STATE, table(data))


def withdraw(root, ch, sc, reason, approval):
    """Withdraw only workflow authorization; preserve every candidate and author edit."""
    require(reason.strip() and approval.strip(), '撤回须记录原因及作者明确授权；参数不能替代真人授权')
    active = [(p, load(p)) for p in journals(root) if load(p)['status'] == 'withdrawing']
    matching = [(p, j) for p, j in active if j.get('kind') == 'withdraw' and j.get('chapter') == ch and j.get('scene') == sc]
    require(not active or len(active) == len(matching) == 1, '先恢复其他中断撤回')
    if matching:
        p, j = matching[0]
    else:
        idle(root)
        data = rows(root); row = data.get((ch, sc))
        require(row is not None and row['status'] in {'撰寫中', '自動審閱中', '待審'}, '只能撤回尚未采用的撰写中、自动审阅中或待审内容')
        require(not row['meta'].get('text'), '已采用身份不能通过撤回清除，请走修订')
        name = 'withdraw-' + digest(os.urandom(24))[:20]
        p = inside(root, f'審閱/採用/{name}/journal.json')
        invalidations = []
        for jp in journals(root):
            prior = load(jp)
            binding = prior.get('binding', prior)
            scoped = (binding.get('kind') in {'scene', 'chapter'} and binding.get('chapter') == ch and binding.get('scene', 0) == sc)
            legacy_scoped = (prior.get('kind') in {'scene', 'chapter'} and
                             any(e['target'] == scene_path(ch, sc) for e in prior.get('changes', [])))
            if (scoped or legacy_scoped or prior['id'] in {row['meta'].get('delivery'), row['meta'].get('review')}) and prior['status'] in {'reviewing', 'prepared'}:
                invalidations.append(prior['id'])
        history = {'id': name, 'from': row['status'], 'reason': reason, 'approval': approval,
                   'candidate': digest(read(root/scene_path(ch, sc) if sc else root/f'草稿/第{ch:03d}章/整章候選.md')),
                   'delivery': row['meta'].get('delivery'), 'review': row['meta'].get('review')}
        row['status'] = '未開始'
        row['meta'].pop('delivery', None); row['meta'].pop('review', None)
        row['meta'].setdefault('withdrawals', []).append(history)
        j = {'version': 2, 'id': name, 'kind': 'withdraw', 'chapter': ch, 'scene': sc,
             'status': 'withdrawing', 'reason': reason, 'approval': approval, 'invalidations': invalidations,
             'changes': [change(root, STATE, table(data))]}
        atomic(p, dump(j))
    e = j['changes'][0]
    require(digest(read(root/STATE)) in {e['before_hash'], e['after_hash']}, '撤回中断后状态被外部修改，保留现场并停止')
    require(digest(base64.b64decode(e['after'])) == e['after_hash'], '撤回快照损坏')
    for name in j['invalidations']:
        jp = inside(root, f'審閱/採用/{ident(name)}/journal.json'); prior = load(jp)
        require(prior['status'] in {'reviewing', 'prepared', 'withdrawn'}, '旧交付身份已改变，停止撤回')
        if prior['status'] != 'withdrawn':
            prior.update(status='withdrawn', withdrawal=j['id'], withdrawal_reason=j['reason'])
            atomic(jp, dump(prior))
    if digest(read(root/STATE)) != e['after_hash']:
        atomic(root/STATE, base64.b64decode(e['after']))
    j['status'] = 'complete'; atomic(p, dump(j))
    return 'withdrawn'


def rebind_plan(root, ch, reason, approval):
    """Keep scene identities. Renumbering/removing started scenes needs explicit migration."""
    idle(root); no_revision(root)
    require(reason.strip() and approval.strip(), '重新绑定须记录新细纲确认、影响复核原因及作者明确授权')
    data = rows(root)
    require(not any(r['status'] in {'待審', '撰寫中', '自動審閱中', '待復核'} for r in data.values()), '先撤回进行中交付，并完成修订及依赖复核')
    p, nums = outline(root, ch); previous_chapter(root, ch, data)
    old = {sc: r for (c, sc), r in data.items() if c == ch}
    require(old, '未登记的章节请使用 confirm-plan')
    require(old.get(0, {}).get('status') != '已通過' or nums == sorted(sc for sc in old if sc), '整章已采用，增删场景须先制定正式章节修订和明确映射方案')
    for sc, row in old.items():
        require(sc == 0 or sc in nums or (row['status'] == '未開始' and not row['meta'].get('withdrawals')), '不能删除或重编号已开始场景；请先制定明确映射和修订方案')
        if row['status'] == '已通過':
            # Historical scene identities remain frozen after formal chapter adoption.
            # revision_identity rejects editing those drafts, but rebinding must retain them.
            meta = row['meta']; jp = inside(root, f'審閱/採用/{ident(meta.get("delivery", ""))}/journal.json')
            require(jp.exists() and load(jp)['status'] == 'complete' and any(e['target'] == scene_path(ch, sc) and e['after_hash'] == meta.get('text') for e in load(jp)['changes']), '采用身份与完整记录不一致')
            verify_adopted(root, ch, sc, data)
    current = digest(p.read_bytes())
    require(any(r['meta'].get('outline') != current for r in old.values()), '细纲版本未变更，无需重新绑定')
    data = {k: v for k, v in data.items() if k[0] != ch}
    for sc in [*nums, 0]:
        row = old.get(sc, {'status': '未開始', 'meta': {}})
        row['meta'].setdefault('plan_history', []).append({'outline': row['meta'].get('outline'), 'reason': reason, 'approval': approval})
        row['meta']['outline'] = current
        data[ch, sc] = row
    atomic(root/STATE, table(data))


def task_path(root, name):
    return inside(root, f'審閱/修訂/{ident(name)}/任務.json')


def revision_identity(root, target, data=None):
    """Check provenance, not current text: author hand edits remain valid review inputs."""
    data = rows(root) if data is None else data
    m = SCENE.fullmatch(target) or CHAPTER.fullmatch(target)
    require(m is not None, '修订只接受章节或场景正文')
    ch, sc = int(m[1]), int(m[2]) if len(m.groups()) == 2 else 0
    if sc:
        require(data.get((ch, 0), {}).get('status') != '已通過', '整章已采用，请修订正式章节而不是保留的场景草稿')
    row = data.get((ch, sc))
    if row is not None:
        require(row['status'] in {'已通過', '待復核'} and row['meta'].get('text') and row['meta'].get('delivery'), '修订目标没有有效采用身份')
        jp = inside(root, f'審閱/採用/{ident(row["meta"]["delivery"])}/journal.json')
        require(jp.exists(), '采用记录不存在')
        j = load(jp)
        require(j['status'] == 'complete' and any(e['target'] == target and e['after_hash'] == row['meta']['text'] for e in j['changes']), '采用身份与完整记录不一致')
        return {'kind': 'adoption', 'delivery': j['id'], 'text': row['meta']['text']}
    ip = root / '導入/清單.json'
    entry = (load(ip) if ip.exists() else {}).get(str(ch), {})
    require(sc == 0 and entry.get('text') and entry.get('source_hash') and entry.get('source'), '修订目标没有有效采用或导入身份')
    source = inside(root, entry['source'])
    require(rel(root, source).startswith('導入/原稿/') and digest(read(source)) == entry['source_hash'], '导入身份对应的原稿备份已变更')
    return {'kind': 'import', 'source': entry['source'], 'source_hash': entry['source_hash'], 'text': entry['text']}


def revision_start(root, name, targets):
    idle(root); no_revision(root)
    require(not any(r['status'] in {'待審', '撰寫中', '自動審閱中'} for r in rows(root).values()), '先完成目前場景交付，再修訂已採用內容')
    p = task_path(root, name)
    require(not p.exists(), '修訂識別碼已存在')
    entries = []
    for target in targets:
        t = rel(root, inside(root, target))
        require(SCENE.fullmatch(t) or CHAPTER.fullmatch(t), '修訂只接受章節或場景正文')
        identity = revision_identity(root, t)
        content = inside(root, t).read_bytes()
        require(t not in [e['target'] for e in entries], '重複修訂目標')
        entries.append({'target': t, 'identity': identity, 'start_hash': digest(content), 'start_bytes': base64.b64encode(content).decode(), 'adopted': None})
    require(entries, '修訂目標不可空白')
    atomic(p, dump({'status': 'active', 'targets': entries}))


def target_allowed(target):
    return bool(SCENE.fullmatch(target) or CHAPTER.fullmatch(target) or
                (target.endswith('.md') and target.split('/')[0] in {'設定', '追蹤', '大綱'})) and target != STATE


def review_binding(root, spec):
    kind = spec['kind']
    require(kind in {'scene', 'chapter', 'revision', 'revision-finish'}, '交付类型错误')
    context = [rel(root, inside(root, x)) for x in spec.get('context', [])]
    require(len(context) == len(set(context)), '上下文清单不可重复')
    files = []
    for item in spec['files']:
        src, target = rel(root, inside(root, item['source'])), rel(root, inside(root, item['target']))
        require(target_allowed(target), '不允许的采用目标：' + target)
        require(target not in [x['target'] for x in files] and src not in [x['source'] for x in files], '候选来源及采用目标不可重复')
        require(src.startswith(('草稿/', '審閱/')) and not src.startswith('審閱/採用/'), '候选必须位于草稿或审阅工作目录')
        require(bool((read(root/src) or b'').strip()), '候选不可空白')
        files.append({'source': src, 'target': target})
    require(files, '采用清单不可空白')
    ranges = spec.get('context_ranges', [])
    require(isinstance(ranges, list) and all(isinstance(x, dict) for x in ranges), '上下文选取范围须为 JSON 对象清单')
    # Freeze semantic ranges too, not just the source-file hashes.
    ranges = json.loads(json.dumps(ranges, ensure_ascii=False))
    for item in ranges:
        require(isinstance(item.get('path'), str), '上下文范围缺少 path')
        item['path'] = rel(root, inside(root, item['path']))
        require(item['path'] in context, '选取范围的原始文件须列在 context：' + item['path'])
        require(isinstance(item.get('start_line'), int) and isinstance(item.get('end_line'), int) and 0 < item['start_line'] <= item['end_line'], '上下文行范围不合法')
        require(item['end_line'] <= len(text(root/item['path']).splitlines()), '上下文行范围超出原文')
    binding = {'kind': kind, 'files': files, 'context': context, 'context_ranges': ranges}
    if kind in {'scene', 'chapter'}:
        ch, sc = int(spec['chapter']), int(spec.get('scene', 0))
        require((kind == 'scene' and sc > 0) or (kind == 'chapter' and sc == 0), '章节或场景参数不一致')
        prose = [x for x in files if SCENE.fullmatch(x['target']) or CHAPTER.fullmatch(x['target'])]
        require(len(prose) == 1 and prose[0]['target'] == scene_path(ch, sc), '交付只能采用指定正文')
        require(kind != 'scene' or len(files) == 1, '场景采用只更新场景；全书追踪在章节采用时更新')
        require(kind != 'chapter' or any(x['target'] == '追蹤/追蹤.md' for x in files), '章節收尾必須交付最終追蹤，與正文一起採用')
        binding.update(chapter=ch, scene=sc)
    else:
        binding['revision'] = ident(spec['revision'])
    return binding


def review_start(root, spec):
    """Freeze inputs before independent readers begin, in the existing adoption journal."""
    idle(root)
    name = ident(spec['id']); binding = review_binding(root, spec)
    dest = inside(root, f'審閱/採用/{name}/journal.json')
    if dest.exists():
        existing = load(dest)
        require(existing.get('version') == 2 and existing['status'] == 'reviewing' and existing.get('binding') == binding, '交付识别码已存在，请使用新版本')
        for source, expected in existing['frozen'].items():
            allowed = {expected}
            if source == STATE and existing.get('review_state'):
                allowed.add(existing['review_state']['before_hash'])
            require(digest(read(root/source)) in allowed, '已冻结的审阅输入已变更：' + source)
        e = existing.get('review_state')
        if e and digest(read(root/STATE)) == e['before_hash']:
            require(digest(base64.b64decode(e['after'])) == e['after_hash'], '审阅开始快照损坏')
            atomic(root/STATE, base64.b64decode(e['after']))
        return 'already-reviewing'
    require(not dest.parent.exists(), '交付识别码目录已存在，请使用新版本')
    watches = {STATE: digest(read(root/STATE))}
    def watch(source, required=True):
        source = rel(root, inside(root, source)); content = read(root/source)
        require(not required or bool(content), '上下文不存在或为空：' + source)
        if content is not None: watches[source] = digest(content)
    for item in binding['files']:
        watch(item['source'])
        watches[item['target']] = digest(read(root/item['target']))
    for source in binding['context']:
        watch(source)
        if source.endswith('.json'):
            packet = load(root/source)
            if isinstance(packet, dict) and packet.get('version') == 1 and 'prose_ranges' in packet and 'input_hashes' in packet:
                require(isinstance(packet.get('dependencies'), list) and isinstance(packet['input_hashes'], dict), '上下文清单格式错误')
                require(set(packet['dependencies']) == set(packet['input_hashes']), '上下文清单来源集合不一致')
                for dependency in packet['dependencies']:
                    dependency = rel(root, inside(root, dependency))
                    require(digest(read(root/dependency)) == packet['input_hashes'][dependency], '上下文清单已过期，请重新生成：' + dependency)
                    watches[dependency] = packet['input_hashes'][dependency]
                for role in ('blind', 'writer'):
                    path = rel(root, inside(root, packet[role+'_path']))
                    require(digest(read(root/path)) == packet[role+'_hash'], '上下文文档与清单版本不一致：' + path)
                    watch(path)
    for source in ['設定/設定.md', '設定/兌現登記.md', '設定/文風樣本.md', '大綱/大綱.md', '追蹤/追蹤.md']:
        watch(source, False)
    for p in sorted((root/'設定/角色').glob('*.md')): watch(rel(root, p))
    state_change = None
    kind = binding['kind']
    if kind in {'scene', 'chapter'}:
        ch, sc = binding['chapter'], binding['scene']
        data = eligible(root, ch, sc)
        require(data[ch, sc]['status'] in {'撰寫中', '自動審閱中'}, '先 begin 再开始审阅')
        op, nums = outline(root, ch); watch(rel(root, op))
        for n in nums if sc == 0 else range(1, sc):
            source = scene_path(ch, n); watch(source)
            identity = data[ch, n]['meta'].get('delivery')
            if identity: watch(f'審閱/採用/{ident(identity)}/journal.json')
        if ch > 1:
            watch(scene_path(ch-1, 0)); watch('導入/清單.json', False)
            identity = data.get((ch-1, 0), {}).get('meta', {}).get('delivery')
            if identity: watch(f'審閱/採用/{ident(identity)}/journal.json')
        data[ch, sc]['status'] = '自動審閱中'; data[ch, sc]['meta']['review'] = name
        state_change = change(root, STATE, table(data))
        watches[STATE] = state_change['after_hash']
    else:
        tp = task_path(root, binding['revision']); task = load(tp)
        require(task['status'] == 'active', '修订任务不是进行中')
        watch(rel(root, tp)); watch('導入/清單.json', False)
        for entry in task['targets']:
            watch(entry['target'])
        if kind == 'revision':
            prose = [x for x in binding['files'] if SCENE.fullmatch(x['target']) or CHAPTER.fullmatch(x['target'])]
            require(len(prose) == len(binding['files']) == 1, '每次修订交付只采用一个正文')
            entry = next((x for x in task['targets'] if x['target'] == prose[0]['target']), None)
            require(entry is not None and entry['adopted'] is None, '目标不在修订范围或已采用')
            require(digest(read(root/entry['target'])) == entry['start_hash'], '修订开始后原文已变化，请先 revision-refresh')
            identity = revision_identity(root, entry['target'])
            if identity['kind'] == 'adoption': watch(f'審閱/採用/{ident(identity["delivery"])}/journal.json')
            else: watch(identity['source'])
    candidates = {x['source']: base64.b64encode(read(root/x['source'])).decode() for x in binding['files']}
    j = {'version': 2, 'id': name, 'kind': kind, 'status': 'reviewing', 'binding': binding,
         'frozen': watches, 'review_candidates': candidates, 'review_state': state_change}
    atomic(dest, dump(j))
    if state_change: atomic(root/STATE, base64.b64decode(state_change['after']))
    return name


def verify_full_delivery(root, delivery, binding):
    content = read(root/delivery)
    require(content is not None, '交付文件不存在')
    for item in binding['files']:
        marker = ('<!-- novel-candidate:' + item['source'] + ' -->\n').encode('utf-8')
        require(content.count(marker) == 1, '交付须逐场景展示唯一完整候选块：' + item['source'])
        after = content.split(marker, 1)[1]
        candidate, separator, _ = after.partition(b'\n<!-- /novel-candidate -->')
        require(separator and candidate == read(root/item['source']), '交付全文与审阅候选不一致：' + item['source'])


def prepare(root, spec):
    idle(root)
    name = ident(spec['id'])
    dest = inside(root, f'審閱/採用/{name}/journal.json')
    require(dest.exists(), '先执行 review-start 冻结输入，再开始独立审阅')
    frozen = load(dest)
    require(frozen.get('version') == 2 and frozen['status'] == 'reviewing', '交付未处于当前版本审阅阶段，请使用新识别码')
    binding = review_binding(root, spec)
    require(frozen.get('binding') == binding, '审阅范围、候选或上下文清单已变更，须重新开始审阅')
    for source, expected_hash in frozen['frozen'].items():
        require(digest(read(root/source)) == expected_hash, '审阅开始后候选、正文身份或上下文已变更：' + source)
    kind = spec['kind']
    require(kind in {'scene', 'chapter', 'revision', 'revision-finish'}, '交付類型錯誤')
    delivery = rel(root, inside(root, spec['delivery']))
    require(delivery.startswith('審閱/') and delivery.endswith('.md'), '交付檔須在審閱目錄')
    require(bool(read(root / delivery)), '先寫好交付檔再 prepare')
    verify_full_delivery(root, delivery, binding)
    task = None
    if kind in {'scene', 'chapter'}:
        ch, sc = int(spec['chapter']), int(spec.get('scene', 0))
        require((kind == 'scene' and sc > 0) or (kind == 'chapter' and sc == 0), '章節/場景參數不一致')
        data = eligible(root, ch, sc)
        require(data[ch, sc]['status'] in {'撰寫中', '自動審閱中'}, '先 begin 再交付')
    else:
        tp = task_path(root, spec['revision'])
        task = load(tp)
        require(task['status'] == 'active', '修訂任務不是進行中')
    review = spec['review']
    require(review['mode'] in REVIEWERS and isinstance(review.get('completed'), list) and isinstance(review.get('unresolved'), list), '審閱紀錄格式錯誤')
    expected = '完整' if kind == 'scene' else '章節' if kind == 'chapter' else review['mode']
    require(review['mode'] == expected, '新場景須完整模式，收尾須章節模式')
    pending = sorted(REVIEWERS[expected] - set(review['completed']))
    watches = {**frozen['frozen'], delivery: digest((root / delivery).read_bytes())}
    if task is not None:
        watches[STATE] = digest(read(root / STATE))
    for source in spec.get('context', []):
        src = rel(root, inside(root, source))
        require(bool(read(root / src)), '上下文不存在或為空：' + src)
        watches[src] = digest(read(root / src))
    changes = []
    for item in spec['files']:
        src, target = rel(root, inside(root, item['source'])), rel(root, inside(root, item['target']))
        require(target_allowed(target), '不允許的採用目標：' + target)
        require(target not in [e['target'] for e in changes], '重複採用目標')
        require(src.startswith(('草稿/', '審閱/')) and not src.startswith('審閱/採用/'), '候選必須位於草稿或審閱工作目錄')
        after = read(root / src)
        require(after is not None and bool(after.strip()), '候選不可空白')
        watches[src] = digest(after)
        changes.append(change(root, target, after))
    require(changes, '採用清單不可空白')
    prose = [e for e in changes if SCENE.fullmatch(e['target']) or CHAPTER.fullmatch(e['target'])]
    if kind in {'scene', 'chapter'}:
        target = scene_path(ch, sc)
        require(len(prose) == 1 and prose[0]['target'] == target, '交付只能採用指定正文')
        if kind == 'scene':
            require(len(changes) == 1, '場景採用只更新場景；全書追蹤在章節採用時更新')
        else:
            require(any(e['target'] == '追蹤/追蹤.md' for e in changes), '章節收尾必須交付最終追蹤，與正文一起採用')
        op, nums = outline(root, ch)
        watches[rel(root, op)] = digest(op.read_bytes())
        for n in nums if sc == 0 else range(1, sc):
            source = scene_path(ch, n); watches[source] = digest(read(root / source))
        if ch > 1:
            source = scene_path(ch - 1, 0); watches[source] = digest(read(root / source))
        data[ch, sc]['status'] = '待審'
        data[ch, sc]['meta']['delivery'] = name
        waiting = table(data)
        if STATE in watches:
            watches[STATE] = digest(waiting)
        data[ch, sc]['status'] = '已通過'
        data[ch, sc]['meta'].pop('review', None)
        data[ch, sc]['meta']['text'] = prose[0]['after_hash']
        changes.append(change(root, STATE, table(data), before=waiting))
    elif kind == 'revision':
        require(len(prose) == 1 and len(changes) == 1, '每次修訂交付只採用一個正文；追蹤更新另走 revision-finish')
        entry = next((e for e in task['targets'] if e['target'] == prose[0]['target']), None)
        require(entry is not None and entry['adopted'] is None, '目標不在修訂範圍或已採用')
        require(prose[0]['before_hash'] == entry['start_hash'], '修訂開始後原文已被改動，請保留手改並用 revision-refresh 更新審閱基準')
        entry['adopted'] = prose[0]['after_hash']
        changes.append(change(root, rel(root, tp), dump(task)))
        # Bind the adopted row without declaring the revision task complete.
        data = rows(root)
        m = SCENE.fullmatch(prose[0]['target']) or CHAPTER.fullmatch(prose[0]['target'])
        ch, sc = int(m[1]), int(m[2]) if len(m.groups()) == 2 else 0
        if (ch, sc) in data:
            data[ch, sc]['status'] = '已通過'
            data[ch, sc]['meta']['text'] = prose[0]['after_hash']
            data[ch, sc]['meta']['delivery'] = name
            for (c, s), r in data.items():
                if c == ch and sc > 0 and (s > sc or s == 0) and r['status'] in {'已通過', '待復核'}:
                    r['status'] = '待復核'
            changes.append(change(root, STATE, table(data)))
        else:
            ip = root / '導入/清單.json'
            imports = load(ip) if ip.exists() else {}
            if str(ch) in imports:
                imports[str(ch)]['text'] = prose[0]['after_hash']
                changes.append(change(root, '導入/清單.json', dump(imports)))
    else:
        require(not prose, '修訂收尾只能更新設定、大綱及追蹤')
        require(any(e['target'] == '追蹤/追蹤.md' for e in changes), '修訂收尾必須交付最終追蹤')
        for e in task['targets']:
            require(e['adopted'] and e['adopted'] == digest(read(root / e['target'])), '所有修訂目標須採用且未變更')
            watches[e['target']] = e['adopted']
        require(not any(r['status'] == '待復核' for r in rows(root).values()), '仍有依賴待復核，先將其納入修訂並採用')
        task['status'] = 'complete'
        changes.append(change(root, rel(root, tp), dump(task)))
    journal = {**frozen, 'version': 2, 'id': name, 'kind': kind, 'delivery': delivery, 'status': 'prepared', 'review': review,
               'missing_reviewers': pending, 'watches': watches, 'changes': changes}
    # Write journal first: interrupted preparation cannot authorize adoption.
    atomic(dest, dump(journal))
    if kind in {'scene', 'chapter'}:
        atomic(root / STATE, waiting)
    return name


_UNSET = object()


def change(root, target, after, before=_UNSET):
    before = read(inside(root, target)) if before is _UNSET else before
    return {'target': target, 'before_hash': digest(before), 'after_hash': digest(after),
            'before': base64.b64encode(before).decode() if before is not None else None,
            'after': base64.b64encode(after).decode()}


def accept(root, name, approval, override=''):
    p = inside(root, f'審閱/採用/{ident(name)}/journal.json')
    j = load(p)
    if j['status'] == 'complete':
        return 'already-complete'
    require(j['status'] in {'prepared', 'applying'}, '交付不可採用')
    require(j['status'] != 'prepared' or j.get('version') == 2, '旧协议待审交付缺少开读冻结，请撤回或 reopen 后重新审阅')
    if j['kind'] == 'chapter' and j['status'] == 'prepared':
        require(any(e['target'] == '追蹤/追蹤.md' for e in j['changes']), '舊章節交付缺少最終追蹤，請 reopen 後重新交付')
    if j['status'] == 'prepared' and j['kind'] in {'scene', 'chapter'}:
        no_revision(root)
    require(approval.strip(), '須記錄作者明確採用的回覆；工具不能替作者授權')
    require(not (j['missing_reviewers'] or j['review']['unresolved']) or override.strip(), '審閱未完成或仍有未決問題，須記錄作者明確裁決')
    for other in journals(root):
        require(other == p or load(other)['status'] not in {'applying', 'reverting', 'withdrawing'}, '先恢复另一中断采用或撤回')
    targets = {e['target']: e for e in j['changes']}
    for name, expected in j['watches'].items():
        current = digest(read(inside(root, name)))
        allowed = {expected}
        if j['status'] == 'applying' and name in targets:
            allowed.add(targets[name]['after_hash'])
        require(current in allowed, '交付來源或上下文已變更，請重新審閱交付：' + name)
    for e in j['changes']:
        require(digest(base64.b64decode(e['after'])) == e['after_hash'], '採用快照損壞')
        expected = {e['before_hash'], e['after_hash']} if j['status'] == 'applying' else {e['before_hash']}
        require(digest(read(inside(root, e['target']))) in expected, '採用目標已變更，保留現場並停止：' + e['target'])
    if j['status'] == 'prepared':
        j.update(status='applying', approval=approval, override=override)
        atomic(p, dump(j))
    for e in j['changes']:
        target = inside(root, e['target'])
        current = digest(read(target))
        require(current in {e['before_hash'], e['after_hash']}, '採用期間檔案被外部改動，已停止：' + e['target'])
        if current != e['after_hash']:
            atomic(target, base64.b64decode(e['after']))
    j['status'] = 'complete'
    atomic(p, dump(j))
    return 'complete'


def rollback(root, name, reason):
    p = inside(root, f'審閱/採用/{ident(name)}/journal.json')
    j = load(p)
    require(reason.strip(), '須記錄取消採用的原因')
    if j['status'] == 'cancelled':
        return 'already-cancelled'
    require(j['status'] in {'applying', 'reverting'}, 'rollback 只用於中斷採用，已完成內容請走修訂')
    for e in j['changes']:
        before = base64.b64decode(e['before']) if e['before'] is not None else None
        require(digest(before) == e['before_hash'], '改前快照損壞，停止回復')
        require(digest(read(inside(root, e['target']))) in {e['before_hash'], e['after_hash']}, '有外部手改，保留現場並停止：' + e['target'])
    j.update(status='reverting', cancel_reason=reason)
    atomic(p, dump(j))
    for e in reversed(j['changes']):
        target = inside(root, e['target'])
        require(digest(read(target)) in {e['before_hash'], e['after_hash']}, '回復期間有外部修改，已停止')
        if e['before'] is None:
            if target.exists():
                target.unlink()
        elif digest(read(target)) != e['before_hash']:
            atomic(target, base64.b64decode(e['before']))
    j['status'] = 'cancelled'; atomic(p, dump(j))
    return 'cancelled'


def revision_extend(root, name, targets):
    idle(root)
    p = task_path(root, name); t = load(p)
    require(t['status'] == 'active', '修訂任務已結束')
    for target in targets:
        target = rel(root, inside(root, target))
        require(SCENE.fullmatch(target) or CHAPTER.fullmatch(target), '只接受正文目標')
        identity = revision_identity(root, target)
        require(target not in [x['target'] for x in t['targets']], '目標已在修訂中')
        content = inside(root, target).read_bytes()
        t['targets'].append({'target': target, 'identity': identity, 'start_hash': digest(content), 'start_bytes': base64.b64encode(content).decode(), 'adopted': None})
    atomic(p, dump(t))


def revision_cancel(root, name):
    idle(root)
    p = task_path(root, name); t = load(p)
    require(t['status'] == 'active' and not any(e['adopted'] for e in t['targets']), '部分已採用的修訂須先完成事實同步，不能直接取消')
    require(not any(e.get('baseline_history') for e in t['targets']), '已重新登記手改基準，須完成審閱採用與事實同步，不能直接取消')
    require(all(digest(read(root / e['target'])) == e['start_hash'] for e in t['targets']), '正文有手改，須先處理後才可取消')
    t['status'] = 'cancelled'; atomic(p, dump(t))


def revision_refresh(root, name, target, reason):
    """Snapshot an author's newer draft without changing prose or declaring it adopted."""
    idle(root)
    require(reason.strip(), '須記錄重新登記作者手改基準的原因')
    p = task_path(root, name); task = load(p)
    require(task['status'] == 'active', '修訂任務不是進行中')
    target = rel(root, inside(root, target))
    entry = next((e for e in task['targets'] if e['target'] == target), None)
    require(entry is not None, '目標不在修訂範圍；新增範圍請先取得作者授權並 revision-extend')
    content = inside(root, target).read_bytes()
    require(bool(content.strip()), '手改正文不可空白')
    require(digest(content) != (entry['adopted'] or entry['start_hash']), '正文未變更，不需重新登記基準')
    entry.setdefault('baseline_history', []).append({
        'start_hash': entry['start_hash'], 'start_bytes': entry['start_bytes'],
        'adopted': entry['adopted'], 'reason': reason,
    })
    entry.update(start_hash=digest(content), start_bytes=base64.b64encode(content).decode(), adopted=None)
    # A single atomic task update also invalidates every prepared delivery bound to
    # the old task, including revision-finish. Completed adoption journals stay intact.
    atomic(p, dump(task))


def confirm_import(root, manifest):
    idle(root); no_revision(root)
    ip = root / '導入/清單.json'
    entries = load(ip) if ip.exists() else {}
    for item in manifest:
        ch = int(item['chapter'])
        require(ch > 0 and str(ch) not in entries and not any(c == ch for c, _ in rows(root)), '章號重複或已登記')
        source = rel(root, inside(root, item['source']))
        require(source.startswith('導入/原稿/'), '原稿必須先備份到導入/原稿')
        target = scene_path(ch, 0)
        require(bool(read(root / source)) and bool(read(root / target)), '原稿或切分正文不存在/空白')
        require(item['coverage'] in {'詳細', '摘要'}, '須記錄抽取覆蓋範圍')
        require(item.get('location'), '須記錄來源中的章節標題或範圍')
        entries[str(ch)] = {**item, 'source_hash': digest(read(root / source)), 'text': digest(read(root / target))}
    atomic(ip, dump(entries))


def safe_commit(root, paths, message):
    """Refuse pre-existing staged changes; commit only the named files."""
    def git(*args, **kwargs):
        return subprocess.run(['git', '-C', str(root), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)
    top = Path(git('rev-parse', '--show-toplevel').stdout.decode().strip()).resolve()
    require(top == root, '只在書稿本身是 Git 根目錄時自動提交')
    require(not git('diff', '--cached', '--name-only', '-z').stdout, '已有暫存變更，保留原樣；本次檔案已採用但不自動提交')
    require(paths, '提交範圍不可空白')
    names = [rel(root, inside(root, p)) for p in paths]
    require(all(n.split('/')[0] in {'草稿', '正文', '審閱', '追蹤', '設定', '大綱', '導入'} and not Path(n).name.startswith('.') for n in names), '提交只接受列明的書稿檔案')
    require(all((root / n).is_file() for n in names), '提交清單須逐個列出現存檔案，不能是目錄')
    # A temporary index based on HEAD avoids staging unrelated work or leaving
    # staged files behind when commit hooks fail.
    with tempfile.TemporaryDirectory(prefix='novel-index-') as d:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(d) / 'index'))
        head = subprocess.run(['git', '-C', str(root), 'rev-parse', '--verify', 'HEAD'], capture_output=True)
        if head.returncode == 0:
            git('read-tree', 'HEAD', env=env)
        git('--literal-pathspecs', 'add', '--', *names, env=env)
        changed = set(git('diff', '--cached', '--name-only', '-z', '--no-renames', env=env).stdout.decode('utf-8').rstrip('\0').split('\0')) - {''}
        require(changed <= set(names), '临时暂存出现未列明文件，停止提交并保留工作区')
        if not changed:
            return 'no-changes'
        # Existing user index remains untouched during commit; reconcile only our paths afterwards.
        git('commit', '-m', message, env=env)
        committed = set(git('diff-tree', '--root', '--no-commit-id', '--name-only', '-r', '-z', '--no-renames', 'HEAD').stdout.decode('utf-8').rstrip('\0').split('\0')) - {''}
        require(committed <= set(names), '提交钩子加入了未列明文件；提交已经产生，未自动调整原暂存，请人工核对该提交')
        git('--literal-pathspecs', 'reset', '-q', 'HEAD', '--', *names)
    return 'committed'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=os.environ.get('NOVEL_KIT_ROOT', os.environ.get('CLAUDE_PROJECT_DIR', '.')))
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('check'); p.add_argument('path')
    p = sub.add_parser('confirm-plan'); p.add_argument('chapter', type=int)
    p = sub.add_parser('rebind-plan'); p.add_argument('chapter', type=int); p.add_argument('--approval', required=True); p.add_argument('--reason', required=True)
    for name in ('begin', 'reopen'):
        p = sub.add_parser(name); p.add_argument('chapter', type=int); p.add_argument('scene', type=int, help='收尾使用 0')
    p = sub.add_parser('withdraw'); p.add_argument('chapter', type=int); p.add_argument('scene', type=int, help='收尾使用 0'); p.add_argument('--approval', required=True); p.add_argument('--reason', required=True)
    for name in ('review-start', 'prepare'):
        p = sub.add_parser(name); p.add_argument('spec')
    p = sub.add_parser('rollback'); p.add_argument('id'); p.add_argument('--reason', required=True)
    p = sub.add_parser('accept'); p.add_argument('id'); p.add_argument('--approval', required=True); p.add_argument('--override', default='')
    for name in ('revision-start', 'revision-extend'):
        p = sub.add_parser(name); p.add_argument('id'); p.add_argument('targets', nargs='+')
    p = sub.add_parser('revision-cancel'); p.add_argument('id')
    p = sub.add_parser('revision-refresh'); p.add_argument('id'); p.add_argument('target'); p.add_argument('--reason', required=True)
    p = sub.add_parser('confirm-import'); p.add_argument('manifest')
    p = sub.add_parser('commit'); p.add_argument('--message', required=True); p.add_argument('paths', nargs='+')
    p = sub.add_parser('prose-check'); p.add_argument('--json', action='store_true'); p.add_argument('paths', nargs='+')
    args = parser.parse_args(argv); root = Path(args.root).resolve()
    if args.command == 'prose-check':
        # Read-only; skip the writing lock so it can run beside an open work unit.
        import prose_check
        try:
            return prose_check.run(root, [rel(root, inside(root, p)) for p in args.paths], args.json)
        except (Invalid, OSError, ValueError) as e:
            print('【寫作流程】' + str(e), file=sys.stderr)
            return 2
    try:
        with locked(root):
            c = args.command
            if c == 'check': check(root, args.path)
            elif c == 'confirm-plan': confirm_plan(root, args.chapter)
            elif c == 'rebind-plan': rebind_plan(root, args.chapter, args.reason, args.approval)
            elif c in {'begin', 'reopen'}: begin(root, args.chapter, args.scene, c == 'reopen')
            elif c == 'withdraw': print(withdraw(root, args.chapter, args.scene, args.reason, args.approval))
            elif c == 'review-start': print(review_start(root, load(inside(root, args.spec))))
            elif c == 'prepare': print(prepare(root, load(inside(root, args.spec))))
            elif c == 'rollback': print(rollback(root, args.id, args.reason))
            elif c == 'accept': print(accept(root, args.id, args.approval, args.override))
            elif c == 'revision-start': revision_start(root, args.id, args.targets)
            elif c == 'revision-extend': revision_extend(root, args.id, args.targets)
            elif c == 'revision-cancel': revision_cancel(root, args.id)
            elif c == 'revision-refresh': revision_refresh(root, args.id, args.target, args.reason)
            elif c == 'confirm-import': confirm_import(root, load(inside(root, args.manifest)))
            elif c == 'commit': print(safe_commit(root, args.paths, args.message))
        return 0
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        print('【寫作流程】' + str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
