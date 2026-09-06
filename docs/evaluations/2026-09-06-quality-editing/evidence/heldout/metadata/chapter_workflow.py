# -*- coding: utf-8 -*-
from pathlib import Path
import sys,json,hashlib,subprocess,datetime,re,shutil
root=Path.cwd(); rt=root.parent/'runtime/.agents/skills'; n=int(sys.argv[2]); stage=sys.argv[1]
plans=json.loads((root/'metadata/planning-source.json').read_text()); p=plans[n-1]; outline=root/f'大纲/细纲_第{n:03d}章.md'; sk=root/f"骨架/第{n:03d}章_{p['title']}.md"; raw=root/f"raw/第{n:03d}章_{p['title']}.md"; candidate=root/f"候选/第{n:03d}章_{p['title']}.md"
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def record(cmd,tag):
 start=datetime.datetime.now(datetime.timezone.utc).isoformat(); r=subprocess.run([str(a) for a in cmd],capture_output=True,text=True); log=root/f'logs/chapter-{n:02d}.{tag}.log'; log.write_text(r.stdout+r.stderr,encoding='utf-8'); result={'stage':tag,'command':[str(a) for a in cmd],'exit_code':r.returncode,'log':str(log.relative_to(root)),'started_at':start,'completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()};
 with (root/'metadata/command-exits.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(result,ensure_ascii=False)+'\n')
 print(json.dumps(result,ensure_ascii=False));return r.returncode
if stage=='pre':
 assert not raw.exists(),'raw is immutable; no second generation'
 statuses=[record(['node',rt/'story-write/scripts/check-outline-contract.js','--json','--project',root,'--chapter',n],'pre.outline-contract'),record(['python3',rt/'story-write/scripts/check-outline-causal.py',root,'--strict',f'--from={n}',f'--to={n}','--json'],'pre.outline-causal'),record(['node',rt/'story-write/scripts/check-chapter-skeleton.js','--json',sk],'pre.skeleton')]
 if any(statuses):sys.exit(1)
 sources=[(rt/'story-setup/references/codex/agents/narrative-writer.toml',None),(rt/'story-write/references/reader-first-writing.md',None),(rt/'story-write/references/long-format.md',None),(rt/'_shared/references/anti-ai-writing.md',[1,180]),(outline,None),(sk,None),(root/'inputs/character-handoff.json',None),(root/'inputs/scene-design-feedback.json',None)]
 if n>1:sources.append((root/f"raw/第{n-1:03d}章_{plans[n-2]['title']}.md",None))
 items=[]
 for src,lines in sources:
  whole=src.read_text(encoding='utf-8'); content='\n'.join(whole.splitlines()[lines[0]-1:lines[1]])+'\n' if lines else whole
  items.append({'path':str(src),'sha256':sha(src),'range':lines or 'full','content':content,'characters':len(content)})
 request={'chapter':n,'title':p['title'],'quality_profile':'fanqie-long-v2','target':2500,'range':[2200,2800],'caliber':'visible_chars_v1','han_requested_range':[2200,2800],'write_once':True,'raw_output':str(raw),'candidate_copy':str(candidate),'pov':'第三人称贴近宋棠','current_scope':p,'constraints':['同一天准备与展览开放；普通住户往来','严格依据当前细纲；不提前泄露下一章','前章raw只是本隔离试验连续稿，未获作者采用','不阅读其他臂或盲评；不改raw；不生成追踪或读者凭证'],'style':'白话顺读；无作者认可样例；线索通过具体发现与人物回应交代'}
 packet={'schema':'heldout-actual-writer-packet/v1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'request':request,'sources':items,'provenance_note':'Writer inherited full parent task and read full story-input.json during planning. Full frozen template used direct, custom agent registry unavailable. No deployed project template was successfully read.'}
 (root/f'packets/chapter-{n:02d}.writer-packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2),encoding='utf-8')
 (root/f'metadata/chapter-{n:02d}.prewrite-reads.json').write_text(json.dumps({'stage':'before_draft','files':[{k:v for k,v in i.items() if k!='content'} for i in items],'initial_requirements':{'path':'inputs/story-input.json','sha256':sha(root/'inputs/story-input.json'),'range':'full'}},ensure_ascii=False,indent=2),encoding='utf-8')
 print('PREWRITE_READY',n)
if stage=='post':
 assert raw.exists(); assert not candidate.exists();shutil.copyfile(raw,candidate)
 record(['python3',rt/'story-write/scripts/storyctl.py','wordcount','measure','--file',raw],'post.wordcount')
 record(['node',rt/'_shared/scripts/check-ai-patterns.js','--check','--fail-on=blocking',candidate],'post.scan')
 record(['node',rt/'_shared/scripts/check-degeneration.js','--check','--json','--fail-on=blocking',candidate],'post.degeneration')
 record(['node',rt/'story-write/scripts/check-outline-copy.js','--outline',outline,candidate],'post.outline-copy')
 body='\n'.join(raw.read_text(encoding='utf-8').splitlines()[1:]); han=len(re.findall('[\u4e00-\u9fff]',body)); visible=len(re.sub(r'\s','',body)); sentences=[re.sub(r'\s','',s) for s in re.split('[。！？!?]',body) if re.sub(r'[\s\"，,：:；;]','',s)]; lengths=[len(s) for s in sentences]
 count={'chapter':n,'raw_sha256':sha(raw),'candidate_sha256':sha(candidate),'han_chars':han,'visible_chars_v1':visible,'han_in_range':2200<=han<=2800,'visible_in_range':2200<=visible<=2800,'sentences':len(lengths),'sentence_distribution':{'short_lt_15':sum(x<15 for x in lengths)/len(lengths),'medium_15_30':sum(15<=x<=30 for x in lengths)/len(lengths),'long_gt_30':sum(x>30 for x in lengths)/len(lengths),'mean':sum(lengths)/len(lengths)},'raw_attempts':1,'reading_edit_passes':0}
 (root/f'metadata/chapter-{n:02d}.counts.json').write_text(json.dumps(count,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(count,ensure_ascii=False))
