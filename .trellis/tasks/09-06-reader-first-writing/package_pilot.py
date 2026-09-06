# -*- coding: utf-8 -*-
"""Preserve the one-attempt pilot and prepare prose-only blinded readings."""
from pathlib import Path
import datetime
import hashlib
import importlib.util
import json
import random
import shutil

REPO = Path(__file__).resolve().parents[3]
TASK = Path(__file__).resolve().parent
LOCATION = json.loads((TASK / 'experiment-location.json').read_text())
SOURCE = Path(LOCATION['experiment_root']) / 'pilot-native'
OUT = REPO / 'docs/evaluations/2026-09-06-reader-first'
OUT.mkdir(parents=True, exist_ok=True)
spec = importlib.util.spec_from_file_location('wc', REPO / 'skills/_shared/scripts/wordcount_core.py')
wc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wc)

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

mapping_path = OUT / 'mapping.json'
if mapping_path.exists():
    mapping = json.loads(mapping_path.read_text())
else:
    codes = ['R17', 'R42', 'R86']
    random.SystemRandom().shuffle(codes)
    mapping = dict(zip(['baseline', 'cleanup', 'combined'], codes))
    mapping_path.write_text(json.dumps(mapping, indent=2) + '\n')

rows = []
for arm, code in mapping.items():
    directory = OUT / 'evidence' / arm
    directory.mkdir(parents=True, exist_ok=True)
    for name in ['policy.md', 'policy.json']:
        shutil.copyfile(SOURCE / arm / name, directory / ('policy.txt' if name.endswith('.md') else name))
    texts = []
    for chapter in range(1, 4):
        prose = SOURCE / arm / f'chapter-{chapter:02}.md'
        prompt = SOURCE / arm / f'chapter-{chapter:02}.prompt.txt'
        assert prose.is_file() and prompt.is_file()
        shutil.copyfile(prose, directory / prose.name)
        shutil.copyfile(prompt, directory / prompt.name)
        texts.append(prose.read_text())
        rows.append({
            'arm': arm, 'blind_code': code, 'chapter': chapter,
            'writer_agent': {'baseline': 'sample_pine', 'cleanup': 'sample_maple', 'combined': 'sample_cedar'}[arm],
            'creative_attempt': 1,
            'raw_prose': str((directory / prose.name).relative_to(OUT)), 'body_sha256': sha(prose),
            'prompt': str((directory / prompt.name).relative_to(OUT)), 'prompt_sha256': sha(prompt),
            'prompt_chars': len(prompt.read_text()), 'length': wc.fanqie_length(prose.read_text()),
            'provenance_note': 'One native writer per arm, same writer continued all three chapters. Model and effort inherited from parent; exact snapshot and seed not exposed. Byte-identical copy, no repair.',
        })
    readings = OUT / 'readings'
    readings.mkdir(exist_ok=True)
    (readings / f'{code}.md').write_text('\n\n'.join(texts))
    reviews = OUT / 'reviews'
    reviews.mkdir(exist_ok=True)
    rubric = '''你是独立的普通读者。这是单一匿名版本的小说前三章。只能读下方正文，不能读取其他文件、设定、作者意图、其他版本、评分或规则资料，不能搜索。只依据正文顺读，不代填真人反馈，不改写小说。你的结果是模型阅读代理证据。

请按章节分别记录：
1. 用自己的话简述发生什么、主角为何行动、阻碍和结果；前提不够就明确说不懂，并引用原句。
2. 第一处想跳读或需要回读的位置，引用原句并解释；没有就明确没有。
3. 最有趣或最想继续读的一处，引用原句并解释。
4. 本章实际兑现了什么，结尾有没有具体继续读的理由。
最后以三章整体看因果、人物、时间、金额是否前后冲突，是否重复疲劳，读完后是否愿意继续及原因。列最值得修改的 1–2 点；不为了凑项凭空找问题，不打总分或宣布胜出。原句引用必须来自正文，标章节。正文有细节让你疑惑也照实记录，不得用常识替它补证。
'''
    (reviews / f'{code}.input.txt').write_text(rubric + f'\n匿名版本：{code}\n\n' + '\n\n'.join(texts))

manifest = json.loads((SOURCE / 'manifest.json').read_text())
manifest['post_freeze_changes'].append('Final deployment documents bare-draft wordcount measure before complete candidate check. Agent priority allows linked requirements in one sentence. Pilot did not include full agent template; frozen prompts and output unchanged.')
manifest['packaged_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest['records'] = rows
manifest['blind_mapping'] = 'mapping.json'
manifest['review_design'] = 'One isolated model reader per arm; only that anonymous three-chapter prose. Same rubric, no other versions or oracle. Not human evidence; no efficacy inference.'
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
shutil.copyfile(TASK / 'pilot-story.json', OUT / 'story-input.json')
print(json.dumps({'output': str(OUT), 'mapping': mapping, 'lengths': [{k: r[k] for k in ['arm', 'chapter', 'length']} for r in rows]}, ensure_ascii=False, indent=2))
