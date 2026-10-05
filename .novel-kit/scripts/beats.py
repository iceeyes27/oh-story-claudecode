"""Split a candidate into beats with numbered sentences, and verify per-sentence review coverage.

The coordinator chooses beat boundaries (by action unit); this module only checks that they tile
the prose exactly, numbers every sentence as `幕-句`, and later proves each reviewer report gave a
verdict for every sentence it was assigned. It never judges prose.
"""
import json
from pathlib import Path
import re

# A sentence ends at terminal punctuation plus any closing quotes/brackets that follow it.
SENTENCE = re.compile(r'.*?(?:[。！？!?]+|…{1,2}|……)[”’」』）)】]*|.+$')
SENTENCE_ID = re.compile(r'(?<![\d-])(\d{1,3})-(\d{2,3})(?![\d-])')
VERDICTS = ('通过', '问题', '待核')


def is_prose(line):
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith('#') and not re.fullmatch(r'-{3,}', stripped)


def sentences(paragraph):
    paragraph = paragraph.strip()
    return [s.strip() for s in SENTENCE.findall(paragraph) if s.strip()]


def split(text, beats):
    """Return numbered beats; reject gaps, overlaps, empty beats or boundaries outside the prose."""
    lines = text.splitlines()
    prose = [i + 1 for i, line in enumerate(lines) if is_prose(line)]
    if not prose:
        raise ValueError('对象没有正文段落')
    if not isinstance(beats, list) or not beats:
        raise ValueError('分幕清单不可空白')
    out, expected = [], prose[0]
    for no, beat in enumerate(beats, 1):
        start, end = beat.get('start_line'), beat.get('end_line')
        if type(start) is not int or type(end) is not int or not 1 <= start <= end <= len(lines):
            raise ValueError('第%d幕行号不合法' % no)
        first = next((n for n in prose if n >= start), None)
        if first != expected:
            raise ValueError('第%d幕起点须接上一幕之后的第一段正文（第%d行）' % (no, expected))
        covered = [n for n in prose if start <= n <= end]
        if not covered:
            raise ValueError('第%d幕没有正文段落' % no)
        items, count = [], 0
        for n in covered:
            for s in sentences(lines[n - 1]):
                count += 1
                items.append({'id': '%d-%02d' % (no, count), 'line': n, 'text': s})
        label = str(beat.get('label', '')).strip()
        if not label:
            raise ValueError('第%d幕须写明动作单元名称' % no)
        out.append({'no': no, 'label': label, 'start_line': start, 'end_line': end, 'sentences': items})
        later = [n for n in prose if n > end]
        expected = later[0] if later else None
    if expected is not None:
        raise ValueError('分幕未覆盖到结尾，第%d行起的正文没有归属' % expected)
    return out


def numbered_markdown(target, beats):
    parts = ['# %s 分幕编号\n' % target]
    for beat in beats:
        parts.append('\n## 第%d幕：%s（第%d–%d行）\n\n' % (beat['no'], beat['label'], beat['start_line'], beat['end_line']))
        parts.extend('[%s] %s\n' % (s['id'], s['text']) for s in beat['sentences'])
    return ''.join(parts)


def coverage(numbered, report, beat_numbers=None, per_beat=False):
    """Return missing ids (sentence mode) or missing beat numbers (per-beat mode)."""
    beats = [b for b in numbered['beats'] if not beat_numbers or b['no'] in beat_numbers]
    if beat_numbers and len(beats) != len(set(beat_numbers)):
        raise ValueError('指定的幕号不存在')
    lines = report.splitlines()
    if per_beat:
        found = {int(m) for line in lines if any(v in line for v in VERDICTS)
                 for m in re.findall(r'第\s*(\d+)\s*幕', line)}
        return ['第%d幕' % b['no'] for b in beats if b['no'] not in found]
    judged = {'%d-%s' % (int(a), b) for line in lines if any(v in line for v in VERDICTS)
              for a, b in SENTENCE_ID.findall(line)}
    return [s['id'] for b in beats for s in b['sentences'] if s['id'] not in judged]


def remap(old, new):
    """Map sentence ids across a revision by aligning sentence text; no judgement of the edit itself.

    Returns rows of (old_id, new_id, kind) where kind is 未改、改写、删除 or 新增. A rewritten run of
    sentences maps pairwise; surplus sentences on either side become 删除 or 新增.
    """
    from difflib import SequenceMatcher
    a = [s for b in old['beats'] for s in b['sentences']]
    b = [s for x in new['beats'] for s in x['sentences']]
    rows = []
    matcher = SequenceMatcher(None, [s['text'] for s in a], [s['text'] for s in b], autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            rows += [(a[i]['id'], b[j]['id'], '未改') for i, j in zip(range(i1, i2), range(j1, j2))]
            continue
        pairs = min(i2 - i1, j2 - j1)
        rows += [(a[i1 + k]['id'], b[j1 + k]['id'], '改写') for k in range(pairs)]
        rows += [(a[i]['id'], None, '删除') for i in range(i1 + pairs, i2)]
        rows += [(None, b[j]['id'], '新增') for j in range(j1 + pairs, j2)]
    return rows


def remap_markdown(rows):
    out = ['| 旧句号 | 新句号 | 变化 |', '|---|---|---|']
    out += ['| %s | %s | %s |' % (o or '—', n or '—', k) for o, n, k in rows]
    return '\n'.join(out) + '\n'
