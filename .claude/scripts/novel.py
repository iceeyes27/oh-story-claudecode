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
SCENE = re.compile(r'草稿/第(\d{3,})章/場景(\d{2,})\.md')
CHAPTER = re.compile(r'正文/第(\d{3,})章\.md')
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
        require(cells[1] == '收尾' or re.fullmatch(r'場景\d{2,}', cells[1]), '場景欄格式錯誤；舊修訂列請遷移到修訂任務')
        ch = int(cells[0][1:-1])
        sc = 0 if cells[1] == '收尾' else int(cells[1][2:])
        require(ch > 0 and (sc > 0 or cells[1] == '收尾'), '章與場景編號必須大於零')
        key = (ch, sc)
        require(key not in result, '場景狀態有重複列')
        require(cells[2] in STATES, '場景狀態值不合法：' + cells[2])
        meta = json.loads(cells[3]) if cells[3] else {}
        require(isinstance(meta, dict), '備註必須是工具產生的 JSON 物件')
        result[key] = {'status': cells[2], 'meta': meta}
    return result


def table(data):
    lines = ['# 場景狀態', '', '> 狀態由 novel.py 維護；備註包含確認與採用版本，請勿手改。', '', '| 章 | 場景 | 狀態 | 備註 |', '|---|---|---|---|']
    for (ch, sc), row in sorted(data.items(), key=lambda x: (x[0][0], x[0][1] or 10**9)):
        unit = f'場景{sc:02d}' if sc else '收尾'
        meta = json.dumps(row['meta'], ensure_ascii=False, separators=(',', ':')).replace('|', '\\u007c')
        lines.append(f'| 第{ch:03d}章 | {unit} | {row["status"]} | {meta} |')
    return ('\n'.join(lines) + '\n').encode('utf-8')


def scene_path(ch, sc):
    return f'草稿/第{ch:03d}章/場景{sc:02d}.md' if sc else f'正文/第{ch:03d}章.md'


def outline(root, ch):
    p = inside(root, f'大綱/細綱/第{ch:03d}章.md')
    content = text(p)
    require(re.search(r'^- 狀態：已確認\s*$', content, re.M), '細綱未確認')
    nums = [int(s) for s in re.findall(r'^## 場景(\d{2,})(?:\s|$)', content, re.M)]
    require(nums and nums == list(range(1, len(nums) + 1)), '細綱場景必須由 01 連續編號且不重複')
    return p, nums


def journals(root):
    return sorted((root / '審閱/採用').glob('*/journal.json'))


def idle(root):
    for p in journals(root):
        require(load(p)['status'] not in {'applying', 'reverting'}, '有中斷的採用，請先 accept 恢復：' + p.parent.name)


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
    p = inside(root, name)
    name = rel(root, p)
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
    atomic(root / STATE, table(data))


def task_path(root, name):
    return inside(root, f'審閱/修訂/{ident(name)}/任務.json')


def revision_start(root, name, targets):
    idle(root); no_revision(root)
    require(not any(r['status'] in {'待審', '撰寫中', '自動審閱中'} for r in rows(root).values()), '先完成目前場景交付，再修訂已採用內容')
    p = task_path(root, name)
    require(not p.exists(), '修訂識別碼已存在')
    entries = []
    for target in targets:
        t = rel(root, inside(root, target))
        require(SCENE.fullmatch(t) or CHAPTER.fullmatch(t), '修訂只接受章節或場景正文')
        if SCENE.fullmatch(t):
            c = int(SCENE.fullmatch(t)[1])
            require(rows(root).get((c, 0), {}).get('status') != '已通過', '整章已採用，請修訂正式章節而不是保留的場景草稿')
        content = inside(root, t).read_bytes()
        require(t not in [e['target'] for e in entries], '重複修訂目標')
        entries.append({'target': t, 'start_hash': digest(content), 'start_bytes': base64.b64encode(content).decode(), 'adopted': None})
    require(entries, '修訂目標不可空白')
    atomic(p, dump({'status': 'active', 'targets': entries}))


def target_allowed(target):
    return bool(SCENE.fullmatch(target) or CHAPTER.fullmatch(target) or
                (target.endswith('.md') and target.split('/')[0] in {'設定', '追蹤', '大綱'})) and target != STATE


def prepare(root, spec):
    idle(root)
    name = ident(spec['id'])
    dest = inside(root, f'審閱/採用/{name}/journal.json')
    require(not dest.parent.exists(), '交付識別碼已存在，請使用新版本')
    kind = spec['kind']
    require(kind in {'scene', 'chapter', 'revision', 'revision-finish'}, '交付類型錯誤')
    delivery = rel(root, inside(root, spec['delivery']))
    require(delivery.startswith('審閱/') and delivery.endswith('.md'), '交付檔須在審閱目錄')
    require(bool(read(root / delivery)), '先寫好交付檔再 prepare')
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
    watches = {delivery: digest((root / delivery).read_bytes())}
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
        data[ch, sc]['meta']['text'] = prose[0]['after_hash']
        changes.append(change(root, STATE, table(data), before=waiting))
    elif kind == 'revision':
        require(len(prose) == 1 and len(changes) == 1, '每次修訂交付只採用一個正文；追蹤更新另走 revision-finish')
        entry = next((e for e in task['targets'] if e['target'] == prose[0]['target']), None)
        require(entry is not None and entry['adopted'] is None, '目標不在修訂範圍或已採用')
        require(prose[0]['before_hash'] == entry['start_hash'], '修訂開始後原文已被改動，請保留手改並重新建立範圍')
        entry['adopted'] = prose[0]['after_hash']
        changes.append(change(root, rel(root, tp), dump(task)))
        # Bind the adopted row without declaring the revision task complete.
        data = rows(root)
        m = SCENE.fullmatch(prose[0]['target']) or CHAPTER.fullmatch(prose[0]['target'])
        ch, sc = int(m[1]), int(m[2]) if len(m.groups()) == 2 else 0
        if (ch, sc) in data:
            data[ch, sc]['status'] = '已通過'
            data[ch, sc]['meta']['text'] = prose[0]['after_hash']
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
    journal = {'version': 1, 'id': name, 'kind': kind, 'status': 'prepared', 'review': review,
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
    if j['status'] == 'prepared' and j['kind'] in {'scene', 'chapter'}:
        no_revision(root)
    require(approval.strip(), '須記錄作者明確採用的回覆；工具不能替作者授權')
    require(not (j['missing_reviewers'] or j['review']['unresolved']) or override.strip(), '審閱未完成或仍有未決問題，須記錄作者明確裁決')
    for other in journals(root):
        require(other == p or load(other)['status'] not in {'applying', 'reverting'}, '先恢復另一個中斷採用')
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
        if SCENE.fullmatch(target):
            ch = int(SCENE.fullmatch(target)[1])
            require(rows(root).get((ch, 0), {}).get('status') != '已通過', '整章已採用，請修訂正式章節')
        require(target not in [x['target'] for x in t['targets']], '目標已在修訂中')
        content = inside(root, target).read_bytes()
        t['targets'].append({'target': target, 'start_hash': digest(content), 'start_bytes': base64.b64encode(content).decode(), 'adopted': None})
    atomic(p, dump(t))


def revision_cancel(root, name):
    idle(root)
    p = task_path(root, name); t = load(p)
    require(t['status'] == 'active' and not any(e['adopted'] for e in t['targets']), '部分已採用的修訂須先完成事實同步，不能直接取消')
    require(all(digest(read(root / e['target'])) == e['start_hash'] for e in t['targets']), '正文有手改，須先處理後才可取消')
    t['status'] = 'cancelled'; atomic(p, dump(t))


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
        git('add', '--', *names, env=env)
        if not git('diff', '--cached', '--name-only', '-z', env=env).stdout:
            return 'no-changes'
        # Existing user index remains untouched during commit; reconcile only our paths afterwards.
        git('commit', '-m', message, env=env)
        git('reset', '-q', 'HEAD', '--', *names)
    return 'committed'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=os.environ.get('CLAUDE_PROJECT_DIR', '.'))
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('check'); p.add_argument('path')
    p = sub.add_parser('confirm-plan'); p.add_argument('chapter', type=int)
    for name in ('begin', 'reopen'):
        p = sub.add_parser(name); p.add_argument('chapter', type=int); p.add_argument('scene', type=int, help='收尾使用 0')
    p = sub.add_parser('prepare'); p.add_argument('spec')
    p = sub.add_parser('rollback'); p.add_argument('id'); p.add_argument('--reason', required=True)
    p = sub.add_parser('accept'); p.add_argument('id'); p.add_argument('--approval', required=True); p.add_argument('--override', default='')
    for name in ('revision-start', 'revision-extend'):
        p = sub.add_parser(name); p.add_argument('id'); p.add_argument('targets', nargs='+')
    p = sub.add_parser('revision-cancel'); p.add_argument('id')
    p = sub.add_parser('confirm-import'); p.add_argument('manifest')
    p = sub.add_parser('commit'); p.add_argument('--message', required=True); p.add_argument('paths', nargs='+')
    args = parser.parse_args(argv); root = Path(args.root).resolve()
    try:
        with locked(root):
            c = args.command
            if c == 'check': check(root, args.path)
            elif c == 'confirm-plan': confirm_plan(root, args.chapter)
            elif c in {'begin', 'reopen'}: begin(root, args.chapter, args.scene, c == 'reopen')
            elif c == 'prepare': print(prepare(root, load(inside(root, args.spec))))
            elif c == 'rollback': print(rollback(root, args.id, args.reason))
            elif c == 'accept': print(accept(root, args.id, args.approval, args.override))
            elif c == 'revision-start': revision_start(root, args.id, args.targets)
            elif c == 'revision-extend': revision_extend(root, args.id, args.targets)
            elif c == 'revision-cancel': revision_cancel(root, args.id)
            elif c == 'confirm-import': confirm_import(root, load(inside(root, args.manifest)))
            elif c == 'commit': print(safe_commit(root, args.paths, args.message))
        return 0
    except (Invalid, OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as e:
        print('【寫作流程】' + str(e), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
