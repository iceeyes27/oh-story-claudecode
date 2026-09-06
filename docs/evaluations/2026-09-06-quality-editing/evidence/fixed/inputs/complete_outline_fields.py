# -*- coding: utf-8 -*-
from pathlib import Path
import json
r=Path(__file__).resolve().parent.parent
s=json.loads((r/'inputs/story-input.json').read_text())
configs={
2:dict(title='鱼要有盖',goal='先保鱼货；在陈望拒绝混放时问清空间与取货时间，按密闭、分放、付费和限时的已有条件谈成临时冷藏。',ending='配件下午能拿，小满已做好安排。',known='临时存放条件与30元另付，鱼货已搬入且配件下午可取',unknown='冷柜是否修好及是否收到尾款',before='第1章：两人讲定总服务费300元、先付100元定金，修复并验证后再付200元。',consequence='临时存放谈妥，鱼货保住，小满电话落实下午配件。',prior='已收100元定金，余款200元未收；鱼货需要临时冷藏；陈望还未同意。'),
3:dict(title='先等它凉下来',goal='完成维修并确认可靠结果；何桂香催结单时仍等温度恢复和稳定运行，随后搬鱼、收尾款，明天先查看排风扇现场。',ending='已约明天看排风扇，未保证修好。',known='冷柜稳定运行，鱼货回搬并清理临时空间，尾款200元已收，总服务费300元结清，明天只约看现场',unknown='明天排风扇的故障原因和维修结果',before='第2章：三人谈成使用鱼摊自备的干净密闭周转箱、分开存放、何桂香付30元临时存放费，傍晚前搬走。',consequence='300元维修服务费结清，邻里愿意介绍生意，约明天看排风扇现场。',prior='鱼货已临时分开冷藏，另付30元且傍晚前搬走；配件下午能拿；冷柜未修好。')}
for n,x in configs.items():
 c=s['chapters'][n-1];events=c['events']
 lines=[f'# 第{n}章 {x["title"]}', '- 核心事件：'+'；'.join(events),'- 字数目标：2500','- 字数口径：visible_chars_v1',f'- 阶段位置：隔离三章序列第{n}章；{c["time"]}',f'- 单元ID/位置：U-01 / {n} of 3','- 目标情绪：日常；按既有事件兑现生活笑点与事情进展','- 主角目标/关键选择：'+x['goal'],f'- 结尾拍ID/类型：EB-0{n} goal；'+events[-1],f'- 期待ID/类型：EX-0{n} goal；'+x['ending'],f'- 读者验收预期：must_know={x["known"]}；may_believe=周小满会讲清条件并承担自己的工作；must_not_know={x["unknown"]}；open_ids=EX-0{n}','- 章节定位：固定事件扩写，不增加策略或结果','- 本章结构公式：场景数量与顺序沿冻结事件自然分配，不另套反转','- 章首钩子：'+events[0],'- 爽点：'+('鱼货有了存处，彼此把实际条件讲明。' if n==2 else '修理收入结清，何桂香愿意介绍生意。'),'- 本章禁止提前释放：'+c['forbidden'],'- 契约风险：不将首稿承接称为正式采用或追踪事实；不增加固定事件以外的后续义务','- 前因：'+x['before'],'- 后果指向：'+x['consequence'],'- 读者已知：'+x['prior'],'### 内容概括']
 for label,event in zip(['起因','发展','转折','高潮','结尾'],events):lines.append('- '+label+'：'+event)
 lines+=['### 情节安排',*[f'- O{i}：{v}' for i,v in enumerate(events,1)],'### 人物关系和出场顺序','- 周小满、何桂香、陈望按现场先后自然出场；'+('周建国只在收束电话中出场。' if n==2 else '周建国不出场，不解决问题。'),'### 情节细化','| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |','| --- | --- | --- | --- |']
 for i,event in enumerate(events,1):lines.append(f'| {i} | {event} | 固定事件O{i} | {c["forbidden"]} |')
 (r/f'大纲/细纲_第{n}章.md').write_text('\n'.join(lines)+'\n')
print('Completed outline fields for chapters 2 and 3 only; chapter 1 unchanged.')
