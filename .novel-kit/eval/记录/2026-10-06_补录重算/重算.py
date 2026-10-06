"""Rescore the Claude baseline and severity-floor runs against the answers after the 2026-10-06 author additions.
Original per-item verdicts come from each run's 评分.json; added items from 补录判定.json in this folder."""
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
EVAL = HERE.parents[1]
RUNS = {'基线': '2026-10-04_Claude基线', '定级下限': '2026-10-05_定级下限'}
HIT = {'S1', 'S2', 'S3', 'S4', '待核'}  # 与原评分同口径：列为待核也算检出


def answers(frozen):
    out = {}
    for f in sorted((EVAL / '答案').glob('*.json')):
        for a in json.loads(f.read_text(encoding='utf-8'))['应抓']:
            if frozen and '补录' in a:
                continue
            out[a['id']] = a['预期严重度']
    return out


def score(verdicts, key, n):
    reg = [i for i in key if i[:1] in 'ABCD' or i.startswith('K02-1') or ('-R' in i and i[:1] == 'K')]
    s12 = [i for i in reg if key[i] in ('S1', 'S2')]
    e01 = [i for i in key if i.startswith('E01')]
    s3 = [i for i in key if key[i] == 'S3']
    hit = lambda i: verdicts[i][n] in HIT
    return {'回归集检出': f'{sum(map(hit, reg))}/{len(reg)}',
            'S1S2达标': f'{sum(verdicts[i][n] in ("S1", "S2") for i in s12)}/{len(s12)}',
            'E01检出': f'{sum(map(hit, e01))}/{len(e01)}',
            '预期S3报S2': sum(verdicts[i][n] in ('S1', 'S2') for i in s3)}


def main():
    add = json.loads((HERE / '补录判定.json').read_text(encoding='utf-8'))
    result = {}
    for name, folder in RUNS.items():
        base = json.loads((EVAL / '记录' / folder / '评分.json').read_text(encoding='utf-8'))['判定']
        merged = {**base, **add[name]}
        for label, frozen in (('冻结答案', True), ('补录后', False)):
            key = answers(frozen)
            missing = [i for i in key if i not in merged]
            assert not missing, (name, missing)
            result.setdefault(name, {})[label] = [score(merged, key, n) for n in range(3)]
        result[name]['补录后K组答案外S1S2'] = [len(x) for x in add['K组答案外S1S2_补录后'][name]]
    print(json.dumps(result, ensure_ascii=False, indent=1))
    (HERE / '重算结果.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
