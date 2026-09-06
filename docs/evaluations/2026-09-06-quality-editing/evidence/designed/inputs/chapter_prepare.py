# coding: utf-8
from pathlib import Path
import json, subprocess, sys, datetime
b=Path(__file__).resolve().parents[1]
r=b.parent/'runtime/.agents/skills'
n=int(sys.argv[1]);plans=json.loads((b/'inputs/plan-data.json').read_text());p=plans[n-1]
commands={
'skeleton':['node',str(r/'story-write/scripts/check-chapter-skeleton.js'),'--dir',str(b/'骨架'),'--from',str(n),'--to',str(n),'--json'],
'outline-contract':['node',str(r/'story-write/scripts/check-outline-contract.js'),'--json','--project',str(b),'--chapter',str(n)],
'outline-causal':['python3',str(r/'story-write/scripts/check-outline-causal.py'),str(b),'--strict',f'--from={n}',f'--to={n}','--json']}
for name,args in commands.items():
 run=subprocess.run(args,cwd=b,text=True,capture_output=True)
 result={'time':datetime.datetime.now(datetime.timezone.utc).isoformat(),'stage':'before_raw_draft','command':args,'exit_code':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'tracking_exists':(b/'追踪/_tracking-state.json').exists()}
 (b/'checks'/f'chapter-{n:02d}.{name}.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
 print(name,run.returncode,run.stdout if run.returncode else '')
s=json.loads((b/'inputs/story-input.json').read_text())
outline=b/'大纲'/f'细纲_第{n:03d}章.md';skeleton=b/'骨架'/f'第{n:03d}章_{p["title"]}.md'
prev='第一章，无上一章。' if n==1 else (b/'raw'/f'第{n-1:03d}章_{plans[n-2]["title"]}.md').read_text()
sections={
'本次要求':f'原创隔离试写 designed 臂，第{n}章《{p["title"]}》；quality_profile=fanqie-long-v2；目标2500，采用口径visible_chars_v1，区间2200–2800。不设置 quality_treatment_mode。继承当前模型和effort；未调用配置CLI launcher。每章只创作一个完整初稿，先存raw再原样复制候选；本轮不执行阅读编辑或重试，不自报reader结果。',
'本章细纲（唯一剧情蓝图）':outline.read_text(),
'本章骨架（覆盖相同语义一次）':skeleton.read_text(),
'关键人物材料及来源':'来源：inputs/story-input.json 的 characters 与 character_details；策略授权来自 inputs/arm-plan.md 和 design.md。本段保留当前出场人，计划不是追踪事实。\n'+json.dumps({name:{'identity':s['characters'][name],**data} for name,data in s['character_details'].items() if name!='周建国' or n==2},ensure_ascii=False,indent=2),
'事实红线':'\n'.join(s['fixed_facts'])+'\n只按当前章允许释放的结果写，不能以整本固定结局提前兑现；四只干净密闭周转箱为本臂已批准的搬运单位。无已采用正文，无追踪事务；本臂此前原稿仅供隔离样章连续性承接。',
'作者偏好与认可样例':s['style']+'\n目标读者：'+s['audience']+'\n作者认可原文：未提供；无对标原文，不以自写片段充当认可样例。',
'上一章完整原稿（未采用）':prev,
'输出路径':f'首稿：{b}/raw/第{n:03d}章_{p["title"]}.md\n候选副本：{b}/候选/第{n:03d}章_{p["title"]}.md\n标题：## 第{n}章 {p["title"]}\n半角双引号，正文段间一个换行，无空行无缩进。',
'预检状态':'本章写前实际日志在checks/；tracking不存在，未补造。结构与因果检查不代表采用或阅读验收。'}
packet='# 实际 writer_packet\n\n'+''.join(f'## {key}\n\n{value}\n\n' for key,value in sections.items())
(b/'inputs'/f'chapter-{n:02d}.packet.md').write_text(packet)
(b/'inputs'/f'chapter-{n:02d}.packet-sizes.json').write_text(json.dumps({'sections':{k:len(v) for k,v in sections.items()},'total_characters':len(packet),'count_note':'输入体积按Unicode字符计，非正文字数口径'},ensure_ascii=False,indent=2))
