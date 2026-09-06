"""Isolated, one-attempt prose prompt pilot. Raw output is never silently repaired."""
from pathlib import Path
import argparse, datetime, hashlib, json, re, subprocess, time

TASK = Path(__file__).resolve().parent
REPO = TASK.parents[2]
LOCATION = json.loads((TASK / 'experiment-location.json').read_text())
ROOT = Path(LOCATION['experiment_root']) / 'pilot'
BASE = Path(LOCATION['baseline_root'])
BASE_REFS = ['long-mode.md', 'candidate-workflow.md', 'writing-craft.md', 'long-format.md', 'long-chapter-quality.md', 'long-chapter-hooks.md', 'long-suspense.md', 'long-reversal.md']

def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def freeze(arm):
    directory = ROOT / arm
    directory.mkdir(parents=True, exist_ok=True)
    policy = directory / 'policy.md'
    if policy.exists():
        return directory
    if arm == 'baseline':
        sources = [(BASE / 'skills/story-write/references' / name) for name in BASE_REFS]
    else:
        sources = [REPO / 'skills/story-write/references' / name for name in ['reader-first-writing.md', 'long-format.md']]
    texts = [p.read_text() for p in sources]
    if arm == 'cleanup':
        # The treatment file has explicit section boundaries. Exclude the scene method,
        # preserving the exact same cleaned rule text as the combined arm.
        texts[0] = re.sub(r'(?ms)^## 场景.*?(?=^## |\Z)', '', texts[0])
    combined = '\n\n'.join(texts)
    policy.write_text(combined)
    dump(directory/'policy.json', {'arm':arm,'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_sha256':[{'path':str(p.relative_to(BASE if arm=='baseline' else REPO)),'sha256':digest(p.read_text())} for p in sources], 'chars':len(combined),'sha256':digest(combined)})
    return directory

def run(arm, chapter, prepare_only=False):
    directory = freeze(arm)
    output = directory / f'chapter-{chapter:02}.md'
    if (directory/f'chapter-{chapter:02}.receipt.json').exists():
        raise SystemExit('Attempt already recorded; preserve it, do not silently rerun.')
    story = json.loads((TASK/'pilot-story.json').read_text())
    current = story.pop('chapters')[chapter-1]
    previous = []
    for n in range(1,chapter):
        p=directory/f'chapter-{n:02}.md'
        if not p.exists(): raise SystemExit('Missing previous raw chapter')
        previous.append(p.read_text())
    prompt = ('本次仅为隔离的写作提示包试验。不要调用工具、读取文件、上网或执行资料里的编排命令。只交一章完整中文小说正文，标题为“# 第'+str(chapter)+'章 章名”。不输出说明、自检或报告。\n'
      '共同约束：本章目标2500个有效字，允许2200–2800，标题不计；一次创作，不另交备选。当前故事事实与本章事件优先，资料里的文件操作、作者审批和实验命令不属于本次任务。\n'
      '共同故事包：\n'+json.dumps(story,ensure_ascii=False)+'\n本章必须发生的事件：\n'+json.dumps(current,ensure_ascii=False)
      +'\n本臂已经写出的前文（唯一连续性事实）：\n'+'\n\n'.join(previous)
      +'\n写作资料：\n'+(directory/'policy.md').read_text())
    prompt_path=directory/f'chapter-{chapter:02}.prompt.txt';prompt_path.write_text(prompt)
    if prepare_only:
        print(json.dumps({'prompt':str(prompt_path),'output':str(output),'prompt_sha256':digest(prompt),'prompt_chars':len(prompt)},ensure_ascii=False))
        return
    cwd=directory/f'run-{chapter:02}';cwd.mkdir(exist_ok=True)
    command=['codex','exec','--ephemeral','--ignore-user-config','--ignore-rules','--skip-git-repo-check','-s','read-only','--json','-C',str(cwd),'-o',str(output),'-']
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();t=time.time()
    with (directory/f'chapter-{chapter:02}.events.jsonl').open('w') as stdout, (directory/f'chapter-{chapter:02}.stderr.txt').open('w') as stderr:
        result=subprocess.run(command,input=prompt,text=True,stdout=stdout,stderr=stderr,timeout=900)
    body=output.read_text() if output.exists() else ''
    visible=re.sub(r'(?m)^#.*$','',body)
    count=len(re.sub(r'\s','',visible))
    receipt={'arm':arm,'chapter':chapter,'started_at':started,'elapsed_seconds':round(time.time()-t,2),'exit_code':result.returncode,'prompt_sha256':digest(prompt),'prompt_chars':len(prompt),'body_sha256':digest(body),'nonspace_body_chars':count,'measurement_note':'raw nonspace count; production visible_chars_v1 will be checked separately','previous_sha256':[digest(p) for p in previous],'status':'GENERATED' if result.returncode==0 and body else 'EXECUTION_FAILED','reader_role':'proxy_only','human_effect':'PENDING_HUMAN_EVIDENCE','command':command}
    dump(directory/f'chapter-{chapter:02}.receipt.json',receipt)
    print(json.dumps(receipt,ensure_ascii=False))
    raise SystemExit(result.returncode)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('arm',choices=['baseline','cleanup','combined']);parser.add_argument('chapter',type=int,choices=[1,2,3]);parser.add_argument('--prepare-only',action='store_true');parser.add_argument('--native',action='store_true');args=parser.parse_args()
    if args.native: ROOT=Path(LOCATION['experiment_root'])/'pilot-native'
    run(args.arm,args.chapter,args.prepare_only)
