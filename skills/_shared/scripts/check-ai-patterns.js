#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node check-ai-patterns.js [--check] [--json] [--fail-on=blocking|all] <file...>

Detect high-risk AI-flavor prose patterns that need human rewrite:
  - negative setup followed by positive flip in the same sentence
  - comma/semicolon/colon + positive flip
  - sentence break + positive flip
  - repeated negative setup followed by positive flip
  - em-dash (按功能改写), 碎句号 (连续短叙述句), 长段落 (按镜头断段)
  - 微动作复读 (「了下/了一下」式轻量补语高密度，电报体指纹)
  - 套式反应细节 (指尖/指节/目光等无功能微动作与「平静得像在念」式语气比喻成片)
  - 抽象总结复读 (命运/棋局/这一刻终于明白/才刚刚开始，AI 结尾腔)
  - 套词密度过高 (仿佛/一丝/深吸一口气/平静无波等禁用词聚集)
  - 比喻密度过高 (像/好像/仿佛/如同等比喻标记成片复现)
  - 抽象裁判金句 (水里/海里/河里“认的是X，不是嘴/威风”、认活路、长骨头等逻辑不落地硬话)
  - 解释链密度过高 (知道/明白/这意味着/必须/需要等判断链聚集)
  - 系统公告公文腔过密 (方括号系统/规则行里硬规则词聚集)
  - 过度精炼短段 (长文本里短叙述段过密且自然连接偏少)
  - 低连接密度 (引号外叙述功能词/白话连接偏少且中长句不足，像提纲/电报体)
  - 监控摄像头式动作清单 (同段连续摆放动作动词，缺少视角温度/情绪缓冲)
  - 音量反差腔 (声音不高/不大…却…, 实战漏网句式)
  - 否定排比 (没有X，没有Y…连排 / 没X…只是Y 先否定后肯定, 实战漏网句式)
  - 工整并列 (至于X不X，怎么X / 同动词「不V A，不V B」，含台词，advisory)
  - 否定校正式排比 (不讲A，只讲B；不求C，只求D, 实战漏网句式)
  - 反序对比 (是A，不是B — not-is 的反序变种, 实战漏网句式)
  - 预告式总结收尾 (文末窗口 没人知道/才刚刚开始/正朝着…压了过去, 实战漏网句式)
  - 旁白口号腔 (引号外叙述喊口号 不胜不休/正义必胜/法治的晴空/正义的铁壁, 实战漏网 F)
  - 引号强调滥用 (叙述里 1-4 字短词加引号强调，密度型)
  - 双端悬空的“的”字身份跳转句 (动作/状态+的，成了+代词)
  - 空壳式人体失真比喻 (骨头/骨架被抽走，只剩皮壳支撑)

Severity 只分两档，按「判定是否需要语境」划线：

blocking —— 只给词表类规则（banned-word-* 系列，以及词表加载失败的 rule-load-error）。
它们判定的是「banned-words.md 明文列出的禁用形态是否出现」，不需要语境判断，出现即替换。
词表是唯一真相源，运行时读 references/banned-words.md，不硬编码、不回退 skill-local 旧副本。

advisory —— 其余全部风格/密度/句式规则（含 voice-contrast / negation-parade / reverse-not-is /
trailer-ending / trailer-summary / english-residue / em-dash 与各 *-tic 密度规则）。
它们是 style/readability 证据，不是 AIGC 判决，也不是自动拒绝规则；一个有功能的真人句子
可以在语境复核后标为 PRESERVED_WITH_FUNCTION——只有语义审查能判断它是否真的伤害了
清晰度、连贯性、声线或节奏。english-residue 尤其依赖题材：短视频/军宣类作品里的
MV、BGM 是正当行业词，不是编辑残留。
--fail-on=blocking 只在出现 blocking finding 时退出 1；默认 --fail-on=all 有任何 finding 即退出 1。

The script reports findings only. It never rewrites text, because the safe fix is
contextual: usually delete the negative setup, write the positive term directly,
or show it via action/detail.`;

const STOP_CHARS = new Set(['。', '！', '？', '!', '?', '\n']);
const SOFT_SEPARATORS = new Set(['，', ',', '、', '；', ';', '：', ':']);
const HARD_SEPARATORS = new Set(['。', '.', '！', '!', '？', '?']);
const MAX_NEGATIVE_SPAN = 80;
const MAX_POSITIVE_SPAN = 80;

// 碎句号：连续 STUTTER_MIN_RUN 个「叙述」短句（每句可见字数 ≤ STUTTER_MAX_SENTENCE）无呼吸。
// 只数叙述句，跳过对话/弹幕/系统播报（成片短句是这些体裁的正常形态，不算碎句号）。
const STUTTER_MIN_RUN = 6;
const STUTTER_MAX_SENTENCE = 5;
// 长段落：单段原始字符数超过阈值即提示按镜头断段（手机阅读保守阈值，正常单段远低于此）。
const LONG_PARAGRAPH_CHARS = 200;

// 微动作复读：「V了下 / V了一下 / 拍了两下 / 松了半圈」式轻量补语在叙述里高密度复现，
// 容易形成删减过头的电报体指纹。只扫引号外叙述；密度与次数双门槛同时达标才报，
// 单次出现是正常中文。
const MICRO_TIC_PATTERN = /了(?:[一两三几半])?[下阵圈道声眼口气会]/g;
const MICRO_TIC_MIN_HITS = 5;
const MICRO_TIC_PER_KILO = 6;

// 套式反应细节：不是禁写身体，而是提示成片出现的“部位 + 轻微动作/状态”、
// “胸口像被撞了一下”、喉结/眼圈/声音放轻等通用情绪尾巴，以及“平静语气 +
// 像在念/宣判”模板。此类句子词面变化大，不能逐词 blocking；按章聚集到 4 处才
// advisory，要求逐处做删除测试。正常受伤、打斗、生理反应若承担物理后果可保留。
const STOCK_REACTION_PATTERNS = [
  /(?:指尖|手指|指节|手背|掌心|拳头|袖口|衣角|裙角|下唇|嘴唇|唇角|嘴角|眉头|眼底|眸光|目光|视线|肩膀|呼吸)[^。！？!?\n]{0,16}(?:轻轻|微微|缓缓|悄然|不自觉|无意识|下意识|攥紧|握紧|收紧|绞紧|泛白|发白|叩|敲|摩挲|抿紧|抿成|移开|垂下|躲开|一颤|颤了?一下|停了?一下|顿了?一下)/g,
  /(?:语气|声音)[^。！？!?\n]{0,12}(?:平静|冷静|平淡|冷淡|淡漠|平直)[^。！？!?\n]{0,12}(?:像|仿佛|如同|好像)[^。！？!?\n]{0,16}(?:念|读|报|说|陈述|宣判|背诵)/g,
  /(?:胸口|心口)[^。！？!?\n]{0,16}(?:像|仿佛|如同|好像)[^。！？!?\n]{0,16}(?:撞|锤|压|攥|堵)[^。！？!?\n]{0,8}(?:一下|一记|一拳)?/g,
  /(?:声音|嗓音|语气)[^。！？!?\n]{0,12}(?:放轻|压低|发紧|发颤|很轻|轻了些)/g,
  /(?:喉结|喉头|喉咙)[^。！？!?\n]{0,10}(?:滚|动|紧|堵|发涩|发干)/g,
  /(?:眼眶|眼圈|鼻子)[^。！？!?\n]{0,8}(?:发红|红了|发热|发酸|一酸)/g,
  /(?:抿了?下唇|抿了?抿唇|抿了?下嘴|抿着笑)/g,
];
const STOCK_REACTION_MIN_HITS = 4;
// 校准（真人语料，<br> 已还原为换行）：qimao 长篇 5584 章 + heiyan 短篇整篇 3983 篇。
// 长篇章尺度（中位约 2100 字）per-kilo 1.0→1.5 误报 0.43%→0.39%，几乎不动；
// 短篇整篇 8000-20000 字下 MIN_HITS 形同虚设、只剩密度门，1.0 时误报 5.57%，
// 1.5 降到 1.46%。故取 1.5，把两个总体拉到同一量级（四份副本共用一组阈值）。
const STOCK_REACTION_PER_KILO = 1.5;

// 监控摄像头式动作清单：同一段连续堆叠通用动作动词（伸手/拿起/取过/挑开/放下/转身等），
// 且用逗号/顿号串联成步骤表时，读感像无视角温度的监控记录。只做 advisory；
// 打斗/追逐等功能性动作编排可保留或人工复核。
const ACTION_LIST_VERB_PATTERN = /伸手|抬手|探手|拿起|拿过|取出|取过|掏出|摸出|抓起|攥住|握住|捏住|按住|推开|拉开|打开|关上|放下|递给|挑开|掀开|扯开|拧开|倒出|端起|转身|回头|抬头|低头|弯腰|俯身|走到|走向|坐下|站起|看向|看着|盯着|扫过/g;
const ACTION_LIST_MIN_HITS = 5;
const ACTION_LIST_MIN_SEPARATORS = 4;

// 抽象总结复读：模板化段落常把角色当下经历拔成「命运/棋局/
// 这一刻终于明白/才刚刚开始」的作者总结。单个词可能服务题材；高密度聚集才报。
const ABSTRACT_SUMMARY_PATTERNS = [
  /这一刻[，,]?[^\n。！？!?]{0,24}(?:终于|才)(?:明白|意识到)/g,
  /从这一刻开始/g,
  /(?:命运|宿命)[^\n。！？!?]{0,28}(?:齿轮|棋局|獠牙|改写|推向|安排)/g,
  /早已[^\n。！？!?]{0,8}(?:布好|安排好)[^\n。！？!?]{0,8}(?:棋局|局)/g,
  /前所未有的(?:决意|清醒|勇气|力量|恐惧|平静|信念)/g,
  /(?:反击|复仇|战争|较量|故事|命运)[^\n。！？!?]{0,12}才刚刚开始/g,
  /(?:新的开始|全新的开始)/g,
];
const ABSTRACT_SUMMARY_MIN_HITS = 3;
const ABSTRACT_SUMMARY_PER_KILO = 4;

// 套词密度：单个「仿佛/一丝」可能是正常中文，高密度聚集才会形成模板腔。
// 词表只收本 repo banned-words 中已明确标为高危的形态，避免把普通功能词一网打尽。
const CLICHE_PATTERNS = [
  /仿佛|犹如|宛若|如同/g,
  /一丝|一抹|些许|几分|隐约/g,
  /深吸一口气|缓缓|微微|轻轻|淡淡/g,
  /眼中闪过|嘴角勾起|眸光微微一闪|指节泛白|目光锐利|眼神锐利/g,
  /心中涌起一股|心头一震|心中一动|心下了然|心中暗道|心中一凛/g,
  /不容置疑|不容置喙|不易察觉|显而易见|毫无疑问|不可否认/g,
  /声音不大[，,]?却带着|语气平静无波|平静无波|声音平直|听不出情绪/g,
  /不知何时|唾手可得|无声翻涌|沉默(?:在[^。！？!?\n]{0,16})?蔓延|难以言说/g,
  /散发着一股|冰冷的光|格外刺眼|深邃而冰冷/g,
];
const CLICHE_DENSITY_MIN_HITS = 8;
const CLICHE_DENSITY_PER_KILO = 12;

// 比喻密度：单个生活化比喻可服务画面；“像/好像/仿佛/如同”成片复现时，
// 容易变成 AI 式修辞堆叠。只做 advisory，修法是删到必要数量并回到具体画面，
// 不是把“像”换成另一组比喻词。
const METAPHOR_MARKER_PATTERN = /好像|像是|仿佛|宛如|如同|犹如|(?<![不头图画影录摄肖])像(?![头像素])/g;
const METAPHOR_LIKE_PHRASE_PATTERN = /(?:死|水|冰|火|潮水|石头|木头|机器|纸|铁|鬼|死人|刀|针|网|墙)一样/g;
const METAPHOR_DENSITY_MIN_HITS = 7;
const METAPHOR_DENSITY_PER_KILO = 3;

// 抽象裁判金句：台词里常见“海里/水里认的是X，不是你嘴上那点Y”这类硬话。
// 问题不是角色不能说狠话，而是把“水/真/命”写成抽象裁判，逻辑落不到能力、证据或规矩上。
// 本规则查全行（含台词），因为这类问题常出现在引号内。
const ABSTRACT_AUTHORITY_PATTERNS = [
  /(?:海里|水里|江里|河里|海上|水上)[^。！？!?\n]{0,24}认的是[^。！？!?\n]{1,18}，?不是(?:你|他|她|他们|咱们|我们)?[^。！？!?\n]{0,18}(?:嘴|口气|威风|漂亮话|狠话)/g,
  /认的是[^。！？!?\n]{0,12}水里那口真/g,
  /认活路/g,
  /长骨头/g,
];

// 旁白口号腔（实战漏网 F，2026-08-19 从《法援律师》168 章全量扫描固化）：
// 叙述者跳出剧情替全书喊口号——「法援律师用铁一般的证据与法条，逐一击穿了……，
// 必将在法治的晴空下……，正义必胜！」。判据：把句子抽出来读，像不像电视普法节目的
// 旁白字幕/法治宣传片解说词。像 → 命中。只扫引号外叙述（maskQuoted），引号内台词
// 由 dialogue-naturalness-scan 第 6 类覆盖，不重复计；in-world 群聊/群众口号
// （如家长群刷「正义必胜」）在引号内被 mask 排除。
// 校准：修复前《法援律师》全书 20+ 处旁白命中；修复后 0 命中（群聊豁免）。
const NARRATION_SLOGAN_PATTERNS = [
  /不胜不休|正义必胜|朗朗乾坤|朗朗晴空|公道自在人心|依法维权到底|公平正义重见天日/g,
  /正义的(?:审判|锁链|巨浪|钟声|铁壁|利剑|之剑|之笔|铁拳|法网|利刃|防线)/g,
  /法治的(?:晴空|轨道|底线|威严|蓝天|审判)/g,
  /正义(?:绝不|永不|终将|必将)(?:向|对|被|让|洗|还|守|来|到|低|妥|缺)/g,
  /胜利(?:终将|必将)属于/g,
  /(?:法援律师|律师团队|我们)(?:用|以|拿|紧握|手握着|的目光坚定如铁)/g,
  /(?:筑起|铸就|扛起|举起|高擎)(?:了)?(?:正义|法治|法律的)(?:铁壁|屏障|盾牌|巨伞|大旗|旗帜|长城)/g,
  /(?:撕开|揭开|撕碎|击穿|戳穿|砸碎)(?:了)?(?:一切|所有)?(?:虚伪|伪善|伪装)(?:面具|外壳|皮|壁)/g,
  /(?:真相|正义|公理)(?:终将|必将|一定|迟早会)大白(?:于天下)?/g,
  /(?:光明|阳光|黎明)(?:终将|必将)来临|(?:黑夜|黑暗)终将过去/g,
  /(?:告慰|不负)[^。！？!?\n]{0,12}(?:在天之灵|亡灵)/g,
  /(?:任何|一切)[^。！？!?\n]{0,12}(?:违法|践踏|亵渎|阴谋|黑恶)[^。！？!?\n]{0,12}(?:必将|都将|都会)[^。！？!?\n]{0,8}(?:严惩|制裁|付出代价|无处遁形|灰飞烟灭|化为乌有)/g,
  /(?:铸就|奠定|树立|打造|建立)(?:了)?(?:一座|一道)?(?:坚如磐石|永不磨灭|坚不可摧|崇高无暇|不可动摇)?(?:的)?(?:堡垒|丰碑|长城|奇迹|基石|神话|大厦|伟业|铠甲)/g,
  /(?:粉碎|击碎|挫败)(?:了)?(?:来自|所有)?(?:各方|一切|旧官僚|对手|国际金融)?(?:的)?(?:暗算|阴谋|企图|挑衅|围剿|反扑|计划|妄想)/g,
  /一场(?:体制|商业|金融|暗流)?(?:层面)?(?:的)?(?:暗流)?交锋[^。！？!?\n]{0,20}(?:化为无形|落幕|定鼎)/g,
  /地位愈发(?:固若金汤|坚不可摧|牢不可破|不可动摇)/g,
];

// 解释链密度：常见“他知道/他明白/这意味着/必须需要”
// 连续替读者推理，读感像报告。单个判断词可服务推理；高密度聚集才提示回到角色当下证据。
const REASONING_CHAIN_PATTERNS = [
  { key: 'mental', core: true, pattern: /(?<![不没未无])(?:他|她|我)?(?:知道|明白|意识到|清楚|判断|确认|分析)/g },
  { key: 'connector', core: true, pattern: /这意味着|也就是说|换句话说|真正的问题(?:在于)?|问题在于|关键在于|在这种情况下|按照这个逻辑|只有这样|想到这里/g },
  { key: 'modal', core: true, pattern: /(?:(?<!不)(?:必须|需要|应该|只要|就会|可能|可以|能够|无法)|不能)[^。！？!?\n]{0,16}(?:判断|确认|承担|维持|稳住|控制|扩大|失控|带来|造成|理解|默认|回家|进门|核对|筛选|减少|建立|风险|结果|秩序|责任)/g },
  { key: 'abstract', core: false, pattern: /(?:任务|条件|风险|来源|逻辑|局面|结果|责任|秩序|规则|信息不足|决策能力)/g },
];
const REASONING_CHAIN_MIN_HITS = 8;
const REASONING_CHAIN_CORE_MIN_HITS = 4;
const REASONING_CHAIN_MIN_BUCKETS = 2;
const REASONING_CHAIN_PER_KILO = 18;

// 系统公告公文腔：只看成片方括号规则/面板行里的硬规则词。
// 这不是特定题材词表；单条严肃规则、日常叙述或普通对话不触发。
const NOTICE_FORMAL_PATTERNS = [
  /不得|必须|不可|禁止|严禁|应当|须|需|务必/g,
  /当前|本公告|本规则|本系统|提示|任务失败|临时权限|权限|状态|等级/g,
  /维持|公共区域|秩序|优先|惩罚|处罚|违规|指令|执行/g,
  /被视为|同样计入|计入|承担|责任|单位|撤回|转发|截图/g,
];
const NOTICE_FORMAL_CORE_PATTERN = /不得|必须|不可|禁止|严禁|应当|须|需|务必|被视为|同样计入|计入/g;
const NOTICE_FORMAL_MIN_LINES = 4;
const NOTICE_FORMAL_MIN_HITS = 12;
const NOTICE_FORMAL_CORE_MIN_HITS = 5;
const NOTICE_FORMAL_PER_KILO = 60;

// 过度精炼短段：过度处理样本里常见大量 15 字以内叙述段，且“的/了/就/着/过/呢/吧/啊”等
// 自然连接偏少；对照文本通常保留更多自然连接。此项只做 advisory，禁止机械注水。
const OVERCOMPRESSED_PROSE_PARTICLE_PATTERN = /[的了就着过呢吧啊呀嘛]/g;
const OVERCOMPRESSED_PROSE_MIN_CHARS = 1200;
const OVERCOMPRESSED_PROSE_MIN_PARAS = 45;
const OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS = 15;
const OVERCOMPRESSED_PROSE_SHORT_RATIO = 0.58;
const OVERCOMPRESSED_PROSE_PARTICLE_PER_KILO = 85;

// 低连接密度：单纯低功能词会误抓有大量中长句的文本；
// 因此必须叠加“中长句不足”，并只看引号外叙述。这是 overcompressed 的短窗口补充，只做 advisory。
const LOW_CONNECTIVE_FUNCTION_TERMS = ['的', '了', '就', '在', '是', '也', '都', '还', '又', '把', '被', '给', '这个', '那个', '里面', '以后', '时候', '现在', '因为', '所以', '但是', '不过', '然后', '已经', '还是', '起来', '出来', '下去'];
const LOW_CONNECTIVE_PLAIN_TERMS = ['的', '了', '就', '也', '还', '又', '这个', '那个', '东西', '事情', '时候', '里面', '以后', '一下', '一点', '有点', '还是'];
const LOW_CONNECTIVE_MIN_CHARS = 800;
const LOW_CONNECTIVE_FUNCTION_PER_KILO = 100;
const LOW_CONNECTIVE_PLAIN_PER_KILO = 65;
const LOW_CONNECTIVE_LONG_SENTENCE_CHARS = 30;
const LOW_CONNECTIVE_LONG_SENTENCE_RATIO = 0.08;

// either-or「不是A就是B / 不是A也是B」里紧贴的「是」是连词的一部分，不是肯定项系动词。
// 含「不」以沿用「不是A，也不是B」第二个否定段不算翻转的旧排除。
const COMPACT_EITHER_OR_PREV = new Set(['不', '就', '也']);
// 句尾语气/反问助词；「…，是吗 / 是吧 / 是嘛」是反问尾巴，不是否定后的肯定翻转。
const TAG_PARTICLES = new Set(['吗', '吧', '嘛']);
// 段首确认语；「不是第一次来。是的，他还记得……」里的「是的/是啊」
// 是承接确认，不是「不是 A，是 B」的肯定翻转。
const AFFIRMATION_TAG_PARTICLES = new Set(['的', '啊', '呀', '呢']);
const AFFIRMATION_TAG_BOUNDARY = new Set(['', '，', ',', '。', '.', '！', '!', '？', '?', '、', '；', ';', '：', ':', '\n', '\r', '\t', ' ']);

// 成对引号（台词/系统播报/弹幕）的字符对，stripQuoted 与 quotedRanges 共用一份来源。
// 引号片段一律不跨行（字符类里排掉 \n）：正文漏一个收引号很常见（多段台词只在末段收尾、
// 全半角引号混用都会漏），若允许跨行配对，一个未闭合的开引号会把后面成百上千字全算成
// 「引号内」，让 quotedRanges 的消费方（not-is 跨行扫描）把整段叙述静默豁免掉。
const QUOTE_PAIRS = [['「', '」'], ['『', '』'], ['【', '】'], ['“', '”'], ['‘', '’'], ['"', '"'], ["'", "'"]];
const QUOTE_SOURCES = QUOTE_PAIRS.map(([open, close]) => `${escapeRegExp(open)}[^${escapeRegExpCharClass(close)}\\n]*${escapeRegExp(close)}`);

// ---- 实战测试漏网句式（来源：实战写作抓到的真实漏网例句；2026-07 校准）----
// 校准基线：《万疆》真人正文 20 章（第1/10/20/…/190章）+ demo 前 20 章。
// blocking 规则要求真人语料命中 ≈0（每 20 章 ≤1 处且人工判定确属该句式）；数据见各规则注释。

// 音量反差腔（实战漏网 A）：「声音不高，第一句却稳稳压住了整个大厅。」
// 旧网只有套词密度桶里的「声音不大，却带着」，音量词/转折词一换就漏。
// 引号外叙述逐处提示；是否修改取决于语境中的信息、声线与节奏功能。
// 校准：《万疆》20 章 0 命中，demo 前 20 章 0 命中。
const VOICE_CONTRAST_PATTERN = /声音(?:并)?不[大高响亮][^。！？!?\n]{0,16}[却但偏]/g;

// 否定排比（实战漏网 B）：「没有伴奏，没有和声，没有提词器。」同句 ≥2 个「没有X，」连排；
// 变体「他没炫技，没有那种…架势。他只是唱」先否定铺垫、再用「只是/只会/只有」收肯定。
// 只收「没/没有」段，不收「不X」段——真人叙述里「不哭不闹」类太常见，收进来误报换不来收益。
// 光杆「没」还得挡两类非否定用法，否则正常叙述会被判成排比：
//   1) 黏着语素（沉没/淹没/埋没/出没/隐没…）——前字排除，「船沉没在雾里，没人回头，…只有…」不算；
//   2) 时间惯用语（没多久/没过多久/没等X）——后字排除，「没多久，没等她撑伞，…只有…」不算。
// 「没有X」段不带这两种歧义（黏着语素后接不出「有」，时间惯用语已被后字排除覆盖），
// 第一条连排式照旧不加护栏。
// 校准：《万疆》20 章 0 命中，demo 前 20 章 0 命中。
const NEGATION_PARADE_PATTERNS = [
  /(?:没有[^。！？!?\n，,]{1,12}[，,]){2}/g,
  /(?<![沉淹埋出隐湮吞覆漫泯])没(?!有?过?多久)(?:有)?[^。！？!?\n，,]{1,12}[，,]\s*没(?!有?过?多久)(?:有)?[^。！？!?\n，,]{1,16}[，,。.][^。！？!?\n，,]{0,6}只(?:是|会|有)/g,
];
const CROSS_NEGATION_START = /^不是[^。！？!?\n]{1,24}[。！？!?]?$/;
const CROSS_NEGATION_MIDDLE = /^(?:也|还)不是[^。！？!?\n]{1,24}[。！？!?]?$/;
const CROSS_NEGATION_END = /^只是[^。！？!?\n]{1,32}[。！？!?]?$/;

// 两类常见但不能直接判错的工整框架，只做 advisory。与 blocking 规则不同，这里故意扫描
// 台词：自然点单「不放辣，不放葱」靠对象最短长度排除；更长的同动词清单交语义审查判断功能。
const DECISION_FRAME_PATTERN = /至于([\u3400-\u9fff]{1,3})不\1[，,]\s*怎么\1/g;
const REPEATED_NEGATIVE_VERB_PATTERN = /不([\u3400-\u9fff]{1,2})([\u3400-\u9fff]{2,8})[，,]\s*不\1([\u3400-\u9fff]{2,8})/g;

// 否定校正式排比（实战漏网 B2）：“不讲A，只讲B；不求C，只求D”。
// 单个“不X，只Y”在自然口语中很常见，只拦同句双联且中间用分号对齐的变体，避免误报。
const NEGATION_ONLY_PARALLEL_PATTERN = /(?:不讲|不求|不谈|不要|不看|不管|不图|不问|不争|不算|不在乎|不考虑)[^。！？!?\n；;，,]{1,18}[，,]\s*(?:要的)?只[^。！？!?\n；;]{1,24}[；;]\s*(?:也)?(?:不讲|不求|不谈|不要|不看|不管|不图|不问|不争|不算|不在乎|不考虑)[^。！？!?\n；;，,]{1,18}[，,]\s*只[^。！？!?\n]{1,30}/g;

// 反序对比腔（实战漏网 C）：「是真嗓子，不是修音修出来的」——not-is-comparison 的反序变种。
// 复用 not-is 的排除基建：引号内剥离（maskQuoted）、「是的/是啊」确认语（isAffirmationTagAt）；
// 前字排除从 either-or 的 不/就/也 扩展到全部「X是」连词/副词合成词（还是/只是/可是/但是/
// 于是/倒是/像是/若是/要是/正是/便是/总是/老是/更是/最是/算是/怕是/凡是/或是/即是/自是/
// 竟是/原是/本是/仍是/许是/净是/光是/单是/尽是）；「是不是」问句起头与「不是吗/不是么/
// 不是吧」反问尾巴单独排除。
// 校准：《万疆》20 章 0 命中，demo 前 20 章 0 命中，按 blocking 实现。
const REVERSE_NOT_IS_PATTERN = /是([^。！？!?\n，,]{1,12})[，,]\s*(?:而)?不是([^。！？!?\n]{1,20})/g;
const REVERSE_NOT_IS_PREV_EXCLUDE = new Set([...COMPACT_EITHER_OR_PREV, '还', '只', '可', '但', '于', '倒', '像', '若', '要', '正', '便', '总', '老', '更', '最', '算', '怕', '凡', '或', '即', '自', '竟', '原', '本', '仍', '许', '净', '光', '单', '尽']);

// 预告式总结收尾（实战漏网 D）：「没人知道，这才刚刚开头。」「一场…震惊接力，正朝着…缓缓压了过去。」
// 章尾替读者预告下一章走向是 AI 收尾腔。只扫文末窗口（剥引号后可见字数，按行取整），
// 正文中段的「没人知道」多为普通叙述，不误伤；引号内台词（「没人知道…」）不计。
// 「正式拉开序幕/帷幕」是场内事件的报幕式陈述（真人语料「钟声再度响起，比赛正式拉开序幕」），
// 不是叙述者预告，前置 lookbehind 排除。
// 校准：《万疆》20 章排除「正式拉开序幕」2 处报幕句后 0 命中，demo 前 20 章 0 命中。
const TRAILER_ENDING_PATTERN = /没人知道|谁也不知道|谁也没想到|殊不知|(?:这)?才刚刚开(?:始|头)|正(?:朝着|向着)[^。！？!?\n]{0,24}(?:压|涌|袭|逼)(?:了?过去|了?过来|来)|(?<!正式)拉开(?:序幕|帷幕)|即将(?:开始|来临|降临)/g;
const TRAILER_ENDING_WINDOW_CHARS = 600;

// 章尾状态总结体与部署 hook 使用同一规格：收束状态是细纲的规划口径，正文应停在
// 具体动作、画面或台词上。每个分支都要求落在句末，避免误伤条件从句、动补、成语、
// 系表与认知句；引号内容仍由 maskQuoted 排除。
const TRAILER_SUMMARY_PATTERN = /这一(?:夜|天|刻|战|年|局|役)[，,]?[^。！？!?，,\n]{0,6}(?<!命中)(?<!是)注定[^。！？!?\n]{0,8}[。！]|就这样[，,][^。！？!?，,\n]{0,8}(?:一切|全部)[^。！？!?，,\n]{0,4}(?:结束了|落幕|收场)[。！]|这一切[，,]?[^。！？!?，,\n]{0,6}(?:都)?(?:说明|意味着|结束了)(?!的)(?:(?!什么)[^。！？!?\n]){0,6}[。！]|(?:新的篇章|新的旅程|崭新的篇章|新的人生)[^。！？!?\n]{0,6}(?:开始|拉开|展开)|命运[^。！？!?\n]{0,6}齿轮/g;

// 引号强调滥用（实战漏网 E，advisory 密度型，风格照 metaphor-density-tic）：
// 叙述里短词加引号强调（他是被请来"把关"的）。只数叙述层 1-4 字成对引号片段；
// 排除项：【】系统面板载体、引语动词（说|道|问|喊|答|念|叫|回|吼|嘀咕，加细 骂|写|读|唱）
// 前 6 字/后 3 字邻接的极短台词、引号内含句读的台词、引号外无叙述的行（独立台词/
// 弹幕流/拟声词连发）、引号套引号（台词内强调）。全文 ≥3 处报一条——单处强调是
// 正常修辞，密度高才是模板腔。
// 校准：demo 前 20 章 0 章过阈值；《万疆》20 章 2 章过阈值（海报标语“我在番城”系列、
// “邀战书”等转述载体，真人也这么写），所以该规则只做 advisory，不升 blocking。
const QUOTE_EMPHASIS_MIN_HITS = 3;
const QUOTE_EMPHASIS_MAX_VISIBLE = 4;
const QUOTE_EMPHASIS_SPEECH_VERB_PATTERN = /[说道问喊答念叫回吼骂写读唱嘀咕]/;

const options = {
  json: false,
  files: [],
  failOn: 'all',
};

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--check') {
    // Accepted for symmetry with normalize-punctuation.js; detection is always check-only.
  } else if (arg === '--json') {
    options.json = true;
  } else if (arg.startsWith('--fail-on=')) {
    const v = arg.slice('--fail-on='.length);
    if (v !== 'blocking' && v !== 'all') die(`--fail-on must be 'blocking' or 'all'`);
    options.failOn = v;
  } else if (arg === '-h' || arg === '--help') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('-')) {
    die(`Unknown option: ${arg}`);
  } else {
    options.files.push(arg);
  }
}

if (options.files.length === 0) {
  die('No files provided');
}

let failed = false;
const allFindings = [];

for (const file of options.files) {
  const fullPath = path.resolve(file);
  let input;
  try {
    input = fs.readFileSync(fullPath, 'utf8');
  } catch (error) {
    failed = true;
    if (!options.json) console.error(`${file}: unable to read (${error.message})`);
    continue;
  }

  const findings = scanDocument(input).map((finding) => ({ file, ...finding }));
  allFindings.push(...findings);
}

if (options.json) {
  process.stdout.write(`${JSON.stringify({ findings: allFindings }, null, 2)}\n`);
} else {
  for (const finding of allFindings) {
    console.log(`${finding.file}:${finding.line}:${finding.column}: [${finding.severity}] ${finding.type}: ${finding.message} (${finding.excerpt})`);
  }
}

// Do not call process.exit() after writing JSON to a pipe. Large multi-file
// reports may still be buffered, and an immediate exit truncates the JSON.
// Setting exitCode preserves the status while allowing stdout to flush.
if (failed) process.exitCode = 2;
// --fail-on=blocking 只在出现 blocking finding 时退出 1（advisory 仅报告）；默认 all 沿用「有任何 finding 即 1」。
const hasBlocking = allFindings.some((f) => f.severity === 'blocking');
if (!failed && (options.failOn === 'blocking' ? hasBlocking : allFindings.length > 0)) {
  process.exitCode = 1;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeRegExpCharClass(text) {
  return text.replace(/[\\\]^-]/g, '\\$&');
}

function die(message) {
  console.error(message);
  console.error(USAGE.trimEnd());
  process.exit(2);
}

function scanDocument(input) {
  const lines = input.split(/\r?\n/);
  const findings = [];
  let fence = null;
  let inFrontMatter = hasYamlFrontMatter(lines);
  let block = [];
  const proseLines = [];

  const flushBlock = () => {
    if (block.length === 0) return;
    findings.push(...scanBlock(block));
    block = [];
  };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();

    if (inFrontMatter) {
      if (index > 0 && trimmed === '---') inFrontMatter = false;
      continue;
    }

    const fenceMarker = parseFenceMarker(trimmed);
    if (fence) {
      if (fenceMarker && fenceMarker.char === fence.char && fenceMarker.length >= fence.length) {
        fence = null;
      }
      continue;
    }

    if (fenceMarker) {
      flushBlock();
      fence = fenceMarker;
      continue;
    }

    block.push({ text: line, lineNo: index + 1 });
    proseLines.push({ text: line, lineNo: index + 1 });
  }

  flushBlock();
  findings.push(...scanProsePatterns(proseLines));
  findings.sort((a, b) => a.line - b.line || a.column - b.column);
  return findings;
}

// 段落级检测：碎句号（连续短叙述句）、长段落、破折号（按功能改写，非机械替换）。
function scanProsePatterns(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;

    const dashPattern = /——|—|--+/g;
    let dash;
    while ((dash = dashPattern.exec(text)) !== null) {
      findings.push({
        line: lineNo,
        column: dash.index + 1,
        type: 'em-dash',
        severity: 'advisory',
        message: '破折号按功能改写：打断→动作 beat/短句，拖长音→省略或动作，插入说明→逗号/冒号；勿一律改句号。',
        excerpt: compact(text.slice(Math.max(0, dash.index - 8), dash.index + dash[0].length + 8)),
      });
    }

    if (trimmed.length > LONG_PARAGRAPH_CHARS) {
      findings.push({
        line: lineNo,
        column: 1,
        type: 'long-paragraph',
        severity: 'advisory',
        message: `段落过长（${trimmed.length} 字）：按镜头/新动作/新线索/视线切换断段，别一段到底。`,
        excerpt: compact(trimmed.slice(0, 40)),
      });
    }
  }

  findings.push(...findVoiceContrast(proseLines));
  findings.push(...findNegationParade(proseLines));
  findings.push(...findFormulaicParallelism(proseLines));
  findings.push(...findNegationOnlyParallel(proseLines));
  findings.push(...findReverseNotIs(proseLines));
  findings.push(...findTrailerEnding(proseLines));
  findings.push(...findTrailerSummary(proseLines));
  findings.push(...findQuoteEmphasisTic(proseLines));
  findings.push(...findPeriodStutter(proseLines));
  findings.push(...findMicroActionTic(proseLines));
  findings.push(...findStockReactionTic(proseLines));
  findings.push(...findActionListTic(proseLines));
  findings.push(...findAbstractAuthoritySlogan(proseLines));
  findings.push(...findAbstractSummaryTic(proseLines));
  findings.push(...findClicheDensityTic(proseLines));
  findings.push(...findMetaphorDensityTic(proseLines));
  findings.push(...findReasoningChainTic(proseLines));
  findings.push(...findNoticeFormalityTic(proseLines));
  findings.push(...findOvercompressedProseTic(proseLines));
  findings.push(...findLowConnectiveDensityTic(proseLines));
  findings.push(...findBannedWordsExact(proseLines));
  findings.push(...findSynestheticMetaphor(proseLines));
  findings.push(...findAntithesis(proseLines));
  findings.push(...findDanglingIdentityShift(proseLines));
  findings.push(...findBodyShellMetaphor(proseLines));
  findings.push(...findContrastRhetorical(proseLines));
  findings.push(...findPhysicalClear(proseLines));
  findings.push(...findAbstractObjectForced(proseLines));
  findings.push(...findPainAsObject(proseLines));
  findings.push(...findGreyCrackInHead(proseLines));
  findings.push(...findSummarySlogan(proseLines));
  findings.push(...findNarrationSlogan(proseLines));
  findings.push(...findEnglishResidue(proseLines));
  findings.push(...findProcessTermAsObject(proseLines));
  return findings;
}

// 抽象裁判金句：逐句报告，blocking。修法是把抽象裁判落成具体能力/证据/规矩。
function findAbstractAuthoritySlogan(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;

    for (const pattern of ABSTRACT_AUTHORITY_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) {
        const hit = match[0];
        findings.push({
          line: lineNo,
          column: match.index + 1,
          type: 'abstract-authority-slogan',
          severity: 'advisory',
          message: '抽象裁判金句：把“水/真/命/骨头/活路”写成裁判但逻辑不落地；改成具体能力、来路证据、行内规矩或组织结果，如“海里讲的是水性，不是嘴上那点威风”。',
          excerpt: compact(hit),
        });
      }
    }
  }

  return findings;
}

// 音量反差腔（实战漏网 A）：引号外叙述逐处提示，位置与摘录取自原文
// （maskQuoted 等长占位保偏移；命中片段不含问号占位符，故不会落进占位区）。
function findVoiceContrast(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);
    VOICE_CONTRAST_PATTERN.lastIndex = 0;
    let match;
    while ((match = VOICE_CONTRAST_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'voice-contrast',
        severity: 'advisory',
        message: '音量反差腔：「声音不大/不高…却/但…」是 AI 高频反差模板；删掉音量铺垫，直接写声音落进场子的具体效果（谁停了手、哪排安静了）。',
        excerpt: compact(text.slice(match.index, match.index + match[0].length)),
      });
    }
  }

  return findings;
}

// 旁白口号腔：逐处 blocking。只扫引号外叙述；摘录取自 mask 前原文保持可读。
function findNarrationSlogan(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);
    const spans = [];
    for (const pattern of NARRATION_SLOGAN_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(masked)) !== null) {
        spans.push([match.index, match.index + match[0].length]);
      }
    }
    spans.sort((a, b) => a[0] - b[0]);

    let lastEnd = -1;
    for (const [start, end] of spans) {
      if (start < lastEnd) {
        lastEnd = Math.max(lastEnd, end);
        continue;
      }
      lastEnd = end;
      findings.push({
        line: lineNo,
        column: start + 1,
        type: 'narration-slogan',
        severity: 'advisory',
        message: '旁白口号腔：叙述者跳出剧情喊口号（「不胜不休/正义必胜/法治的晴空/正义的铁壁」家族），读着像普法宣传片解说词。删掉口号尾，收束成角色当下可见的场景/动作/物件（窗外、白板、证据链、灯光、卷宗），情绪留给下一章钩子，不替读者下结论。',
        excerpt: compact(text.slice(Math.max(0, start - 12), Math.min(text.length, end + 12))),
      });
    }
  }

  return findings;
}

// 否定排比（实战漏网 B）：同句「没有X，」连排 / 先否定后「只是」收肯定。
// 可能在同一片文字上重叠命中，按区间去重只报一次。
function findNegationParade(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);

    const spans = [];
    for (const pattern of NEGATION_PARADE_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(masked)) !== null) {
        spans.push([match.index, match.index + match[0].length]);
      }
    }
    spans.sort((a, b) => a[0] - b[0]);

    let lastEnd = -1;
    for (const [start, end] of spans) {
      if (start < lastEnd) {
        lastEnd = Math.max(lastEnd, end);
        continue;
      }
      lastEnd = end;
      findings.push({
        line: lineNo,
        column: start + 1,
        type: 'negation-parade',
        severity: 'advisory',
        message: '否定排比：「没有X，没有Y…」/「没X，没有Y，只是Z」是 AI 高频排比模板；删掉否定清单，直接写现场实际有什么，最多留一个最有信息量的否定。',
        excerpt: compact(text.slice(start, end)),
      });
    }
  }

  return findings;
}

function findFormulaicParallelism(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    for (const [pattern, message] of [
      [DECISION_FRAME_PATTERN, '「至于X不X，怎么X」把同一决定拆成工整栏目；若只是复述细纲，压成角色当下的一次判断或直接动作。'],
      [REPEATED_NEGATIVE_VERB_PATTERN, '同动词「不V A，不V B」容易写成否定清单；含台词也要按语境复核，保留真正有功能的一项即可。'],
    ]) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(text)) !== null) {
        findings.push({
          line: lineNo,
          column: match.index + 1,
          type: 'formulaic-parallelism',
          severity: 'advisory',
          message,
          excerpt: compact(match[0]),
        });
      }
    }
  }

  // 跨段「不是A / 也不是B / 只是C」既可能是细纲复述，也可能是正常的
  // 辩解、悬念排除或情绪递进。纯句法无法稳定区分，因此只给 advisory，交给语义复核。
  const window = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed) continue;
    if (isDivider(trimmed) || isStructural(trimmed)) {
      window.length = 0;
      continue;
    }
    if (window.length && lineNo - window[window.length - 1].lineNo > 2) window.length = 0;
    window.push({ text: maskQuoted(trimmed), original: trimmed, lineNo });
    if (window.length > 3) window.shift();
    if (window.length !== 3) continue;
    if (!CROSS_NEGATION_START.test(window[0].text)
      || !CROSS_NEGATION_MIDDLE.test(window[1].text)
      || !CROSS_NEGATION_END.test(window[2].text)) continue;
    findings.push({
      line: window[0].lineNo,
      column: 1,
      type: 'formulaic-parallelism',
      severity: 'advisory',
      message: '跨段「不是… / 也不是… / 只是…」可能是工整否定铺排，也可能承担辩解或悬念排除；通读语境，只在重复细纲或拖慢画面时改写。',
      excerpt: compact(window.map((entry) => entry.original).join(' / ')),
    });
  }

  return findings;
}

// 否定校正式排比（实战漏网 B2）：只扫引号外叙述，双联对齐逐处 blocking。
function findNegationOnlyParallel(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);
    NEGATION_ONLY_PARALLEL_PATTERN.lastIndex = 0;
    let match;
    while ((match = NEGATION_ONLY_PARALLEL_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'negation-only-parallel',
        severity: 'advisory',
        message: '否定校正式排比：“不讲A，只讲B；不求C，只求D”是工整的作者总结腔；改写为具体动作、利益或后果。',
        excerpt: compact(text.slice(match.index, match.index + match[0].length)),
      });
    }
  }

  return findings;
}

// 反序对比腔（实战漏网 C）：「是A，不是B」。排除基建复用 not-is-comparison：
// 引号内剥离、「是的/是啊」确认语；前字合成词与反问尾巴见 REVERSE_NOT_IS_PREV_EXCLUDE 注释。
function findReverseNotIs(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const masked = maskQuoted(text);
    REVERSE_NOT_IS_PATTERN.lastIndex = 0;
    let match;
    while ((match = REVERSE_NOT_IS_PATTERN.exec(masked)) !== null) {
      const start = match.index;
      // 「就是/也是/还是/只是/可是…」里的「是」是合成词一部分，不是肯定项系动词。
      if (REVERSE_NOT_IS_PREV_EXCLUDE.has(masked[start - 1])) continue;
      // 「是不是…」问句起头。
      if (masked[start + 1] === '不') continue;
      // 「是的，…不是…」承接确认语（复用 not-is 的判定）。
      if (isAffirmationTagAt(masked, start)) continue;
      // 「…，不是吗/不是么/不是吧」反问尾巴。
      if (/^[吗么吧]/.test(match[2])) continue;
      findings.push({
        line: lineNo,
        column: start + 1,
        type: 'reverse-not-is',
        severity: 'advisory',
        message: '反序对比腔：「是A，不是B」与「不是A，是B」同族；删掉后置否定，直接写 A 的具体表现，或用细节让读者自己对比。',
        excerpt: compact(text.slice(start, start + match[0].length)),
      });
    }
  }

  return findings;
}

// 预告式总结收尾（实战漏网 D）：只扫文末窗口。从文末往回收集叙述行，
// 直到剥引号后的可见字数达到窗口大小（按行取整，边界行整行计入）。
function trailerWindowLines(proseLines) {
  const windowLines = [];
  let accumulated = 0;

  for (let i = proseLines.length - 1; i >= 0 && accumulated < TRAILER_ENDING_WINDOW_CHARS; i -= 1) {
    const { text } = proseLines[i];
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    windowLines.unshift(proseLines[i]);
    accumulated += visibleLength(stripQuoted(trimmed));
  }

  return windowLines;
}

function findTrailerEnding(proseLines) {
  const windowLines = trailerWindowLines(proseLines);

  const findings = [];
  for (const { text, lineNo } of windowLines) {
    const masked = maskQuoted(text);
    TRAILER_ENDING_PATTERN.lastIndex = 0;
    let match;
    while ((match = TRAILER_ENDING_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'trailer-ending',
        severity: 'advisory',
        message: '预告式总结收尾：「没人知道/才刚刚开始/正朝着…压了过去」是 AI 章尾预告腔；结尾停在具体动作、画面或一句台词上，悬念让事件自己挂住，别替读者预告下一章。',
        excerpt: compact(text.slice(match.index, match.index + match[0].length)),
      });
    }
  }

  return findings;
}

function findTrailerSummary(proseLines) {
  const findings = [];
  for (const { text, lineNo } of trailerWindowLines(proseLines)) {
    const masked = maskQuoted(text);
    TRAILER_SUMMARY_PATTERN.lastIndex = 0;
    let match;
    while ((match = TRAILER_SUMMARY_PATTERN.exec(masked)) !== null) {
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'trailer-summary',
        severity: 'advisory',
        message: '章尾状态总结体：「这一夜注定…/这一切都结束了/新的人生才刚刚开始/命运的齿轮」是把细纲的收束状态原样写成了总结句；收束状态是规划口径，正文落到最后一个具体动作、画面或台词上，别替读者盖章。',
        excerpt: compact(text.slice(match.index, match.index + match[0].length)),
      });
    }
  }
  return findings;
}

// 引号强调滥用（实战漏网 E）：统计叙述层 1-4 字成对引号强调片段，全文只报一条
// （密度型分布指纹）。台词类排除见 QUOTE_EMPHASIS_* 常量注释。
function findQuoteEmphasisTic(proseLines) {
  let hits = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    // 引号外没有叙述的行（独立台词/弹幕流/拟声词连发「“叮咚~”“叮咚~”」）整行跳过：
    // 强调滥用是叙述层指纹，没有叙述就无所谓强调。
    if (visibleLength(stripQuoted(trimmed)) === 0) continue;
    const ranges = quotedRanges(text);

    for (const [start, end] of ranges) {
      if (text[start] === '【') continue; // 系统面板/公告载体，不是强调引号
      // 引号套引号：台词内部的强调属于角色语言，不算叙述层强调滥用。
      if (ranges.some(([s2, e2]) => s2 <= start && end <= e2 && (s2 !== start || e2 !== end))) continue;
      const inner = text.slice(start + 1, end - 1);
      const visible = visibleLength(inner);
      if (visible < 1 || visible > QUOTE_EMPHASIS_MAX_VISIBLE) continue;
      if (/[。！？!?…，,；;：:]/.test(inner)) continue; // 含句读的是台词/播报，不是强调
      const before = text.slice(Math.max(0, start - 6), start);
      const after = text.slice(end, end + 3);
      if (QUOTE_EMPHASIS_SPEECH_VERB_PATTERN.test(before) || QUOTE_EMPHASIS_SPEECH_VERB_PATTERN.test(after)) continue; // 引语动词邻接=极短台词
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      if (samples.length < 6 && !samples.includes(inner)) samples.push(inner);
    }
  }

  if (hits < QUOTE_EMPHASIS_MIN_HITS) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'quote-emphasis-tic',
    severity: 'advisory',
    message: `引号强调滥用：叙述里 1-4 字短词加引号强调 ${hits} 处；只留真正反讽/转述必要的一两处，其余去掉引号直接写，或换成具体动作让读者自己品。`,
    excerpt: compact(samples.join(' ')),
  }];
}

// 微动作复读：统计引号外叙述里「了X量词」轻量补语的密度。次数与每千字密度双门槛，
// 全文只报一条（这是分布级指纹，不是逐处问题）。
function findMicroActionTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);
    MICRO_TIC_PATTERN.lastIndex = 0;
    let match;
    while ((match = MICRO_TIC_PATTERN.exec(narrative)) !== null) {
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      if (samples.length < 6 && !samples.includes(match[0])) samples.push(match[0]);
    }
  }

  if (narrativeChars === 0 || hits < MICRO_TIC_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < MICRO_TIC_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'micro-action-tic',
    severity: 'advisory',
    message: `微动作复读：「了下/了一下」式轻量补语 ${hits} 处（${perKilo.toFixed(1)}/千字）；同一反应模板高密度复现是机械指纹，合并动作 beat、换具体细节，别每个动作都补一个轻反应尾巴。`,
    excerpt: compact(samples.join(' ')),
  }];
}

// 套式反应细节：统计引号外叙述中通用的部位/声线反应与固定语气比喻。
// 这是删除测试的候选集，不是身体描写黑名单；全篇只报一条，保留有动作后果、
// 伤势、人物习惯或情节功能的细节。
function findStockReactionTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const pattern of STOCK_REACTION_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        const sample = sentenceAround(narrative, match.index);
        if (samples.length < 6 && sample && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (narrativeChars === 0 || hits < STOCK_REACTION_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < STOCK_REACTION_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'stock-reaction-tic',
    severity: 'advisory',
    message: `套式反应细节：指尖/指节/喉结/眼圈/声音放轻等通用反应或“平静得像在念”式语气比喻 ${hits} 处（${perKilo.toFixed(1)}/千字）；逐处做删除测试，只标注情绪、不改变选择、关系、物件或动作结果的删掉，不要换部位或同义动作。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

function findActionListTic(proseLines) {
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed).trim();
    if (!narrative) continue;

    ACTION_LIST_VERB_PATTERN.lastIndex = 0;
    const verbs = [];
    let match;
    while ((match = ACTION_LIST_VERB_PATTERN.exec(narrative)) !== null) {
      verbs.push(match[0]);
    }

    if (verbs.length < ACTION_LIST_MIN_HITS) continue;
    const separators = (narrative.match(/[，、；;]/g) || []).length;
    if (separators < ACTION_LIST_MIN_SEPARATORS) continue;

    findings.push({
      line: lineNo,
      column: 1,
      type: 'action-list-tic',
      severity: 'advisory',
      message: `监控摄像头式动作清单：同段连续动作动词 ${verbs.length} 个、分隔符 ${separators} 个；合并琐碎步骤，只保留有情绪/情节功能的动作，必要时用角色犹豫、误判或环境反馈做缓冲。`,
      excerpt: compact(verbs.slice(0, 8).join(' ')),
    });
  }

  return findings;
}

// 套词密度：统计引号外叙述中的高危禁用词聚集。不是逐词替换器；只在密度高到
// 形成模板腔时提示，修法是删总结、换具体动作/物件/对话，不是同义词轮换。
function findClicheDensityTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const pattern of CLICHE_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        if (samples.length < 8 && !samples.includes(match[0])) samples.push(match[0]);
      }
    }
  }

  if (narrativeChars === 0 || hits < CLICHE_DENSITY_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < CLICHE_DENSITY_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'cliche-density-tic',
    severity: 'advisory',
    message: `套词密度过高：高危 AI 套词 ${hits} 处（${perKilo.toFixed(1)}/千字）；不要同义词轮换，改成角色当下可见的动作、物件、对话和具体后果。`,
    excerpt: compact(samples.join(' ')),
  }];
}

// 比喻密度：统计引号外叙述中“像/好像/仿佛/如同”等比喻标记。
// 单个比喻不是问题；高密度成片时才提示，避免把文本改成另一种修辞模板。
function findMetaphorDensityTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    METAPHOR_MARKER_PATTERN.lastIndex = 0;
    let match;
    while ((match = METAPHOR_MARKER_PATTERN.exec(narrative)) !== null) {
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      const sample = sentenceAround(narrative, match.index);
      if (samples.length < 6 && sample && !samples.includes(sample)) samples.push(sample);
    }

    METAPHOR_LIKE_PHRASE_PATTERN.lastIndex = 0;
    while ((match = METAPHOR_LIKE_PHRASE_PATTERN.exec(narrative)) !== null) {
      const prefix = narrative.slice(Math.max(0, match.index - 8), match.index);
      if (/好像|像是|像|仿佛|宛如|如同|犹如/.test(prefix)) continue;
      hits += 1;
      if (firstLine === null) firstLine = lineNo;
      const sample = sentenceAround(narrative, match.index);
      if (samples.length < 6 && sample && !samples.includes(sample)) samples.push(sample);
    }
  }

  if (narrativeChars === 0 || hits < METAPHOR_DENSITY_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < METAPHOR_DENSITY_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'metaphor-density-tic',
    severity: 'advisory',
    message: `比喻密度过高：像/好像/仿佛/如同等比喻标记 ${hits} 处（${perKilo.toFixed(1)}/千字）；保留最有叙事功能的少数比喻，其余回到具体动作、物件、声音或后果，不要换成新比喻。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 解释链密度：统计引号外叙述中“知道/明白/这意味着/必须需要”等判断链。
// 全篇只报一条；修法不是补结构虚词，而是把判断落到动作、物件、对话和现场反馈。
function findReasoningChainTic(proseLines) {
  let hits = 0;
  let coreHits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];
  const buckets = new Set();

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const { pattern, key, core } of REASONING_CHAIN_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (core) coreHits += 1;
        buckets.add(key);
        if (firstLine === null) firstLine = lineNo;
        const sample = compact(match[0]);
        if (samples.length < 8 && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (narrativeChars === 0 || hits < REASONING_CHAIN_MIN_HITS) return [];
  if (coreHits < REASONING_CHAIN_CORE_MIN_HITS || buckets.size < REASONING_CHAIN_MIN_BUCKETS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < REASONING_CHAIN_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'reasoning-chain-tic',
    severity: 'advisory',
    message: `解释链密度过高：知道/明白/这意味着/必须/需要等判断链 ${hits} 处（${perKilo.toFixed(1)}/千字）；像逻辑报告时，把判断落到角色当下可见的动作、物件、对话和现场反馈。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 系统/规则行如果连续像 API 文档或政府公文，读者容易闻到机器味。
// 修法不是删除规则，而是保留功能后把一部分硬词改成白话或具体后果。
function findNoticeFormalityTic(proseLines) {
  let hits = 0;
  let noticeChars = 0;
  let noticeLines = 0;
  let coreHits = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!/^【[^】]+】$/.test(trimmed)) continue;
    noticeLines += 1;
    noticeChars += visibleLength(trimmed);

    NOTICE_FORMAL_CORE_PATTERN.lastIndex = 0;
    while (NOTICE_FORMAL_CORE_PATTERN.exec(trimmed) !== null) coreHits += 1;

    for (const pattern of NOTICE_FORMAL_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(trimmed)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        const sample = compact(match[0]);
        if (samples.length < 8 && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (noticeLines < NOTICE_FORMAL_MIN_LINES || noticeChars === 0 || hits < NOTICE_FORMAL_MIN_HITS || coreHits < NOTICE_FORMAL_CORE_MIN_HITS) return [];
  const perKilo = (hits / noticeChars) * 1000;
  if (perKilo < NOTICE_FORMAL_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'system-notice-formality-tic',
    severity: 'advisory',
    message: `系统公告公文腔过密：方括号规则行中硬规则词 ${hits} 处（${perKilo.toFixed(1)}/千字）；保留为角色看见的屏幕/公告/规则载体，只在载体内部白话化部分硬词，或补角色当场看懂的具体后果，不改成叙述者解释。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 长文本整体过于“精炼”：短段很多、自然连接偏少，读起来像处理过的梗概/分镜表。
// 修法是通读后补断裂处，不是为凑阈值全局加“的/了/就”。
function findOvercompressedProseTic(proseLines) {
  let narrativeChars = 0;
  let narrativeParas = 0;
  let shortParas = 0;
  let particles = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed) || /^【[^】]+】$/.test(trimmed)) continue;
    const narrative = stripQuoted(trimmed).trim();
    const len = visibleLength(narrative);
    if (len === 0) continue;

    if (firstLine === null) firstLine = lineNo;
    narrativeParas += 1;
    narrativeChars += len;
    if (len <= OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS) {
      shortParas += 1;
      if (samples.length < 6) samples.push(narrative);
    }

    OVERCOMPRESSED_PROSE_PARTICLE_PATTERN.lastIndex = 0;
    while (OVERCOMPRESSED_PROSE_PARTICLE_PATTERN.exec(narrative) !== null) particles += 1;
  }

  if (narrativeChars < OVERCOMPRESSED_PROSE_MIN_CHARS || narrativeParas < OVERCOMPRESSED_PROSE_MIN_PARAS) return [];
  const shortRatio = shortParas / narrativeParas;
  if (shortRatio < OVERCOMPRESSED_PROSE_SHORT_RATIO) return [];
  const particlePerKilo = (particles / narrativeChars) * 1000;
  if (particlePerKilo >= OVERCOMPRESSED_PROSE_PARTICLE_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'overcompressed-prose-tic',
    severity: 'advisory',
    message: `过度精炼短段：叙述段 ${narrativeParas} 个，其中 ${shortParas} 个≤${OVERCOMPRESSED_PROSE_SHORT_MAX_CHARS}字（${(shortRatio * 100).toFixed(0)}%），自然连接 ${particlePerKilo.toFixed(1)}/千字偏少；先通读判断，确有提纲感再补断裂处和必要结构虚词，有意短镜头可留，别机械注水。`,
    excerpt: compact(samples.join(' | ')),
  }];

}

// 低连接密度：长文本/中短窗口里，引号外叙述的功能词和白话连接同时偏低，且缺少中长承接句，
// 会呈现“提纲/电报体”分布。修法是恢复必要连接和句群，不是全局补词。
function findLowConnectiveDensityTic(proseLines) {
  let bodyChars = 0;
  let functionHits = 0;
  let plainHits = 0;
  let firstLine = null;
  const sentences = [];
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;

    // 只看引号外叙述。台词/弹幕/系统播报可以天然短促，混入统计会把体裁特征误当电报体。
    const narrative = stripQuoted(trimmed).trim();
    const narrativeLen = visibleLength(narrative);
    if (narrativeLen === 0) continue;

    if (firstLine === null) firstLine = lineNo;
    bodyChars += narrativeLen;
    functionHits += countTerms(narrative, LOW_CONNECTIVE_FUNCTION_TERMS);
    plainHits += countTerms(narrative, LOW_CONNECTIVE_PLAIN_TERMS);

    for (const sentence of splitSentences(narrative)) {
      const len = visibleLength(sentence);
      if (len === 0) continue;
      sentences.push(len);
      if (len <= 12 && samples.length < 6) samples.push(sentence);
    }
  }

  if (bodyChars < LOW_CONNECTIVE_MIN_CHARS || sentences.length === 0) return [];
  const functionPerKilo = (functionHits / bodyChars) * 1000;
  if (functionPerKilo >= LOW_CONNECTIVE_FUNCTION_PER_KILO) return [];
  const plainPerKilo = (plainHits / bodyChars) * 1000;
  if (plainPerKilo >= LOW_CONNECTIVE_PLAIN_PER_KILO) return [];
  const longSentenceRatio = sentences.filter((len) => len >= LOW_CONNECTIVE_LONG_SENTENCE_CHARS).length / sentences.length;
  if (longSentenceRatio >= LOW_CONNECTIVE_LONG_SENTENCE_RATIO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'low-connective-density-tic',
    severity: 'advisory',
    message: `低连接密度：引号外叙述功能词 ${functionPerKilo.toFixed(1)}/千字、白话连接 ${plainPerKilo.toFixed(1)}/千字，且≥${LOW_CONNECTIVE_LONG_SENTENCE_CHARS}字承接句仅 ${(longSentenceRatio * 100).toFixed(0)}%；容易像提纲/电报体。通读后补必要连接和中长句群，别机械注水。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

// 抽象总结复读：统计引号外叙述中的高抽象收束模板。全篇只报一条，提醒回到角色
// 当下可见的文件、动作、对话或物理后果；不要用命运大词替读者总结。
function findAbstractSummaryTic(proseLines) {
  let hits = 0;
  let narrativeChars = 0;
  let firstLine = null;
  const samples = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    narrativeChars += visibleLength(narrative);

    for (const pattern of ABSTRACT_SUMMARY_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        hits += 1;
        if (firstLine === null) firstLine = lineNo;
        const sample = compact(match[0]);
        if (samples.length < 6 && !samples.includes(sample)) samples.push(sample);
      }
    }
  }

  if (narrativeChars === 0 || hits < ABSTRACT_SUMMARY_MIN_HITS) return [];
  const perKilo = (hits / narrativeChars) * 1000;
  if (perKilo < ABSTRACT_SUMMARY_PER_KILO) return [];

  return [{
    line: firstLine,
    column: 1,
    type: 'abstract-summary-tic',
    severity: 'advisory',
    message: `抽象总结复读：命运/棋局/这一刻终于明白/才刚刚开始等作者总结 ${hits} 处（${perKilo.toFixed(1)}/千字）；回到角色当下可见的文件、动作、对话或物理后果，别替读者盖章。`,
    excerpt: compact(samples.join(' | ')),
  }];
}

function findPeriodStutter(proseLines) {
  const findings = [];
  let runLen = 0;
  let runStartLine = null;
  let runSample = [];

  const flush = () => {
    if (runLen >= STUTTER_MIN_RUN) {
      findings.push({
        line: runStartLine,
        column: 1,
        type: 'period-stutter',
        severity: 'advisory',
        message: `碎句号：连续 ${runLen} 个短句无呼吸；按目标句长把碎句合并成中长句、补回画面与连接（见本 skill 句长/疏密节奏规则）。`,
        excerpt: compact(runSample.join(' ')),
      });
    }
    runLen = 0;
    runStartLine = null;
    runSample = [];
  };

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed) continue; // 空行是一句一段排版，不打断叙述连贯
    if (isDivider(trimmed) || isStructural(trimmed)) {
      flush(); // 分隔线/markdown 结构行：重置碎句计数
      continue;
    }
    const narrative = stripQuoted(trimmed);
    if (visibleLength(narrative) === 0) {
      flush(); // 纯对话/弹幕/系统播报：成片短句是正常形态，重置碎句计数
      continue;
    }
    // 只数引号外叙述句：混合行（叙述+引号内物件/短台词）的引号外片段仍参与碎句计数。
    for (const sentence of splitSentences(narrative)) {
      if (visibleLength(sentence) <= STUTTER_MAX_SENTENCE) {
        if (runLen === 0) runStartLine = lineNo;
        runLen += 1;
        if (runSample.length < 6) runSample.push(sentence);
      } else {
        flush();
      }
    }
  }
  flush();
  return findings;
}

function isDivider(trimmed) {
  return /^-{3,}$/.test(trimmed) || /^[*_]{3,}$/.test(trimmed);
}

// markdown 结构行（标题/列表/引用/表格）不是叙述正文，长段落/碎句号/破折号检测都跳过。
function isStructural(trimmed) {
  return /^(#{1,6}\s|>\s?|[-*+]\s|\d+[.)]\s|\|)/.test(trimmed)
    || /^第[零一二三四五六七八九十百千万\d]+章(?:\s|_|$)/.test(trimmed);
}

// 去掉成对引号内的片段（台词/系统播报），只留引号外叙述。碎句号判定用：纯对话/弹幕成片短句
// 是体裁正常形态（豁免），但「叙述 + 引号内物件/短台词」混合行的引号外叙述仍要参与短句计数。
function stripQuoted(text) {
  let out = text;
  for (const src of QUOTE_SOURCES) out = out.replace(new RegExp(src, 'g'), '');
  return out;
}

// 把成对引号片段（含引号）替换为等长问号占位：既豁免引号内台词/播报，又保住原文
// 偏移量，供逐处 finding 定位与截取原文摘录（stripQuoted 会移位，不适合定位）。
// 占位字符用「？」而不是「。」：占位既要截断各规则的 [^。！？!?…] 否定类（？与句号在每条
// 规则的否定类里等效），又不能落在任何规则的接受位。句号占位会替 trailer-summary 的句末
// [。！] 伪造出终止符，让「这一战注定是「血屠」的开端，…」这类引号里放代号/绰号的叙述行
// 被误报，且报出的『这一战注定是。』在原文里 grep 不到。占位长度不变，故偏移与摘录窗口不漂移。
function maskQuoted(text) {
  let out = text;
  for (const src of QUOTE_SOURCES) {
    out = out.replace(new RegExp(src, 'g'), (m) => '？'.repeat(m.length));
  }
  return out;
}

// 返回引号内片段（含引号本身）的 [start, end) 区间，供 not-is 对比句豁免台词用。
function quotedRanges(text) {
  const ranges = [];
  for (const src of QUOTE_SOURCES) {
    const re = new RegExp(src, 'g');
    let match;
    while ((match = re.exec(text)) !== null) ranges.push([match.index, match.index + match[0].length]);
  }
  return ranges;
}

function insideRanges(pos, ranges) {
  return ranges.some(([start, end]) => pos >= start && pos < end);
}

function splitSentences(trimmed) {
  return trimmed
    .split(/[。！？!?]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function sentenceAround(text, index) {
  let start = index;
  while (start > 0 && !STOP_CHARS.has(text[start - 1])) start -= 1;
  let end = index;
  while (end < text.length && !STOP_CHARS.has(text[end])) end += 1;
  return compact(text.slice(start, end).trim());
}

function visibleLength(sentence) {
  const matched = sentence.match(/[一-鿿Ａ-ｚA-Za-z0-9]/g);
  return matched ? matched.length : 0;
}

function countTerms(text, terms) {
  let count = 0;
  for (const term of terms) {
    let index = text.indexOf(term);
    while (index !== -1) {
      count += 1;
      index = text.indexOf(term, index + term.length);
    }
  }
  return count;
}

function parseFenceMarker(trimmedLine) {
  const match = /^(?:`{3,}|~{3,})/.exec(trimmedLine);
  if (!match) return null;
  return { char: match[0][0], length: match[0].length };
}

function hasYamlFrontMatter(lines) {
  if (!lines[0] || lines[0].trim() !== '---') return false;
  let sawYamlField = false;
  for (let i = 1; i < Math.min(lines.length, 40); i += 1) {
    const trimmed = lines[i].trim();
    if (trimmed === '---') return sawYamlField;
    if (/^[A-Za-z0-9_-]+:\s*/.test(trimmed)) sawYamlField = true;
  }
  return false;
}

function scanBlock(block) {
  const text = block.map((entry) => entry.text).join('\n');
  const lineStarts = [];
  let cursor = 0;

  for (const entry of block) {
    lineStarts.push({ offset: cursor, lineNo: entry.lineNo });
    cursor += entry.text.length + 1;
  }

  return findNotIsComparisons(text, (offset) => positionForOffset(lineStarts, offset));
}

function positionForOffset(lineStarts, offset) {
  let low = 0;
  let high = lineStarts.length - 1;

  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const current = lineStarts[mid];
    const next = lineStarts[mid + 1];

    if (offset < current.offset) {
      high = mid - 1;
    } else if (next && offset >= next.offset) {
      low = mid + 1;
    } else {
      return {
        line: current.lineNo,
        column: offset - current.offset + 1,
      };
    }
  }

  return { line: lineStarts[0].lineNo, column: 1 };
}

function findNotIsComparisons(text, getPosition) {
  const findings = [];
  const quoted = quotedRanges(text);
  let offset = 0;

  while (offset < text.length) {
    const start = text.indexOf('不是', offset);
    if (start === -1) break;

    // 引号内是台词/系统播报：口语里「不是A，是B」是自然辩解/反问，不算叙述层 AI 对比句式
    // （与碎句号一致豁免引号内容）。
    if (insideRanges(start, quoted)) {
      offset = start + 2;
      continue;
    }

    // Avoid the common yes/no question fragment “是不是”.
    if (start > 0 && text[start - 1] === '是') {
      offset = start + 2;
      continue;
    }

    const candidate = text.slice(start);
    const markerEnd = findPositiveFlipEnd(candidate);

    if (markerEnd === -1) {
      offset = start + 2;
      continue;
    }

    const raw = trimTrailingNoise(extractFinding(candidate, markerEnd));
    if (raw.length >= 4) {
      const position = getPosition(start);
      findings.push({
        line: position.line,
        column: position.column,
        type: 'not-is-comparison',
        severity: 'advisory',
        message: '高频 AI 对比句式；删掉否定铺垫，直接写后项，或改成动作/细节呈现。',
        excerpt: compact(raw),
      });
    }

    offset = start + Math.max(raw.length, 2);
  }

  return findings;
}

function findPositiveFlipEnd(candidate) {
  let index = 2; // after “不是”
  let scanned = 0;
  let crossedSeparator = false;

  while (index < candidate.length && scanned <= MAX_NEGATIVE_SPAN) {
    const char = candidate[index];

    if (startsWithAt(candidate, index, '而是')) return index + 2;

    if (SOFT_SEPARATORS.has(char)) {
      const next = skipGap(candidate, index + 1);
      if (startsWithAt(candidate, next, '而是')) return next + 2;
      if (candidate[next] === '是' && !TAG_PARTICLES.has(candidate[next + 1]) && !isAffirmationTagAt(candidate, next)) return next + 1;
      crossedSeparator = true;
    }

    if (HARD_SEPARATORS.has(char)) {
      const next = skipGap(candidate, index + 1);
      if (candidate[next] === '是' && !TAG_PARTICLES.has(candidate[next + 1]) && !isAffirmationTagAt(candidate, next)) return next + 1;
      if (char !== '.') break;
      crossedSeparator = true;
    }

    if (STOP_CHARS.has(char)) break;

    // Catch compact forms such as “不是A是B”, but only within the first clause —
    // before any separator. After a separator the trailing “是” of a conjunction
    // (只是/可是/但是/还是/于是/倒是/总是…) is part of that word, not a positive
    // copula (issue #166 false-positive class). Post-separator flips are still
    // caught when separator-adjacent (“，是”/“，而是”) by the separator branches
    // above; subject-present flips like “，他是”/“，那是” are intentionally NOT
    // caught here — there is no separator-local way to tell them from a
    // conjunction without a word list, and on a hard rescan-to-0 gate a false
    // positive (forcing a rewrite of good prose) costs more than missing this
    // rarer form. The “是” in the either-or idiom “不是A就是B / 也是B” is part of
    // the 就是/也是 conjunction, not a copula, so 就/也 are excluded too. Also never
    // treat the “是” inside a second negative fragment (“不是A，也不是B”) as the flip.
    if (char === '是' && !COMPACT_EITHER_OR_PREV.has(candidate[index - 1]) && !crossedSeparator) {
      return index + 1;
    }

    index += 1;
    scanned += 1;
  }

  return -1;
}

function extractFinding(candidate, markerEnd) {
  let end = markerEnd;
  const limit = Math.min(candidate.length, markerEnd + MAX_POSITIVE_SPAN);

  while (end < limit) {
    if (STOP_CHARS.has(candidate[end])) break;
    end += 1;
  }

  return candidate.slice(0, end);
}

function startsWithAt(text, index, needle) {
  return text.slice(index, index + needle.length) === needle;
}

function isAffirmationTagAt(text, index) {
  if (text[index] !== '是') return false;
  const particle = text[index + 1];
  if (!AFFIRMATION_TAG_PARTICLES.has(particle)) return false;
  const boundary = text[index + 2] || '';
  return AFFIRMATION_TAG_BOUNDARY.has(boundary);
}

// 跳过行内空白与换行（含空行/段落间距），停在下一个实义字符。原实现只吞一个换行，
// 会漏掉跨空行的「不是A。（空行）是B」这类分段揭示句。
function skipGap(text, index) {
  while (index < text.length && (isInlineSpace(text[index]) || text[index] === '\n')) index += 1;
  return index;
}

function isInlineSpace(char) {
  return char === ' ' || char === '\t' || char === '\r';
}

function trimTrailingNoise(text) {
  return text.replace(/[\s|）)】\]]+$/u, '');
}


// 精确禁词：运行时读取 references/banned-words.md 的「一级禁用词」整段，对所有短语做
// 精确子串匹配；每命中一次报一条 blocking finding，对应「出现即替换」。与 CLICHE_PATTERNS
// 密度表互补：密度表管 paraphrase/成片堆砌，本表管被点名的精确禁词。项目根 .deslop-whitelist
// （一行一词，# 注释）中的子串命中时跳过，避免误伤世界观术语/绰号。

var _bannedExactCache = null;
function loadBannedExactPhrases() {
  if (_bannedExactCache) return _bannedExactCache;
  const result = { phrases: [], error: null };
  try {
    const mdPath = path.join(__dirname, '..', 'references', 'banned-words.md');
    const md = fs.readFileSync(mdPath, 'utf8');
    const lines = md.split(/\r?\n/);
    let inPrimary = false;
    for (const raw of lines) {
      const line = raw.trim();
      if (/^##\s/.test(line)) {
        inPrimary = /^##\s*一级禁用词/.test(line);
        continue;
      }
      if (!inPrimary) continue;
      if (line === '' || line.startsWith('#') || line.startsWith('<!--')) continue;
      for (const piece of line.split('、')) {
        const phrase = piece.trim();
        if (phrase) result.phrases.push(phrase);
      }
    }
  } catch (error) {
    result.error = error.message;
  }
  _bannedExactCache = result;
  return result;
}



var _regexSectionCache = null;
function loadRegexSectionPatterns(cacheKey, headingPattern) {
  if (!_regexSectionCache) _regexSectionCache = new Map();
  if (_regexSectionCache.has(cacheKey)) return _regexSectionCache.get(cacheKey);
  const result = { patterns: [], error: null };
  try {
    const mdPath = path.join(__dirname, '..', 'references', 'banned-words.md');
    const md = fs.readFileSync(mdPath, 'utf8');
    const lines = md.split(/\r?\n/);
    let inSec = false;
    for (const raw of lines) {
      const line = raw.trim();
      if (/^##\s/.test(line)) {
        inSec = headingPattern.test(line);
        continue;
      }
      if (!inSec) continue;
      const m = line.match(/^\/(.+)\/$/);
      if (m) {
        try { result.patterns.push(new RegExp(m[1], 'g')); } catch (e) { /* skip invalid regex */ }
      }
    }
  } catch (error) {
    result.error = error.message;
  }
  _regexSectionCache.set(cacheKey, result);
  return result;
}

function loadSynaPatterns() {
  return loadRegexSectionPatterns('syna', /^##\s*通感隐喻/);
}

function loadAntithesisPatterns() {
  return loadRegexSectionPatterns('antithesis', /^##\s*对仗反义俏皮话/);
}

function loadDanglingIdentityPatterns() {
  return loadRegexSectionPatterns('dangling-identity', /^##\s*双端悬空的[“\"]的[”\"]字身份跳转句/);
}

function loadBodyShellPatterns() {
  return loadRegexSectionPatterns('body-shell', /^##\s*空壳式人体失真比喻/);
}

function loadContrastPatterns() {
  return loadRegexSectionPatterns('contrast', /^##\s*(?:反问式内省|伪深刻对比)/);
}

function loadPhysicalClearPatterns() {
  return loadRegexSectionPatterns('physical-clear', /^##\s*物理清除动词/);
}

function loadAbstractObjectForcedPatterns() {
  return loadRegexSectionPatterns('abstract-object-forced', /^##\s*抽象对象被当物理对象处理/);
}

function loadPainAsObjectPatterns() {
  return loadRegexSectionPatterns('pain-as-object', /^##\s*痛感\/感受当物理动作的可数宾语/);
}

var _whitelistCache = null;
function loadWhitelist() {
  if (_whitelistCache) return _whitelistCache;
  const set = new Set();
  try {
    const wlPath = path.resolve(process.cwd(), '.deslop-whitelist');
    if (fs.existsSync(wlPath)) {
      const text = fs.readFileSync(wlPath, 'utf8');
      for (const raw of text.split(/\r?\n/)) {
        const line = raw.trim();
        if (line === '' || line.startsWith('#')) continue;
        set.add(line);
      }
    }
  } catch (error) {
    // whitelist 读取失败：当作空，不阻断扫描
  }
  _whitelistCache = set;
  return set;
}

// 白名单子串重叠豁免：若命中点与某个白名单词条在字符上重叠（如禁词「几分」落在「分钟」内），跳过该命中，避免误伤正常复合词。
function isWhitelistedOverlap(narrative, idx, phraseLen, whitelist) {
  if (whitelist.size === 0) return false;
  const start = idx, end = idx + phraseLen;
  for (const w of whitelist) {
    const wi = narrative.indexOf(w);
    if (wi === -1) continue;
    const we = wi + w.length;
    if (wi < end && we > start) return true;
  }
  return false;
}

function ruleLoadFailure(section, error) {
  return [{
    line: 1,
    column: 1,
    type: 'rule-load-error',
    severity: 'blocking',
    message: `无法加载共享禁词规则（${section}）：${error || '规则段为空'}。检查 .agents/skills/_shared/references/banned-words.md；禁止回退到 skill-local 旧副本。`,
    excerpt: section,
  }];
}

function findBannedWordsExact(proseLines) {
  const { phrases, error } = loadBannedExactPhrases();
  if (error || phrases.length === 0) return ruleLoadFailure('一级禁用词', error);
  const whitelist = loadWhitelist();
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    // 只查引号外叙述；台词/系统播报里出现不算（与碎句号一致豁免）。
    const narrative = stripQuoted(trimmed);
    for (const phrase of phrases) {
      if (whitelist.has(phrase)) continue;
      let from = 0;
      let idx;
      while ((idx = narrative.indexOf(phrase, from)) !== -1) {
        if (isWhitelistedOverlap(narrative, idx, phrase.length, whitelist)) { from = idx + phrase.length; continue; }
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-exact',
          severity: 'blocking',
          message: `精确禁词「${phrase}」：banned-words.md 一级禁用词，出现即替换；改用具体动作/物件/对话/身体反应展示，不要同义词轮换。`,
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + phrase.length + 8)),
        });
        from = idx + phrase.length;
      }
    }
  }
  return findings;
}



// 通感隐喻：运行时读取 references/banned-words.md 的「通感隐喻」整段，把其中 /.../ 正则
// 编译为 blocking 规则；每命中一次报一条 banned-word-syna finding，对应「出现即改」。
// 与 一级禁用词精确匹配互补：本类问题多为句式而非固定词，用正则覆盖变体。
// 项目根 .deslop-whitelist 中的子串仍豁免（沿用 isWhitelistedOverlap）。
function findSynestheticMetaphor(proseLines) {
  const { patterns, error } = loadSynaPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('通感隐喻', error);
  const whitelist = loadWhitelist();
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = narrative.indexOf(hit);
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-syna',
          severity: 'blocking',
          message: '通感隐喻[' + hit + ']：banned-words.md 通感隐喻规则，感官词抽象化情绪/局势，出现即改；用角色当下可见的动作、物件、对话或具体后果展示，不要同义词轮换。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}



function findAntithesis(proseLines) {
  const { patterns, error } = loadAntithesisPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('对仗反义俏皮话', error);
  const whitelist = loadWhitelist();
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = narrative.indexOf(hit);
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-antithesis',
          severity: 'blocking',
          message: '对仗反义俏皮话[' + hit + ']：banned-words.md 对仗反义俏皮话规则，工整对称反义金句（如"X轻，Y不轻"）是 AI 写作套路，出现即改；改成角色自然口语或具体动作/物件/对话，不要同义词轮换。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

function findDanglingIdentityShift(proseLines) {
  const { patterns, error } = loadDanglingIdentityPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('双端悬空的“的”字身份跳转句', error);
  const whitelist = loadWhitelist();
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = match.index;
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-dangling-identity',
          severity: 'blocking',
          message: '双端悬空的“的”字身份跳转句[' + hit + ']：左端省掉中心语或经历者，右端只用代词代替新身份，再靠逗号制造伪停顿，导致“谁醒来、谁成了谁”同时含混；补齐时间、经历者和新身份中的必要信息，改成完整主谓句。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

function findBodyShellMetaphor(proseLines) {
  const { patterns, error } = loadBodyShellPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('空壳式人体失真比喻', error);
  const whitelist = loadWhitelist();
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = match.index;
        // 本规则已经由「比喻标记＋骨架消失＋皮壳支撑」三重条件限死，不能让项目级
        // 单词白名单（如“仿佛”）仅凭局部重叠豁免整句；只接受整条命中被显式放行。
        if (whitelist.has(hit)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-body-shell',
          severity: 'blocking',
          message: '空壳式人体失真比喻[' + hit + ']：用“骨架被抽走＋只剩皮壳支撑”代替可见反应，身体逻辑失真，且容易与“僵、绷直”等姿态互相冲突；改成上下文中能看见的姿态、动作或生理反应，不要换一套人体比喻。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

function findContrastRhetorical(proseLines) {
  const { patterns, error } = loadContrastPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('反问式内省/伪深刻对比', error);
  const whitelist = loadWhitelist();
  const findings = [];

  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = narrative.indexOf(hit);
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'contrast-rhetorical',
          severity: 'advisory',
          message: '反问式内省/伪深刻对比[' + hit + ']：用「倒被X吓住？」式伪深刻反问做内省，靠过去/现在反差+模糊指代（一沓纸/那页东西/这玩意）撑"人物复杂"，是高级 AI 味；改成角色当下可见的具体动作/生理反应（手抖/手顿/把纸翻过去）或本书招牌"裂痕"装置展示，对象写具体（这份材料/这份协议），去掉文艺腔反问。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

// 物理清除动词 × 抽象对象：把抽象域（时间/记忆/痕迹/棱角）当实物"抹平/冲走/刮掉"，blocking。
function findPhysicalClear(proseLines) {
  const { patterns, error } = loadPhysicalClearPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('物理清除动词×抽象对象', error);
  const whitelist = loadWhitelist();
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = match.index;
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-physical-clear',
          severity: 'blocking',
          message: '物理清除动词×抽象对象[' + hit + ']：把时间/记忆/痕迹等抽象域当实物去抹平/冲走/刮掉，出现即改；用具体说法（趁痕迹还在→别让证据被清掉、把记忆冲走→记不起来了）。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

// 抽象对象被当物理对象处理：目光/视线/情绪/声音被"压/钉/砸/拽"等施力，blocking。
function findAbstractObjectForced(proseLines) {
  const { patterns, error } = loadAbstractObjectForcedPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('抽象对象被当物理对象处理', error);
  const whitelist = loadWhitelist();
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = match.index;
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-abstract-forced',
          severity: 'blocking',
          message: '抽象对象被当物理对象处理[' + hit + ']：目光/视线/情绪/声音不是物理实体，不能被压/钉/砸/拽；改成"落/停/移/转"等视线自身动作，或改主体为实体。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

// 痛感/感受当物理动作的可数宾语："刮出+一道/阵/股+感受"，blocking。
function findPainAsObject(proseLines) {
  const { patterns, error } = loadPainAsObjectPatterns();
  if (error || patterns.length === 0) return ruleLoadFailure('痛感/感受当物理动作的可数宾语', error);
  const whitelist = loadWhitelist();
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const re of patterns) {
      re.lastIndex = 0;
      let match;
      while ((match = re.exec(narrative)) !== null) {
        const hit = match[0];
        const idx = match.index;
        if (whitelist.has(hit) || isWhitelistedOverlap(narrative, idx, hit.length, whitelist)) continue;
        findings.push({
          line: lineNo,
          column: idx + 1,
          type: 'banned-word-pain-object',
          severity: 'blocking',
          message: '痛感/感受当物理动作的可数宾语[' + hit + ']：痛感是身体反应不是物体，不能被"刮出/划出"；写痛感的性质（蜇/灼/锐/钝）或身体反应（缩手/倒吸气/咬牙）。',
          excerpt: compact(narrative.slice(Math.max(0, idx - 8), idx + hit.length + 8)),
        });
      }
    }
  }
  return findings;
}

// ---- 全面检查补充维度（来源：实战写作抓到的真实漏网，2026-08 校准）----
// 覆盖项目已立铁律中被原版 check 漏检的部分：灰裂脑子里裂、总结腔、英文残留、
// 过程术语不作动作宾语。均为「出现即修」级硬伤，单处即 blocking（不像密度型放行）。
// 校准基线：第一卷全扫回填（新增维度首次全扫应 0 命中或仅命中已知残留）。

// 灰裂铁律：裂痕必须锚定证据/纸面/屏幕等可见物，绝不写「脑子里…裂」。
// 单处 blocking；引号内台词豁免（与碎句号一致）。
function findGreyCrackInHead(proseLines) {
  const GREY_CRACK_IN_HEAD_PATTERN = /脑子里.{0,8}(?:裂|裂开|裂缝|裂痕|裂了一道|裂着)/g;
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    GREY_CRACK_IN_HEAD_PATTERN.lastIndex = 0;
    let match;
    while ((match = GREY_CRACK_IN_HEAD_PATTERN.exec(narrative)) !== null) {
      findings.push({
        line: lineNo,
        column: narrative.indexOf(match[0]) + 1,
        type: 'grey-crack-in-head',
        severity: 'advisory',
        message: '灰裂铁律：裂痕必须锚定证据/纸面/屏幕等可见物，绝不写「脑子里…裂」；改为「视野里/纸面上/那几行上」等具体落点。',
        excerpt: compact(narrative.slice(Math.max(0, match.index - 8), match.index + match[0].length + 8)),
      });
    }
  }
  return findings;
}

// 总结腔：角色给自己写跨时段人生格言（「X辈子的经验合起来只有一条」）是 AI 总结腔高危形态，
// 单处即 blocking。必须含「经验/教训/总结/活法/道理」或「合起来/说到底/到头来/总结起来」等
// 总结标记，避免误伤普通「这辈子只想X」式正常叙述。
function findSummarySlogan(proseLines) {
  const SUMMARY_SLOGAN_PATTERNS = [
    /(?:两辈子|这辈子|上辈子|半辈子|两世)(?:的)?[^。！？!?\n]{0,16}(?:经验|教训|总结|活法|道理|合起来|说到底|归根到底|到头来)[^。！？!?\n]{0,12}(?:只有|就|不外乎|无非|是)[^。！？!?\n]{0,10}(?:一条|这一条|一个|一句话|一句)/g,
    /(?:合起来|说到底|归根到底|到头来|总结起来|横竖|无论如何|说白了|一句话)[^。！？!?\n]{0,6}(?:只有|就|不外乎|无非|是)[^。！？!?\n]{0,10}(?:一条|这一条|一个|一种|一句话|一句)/g,
  ];
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    for (const pattern of SUMMARY_SLOGAN_PATTERNS) {
      pattern.lastIndex = 0;
      let match;
      while ((match = pattern.exec(narrative)) !== null) {
        findings.push({
          line: lineNo,
          column: narrative.indexOf(match[0]) + 1,
          type: 'summary-slogan',
          severity: 'advisory',
          message: '总结腔：角色给自己写跨时段人生格言（「X辈子的经验合起来只有一条」）是 AI 总结腔；改成具体画面/身体记忆/当下闪念，不要替读者盖章。',
          excerpt: compact(narrative.slice(Math.max(0, match.index - 8), match.index + match[0].length + 8)),
        });
      }
    }
  }
  return findings;
}

// 英文残留：正文（引号外叙述）出现 ASCII 英文词（≥2 字母）即视为残留；
// 白名单放常见有意英文。法援律师正文应为纯中文，叙述里夹英文是编辑/生成残留。
function findEnglishResidue(proseLines) {
  const ENGLISH_WORD_PATTERN = /[A-Za-z]{2,}/g;
  const ENGLISH_WHITELIST = new Set(['OK', 'APP', 'DNA', 'GPS', 'WiFi', 'AI', 'ID', 'QQ']);
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    ENGLISH_WORD_PATTERN.lastIndex = 0;
    let match;
    while ((match = ENGLISH_WORD_PATTERN.exec(narrative)) !== null) {
      const word = match[0];
      if (ENGLISH_WHITELIST.has(word)) continue;
      findings.push({
        line: lineNo,
        column: match.index + 1,
        type: 'english-residue',
        severity: 'advisory',
        message: `英文残留「${word}」：正文应为纯中文，英文词是编辑/生成残留，译为对应中文或删除。`,
        excerpt: compact(narrative.slice(Math.max(0, match.index - 8), match.index + word.length + 8)),
      });
    }
  }
  return findings;
}

// 过程术语不作动作宾语：动词（确认/核对/检查/复查/比对/核实）的宾语是过程术语本身
// （校验/验证/认证/审核/确认），等于「确认了一遍验证」。宾语须是具体结果或对象（文件、编号、页码）。
function findProcessTermAsObject(proseLines) {
  const PROCESS_TERM_OBJECT_PATTERN = /(?:确认|核对|检查|复查|比对|核实)(?:了|过)?(?:一遍|一下|一次|这份|这些|所有|都)?[^，。！？!?\n]{0,8}(?:校验|验证|认证|审核)/g;
  const findings = [];
  for (const { text, lineNo } of proseLines) {
    const trimmed = text.trim();
    if (!trimmed || isDivider(trimmed) || isStructural(trimmed)) continue;
    const narrative = stripQuoted(trimmed);
    PROCESS_TERM_OBJECT_PATTERN.lastIndex = 0;
    let match;
    while ((match = PROCESS_TERM_OBJECT_PATTERN.exec(narrative)) !== null) {
      findings.push({
        line: lineNo,
        column: narrative.indexOf(match[0]) + 1,
        type: 'process-term-as-object',
        severity: 'advisory',
        message: '过程术语不作动作宾语：动词宾语必须是具体结果或对象（文件、编号、页码、时间戳），不能拿过程术语本身（校验/验证/认证/审核）当宾语；改为「确认了一遍文件都在」之类。',
        excerpt: compact(narrative.slice(Math.max(0, match.index - 8), match.index + match[0].length + 8)),
      });
    }
  }
  return findings;
}

function compact(text) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > 80 ? `${normalized.slice(0, 77)}...` : normalized;
}
