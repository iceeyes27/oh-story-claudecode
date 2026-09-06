from pathlib import Path
import json,sys
root=Path(__file__).resolve().parent.parent
source=root/'inputs/story-input.json'
s=json.loads(source.read_text())
plan=(root/'inputs/arm-plan.md').read_text()
titles=['一百块定金','鱼要有盖','先等它凉下来']
scenes=[
[('铺里接单',[1],600,'何桂香来找老周，小满说明父亲腿伤与自己接单；随她去鱼摊。','把担心经验与接单意愿说清'),('鱼摊诊断与议价',[2,3,4],1500,'确认需要下午的配件，拒绝立即修好的保证；提出保货与下午维修；约定300元，先收100元，验证后付200元。','客户怕坏货，小满怕逞能；双方接受具体条件'),('去包子铺',[5],400,'小满想到陈望店里的冷藏空间，带何桂香前去；停在准备谈条件的动作。','保货有了可商量的去处，尚未得到许可')],
[('商量临时冷藏',[1,2,3],1500,'陈望拒绝混放；何桂香嫌小气；小满问空间和取货时间，三人讲定密闭周转箱、分开存放、30元与傍晚前搬走。','理解各自生意顾虑后商定临时办法'),('搬货',[4],600,'小满参与搬运清点，陈望说一句与眼前事情有关的实在话，争执缓和。','鱼货获得临时存放，关系松动'),('确认配件与父亲电话',[5],400,'小满电话确认下午配件；周建国来电想给建议，小满告知已做安排。','下一步落实，父亲听取女儿判断')],
[('下午维修',[1],800,'小满取到配件回市场，完成维修，说明要等温度合适再搬鱼。','维修完成但尚需验证'),('等冷柜恢复',[2],900,'何桂香催结单，小满坚持等结果；围绕眼前生意和修理有自然交流。','从催促到愿意等待；没有新承诺或支线'),('回搬结账与下一单',[3,4,5],800,'冷柜稳定后，三人搬鱼归还清理临时空间；付200元尾款，何桂香愿介绍生意；陈望问排风扇，小满约明天看现场。','300元结清，获得信任和具体下一单')]]
for d in ['大纲','骨架','raw','候选','logs']: (root/d).mkdir(exist_ok=True)
n=int(sys.argv[1]);c=s['chapters'][n-1];title=titles[n-1]
characters=['周小满','何桂香','陈望']+(['周建国'] if n==2 else [])
parts={
'执行要求':f'隔离试写 fixed 臂；普通长篇 quality_profile=fanqie-long-v2；无 quality_treatment_mode；保持继承模型与effort。每章只产一份完整首稿，本轮不执行reading edit，不重采样。字数口径visible_chars_v1：不计标题和空白，标点计入；2200～2800，目标2500。\n本臂授权：{plan.strip()}\n原标题未提供，以下标题由本次简单规划确定。原始输出路径：{root}/raw/第{n:03d}章_{title}.md；即时复制候选路径：{root}/候选/第{n:03d}章_{title}.md。',
'故事与本书偏好':json.dumps({k:s[k] for k in ['title','scope','premise','audience','style']},ensure_ascii=False,indent=2)+'\n作者认可样例：未提供；真人反馈：pending。',
'本章蓝图':(root/f'大纲/细纲_第{n}章.md').read_text(),
'本章骨架':(root/f'骨架/第{n:03d}章_{title}.md').read_text(),
'关键人物摘录': '\n'.join(name+'：'+s['characters'][name]+'\n'+json.dumps(s['character_details'][name],ensure_ascii=False)+'\n来源：inputs/story-input.json characters与character_details。' for name in characters),
'事实红线': '\n'.join(s['fixed_facts'])+'\n本章禁止：'+c['forbidden'],
'上一章正文': '第一章，无上一章。' if n==1 else '以下只为同一隔离序列的首稿承接，不是作者采用正文，不进入正式追踪。\n'+(root/f'raw/第{n-1:03d}章_{titles[n-2]}.md').read_text(),
'本章可用连续性': ['第一章，尚未接单。','由前章原始稿确定：总服务费300元，已收定金100元，余款200元须修复验证；临时冷藏尚未谈妥；到陈望店门口准备商量。','由前章原始稿确定：已借到分开存放的冷藏位置，使用鱼摊自备干净密闭周转箱；何桂香另付30元；傍晚前搬走；配件已确认下午可取，维修尚未完成。'][n-1]
}
packet='\n\n'.join('## '+key+'\n'+val for key,val in parts.items())+'\n'
p=root/f'inputs/chapter-{n:02d}.packet.md';p.write_text(packet)
(root/f'inputs/chapter-{n:02d}.packet.parts.json').write_text(json.dumps({k:len(v) for k,v in parts.items()},ensure_ascii=False,indent=2)+'\n')
log=root/'inputs/read-files.json';readfiles=json.loads(log.read_text())
for fp in [root/'inputs/build_packet.py',root/f'大纲/细纲_第{n}章.md',root/f'骨架/第{n:03d}章_{title}.md',p]+([] if n==1 else [root/f'raw/第{n-1:03d}章_{titles[n-2]}.md']):
 if str(fp) not in readfiles:readfiles.append(str(fp))
log.write_text(json.dumps(readfiles,ensure_ascii=False,indent=2)+'\n')
print(packet)
