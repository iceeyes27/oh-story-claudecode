"""Deterministic, read-only prose degeneration check for scene and chapter candidates.

Ported from zenstory-ai/oh-story-claudecode check-degeneration.js (MIT). It only flags
fingerprints a model cannot self-report -- verbatim loops, truncation, placeholder or
refusal text, and pipeline vocabulary leaking into prose. It never rewrites and never
judges style; naturalness stays with prose-reviewer.

blocking: never legal in prose; regenerate the affected paragraph before review-start.
advisory: may be legal in-story; prose-reviewer verifies each position.
"""
import json
from pathlib import Path
import re

# Long narration sentence repeated >= 3 times, or an identical adjacent line, means the model
# looped. Short lines and quoted dialogue are exempt: deliberate refrain is a genre device.
REPEAT_MIN_LEN = 12
REPEAT_MIN_COUNT = 3
ADJACENT_MIN_LEN = 8

QUOTED_SPANS = [re.compile(p) for p in (r'「[^」]*」', r'『[^』]*』', r'【[^】]*】', r'“[^”]*”', r'‘[^’]*’', r'"[^"]*"')]
SENTENCE_END = re.compile(r'[。！？!?]')
VISIBLE = re.compile(r'[一-鿿Ａ-ｚA-Za-z0-9]')
TERMINAL = re.compile(r'[。！？!?…”"』」）)】’～]$')
FENCE = re.compile(r'^(?:`{3,}|~{3,})')

# (pattern, label, hard). hard patterns scan the whole line; soft ones skip paired quotes,
# because a character may legitimately say "我无法答应你" or play an AI in-story.
PLACEHOLDERS = [
    (re.compile(r'作[为為](一个|一個)?(AI|人工智能|大?[语語]言模型|智能助手|聊天助手)(?:[语語]言模型|大?模型|助手|机器人|機器人)?'
                r'(?=[，,。、；;：:！!？?\s）)」』"】]|我|无法|無法|不能|没法|沒法|$)'), '元信息泄漏（AI 自指）', False),
    (re.compile('�'), '乱码（替换字符）', True),
    (re.compile(r"^(Sure|Certainly|Here'?s|As an AI|I (?:cannot|can't|am unable|apologize))"), '元信息泄漏（英文 AI 腔）', True),
    (re.compile(r'[（(](此处|此處|以下|这里|這裡|下文|后续|後續)?\s*(省略|略)(去|过|過)?[^）)]{0,10}[）)]'), '占位符（括号省略）', True),
    (re.compile(r'(未完待续|未完待續|TODO|占位符|placeholder)'), '占位符', True),
    # "我不能写信" is ordinary first-person narration, so plain 写 needs a preceding 继续.
    (re.compile(r'我(无法|無法|不能)((继续|繼續)(写|寫|创作|創作|生成|下去)|生成(内容|內容|文本|正文)?|创作|創作|续写|續寫|'
                r'完成(这个|這個|本)?(章|篇|场景|場景|创作|創作|请求|請求))'), '元信息泄漏（生成拒绝语）', False),
]

# tier1: pipeline terms from outlines, review and adoption; essentially never legal in prose.
# tier2: chapter-structure words a character could still say in-story, so advisory only.
META_TIER1 = re.compile(
    r'细纲|細綱|情节点|情節點|卷纲|卷綱|功能标签|功能標籤|目标情绪|目標情緒|字数目标|字數目標|'
    r'章首钩子|章首鉤子|章尾钩子|章尾鉤子|出口状态|出口狀態|入场状态|入場狀態|兑现登记|兌現登記|'
    r'兑现编号|兌現編號|文风样本|文風樣本|语文规格|語文規格|创作护栏|創作護欄|累计事实|累計事實')
META_TIER2 = re.compile(
    r'第[一二三四五六七八九十百千万萬两兩0-9]+章|本章|这一章|這一章|上一章|下一章|上章|下章|前一章|'
    r'后一章|後一章|前文|后文|後文|伏笔|伏筆|读者|讀者|任务描述|任務描述')

AI_ISMS_PATTERNS = [
    (re.compile(r'寸影随行|心绪微漾|神情冷凝'), '伪成语/生造词', 'advisory', '正文疑似使用生造词；由审阅者核对词义、文风及表达功能。'),
    (re.compile(r'神经末梢|大脑皮层|多巴胺分泌'), '解剖生理术语穿越', 'advisory', '非现代医学解剖视角疑似混入专业解剖术语；核对时代语境。'),
]
DEMONSTRATIVE_TELL = re.compile(r'^(?:这是|那是|這是)')


def mask_quoted(text):
    """Blank paired quotes with spaces of equal length so columns stay accurate."""
    for pattern in QUOTED_SPANS:
        text = pattern.sub(lambda m: ' ' * len(m.group(0)), text)
    return text


def strip_quoted(text):
    for pattern in QUOTED_SPANS:
        text = pattern.sub('', text)
    return text


def visible_length(text):
    return len(VISIBLE.findall(text))


def compact(text, limit=80):
    text = ' '.join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + '...'


def body_lines(text):
    """Return (line_no, stripped) for prose lines outside front matter, fences and headings."""
    lines = text.splitlines()
    out, fence = [], None
    in_front = bool(lines) and lines[0].strip() == '---'
    for index, line in enumerate(lines):
        stripped = line.strip()
        if in_front:
            if index and stripped == '---':
                in_front = False
            continue
        marker = FENCE.match(stripped)
        if fence:
            if marker and stripped[0] == fence:
                fence = None
            continue
        if marker:
            fence = stripped[0]
            continue
        if stripped and not stripped.startswith('#') and not re.fullmatch(r'-{3,}', stripped):
            out.append((index + 1, stripped))
    return out


def finding(line, column, kind, severity, message, excerpt):
    return {'line': line, 'column': column, 'type': kind, 'severity': severity,
            'message': message, 'excerpt': compact(excerpt)}


def find_repetition(body):
    found = []
    for (_, prev), (no, cur) in zip(body, body[1:]):
        if cur == prev and visible_length(strip_quoted(cur)) >= ADJACENT_MIN_LEN:
            found.append(finding(no, 1, 'verbatim-repeat', 'blocking', '紧邻整行重复，疑似模型打转；重写本段并删除重复。', cur))
    counts, first = {}, {}
    for no, line in body:
        for sentence in SENTENCE_END.split(strip_quoted(line)):
            sentence = sentence.strip()
            if visible_length(sentence) >= REPEAT_MIN_LEN:
                counts[sentence] = counts.get(sentence, 0) + 1
                first.setdefault(sentence, no)
    for sentence, count in counts.items():
        if count >= REPEAT_MIN_COUNT:
            found.append(finding(first[sentence], 1, 'verbatim-repeat', 'blocking',
                                 '同一叙述长句出现 %d 次，疑似模型打转；重写并只保留一处。' % count, sentence))
    return found


def find_truncation(body):
    if not body or TERMINAL.search(body[-1][1]):
        return []
    no, line = body[-1]
    return [finding(no, len(line), 'truncated', 'blocking', '末尾没有句末或收尾标点，疑似生成中断；补完或重写结尾。', line[-24:])]


def find_placeholders(body):
    found = []
    for no, line in body:
        outside = mask_quoted(line)
        for pattern, label, hard in PLACEHOLDERS:
            m = pattern.search(line if hard else outside)
            if m:
                found.append(finding(no, m.start() + 1, 'placeholder-leak', 'blocking',
                                     label + '：正文混入元信息、拒绝语或占位符；重写本段。', line[max(0, m.start() - 4):m.start() + 20]))
                break
    return found


def find_meta_leak(body):
    found = []
    for no, line in body:
        m = META_TIER1.search(mask_quoted(line))
        quoted = False
        if not m:
            m = META_TIER1.search(line)
            quoted = bool(m)
        if m:
            note = '；位于引号内，若角色在故事内真实讨论创作可保留' if quoted else ''
            found.append(finding(no, m.start() + 1, 'meta-leak', 'advisory' if quoted else 'blocking',
                                 '流程术语「%s」混入正文%s。' % (m.group(0), note), line[max(0, m.start() - 6):m.start() + 18]))
            continue
        m = META_TIER2.search(line)
        if m:
            found.append(finding(no, m.start() + 1, 'meta-leak', 'advisory',
                                 '章节结构词「%s」疑似混入正文；故事内真实阅读、讨论或称呼时保留。' % m.group(0),
                                 line[max(0, m.start() - 6):m.start() + 18]))
    return found


def find_ai_isms(body):
    found = []
    tell_counts = 0
    for no, line in body:
        outside = mask_quoted(line)
        for pattern, label, severity, message in AI_ISMS_PATTERNS:
            m = pattern.search(outside)
            if m:
                found.append(finding(no, m.start() + 1, 'ai-ism', severity,
                                     label + '：' + message, line[max(0, m.start() - 4):m.start() + 20]))
                break
        stripped = outside.strip()
        if DEMONSTRATIVE_TELL.match(stripped):
            tell_counts += 1
            if tell_counts >= 2:
                found.append(finding(no, 1, 'ai-ism', 'advisory',
                                     '指认说明腔：多处以「这是/那是」指示词下定义；由审阅者核对功能，不据命中自动改稿。', stripped[:24]))
    return found


def scan(text):
    body = body_lines(text)
    found = (find_repetition(body) + find_truncation(body) +
             find_placeholders(body) + find_meta_leak(body) + find_ai_isms(body))
    return sorted(found, key=lambda f: (f['line'], f['column']))


def run(root, paths, as_json=False):
    """Print findings for each file; return 1 when any blocking finding exists."""
    results = []
    for name in paths:
        path = Path(name) if Path(name).is_absolute() else Path(root) / name
        for item in scan(path.read_text(encoding='utf-8')):
            results.append(dict(file=name, **item))
    if as_json:
        print(json.dumps({'findings': results}, ensure_ascii=False, indent=2))
    else:
        for f in results:
            print('%s:%d:%d: [%s] %s: %s（%s）' % (f['file'], f['line'], f['column'], f['severity'], f['type'], f['message'], f['excerpt']))
        blocking = sum(f['severity'] == 'blocking' for f in results)
        print('prose-check：blocking %d，advisory %d' % (blocking, len(results) - blocking))
    return 1 if any(f['severity'] == 'blocking' for f in results) else 0
