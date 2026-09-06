# -*- coding: utf-8 -*-
from pathlib import Path
import json,hashlib,datetime
r=Path(__file__).resolve().parent.parent
(r/'metadata').mkdir(exist_ok=True)
titles=['一百块定金','鱼要有盖','先等它凉下来']
paths={n:r/f'候选/第{n:03d}章_{title}.md' for n,title in enumerate(titles,1)}
texts={n:p.read_text() for n,p in paths.items()}

def span(n,start,end):
 text=texts[n];a=text.index(start);b=text.index(end,a)+len(end)
 return text[a:b]

def metric(n,value,phrase,source_chapter=None):
 sc=source_chapter or n
 assert phrase in texts[sc],phrase
 return dict(value=value,as_of_chapter=n,source_phrase=phrase,source_chapter=sc)

ranges={
1:[('周小满刚把修理铺的卷帘门推过头顶','"修过。你先别把盖子来回打开，我拿工具。"'),('检查完，小满将卸下的护板放稳','"眼下先管鱼。咱们找地方临时冷藏，东西到了我回来修。"'),('"你跟我说句准话，到底能不能修？"','"拿到配件我就来。修完还得看它能不能稳稳降温，不能听见响了就算完。"'),('"这一单总共三百','三百块还没挣到手，她倒先觉得工具包没有刚才那么勒了。'),('小满转身望向通道外','"是鱼。你先听我们把事情说完，条件咱们当面谈。"')],
2:[('"鱼不行。"','"东西是我在卖，我不得想？"'),('何桂香往店里指了指','"傍晚。我收拾完就得用，不能晚上关门了还等人来搬。"'),('"那就按傍晚前搬走谈','"留给你。你也别放着放着忘了时间。"'),('回到鱼摊，她从摊下拖出洗净晾干的周转箱','她付了三十块。陈望当着她的面收下，又把门口的一点水擦了。'),('何桂香向她问了下午回来的安排','"那你忙你的。"他说，"我就问一声。"')],
3:[('下午，小满提着配件走进市场','"响是开始干活。等里面真凉下来，我再看它稳不稳，鱼先在陈望那里待着。"'),('"那你把钱收了，单子结掉','两个人都坐正了，谁也没再忙着起来。'),('等候间，小满按需要查看温度和运行情况','"干净。"'),('何桂香没再接这句','"怕你又叫人找老周。"'),('陈望从通道那边过来','才低头把明早要带的本子摆到手边。')]
}
protagonists={
1:dict(identity='周小满，29岁，有维修经验，接下父亲修理铺独立接单。',location='陈望包子铺门口，正准备和何桂香一起谈临时存鱼条件。',goal='先给鱼货找临时冷藏处，下午取件完成冷柜维修，挣到约定的三百元。',state='已检查冷柜并收一百元定金，冷柜未修好，尚未得到陈望的存放许可。',abilities_resources=['具备实际冷柜维修经验并能判断需更换配件','带有工具包和记事本','本单已收100元定金'],relationships=['何桂香起初要找老周，对小满独立维修有疑虑，现接受明确收费与验证条件','知道隔壁陈望店内可能有冷藏空间，尚未谈妥'],knowledge=['该冷柜无法立即恢复，需要合适配件，下午才能取到','鱼货不能继续等修，须先安排临时冷藏','总服务费300元；先付100元；修复验证后付200元；临时存放费另谈'],open_threads=['和陈望商量鱼货临时冷藏空间与条件','下午取配件并返回维修','维修验证完成后收200元尾款']),
2:dict(identity='周小满，独立接下何桂香冷柜维修的小满修理铺经营者。',location='上午，陈望包子铺门口，准备回修理铺。',goal='下午按电话确认取配件，回来修好何桂香的冷柜。',state='已参与把鱼货移入陈望店内独立冷藏位置，临时存放已安排，冷柜尚未修好。',abilities_resources=['工具包和记录冷柜型号及配件信息的小本子','本单已收100元定金','已确认下午可取到所需配件'],relationships=['和何桂香、陈望讲明各自顾虑，三人按密闭、分放、付费与限时条件协作搬货','何桂香与陈望的争执因实在的玩笑缓和','父亲电话听完安排后让小满忙自己的，没有代为解决故障'],knowledge=['鱼货装在鱼摊自备洗净晾干、扣严的周转箱内，与包子食材分开冷藏','何桂香已另外付陈望30元','临时位置须傍晚前清空','供货方电话确认下午可以取配件','维修总费300元，定金100元，试好后余款200元'],open_threads=['下午取件维修并验证冷柜','傍晚前搬回鱼货归还位置','验证后收200元维修尾款']),
3:dict(identity='周小满，独立完成本单维修并结清费用的修理铺经营者。',location='接近傍晚，已从市场回到自己的修理铺柜台。',goal='记录明早查看陈望排风扇的约定，先看现场再说明维修办法。',state='配件已换，冷柜恢复并稳定运行，鱼货回搬，临时位置清理归还，本单300元已结清。',abilities_resources=['工具包与记录收款和预约的小本子','本单累计收到300元服务费；不等于净利润','已实际完成这台冷柜的维修与试机'],relationships=['何桂香从质疑转为明确愿意把修理生意介绍给周小满，尚未实际介绍新客户','陈望参与搬运，并约小满明早看排风扇现场','何桂香和陈望均完成各自约定，不存在未付临时存放费'],knowledge=['冷柜达到适合存鱼的温度，持续观察后运行稳定','鱼货已搬回，包子铺临时位置清理完毕','何桂香早付100元、现付200元，总服务费300元结清；30元存放费此前另付','陈望店里的排风扇时好时坏，原因和能否修好仍未检查'],open_threads=['明早开门后去陈望店里查看排风扇，尚未承诺修复结果'])
}
summaries={1:'何桂香找老周修冷柜，小满检查后说明下午才有配件。双方约定总费300元，先收100元，验证后付200元；两人到陈望店里准备谈临时冷藏。',2:'陈望拒绝鱼与食材混放。三人商定密闭周转箱分放、30元存放费与傍晚前搬走并搬妥鱼货。小满电话落实下午配件，父亲听完已有安排。',3:'小满取件修复冷柜，坚持温度合适且运行稳定后搬鱼。三人清理归还临时位置，何桂香付200元尾款并愿介绍生意；小满约明早看陈望排风扇。'}
commitments={1:['小满拿到配件就回鱼摊，维修后验证冷柜稳定运行再结束本单。','双方约定总服务费300元，已付100元定金，修复验证后再付200元。'],2:['三人约定使用鱼摊自备干净密闭周转箱，与包子铺食材分开存放，傍晚前搬走。','何桂香同意另付30元临时存放费，并已在本章付清。','供货方电话确认所需配件下午可取，小满计划自己去取并返回维修。'],3:['何桂香表示往后有人问修东西，会让对方找周小满；这是介绍意愿，尚无实际转介。','小满与陈望约定明早开门后看排风扇现场，先确认毛病与维修办法，不承诺一定修好。']}
for n in [1,2,3]:
 coverage=[]
 for i,(a,b) in enumerate(ranges[n],1):
  evidence=span(n,a,b);coverage.append(dict(id=f'O{i}',evidence=evidence,source_path=str(paths[n]),source_line=texts[n][:texts[n].index(evidence)].count('\n')+1))
 assert len(summaries[n])<=110
 if n==1:
  metrics={'agreed_total_service_fee_yuan':metric(n,300,'这一单总共三百，配件和这次维修都在里头。'),'received_service_fee_yuan':metric(n,100,'小满收好，在本子上写明已收一百，把金额又指给何桂香确认。'),'remaining_service_fee_yuan':metric(n,200,'两百待修复验证后付。')}
 elif n==2:
  metrics={'agreed_total_service_fee_yuan':metric(n,300,'总共三百，定金一百，试好了再收两百。'),'received_service_fee_yuan':metric(n,100,'小满收好，在本子上写明已收一百，把金额又指给何桂香确认。',1),'remaining_service_fee_yuan':metric(n,200,'总共三百，定金一百，试好了再收两百。'),'separate_storage_fee_paid_yuan':metric(n,30,'她付了三十块。陈望当着她的面收下')}
 else:
  metrics={'agreed_total_service_fee_yuan':metric(n,300,'早上一百，现在两百，三百齐了。'),'received_service_fee_yuan':metric(n,300,'小满接过钱，在早上的记录后写好余款已收'),'received_this_chapter_yuan':metric(n,200,'她就从兜里取出两张一百的，递了过来。'),'remaining_service_fee_yuan':metric(n,0,'早上一百，现在两百，三百齐了。'),'separate_storage_fee_paid_yuan':metric(n,30,'存放那三十，我已经另外付给他。')}
 data=dict(chapter=n,summary=summaries[n],coverage=coverage,protagonist=protagonists[n],commitments=commitments[n],metrics=metrics,provenance={'phase':'postwrite_fact_extraction','not_original_writer_input':True,'candidate_sha256':hashlib.sha256(paths[n].read_bytes()).hexdigest(),'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'role':'writer fact extraction, not independent reader or author adoption'})
 (r/f'metadata/chapter-{n:02d}.postwrite.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 print('chapter',n,'summary_chars',len(summaries[n]),'coverage_exact',len(coverage))
f=r/'inputs/read-files.json';prior=json.loads(f.read_text())
if isinstance(prior,dict):prior=prior['all_files']
prior=list(dict.fromkeys(prior))
gen=[];support=[];audit=[]
for p in prior:
 if '/logs/' in p:audit.append(p)
 elif '/scripts/' in p or p.endswith('.py'):support.append(p)
 else:gen.append(p)
extraction=[str(p.resolve()) for p in paths.values()]+[str(Path(__file__).resolve())]
record={'schema':'writer-read-files-by-phase/v1','generation_and_sequence_inputs':{'files':gen,'note':'Core references, frozen story inputs, chapter outlines/skeletons and actual writer packets; earlier raw chapters consumed only for same-arm sequence continuity. Original generated story-input includes all three authorized chapter boundaries.'},'execution_support':{'files':support,'note':'Runtime checks and self-authored helpers. Programmatically loaded internal runtime dependencies are not additional model reference recall.'},'postwrite_check_logs':{'files':audit,'note':'Read after the corresponding first draft; not original writing input.'},'postwrite_fact_extraction':{'files':extraction,'note':'Read only after all three raw drafts and candidates existed, to extract exact evidence; never supplied to the initial writing calls.'},'all_files':list(dict.fromkeys(prior+extraction))}
f.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n')
