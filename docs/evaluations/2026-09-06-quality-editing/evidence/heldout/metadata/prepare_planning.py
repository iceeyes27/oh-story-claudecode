# -*- coding: utf-8 -*-
from pathlib import Path
import json,hashlib,datetime,shutil
root=Path.cwd(); runtime=root.parent/'runtime/.agents/skills'
def save(p,s):
 p.write_text(s,encoding='utf-8')
chars=json.loads((root/'inputs/story-input.json').read_text())['characters']
packet={'source':'inputs/story-input.json#characters','status':'planning_only','characters':chars,'narrative_pov':'第三人称贴近宋棠，不进入他人内心','provided_approved_samples':[]}
save(root/'inputs/character-handoff.json',json.dumps(packet,ensure_ascii=False,indent=2))
feedback={'source':'inputs/story-input.json','decision':'仅在已批准三章边界内具体化表现','chapters':[{'chapter':1,'problem':'查人数易写成名册核验步骤','chosen_interaction':'齐叔珍惜老同伴的合影，但怕自己说错；宋棠既不顺从猜测，也不把缺名指成恶意。留空行是她当场选择。','rejected_alternative':'指控旧站蓄意裁人，超越题材边界。'},{'chapter':2,'problem':'女儿提供资料易成为单向信息倾倒','chosen_interaction':'程雪先看见空行才愿意取出资料；宋棠想及时补名，程雪把母亲意愿放在前面。两人用另一照片推翻外套职业判断。','rejected_alternative':'追加取证阻碍或调查第三人，未获授权。'},{'chapter':3,'problem':'核对事实易重复前章清点','chosen_interaction':'林琴和齐叔先各自认位置，借衣与搬书由记忆差异接话对上；她主动限制展牌的夸赞，宋棠保留准确的普通搭手。','rejected_alternative':'再加隐瞒身份或大恩怨以制造高潮。'}]}
save(root/'inputs/scene-design-feedback.json',json.dumps(feedback,ensure_ascii=False,indent=2))
plan=[
{'n':1,'title':'空着的位置','emotion':'悬疑','goal':'把照片下的人名写准确；在资料未明时选择留空，承担说明牌暂未完成的结果','payoff':'发现多出来的人，并得到联系寄件人的现实途径','end':'宋棠由包装上的寄件联系信息约到程雪，同日带另一张照片来','cause':'开篇无前因','known':'尚不知合影少人；不知第五人的身份及寄件者目的','consequence':'约到程雪带同日另一张照片来','forbid':'第五人姓名、女儿关系、邮递员真相、阴谋；衣服不能定身份','events':['匿名完整照片与提醒纸条到达，打断宋棠照旧名单写说明牌','通过同一排人站位与箱子比对，确认墙图右边缘裁掉半个人；原片五人，职工名单四名','齐叔猜边缘是路过者却无法确认，宋棠只留第五行空白且不指控裁图动机','站服造成同事假说；宋棠由照片背面相邻编号判断另有同日片，通过包装电话约程雪来']},
{'n':2,'title':'借来的外套','emotion':'悬疑','goal':'凭新增材料推进认人，但同意先问当事人再定稿','payoff':'排除衣服代表职业的假设，确定第五人与寄件者的亲属关系','end':'程雪承认照片里的是母亲，先电话问她愿否来；齐叔表示一起核对','cause':'第1章：约到程雪带同日另一张照片来','known':'五人合影与四人职工名单不符；齐叔记不准；站服仅是猜测；程雪将来','consequence':'程雪同母亲商量来展厅，齐叔愿意一起核对','forbid':'未经母亲核对就公布名字，救命大恩，秘密凶手；本章不出现林琴姓名','events':['程雪前来承认照片是自己寄的，担忧先写成失落英雄，拿出另一照片及家中便条','同日稍早照片里同样的外套在齐叔同事身上，合影边缘者是后来借穿；宋棠放弃站服代表职工的判断','便条写搬书之后仍须送信，提供职业方向；查找范围改为临时来帮忙的人','程雪说边缘者是母亲但不肯代她决定署名及功劳；齐叔接受不凭记忆定案并愿一起核对']},
{'n':3,'title':'林琴','emotion':'温情','goal':'核实真实经历并征得署名同意，完成说明牌','payoff':'第五人的姓名与普通帮忙的经历被看见','end':'开放后观众循姓名找到第五人；空行写满，宋棠想继续记录其他普通人','cause':'第2章：程雪同母亲商量来展厅，齐叔愿意一起核对','known':'衣服借来；帮忙者之后要送信；程雪说是母亲；姓名尚未公布','consequence':'本单元谜题关闭，无新增硬钩子','forbid':'英雄传奇、拯救全部书籍、阴谋或新惊天谜团','events':['林琴来到展厅，和宋棠、齐叔对照两张照片及便条，相互对应搬书时间、地点与借外套细节','当事人确认邮递员职业和临时搭手，纠正把全部书归功于她的说法，明确姓名林琴','齐叔由具体旧事认人，承认名单只列职工；双方不追究抹名动机','宋棠询问母女意愿获准补名，写清临时搬书与借衣，合影保留完整','当天展览开放，观众顺着名字找到她；宋棠填满空行，愿继续听其他照片里普通人的事']}
]
save(root/'metadata/planning-source.json',json.dumps(plan,ensure_ascii=False,indent=2))
for p in plan:
 n=p['n']; ev=p['events']; act=[ev[0],ev[1],ev[min(2,len(ev)-1)],ev[min(3,len(ev)-1)],p['end']]
 oracle=f"must_know={p['payoff']}；may_believe=所有照片资料尚须以本章明示限度理解；must_not_know={p['forbid']}；open_ids="+('EX-01' if n<3 else '无')
 fields={'核心事件':'；'.join(ev),'字数目标':'2500','字数口径':'visible_chars_v1','阶段位置':f'同一天社区展览准备，第{n}/3章','单元ID/位置':f'UNIT-01 第{n}/3章','目标情绪':p['emotion']+'；'+p['payoff'],'主角目标/关键选择':p['goal'],'结尾拍ID/类型':f'EB-0{n} / '+('open_question' if n<3 else 'aftermath')+'；'+p['end'],'期待ID/类型':'EX-01 / payoff；认全第五个人并获得准确署名','读者验收预期':oracle,'章节定位':'轻悬疑推进' if n<3 else '身份回收与普通人的余味','本章结构公式':'具体疑问→人物不同顾忌→依据改变判断→主动选择→本章回报','章首钩子':ev[0],'爽点':p['payoff'],'本章禁止提前释放':p['forbid'],'契约风险':'不追加新事件；不把亲属口述和衣服各自当作唯一身份证据','前因':p['cause'],'后果指向':p['consequence'],'读者已知':p['known']}
 text=f"# 第{n:03d}章 {p['title']}\n\n"+'\n'.join(f'- {k}：{v}' for k,v in fields.items())+'\n\n### 内容概括\n'+'\n'.join(f'- {k}：{v}' for k,v in zip(['起因','发展','转折','高潮','结尾'],act))+'\n\n### 情节安排\n按现场注意力承接以下独立变化，相同结论只消费一次。\n\n### 人物关系和出场顺序\n'+(['宋棠先在展厅；齐叔在整理展件；程雪章尾以联络回应出现。','宋棠、齐叔在原展厅等候，程雪到场；母亲只被提及，不出场。','宋棠、齐叔、程雪在展厅；林琴到来参加核对，开放后为无名普通观众。'][n-1])+'\n\n### 情节细化\n| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n|---|---|---|---|\n'
 text+='\n'.join(f'| {i} | O-{i:02d} {e} | 信息/选择 | 只实现该项，不重复总结、不新开义务 |' for i,e in enumerate(ev,1))+'\n'
 save(root/f'大纲/细纲_第{n:03d}章.md',text)
 # Each chapter one continuous exhibition-room scene; ch3 admits same-day door opening as scene 2.
 scenes=[(ev,2500)] if n<3 else [(ev[:4],2150),(ev[4:],350)]
 sk=f"# 第{n:03d}章 {p['title']}\n\n## 章节契约\n- 来源细纲：大纲/细纲_第{n:03d}章.md\n- 最终正文字数目标：2500 字\n- 目标情绪：{p['emotion']}\n- 读者获得：{p['payoff']}\n- 禁止提前释放：{p['forbid']}\n- 开场动作：{ev[0]}\n- 章尾钩子：{p['end']}\n"
 for j,(items,budget) in enumerate(scenes,1):
  sf={'时空与人物':(['上午社区展厅，宋棠、齐叔','同日上午稍后同一展厅，宋棠、齐叔、程雪','同日下午展厅，宋棠、齐叔、程雪、林琴'][n-1] if j==1 else '同日下午展览开放，宋棠、母女、无名观众'),'场景目标':p['goal'],'阻力':['现存名册四名；齐叔惜同伴但担忧记错；陌生寄件人未说明身份','程雪不愿将母亲写成失落英雄，也不能代母亲定功劳','林琴不愿把临时帮忙夸大；齐叔需从位置和借衣重建记忆'][n-1],'动作链':' → '.join(items),'结果变化':p['payoff'] if j==1 else p['end'],'情绪转折':['疑惑变成可追的具体问题','期待确认转为愿意听当事人说','认出人并尊重其意愿后踏实'][n-1],'信息/伏笔':p['known']+'；仅兑现本场条目','台词意图与潜台词':feedback['chapters'][n-1]['chosen_interaction'],'正文字数预算':f'{budget} 字'}
  sk+=f'\n## 场景 {j}\n'+'\n'.join(f'- {k}：{v}' for k,v in sf.items())+'\n'
 sk+='\n## 细纲覆盖\n'+'\n'.join(f'- [x] O{i} {e} -> 场景 {2 if n==3 and i==5 else 1}' for i,e in enumerate(ev,1))+'\n\n## 扩写约束\n- 人物声线：以 inputs/character-handoff.json 为准，宋棠问具体问题，齐叔会改口，程雪克制，林琴纠正过赞。\n- 事实红线：'+p['forbid']+'；同一天，不增独立危机。\n- 允许自由发挥：照片摆放、对话承接、观看位置等微连接；可具体化同一条已批准线索的可见细节，不增加新的证据种类。\n'
 save(root/f"骨架/第{n:03d}章_{p['title']}.md",sk)
