# coding: utf-8
from pathlib import Path
import json, hashlib, datetime
b=Path(__file__).resolve().parents[1];(b/'metadata').mkdir(exist_ok=True)
plans=json.loads((b/'inputs/plan-data.json').read_text())
coverage={1:{
'O1':['何桂香进门时，周小满正把工具包的背带调短。','"他现在过不来，我去看。"','"柜里一批鱼呢，不能拿那个练手。"'],
'O2':['确认故障后，小满把拆下来的小组件搁在布上。温度到了该启动的时候，它却不能正常控制柜子制冷，得换合适的。这型号她手边没有，能拿到的配件要等下午。'],
'O3':['"你给我个准话，上午能不能让我接着用？"','"不能。"','"我先帮你安排临时冷藏，下午取到配件就回来修。先把鱼保住。"'],
'O4':['"我这边总共三百，配件、修理和今天帮你安排搬货都在里面。先一百，修好了，确认柜子能正常用，再给剩下二百。"','小满收好定金，提起工具包，抬头便看见了隔壁包子铺门前的蒸汽。'],
'O5':['她陪何桂香把柜盖合紧，沿走道回到包子铺。','"陈望，想跟你借点冷藏位置。你先听听怎么放，条件你开。"']},
2:{
'O1':['"鱼不行。"','"鲜鱼也有鱼味。我的馅不能跟鱼混着放。"','"行，你的包子金贵。"'],
'O2':['"你后面空哪块？能让我看看吗？不合适再说。"','"你下午取哪盆？"','"左边下面那盆。"'],
'O3':['"那就四只。右边这两层，跟馅料分开。装的时候外边擦干净，箱盖扣严，不在他柜子里开盖。陈望，你看行不行？"','"行。傍晚前得搬走，我自己的地方还要用。"','"三十。"','小满已经准备好再问一句哪些东西需要挪，何桂香却从口袋里掏出钱来，数出三十元，放在外头的干燥柜台上。'],
'O4':['"等会儿，这么放，他那盆馅拿不出来。"','陈望从旁边托住，三个人把箱子转过来。','"行。它要是不出来，我明天就只能卖皮了。"','剩下两只搬过来，小满照着位置放好，一只只点过去。何桂香把鱼的种类对了一遍，陈望看了箱外和空出的取物位置，把柜门关上。'],
'O5':['小满回到修理铺门口，先给供货方拨电话，对了一遍配件型号，确认下午能拿到，才把记下的号码收好。','"我先按我看的做，真有拿不准的再问你。"','"行。"父亲说，"你都安排好了，就照你判断的弄。"']},
3:{
'O1':['小满下午回到鱼摊，何桂香先看她的手。','她在断电的情况下完成更换，检查妥当，把该装回去的地方收好，才让冷柜重新通电。','"修的地方弄好了，柜里还不够凉。鱼从陈望那边拿出来，总不能搬回一个暖柜子里。温度降到能存鱼，我再看看它能不能稳住。"'],
'O2':['"剩下二百，给你。咱们去搬？"','"想收啊。"她笑了笑，"早上就在等你这二百了。可咱们说好确认能用再付，现在还差这一会儿。"','"早上我那句练手，说得不好听。"'],
'O3':['温度终于落到适合存这批鱼的范围，小满仍留着检查了一段时间。冷柜照常启停，温度也稳得住，她才把包扣上。','小满扶住箱底，三个人照来时的位置把箱子一只只取出。','箱外擦得干净，里面没留下鱼水，她们还是把两层都清理了一遍，把走动时带进去的水迹也擦干。','"行，我接着用了。"'],
'O4':['小满接过钱，数清，和早上的定金合在一起。三百元服务费，一分没少，也没多收。','"以后有人问修东西，我把你号码给他。就说找周小满，在老铺子里。"'],
'O5':['"小满，你明天有空，看看我后间那个排风扇。时转时不转，我开门的时候它倒像还想睡。"','"得看现场，查清哪里有问题再跟你说怎么修、多少钱。现在问，我也只能答应过去。"','小满在旁边另记下陈望的排风扇，时间写明早，后面添上看现场。']}}
summaries={1:'何桂香找老周修冷柜，小满接手检查，说明配件下午才能拿到，拒绝立即修好保证。双方约定三百元、先付一百、验好再付二百。小满带她到陈望店门口商量临存。',2:'陈望拒绝混放鱼货。三人看箱与空间后议定密闭分放、三十元及傍晚前取走，搬好四箱鱼。小满确认下午可取配件，父亲电话尊重她已做好的安排。',3:'小满取件修柜，坚持降温并验证后才搬鱼。三人搬回四箱货、清理归还借位，何桂香付二百尾款并愿介绍生意。陈望约明早查看排风扇，小满未保证修好。'}
protagonists={
1:{'identity':'周小满，接手父亲旧修理铺并独立接冷柜维修单的人。','location':'陈望包子铺门槛外。','goal':'为何桂香的鱼货谈到临时冷藏位置，下午取件回来修柜并取得剩余服务费。','state':'已收一百元定金；已说明无法上午修好；临存尚未谈成，柜子未修好。','abilities_resources':['有维修经验，检查出须更换合适组件','工具包与单据本','一百元定金'],'relationships':['何桂香同意由小满接单并给出有限信任','与陈望是邻铺熟人，正向他请求借位','父亲在家养腿，本章未通话'],'knowledge':['需要匹配的温控组件，下午才能取得','应先给鱼货找冷藏位置','陈望后间有可能腾出冷藏空间但需征得同意'],'open_threads':['临时存放条件未确定','下午取件维修','验证修好后余款二百待收']},
2:{'identity':'周小满，独立负责何桂香冷柜维修及当日保货安排的维修工。','location':'修理铺工作台旁，刚挂断父亲电话后提起工具包。','goal':'按自己的诊断取到匹配配件并修好冷柜。','state':'四箱鱼已在陈望指定位置临存；配件下午可取已电话确认；冷柜尚未修好。','abilities_resources':['工具包','会检查故障并确认匹配配件型号','已收的一百元定金','陈望获偿三十元后同意临存四箱鱼'],'relationships':['何桂香、陈望通过看箱与搬箱达成合作','父亲接受她先按自己判断处理，不替她决定'],'knowledge':['陈望需分开食材且下午能取到左侧馅料','密闭四箱已在右侧两层存妥','临存三十元已付，傍晚前必须搬走','供货方确认下午能取得配件'],'open_threads':['取配件修柜','傍晚前搬回鱼货归还位置','修复验证后收二百元尾款']},
3:{'identity':'周小满，已独立完成当天冷柜维修与保货安排的维修工。','location':'自己的修理铺工作台旁。','goal':'明早去陈望后间看排风扇现场，再判断怎么修和报价。','state':'冷柜稳定、鱼货已回柜、临存位置归还、三百元服务费全结清；已记下明早查看预约。','abilities_resources':['工具包、带回的旧组件','记有三百元结清与明早预约的单据本','已收服务费三百元'],'relationships':['何桂香承认早上说话不好听，愿按小满名字介绍生意','陈望愿请她看自己的排风扇'],'knowledge':['鱼摊冷柜经正常启停与温度验证可以使用','四箱鱼货全部回到何桂香柜内','陈望排风扇时转时不转，具体故障尚不知'],'open_threads':['明早查看陈望排风扇，未承诺必修好且未报价']}}
commitments={1:[{'promise':'先帮助安排鱼货临时冷藏，下午取配件回来修理。','state':'尚待履行','evidence':'"我先帮你安排临时冷藏，下午取到配件就回来修。先把鱼保住。"'},{'promise':'维修总服务费三百元不加收，修复验证后收剩余二百。','state':'已收定金，待维修验证','evidence':'"不再加。借位置那笔另算，谈多少，你当面听。"'}],2:[{'promise':'四只密闭鱼箱在指定位置分开存放，傍晚前搬走。','state':'临存已落实，搬走待履行','evidence':'"行。傍晚前得搬走，我自己的地方还要用。"'},{'promise':'小满先照自己的判断做，有拿不准的再问父亲。','state':'当前决定','evidence':'"我先按我看的做，真有拿不准的再问你。"'}],3:[{'promise':'何桂香遇到有人问修理时，介绍周小满并给她的电话。','state':'条件性口头承诺，未写成已有转介绍客户','evidence':'"以后有人问修东西，我把你号码给他。就说找周小满，在老铺子里。"'},{'promise':'小满明早去陈望后间看排风扇现场，查清后再说修法与费用。','state':'未来预约，未修理未报价','evidence':'"明天你开门后我过去看。"'}]}
metric_sources={1:[('service_fee_agreed',300,1,'我这边总共三百'),('service_fee_received',100,1,'小满收好定金'),('service_fee_outstanding',200,1,'再给剩下二百')],2:[('service_fee_agreed',300,1,'我这边总共三百'),('service_fee_received',100,1,'小满收好定金'),('service_fee_outstanding',200,1,'再给剩下二百'),('temporary_storage_fee_paid_to_chen',30,2,'数出三十元，放在外头的干燥柜台上'),('stored_fish_boxes',4,2,'四只，全在你这里')],3:[('service_fee_received',300,3,'三百元服务费，一分没少，也没多收'),('service_fee_final_payment',200,3,'何桂香已经把二百元拿出来'),('service_fee_outstanding',0,3,'又写上结清'),('temporary_storage_fee_paid_to_chen',30,3,'借位置的三十，你上午给陈望了'),('returned_empty_boxes',4,3,'何桂香把四只空箱叠在一起')]}
for p in plans:
 n=p['n'];f=b/'候选'/f'第{n:03d}章_{p["title"]}.md';text=f.read_text();lines=text.splitlines()
 ev=[]
 for oid,quotes in coverage[n].items():
  evidence=[]
  for q in quotes:
   assert q in text,(n,oid,q)
   line=next(i for i,x in enumerate(lines,1) if q in x)
   evidence.append({'evidence':q,'line':line})
  ev.append({'o_id':oid,'evidence':evidence})
 for c in commitments[n]:assert c['evidence'] in text
 metrics=[]
 for name,value,source_n,phrase in metric_sources[n]:
  source=b/'候选'/f'第{source_n:03d}章_{plans[source_n-1]["title"]}.md'
  assert phrase in source.read_text(),phrase
  metrics.append({'name':name,'value':value,'as_of_chapter':n,'source_chapter':source_n,'source_phrase':phrase,'unit':'只' if 'boxes' in name else '元'})
 obj={'schema':'postwrite-extraction/v1','chapter':n,'extraction_phase':'after_all_three_raw_drafts_and_scans; not generation input','extracted_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'candidate_path':str(f),'candidate_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'summary':summaries[n],'coverage':ev,'protagonist':protagonists[n],'commitments':commitments[n],'metrics':metrics,'not_a_reader_receipt':True,'adopted':False}
 assert len(summaries[n])<=110
 (b/'metadata'/f'chapter-{n:02d}.postwrite.json').write_text(json.dumps(obj,ensure_ascii=False,indent=2))
 print(n,'summary_chars',len(summaries[n]),'O_IDs',len(ev),'exact_evidence_verified',True)
