"""Draft matching for manual scoring: show each answer / protected item beside reported issues that
quote overlapping text. It only proposes candidates; final hits are judged by hand in 评分.json."""
import json
import pathlib
import re
import sys

EVAL = pathlib.Path(__file__).resolve().parents[2]


def norm(s):
    return re.sub(r'[\s“”"「」『』，。！？、：；…—\-]', '', s)


def overlap(a, b, n=6):
    a, b = norm(a), norm(b)
    if len(a) < n:
        return a in b
    return any(a[i:i + n] in b for i in range(len(a) - n + 1))


def issues(report):
    section = re.split(r'\n##\s*(?:前文不足|保留项)', report)[0]
    out = []
    for chunk in re.split(r'\n\s*-\s*id:\s*', section)[1:]:
        sev = re.search(r'severity:\s*([^\n#]+)', chunk)
        what = re.search(r'issue:\s*"?([^\n]{0,70})', chunk)
        out.append({'id': chunk.split('\n')[0].strip(), 'sev': sev.group(1).strip()[:6] if sev else '',
                    'issue': what.group(1) if what else '', 'text': chunk})
    return out


def main(folder, pattern):
    for f in sorted(pathlib.Path(folder).glob(pattern)):
        key = json.loads((EVAL / '答案' / (f.name[:3] + '.json')).read_text(encoding='utf-8'))
        found = issues(f.read_text(encoding='utf-8'))
        print('==', f.name, '问题数', len(found), 'S1/S2', sum(bool(re.match(r'S[12]', x['sev'])) for x in found))
        items = key['应抓'] + [{'id': '保护', '证据': p['证据'], '说明': p['理由'], '预期严重度': ''} for p in key['不应报']]
        for a in items:
            print(' *', a['id'], a['预期严重度'], a['说明'][:40])
            for h in found:
                if overlap(a['证据'], h['text']):
                    print('    ->', h['id'], h['sev'], '|', h['issue'][:70])
        print('  全部S1/S2:', [(x['id'], x['issue'][:30]) for x in found if re.match(r'S[12]', x['sev'])])


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
