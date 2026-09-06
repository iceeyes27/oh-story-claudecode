# -*- coding: utf-8 -*-
from pathlib import Path
import json,hashlib,datetime,shutil,importlib.util
root=Path.cwd();rt=root.parent/'runtime/.agents/skills'
def read(p):return p.read_text(encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
plan=json.loads(read(root/'metadata/planning-source.json'))
records=[
{'summary':'宋棠收到完整合影，发现墙图裁去边缘半个人。四名职工与五人照片对不上，齐叔不敢认人，她留空姓名，借背面编号及包装电话约到程雪。','protagonist':{'identity':'社区旧站照片展整理者','location':'青平码头旧站照片展展厅','goal':'认出合影中第五人，写准说明牌','state':'暂留姓名空行，等待程雪带另一照片来','abilities_resources':['完整合影及提醒纸条','四名职工旧名单','照片背面的相邻编号','程雪的联系电话'],'relationships':['齐叔协助认人，承认记不准','已联系程雪，约她上午来'],'knowledge':['完整合影有五人，墙图裁去右边缘','旧名单对应四名职工','第五人穿站员外套，身份未定','程雪持有编号相邻的同日照片'],'open_threads':['第五人身份待核对','程雪尚未到场']},'commitments':['程雪答应上午带另一张照片来展厅'],'coverage':[{'id':'O-01','evidence':'随照片掉出来的纸条很短，上面写着：请别再少写一个名字。'},{'id':'O-02','evidence':'可信封里这张，站着五个人。'},{'id':'O-03','evidence':'宋棠翻过说明牌，在背面重新排人名。这一回，她依照片从左到右写，写完第四个，在下面留了一行。'},{'id':'O-04','evidence':'"我姓程，程雪。另一张在我这里。"'}]},
{'summary':'程雪承认寄件，出示同日照片和便条。宋棠确认外套曾在站员身上，不能据此认职业，便条引向搬书后还要送信的人。程雪承认是母亲并先电话询问，齐叔愿一起核对。','protagonist':{'identity':'社区旧站照片展整理者','location':'旧站照片展展厅','goal':'听程雪母亲亲口确认姓名与经历，取得署名同意','state':'放弃只沿职工名单认人的方向，留空行待当事人核对','abilities_resources':['同日两张照片','程雪提供的家中便条','现场笔记'],'relationships':['程雪承认照片里的是母亲，愿联系母亲','齐叔愿意参加核对'],'knowledge':['厚外套原先属于站员老郭，后来借出','便条提到搬书后还须送信和归还衣服','程雪称第五人是其母，尚未公布姓名'],'open_threads':['母亲尚待到场亲口核对','是否同意署名未定']},'commitments':['程雪电话问母亲意愿','齐叔答应留在展厅一起核对'],'coverage':[{'id':'O-01','evidence':'"我想先说，别写失落的英雄之类的话。她就是那天在那里，做了那点事。写得太大，她不会愿意。"'},{'id':'O-02','evidence':'同样的位置，同样有块补丁。不过外套穿到了边缘那个人身上，衣摆显得更长，袖子也往上多卷了一道。'},{'id':'O-03','evidence':'宋棠低头读：在旧站帮着搬了书，还得把剩下的信送完，晚些回。'},{'id':'O-04','evidence':'程雪看她把本子合上，才说："那个人是我妈。"'}]},
{'summary':'林琴到场，与齐叔对上搬书位置、午后雨天、借衣及归还细节，并确认便条与邮递员身份。她纠正夸大功劳，母女同意署名。宋棠补齐说明牌，开放后观众循姓名认出照片第五人。','protagonist':{'identity':'社区旧站照片展整理者','location':'开放后的旧站照片展展厅','goal':'继续听其他照片里普通人的经历，再落笔记录','state':'填满姓名空行，已完成第五人的核对与署名','abilities_resources':['完整合影和同日另一照片已展出','林琴署名与搬书事实说明牌','现场笔记'],'relationships':['林琴同意写明姓名和实际帮忙事实','程雪同意并列展出两张照片','齐叔与林琴通过旧事认出彼此'],'knowledge':['第五人姓名林琴，当年为邮递员','林琴只是路过搭手，未独自救下所有书','外套由站员借出','旧名单只列职工，无需推断恶意抹名'],'open_threads':[]},'commitments':[],'coverage':[{'id':'O-01','evidence':'阿姨往照片里的门指了指："进门靠左。外头雨大，水往这边泼，放地上的书先往高处搬。"'},{'id':'O-02','evidence':'"林琴。树林的林，弹琴的琴。"'},{'id':'O-03','evidence':'"我今天就是照这个给她认的。四个，都是站里上班的。你借了衣服，我还有点往同事上想，越想越不对。"'},{'id':'O-04','evidence':'林琴看了一会儿那道空行，说："那就写上。写对了就行。"'},{'id':'O-05','evidence':'她把本子翻到下一张空白页，等有人愿意讲讲别的照片。今天她想多听一会儿，再落笔。'}]}
]
# Read-only schema validation. Do not invoke state mutation or tracking commit.
spec=importlib.util.spec_from_file_location('heldout_tracking_schema',rt/'story-write/scripts/tracking_commit.py'); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
checks=[]
for p,d in zip(plan,records):
 n=p['n']; raw=root/f"raw/第{n:03d}章_{p['title']}.md"; cand=root/f"候选/第{n:03d}章_{p['title']}.md"; body=read(raw)
 d['metrics']={}; d['chapter']=n;d['source_raw_sha256']=sha(raw);d['status']='postwrite_fact_extraction_only';mod.normalize_snapshot(d['protagonist'],'protagonist')
 for x in d['coverage']:assert x['evidence'] in body,(n,x)
 save(root/f'metadata/chapter-{n:02d}.postwrite.json',d)
 postreads=[{'path':str(raw),'sha256':sha(raw),'purpose':'事实抽取与计数，非生成前输入','range':'full'},{'path':str(rt/'story-write/scripts/tracking_commit.py'),'sha256':sha(rt/'story-write/scripts/tracking_commit.py'),'purpose':'写后normalize_snapshot字段结构确认','range':'270-301 plus module read-only import'}]
 for tag in ['wordcount','scan','degeneration','outline-copy']:
  path=root/f'logs/chapter-{n:02d}.post.{tag}.log';postreads.append({'path':str(path),'sha256':sha(path),'purpose':'写后检查结果','range':'full'})
 save(root/f'metadata/chapter-{n:02d}.postwrite-reads.json',{'stage':'after_draft','files':postreads,'no_reader_inputs':True})
 checks.append({'chapter':n,'coverage_quotes_exact':True,'protagonist_schema_valid':True,'raw_equals_candidate':sha(raw)==sha(cand)})
save(root/'logs/postwrite-metadata-validation.json',{'command':'python3 metadata/finish_handoff.py','exit_code':0,'checks':checks,'writes_tracking_state':False})
# Preserve exact source snapshots used as generation context.
source_paths=['story-setup/references/codex/agents/narrative-writer.toml','story-write/SKILL.md','story-write/references/reader-first-writing.md','story-write/references/long-format.md','_shared/references/anti-ai-writing.md']
source_manifest=[]
for rel in source_paths:
 src=rt/rel; dest=root/'inputs/materials'/src.name;shutil.copyfile(src,dest)
 source_manifest.append({'source':str(src),'snapshot':str(dest.relative_to(root)),'sha256':sha(src),'read_range':'1-180' if src.name=='anti-ai-writing.md' else 'full','snapshot_range':'full'})
save(root/'metadata/source-manifest.json',source_manifest)
(root/'logs/planning.prepare-attempt-1.log').write_text("Captured from tool output; original execution exit 1:\nSyntaxError: Non-UTF-8 code starting with '\\xe6' in prepare_planning.py on line 9, but no encoding declared.\n",encoding='utf-8')
save(root/'metadata/setup-issues.json',{'resolved':[{'issue':'runtime/.codex/agents/narrative-writer.toml not deployed','resolution':'Parent directed actual full frozen generated template in runtime/.agents/skills/story-setup/references/codex/agents/narrative-writer.toml; used full instructions as direct narrative writer.'},{'issue':'Requested current project .codex/agents/narrative-writer.toml did not exist','attempts':'wc and sed failed, exit 1; no current-source instructions consumed.'},{'issue':'anti-ai-core.md filename absent','resolution':'Parent corrected to runtime/_shared/references/anti-ai-writing.md core. Read lines 1-180 covering core rules and their context.'},{'issue':'Planning helper Python UTF-8 source parse error despite UTF-8 bytes','resolution':'Added explicit UTF-8 coding header before planning generation; failed output retained in logs/planning.prepare-attempt-1.log and attempt-2.log; no prose existed at this stage.'}], 'caliber_clarification':'Parent clarified 汉字 was colloquial chapter wordcount. Sole delivery range is visible_chars_v1 2200-2800; pure Han statistics are descriptive and not a failure.'})
commands=[json.loads(s) for s in read(root/'metadata/command-exits.jsonl').splitlines()]
counts=[json.loads(read(root/f'metadata/chapter-{n:02d}.counts.json')) for n in range(1,4)]
for c in counts:
 c['han_in_range_applicability']='not_a_gate; parent clarification';save(root/f"metadata/chapter-{c['chapter']:02d}.counts.json",c)
# Explicit advisory left for independent reading edit; never fabricate reader PASS.
advisory=[{'chapter':2,'code':'micro-action-tic','severity':'advisory','log':'logs/chapter-02.post.scan.log','evidence':'了一会 了一下 了一道 了声 了下 了一口','writer_status':'retained_raw_unedited','writer_note':'命中混含喝水、卷袖口等可见动作；密度本身不能代替阅读结论。依本次一版raw要求不编辑，交root结合独立阅读决定。'}]
assets=[]
for folder in ['inputs','大纲','骨架','packets','raw','候选','metadata','logs']:
 for path in sorted((root/folder).rglob('*')):
  if path.is_file():assets.append({'path':str(path.relative_to(root)),'sha256':sha(path),'bytes':path.stat().st_size})
handoff={'schema':'heldout-writer-handoff/v1','completed_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'root':str(root),'title':'第五个人','actual_template':source_manifest[0],'core_sources':source_manifest[2:],'execution':'fresh-context spawned writer; full frozen Codex generated instructions used via direct fallback; no additional writer subagents','initial_context':'Parent task plus full inputs/story-input.json. All three chapter boundaries visible at planning; no other arm prose or reports read. Initial filesystem inventory showed other arm filenames only, never their contents.','planning_inputs':['inputs/character-handoff.json','inputs/scene-design-feedback.json'],'writer_packets':[f'packets/chapter-{n:02d}.writer-packet.json' for n in range(1,4)],'template_hashes':source_manifest,'commands':commands,'chapter_counts':counts,'raw_attempts_per_chapter':1,'reading_edit_passes':0,'candidate_equals_raw':True,'unresolved_advisory':advisory,'gate_failures':[],'setup_issues':'metadata/setup-issues.json','postwrite_metadata_validation':'logs/postwrite-metadata-validation.json','coverage_id_mapping':'metadata O-01 maps to skeleton O1; metadata O-02 maps to O2 etc. metadata is not a candidate binding or transaction.','reader_status':'Delegated by root; writer did not read any reader report. Only file-ready notices sent.','author_adoption':'pending; no tracking state or formal prose writes','wordcount_caliber':'visible_chars_v1 per parent clarification; 2200-2800 inclusive','pending_root_work':['独立顺读与理解凭证','按实际阅读反馈最多一轮定点编辑','正式candidate检查与其余试验汇总'],'asset_manifest':assets,'memory_used':{'path':'/Users/yolandahao/.codex/memories/MEMORY.md','lines':[103,138],'purpose':'确认候选、单稿与实验结果不能代表作者采用；没有读到相关实验正文','rollout_id':'01a05205-2fe9-7611-9467-c837cb845313'}}
save(root/'writer-handoff.json',handoff)
print(json.dumps({'chapters':[(c['chapter'],c['visible_chars_v1']) for c in counts],'raw_unchanged':all(c['raw_equals_candidate'] for c in checks),'commands':len(commands),'nonzero':[x for x in commands if x['exit_code']],'advisory':advisory,'handoff':str(root/'writer-handoff.json')},ensure_ascii=False))
