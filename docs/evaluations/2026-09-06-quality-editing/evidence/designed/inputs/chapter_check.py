# coding: utf-8
from pathlib import Path
import json, subprocess, sys, datetime, hashlib, shutil, re
b=Path(__file__).resolve().parents[1];r=b.parent/'runtime/.agents/skills';n=int(sys.argv[1])
p=json.loads((b/'inputs/plan-data.json').read_text())[n-1]
raw=b/'raw'/f'第{n:03d}章_{p["title"]}.md';candidate=b/'候选'/raw.name
raw_hash=hashlib.sha256(raw.read_bytes()).hexdigest()
shutil.copyfile(raw,candidate)
commands={
'wordcount':['python3',str(r/'story-write/scripts/storyctl.py'),'wordcount','measure','--file',str(raw),'--chapter',str(n)],
'ai-patterns':['node',str(r/'_shared/scripts/check-ai-patterns.js'),'--check','--fail-on=blocking','--json','--book-dir',str(b),str(candidate)],
'degeneration':['node',str(r/'_shared/scripts/check-degeneration.js'),'--check','--fail-on=blocking','--json',str(candidate)],
'outline-copy':['node',str(r/'_shared/scripts/check-outline-copy.js'),str(candidate)]}
results={}
for name,args in commands.items():
 run=subprocess.run(args,cwd=b,text=True,capture_output=True)
 result={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':'raw_saved_candidate_copied_no_edit','command':args,'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'raw_sha256':raw_hash,'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest()}
 (b/'checks'/f'chapter-{n:02d}.{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 results[name]=result
 print(name,run.returncode,run.stdout[:6000])
body='\n'.join(raw.read_text().splitlines()[1:])
sentences=[re.sub(r'\s','',s) for s in re.split(r'[。！？!?]+',body) if re.sub(r'[\s\"“”]','',s)]
lengths=[len(s.strip('\"“”')) for s in sentences];total=len(lengths)
stats={'source':'Python execution; split body on 。！？!?; strip surrounding dialogue quotes; exclude title and whitespace; sentence-ending separator not counted','sentence_count':total,'short_lt15_percent':round(100*sum(x<15 for x in lengths)/total,2),'medium_15to30_percent':round(100*sum(15<=x<=30 for x in lengths)/total,2),'long_gt30_percent':round(100*sum(x>30 for x in lengths)/total,2),'mean_sentence_length':round(sum(lengths)/total,2),'raw_sha256':raw_hash,'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),'blank_body_lines':[i+2 for i,line in enumerate(raw.read_text().splitlines()[1:]) if not line.strip()],'dialogue_quote_count':body.count('"'),'raw_preserved':raw_hash==hashlib.sha256(raw.read_bytes()).hexdigest()}
(b/'checks'/f'chapter-{n:02d}.statistics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2))
print('statistics',json.dumps(stats,ensure_ascii=False))
