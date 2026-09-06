# coding: utf-8
from pathlib import Path
import json, sys
b=Path(__file__).resolve().parents[1]
plans=json.loads((b/'inputs/plan-data.json').read_text())
if len(plans)==2:
 plans.append({'n':3,'title':'等凉了再收钱','time':'下午到傍晚','emotion':'事业；急于结单到凭结果被信任','goal':'小满想拿齐三百元，选择暂缓收尾款，等柜温与运转稳定再移鱼；以自己判断完成整单。','reader':'看懂修好后还须等柜温的原因，获得鱼货回柜与服务费结清的兑现，看到客户开始找小满本人。','ending':'EB-03/goal','expect':'EX-03/goal','hook':'陈望请她明天看时好时坏的排风扇，她只约看现场；当天账单结清后记下具体下一单。','open':'小满带合适配件回市场，在何桂香同意下断电完成维修。','ban':'不靠父亲解决问题；不新增故障危机；不直接许诺排风扇必能修好；维修共300，临存另30。','events':['小满取到合适温控组件回市场完成维修，说明要等冷柜降至合适温度并验证稳定后才搬鱼。','何桂香急于把货放回自己的柜里，想付尾款结单；小满承认想收钱却坚持先验结果，等候中围绕称呼与独立接单自然互动。','冷柜稳定后，三人将四箱鱼货搬回，清点并清理归还临存位置。','何桂香付余款200，维修总额300结清，愿意以小满的名字介绍生意。','陈望约她明天看时好时坏的排风扇，小满先约看现场不保证修好，以当天单据和下一单结束。'], 'scenes':[{'where':'下午，鱼摊；小满、何桂香','goal':'完成修理并让结果可靠，既想收款又不省掉等待','resist':'柜子刚恢复运转尚未足够冷，何桂香想把货留在自己眼皮下，小满也盼早结单','chain':'带件归来 -> 断电修理完成 -> 通电降温 -> 何桂香提出付尾款搬货 -> 小满暂不收钱说明实际标准 -> 等候中谈到叫老周还是叫小满 -> 柜温及运转稳定','change':'冷柜实际达到存货条件；何桂香能理解小满为何不急着拿钱，开始按她自己的名字称呼','turn':'修复后的轻松 -> 等待中的急切 -> 用结果换来踏实','info':'不写具体带电维修步骤；父亲不参与；称呼变化只兑现本次独立接单','dialog':'何桂香催促因惦记自己鱼货，不是刁难；小满不端师傅架子，坦率承认想拿钱但还没到收尾节点','budget':1500,'oids':[1,2]}, {'where':'傍晚，包子铺后间、鱼摊、修理铺；小满、何桂香、陈望','goal':'归还临存空间、结清此单，接下可验证范围内的新预约','resist':'收尾仍要把鱼货搬妥、借位清干净；小满不能因为被信任便预报下一次必修好','chain':'三人搬四箱回鱼摊 -> 清理归还临存位置 -> 何桂香付二百元 -> 说愿介绍小满生意 -> 陈望约看排风扇 -> 小满只约明天看现场 -> 记清已收款和新预约','change':'鱼货回柜、维修费结清、借位归还；获得口碑与排风扇查看预约','turn':'忙碌收尾 -> 熟人肯认自己 -> 带具体下一单结束','info':'总维修300，余款200；临存30已另付；排风扇仅查看预约','dialog':'何桂香用付款和介绍表示认可；陈望先说明时好时坏，小满先看再说的口吻延续清晨','budget':1000,'oids':[3,4,5]}]})
 (b/'inputs/plan-data.json').write_text(json.dumps(plans,ensure_ascii=False,indent=2))
for p in plans:
 n=p['n'];title=p['title']
 if n==1:p.update(emotion='事业；受窘与急迫，转为有限信任',ending='EB-01/goal',expect='EX-01/goal')
 if n==2:p.update(emotion='温情；护短争执，转为能一起做事的松快',ending='EB-02/relationship',expect='EX-02/goal')
 oracle=[
 'must_know=小满接单、配件下午可取、先保鱼、总300先付100、借位未定；may_believe=诚实可能争到有限信任；must_not_know=借位条件是否谈成与修理最终结果；open_ids=EX-01',
 'must_know=密闭箱分开临存、另付30且傍晚前搬走、四箱鱼已暂存、小满准备好修理；may_believe=双方条件说清便能一起干活；must_not_know=修理验收和尾款结算；open_ids=EX-02',
 'must_know=修理验收完成、四箱鱼回柜、临存归还、余款200与总300结清、明天只约看排风扇；may_believe=小满能开始凭自己名字接单；must_not_know=排风扇故障原因与后续修理结果；open_ids=EX-03'][n-1]
 cause=['开篇无前因。河平县旧菜市场冷柜坏了，何桂香找老周。','第1章：小满想到陈望有冷藏空间，带何桂香到包子铺开始商量，止于条件谈判前。','第2章：小满电话确认下午可取配件；父亲电话想给建议，她已做好安排；不重复整套时间金额信息。'][n-1]
 outline=f'''# 第{n:03d}章 {title}\n\n- 内容来源：inputs/story-input.json、inputs/arm-plan.md、design.md\n- 核心事件：{p['goal']}\n- 字数目标：2500 字\n- 字数口径：visible_chars_v1\n- 阶段位置：原创三章试写第{n}章，{p['time']}\n- 单元ID/位置：U01/{n}，一日冷柜修理\n- 目标情绪：{p['emotion']}\n- 主角目标/关键选择：{p['goal']}\n- 结尾拍ID/类型：{p['ending']}；{p['hook']}\n- 期待ID/类型：{p['expect']}；{p['hook']}\n- 读者验收预期：{oracle}\n- 章节定位：{p['reader']}\n- 本章结构公式：顺时序，目标遇到实际顾虑，选择应对并获得本章限定结果；不按字段逐段成文。\n- 章首钩子：{p['open']}\n- 爽点：{p['reader']}\n- 本章禁止提前释放：{p['ban']}\n- 契约风险：不能以承诺替代结果、不能新增独立事件或借别人人物兜底。\n- 前因：{cause}\n- 后果指向：{p['hook']}\n- 读者已知：{'开篇暂无前文事实。' if n==1 else '仅本臂前一章完整原稿承接；原稿未采用，未生成追踪。'}\n\n### 内容概括\n\n'''
 for act,event in zip(['起因','发展','转折','高潮','结尾'],p['events']):outline+=f'- {act}：{event}\n'
 outline+='\n### 情节安排\n\n'+''.join(f'- O{i}：{event}\n' for i,event in enumerate(p['events'],1))
 outline+='\n### 人物关系和出场顺序\n\n'+('小满、何桂香，末尾陈望。客户认识父亲手艺，对女儿没有独立接单的信任。' if n==1 else '小满、何桂香、陈望，末尾周建国仅电话。两位店主均有经营边界，父亲尊重女儿的判断。' if n==2 else '小满、何桂香，搬运时陈望参与。称呼、付款和预约兑现今天形成的信任；父亲不参与解决。')
 outline+='\n\n### 情节细化\n\n| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |\n| --- | --- | --- | --- |\n'+''.join(f'| {i} | O{i}：{event} | {"选择" if i==3 else "推进"} | {p["ban"]} |\n' for i,event in enumerate(p['events'],1))
 outline+='\n## 扩写边界\n\n- 第三人称贴近小满；不切他人内心。只消费本章语义点，允许服务既有行动的移动、环境、短对话和判断。\n- 写作开始后锁定，不为字数和扫描结果改纲；全部是本次隔离规划，不是追踪事实。\n'
 (b/'大纲'/f'细纲_第{n:03d}章.md').write_text(outline)
 skeleton=f'''# 第{n:03d}章 {title}\n\n## 章节契约\n\n- 来源细纲：大纲/细纲_第{n:03d}章.md\n- 最终正文字数目标：2500 字\n- 目标情绪：{p['emotion']}\n- 读者获得：{p['reader']}\n- 禁止提前释放：{p['ban']}\n- 开场动作：{p['open']}\n- 章尾钩子：{p['hook']}\n'''
 for i,c in enumerate(p['scenes'],1):
  skeleton+=f'''\n## 场景 {i}\n\n- 时空与人物：{c['where']}\n- 场景目标：{c['goal']}\n- 阻力：{c['resist']}\n- 动作链：{c['chain']}\n- 结果变化：{c['change']}\n- 情绪转折：{c['turn']}\n- 信息/伏笔：{c['info']}\n- 台词意图与潜台词：{c['dialog']}\n- 正文字数预算：{c['budget']} 字\n'''
 skeleton+='\n## 细纲覆盖\n\n'+''.join(f'- [x] O{oid} {p["events"][oid-1]} -> 场景 {i}\n' for i,c in enumerate(p['scenes'],1) for oid in c['oids'])
 skeleton+='\n## 扩写约束\n\n- 人物声线：按 inputs/story-input.json 的 character_details；不套用题材口头禅。\n- 事实红线：同日、一台冷柜、四位固定人物；服务费300，首付100，尾款200，临存另30。\n- 允许自由发挥：不改变结果的语序、动作承接、现场细节与小满内心；不得新增独立事件。\n'
 (b/'骨架'/f'第{n:03d}章_{title}.md').write_text(skeleton)
(b/'inputs/plan-data.json').write_text(json.dumps(plans,ensure_ascii=False,indent=2))
print('三章蓝图已在首稿前形成；第1至2章为首批，第3章为后续批。')
