from pathlib import Path
import subprocess,json,sys,datetime,re,hashlib
r=Path(__file__).resolve().parent.parent
runtime=r.parent/'runtime/.agents/skills'
n=int(sys.argv[1]);mode=sys.argv[2]
titles=['一百块定金','鱼要有盖','先等它凉下来'];p=r/f'候选/第{n:03d}章_{titles[n-1]}.md'
if mode=='pre':
 commands=[('skeleton',['node',str(runtime/'story-write/scripts/check-chapter-skeleton.js'),'--json',str(r/f'骨架/{p.name}')]),('outline-contract',['node',str(runtime/'story-write/scripts/check-outline-contract.js'),'--json','--project',str(r),'--chapter',str(n)]),('outline-causal',['python3',str(runtime/'story-write/scripts/check-outline-causal.py'),str(r),'--strict',f'--from={n}',f'--to={n}','--json'])]
else:
 commands=[('wordcount',['python3',str(runtime/'story-write/scripts/storyctl.py'),'wordcount','measure','--file',str(p)]),('ai-patterns',['node',str(runtime/'_shared/scripts/check-ai-patterns.js'),'--check','--fail-on=blocking','--json',str(p)]),('degeneration',['node',str(runtime/'_shared/scripts/check-degeneration.js'),'--check','--fail-on=blocking','--json',str(p)]),('outline-copy',['node',str(runtime/'_shared/scripts/check-outline-copy.js'),str(p)])]
records=[]
for key,cmd in commands:
 start=datetime.datetime.now(datetime.timezone.utc).isoformat()
 result=subprocess.run(cmd,cwd=str(r),capture_output=True,text=True)
 log=r/f'logs/chapter-{n:02d}.{mode}.{key}.log';log.write_text(result.stdout+('\nSTDERR:\n'+result.stderr if result.stderr else ''))
 rec={'check':key,'command':cmd,'exit_code':result.returncode,'started_at':start,'log':str(log)}
 records.append(rec)
 print(key,'exit',result.returncode)
 if key=='wordcount' or result.returncode:print((result.stdout+result.stderr)[:1800])
(r/f'logs/chapter-{n:02d}.{mode}.json').write_text(json.dumps({'stage':mode,'preflight_before_draft':mode=='pre' and not (r/'raw'/p.name).exists(),'tracking_state_present':(r/'追踪/_tracking-state.json').exists(),'records':records},ensure_ascii=False,indent=2)+'\n')
f=r/'inputs/read-files.json';files=json.loads(f.read_text())
for _,cmd in commands:
 for fp in [cmd[1],str(log)]:
  if fp not in files:files.append(fp)
if mode=='post':
 body='\n'.join(p.read_text().splitlines()[1:]);sent=[re.sub(r'\s','',s) for s in re.split(r'[。！？!?]+["”]?',body)];sent=[s for s in sent if s]
 sizes=[len(v) for v in sent];counts={'short_lt_15':sum(v<15 for v in sizes),'medium_15_30':sum(15<=v<=30 for v in sizes),'long_gt_30':sum(v>30 for v in sizes)}
 stats={'definition':'正文去标题，按。！？!?分句，移除空白；句内标点计入，仅作风格统计','sentences':len(sizes),'average':sum(sizes)/len(sizes),'counts':counts,'percent':{k:round(v/len(sizes)*100,2) for k,v in counts.items()},'raw_sha256':hashlib.sha256((r/'raw'/p.name).read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
 (r/f'logs/chapter-{n:02d}.sentence-stats.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
 for fp in [str(p),str(r/'raw'/p.name)]:
  if fp not in files:files.append(fp)
f.write_text(json.dumps(files,ensure_ascii=False,indent=2)+'\n')
