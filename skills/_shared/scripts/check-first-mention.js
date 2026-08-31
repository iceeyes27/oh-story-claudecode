#!/usr/bin/env node
/**
 * check-first-mention.js — 专名首现交代缺失检测（读者视角，确定性层）
 *
 * 背景：现有一致性检查都是「作者视角」——拿正文比对 设定/追踪/细纲。设定里
 * 自洽 ≠ 正文里交代过。读者手上只有正文，弃书弃在「正文没说清楚」。本脚本
 * 只读 正文/，判断被当作已知前提使用的专名（人名/机构/道具/能力）在其首次
 * 出现处附近有没有一次身份/来历交代。
 *
 * 能力边界（重要）：中文没有分词，纯频率会把常用词（说道/办公室/越来越）全当
 * 专名，噪音爆炸。故本脚本只报**高精度信号**：① 书名号/引号具名实体（作品/道具/
 * 绰号）；② 命中虚构专名尾字白名单的 token（系统/阁/宗/令/诀…，避开泛场所词）。
 * 人名/机构这类需 NER 的召回**交给语义三问层**（references/reading-protocol.md），
 * 脚本不猜。默认报 advisory；「首现零交代 + 之后 ≥2 章再当已知前提出现」升 blocking。
 * 通过不代表读者一定看得懂。
 *
 * 现实世界实体：脚本无法判断《如愿》是真实歌曲还是虚构曲目——真实歌曲对读者本就
 * 是已知的，不需要正文交代。这类实体由作者用 `--known=<文件>` 声明一次（每行一个，
 * `#` 开头为注释），或在书根放 `正文/_已知实体.txt` 自动读取。
 *
 * 用法:
 *   node check-first-mention.js <书目录> [--json] [--min-freq=3] [--reintro-gap=2] [--known=<文件>]
 *   <书目录>：书根（含 正文/），或直接指向 正文/ 目录
 *
 * 退出码：0 无 blocking / 1 有 blocking / 2 参数或读取错误
 */
'use strict';
const fs = require('fs');
const path = require('path');

// 默认参数（analyze 通过 opts 覆盖，CLI 解析在 main 内进行，避免被 require 时触发）
const DEFAULTS = { MIN_FREQ: 3, REINTRO_GAP: 2 };

// ---------- 定位正文目录 ----------
function resolveTextDir(root) {
  if (!fs.existsSync(root)) return null;
  if (path.basename(root) === '正文') return root;
  const nested = path.join(root, '正文');
  if (fs.existsSync(nested)) return nested;
  return root; // 允许直接把章节目录传进来
}

// ---------- 收集章节 ----------
function chapterNo(fn) {
  const m = fn.match(/第(\d+)章/);
  return m ? parseInt(m[1], 10) : null;
}
function collectChapters(dir) {
  const out = [];
  function walk(d) {
    for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, ent.name);
      if (ent.isDirectory()) walk(p);
      else if (ent.isFile() && ent.name.endsWith('.md') && ent.name !== '目录.md') {
        const n = chapterNo(ent.name);
        if (n != null) out.push({ num: n, file: p, title: (ent.name.match(/第\d+章_(.+)\.md$/) || [, ''])[1] });
      }
    }
  }
  walk(dir);
  out.sort((a, b) => a.num - b.num);
  return out;
}

// ---------- 停用词 / 工程词（不作候选专名） ----------
const STOPWORDS = new Set([
  '知道','这个','那个','什么','怎么','没有','可以','这样','那样','自己','我们','你们','他们',
  '一个','这些','那些','现在','已经','就是','但是','因为','所以','如果','还是','或者','这里',
  '那里','时候','觉得','看着','听到','看到','起来','出来','过来','下来','上来','进来','出去',
  '一下','一样','一直','有些','东西','事情','问题','时间','地方','声音','眼睛','手机','脑子',
  '第一','第二','第三','之后','之前','然后','开始','继续','终于','忽然','突然','立刻','马上',
]);
const ENGINEERING = /第[一二三四五六七八九十百千万两0-9]+章|上一章|前一章|本章|细纲|伏笔|读者/;
// 边界虚字：以它开头或结尾的 gram 多半是词的截断（「天枢阁的」「的人来」），不作候选专名
const BOUNDARY = new Set('的了是在也都就而和与又还这那有着过把被让向从对到与之其且或但却虽因所以及能会要想'.split(''));
// 虚构专名尾字白名单：token 以这些字结尾才作裸串候选（避开泛场所词 团/场/室/区/店 等）。
// 人名不含这类尾字 → 脚本不报，交给语义三问层。
// 注：不含「经/团/场/室/区」等泛词尾（会误伤 饱经/文工团/训练场）。可按题材在此增删。
const NAME_SUFFIX = /(系统|阁|宗|殿|盟|诀|术|阵法|阵眼|令牌|令|塔|鼎|珏|幡|真君|上仙|尊者|剑诀)$/;
// 量词前缀：n-gram 会把量词粘进候选（「获得了一个系统」→「个系统」）。裸串候选以
// 这些字开头一律丢弃——正确切分的那一份（「系统」）本来就是独立候选，不会因此漏报，
// 只是不再输出「个系统」这种切分残留误导作者。
// 只收**不会做专名首字**的纯量词：数词（三清殿/九幽阁/万剑宗）和兼作名词的量词
// （道诀、口诀、本命、层塔）一律不收，否则会误杀真专名。
const MEASURE_PREFIX = /^[个只件张份位名枚颗粒匹头群批朵棵株尾]/;

// 首现交代锚点：判断句 / 职务身份词 / 来历动词
const APPOSITION = /是|为|叫|名为|称为|名叫|所谓|乃是/;
const ROLE = /[长师官员帅将兵警医生士主任记者团队连营排班司公司集团门派阁宗帮会盟军校院部局处科]/;
const ORIGIN = /出身|来自|毕业|曾经|原本|前世|本名|外号|绰号|人称|据说|传闻|生于/;

function hasAnchor(text) {
  return APPOSITION.test(text) || ROLE.test(text) || ORIGIN.test(text);
}

// ---------- 候选专名提取 ----------
// 1) 书名号/引号包裹的具名实体
const BRACKETED = /[《『「]([^》』」\n]{1,12})[》』」]/g;
// 2) 连续中文段（段内全展开 2–4 gram，重叠计频，靠同频包含去重取频繁最大子串）
const CJK_SEG = /[一-龥]+/g;

function extractCandidates(chapters, opts) {
  // token -> { freq, chapters:Set, first:{num,line,lineText}, bracketed }
  const map = new Map();
  function bump(token, num, line, lineText, bracketed) {
    if (!token) return;
    if (STOPWORDS.has(token) || ENGINEERING.test(token)) return;
    // 书名号实体不受边界虚字约束；普通 gram 首尾为虚字则跳过（词截断噪音）
    if (!bracketed && (BOUNDARY.has(token[0]) || BOUNDARY.has(token[token.length - 1]))) return;
    // 裸串以量词开头同样是切分残留
    if (!bracketed && MEASURE_PREFIX.test(token)) return;
    let e = map.get(token);
    if (!e) { e = { token, freq: 0, chapters: new Set(), first: null, bracketed }; map.set(token, e); }
    e.freq++;
    e.chapters.add(num);
    if (e.first == null) e.first = { num, line, lineText };
    if (bracketed) e.bracketed = true;
  }
  for (const ch of chapters) {
    const lines = fs.readFileSync(ch.file, 'utf8').split(/\r?\n/);
    lines.forEach((lineText, i) => {
      if (/^#/.test(lineText)) return; // 跳过标题行
      const line = i + 1;
      let m;
      BRACKETED.lastIndex = 0;
      while ((m = BRACKETED.exec(lineText))) bump(m[1], ch.num, line, lineText, true);
      CJK_SEG.lastIndex = 0;
      while ((m = CJK_SEG.exec(lineText))) {
        const seg = m[0];
        for (let s = 0; s < seg.length; s++) {
          for (let L = 2; L <= 4 && s + L <= seg.length; L++) {
            bump(seg.slice(s, s + L), ch.num, line, lineText, false);
          }
        }
      }
    });
  }
  return map;
}

// 同频包含去重：若短候选是某长候选的子串、且频率相等、首现同章，丢弃短的（保留频繁最大子串）
function dedupeContained(entries) {
  const byLen = [...entries].sort((a, b) => b.token.length - a.token.length);
  const kept = [];
  for (const e of byLen) {
    const covered = kept.some(
      (k) => k.token.length > e.token.length &&
        k.token.includes(e.token) &&
        k.freq === e.freq &&
        k.first && e.first && k.first.num === e.first.num,
    );
    if (!covered) kept.push(e);
  }
  return kept;
}

// ---------- 首现附近交代判定 ----------
function firstMentionContext(chapters, token, first) {
  // 取首现行 ±1 行文本判锚点
  const ch = chapters.find((c) => c.num === first.num);
  if (!ch) return '';
  const lines = fs.readFileSync(ch.file, 'utf8').split(/\r?\n/);
  const idx = first.line - 1;
  return [lines[idx - 1] || '', lines[idx] || '', lines[idx + 1] || ''].join('');
}

// 读取「现实世界已知实体」清单：每行一个，# 开头为注释，空行忽略。
// 真实歌曲/影视/历史人物对读者本就是已知的，正文不交代不构成理解断点。
function loadKnownEntities(file) {
  if (!file || !fs.existsSync(file)) return new Set();
  return new Set(
    fs.readFileSync(file, 'utf8')
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line && !line.startsWith('#')),
  );
}

function defaultKnownFile(textDir) {
  const p = path.join(textDir, '_已知实体.txt');
  return fs.existsSync(p) ? p : null;
}

function analyze(chapters, opts = {}) {
  const MIN_FREQ = opts.MIN_FREQ ?? DEFAULTS.MIN_FREQ;
  const REINTRO_GAP = opts.REINTRO_GAP ?? DEFAULTS.REINTRO_GAP;
  const known = opts.known instanceof Set ? opts.known : loadKnownEntities(opts.knownFile);
  const map = extractCandidates(chapters, opts);
  // 高精度候选：书名号实体，或命中专名尾字白名单且 ≥2 次。裸高频词一律不作候选。
  const qualified = [...map.values()].filter(
    (e) => e.first && !known.has(e.token) &&
      (e.bracketed || (NAME_SUFFIX.test(e.token) && e.freq >= 2)),
  );
  const candidates = dedupeContained(qualified);
  const findings = [];
  for (const e of candidates) {
    const ctx = firstMentionContext(chapters, e.token, e.first);
    // 去掉 token 本身再判锚点，避免 token 自带角色字（如「记者」）误判为已交代
    const ctxWithoutToken = ctx.split(e.token).join('');
    if (hasAnchor(ctxWithoutToken)) continue; // 首现有交代，放过
    // 首现零交代
    const laterChapters = [...e.chapters].filter((n) => n - e.first.num >= REINTRO_GAP);
    const severity = laterChapters.length > 0 ? 'blocking' : 'advisory';
    findings.push({
      token: e.token,
      severity,
      freq: e.freq,
      firstChapter: e.first.num,
      firstLine: e.first.line,
      reintroChapters: laterChapters.slice(0, 5),
      excerpt: (e.first.lineText || '').trim().slice(0, 60),
    });
  }
  // blocking 优先、再按跨章跨度排序
  findings.sort((a, b) =>
    (a.severity === b.severity ? b.reintroChapters.length - a.reintroChapters.length
      : a.severity === 'blocking' ? -1 : 1));
  return findings;
}

// ---------- main ----------
function main() {
  const args = process.argv.slice(2);
  let bookDir = null;
  let jsonMode = false;
  const opts = { MIN_FREQ: DEFAULTS.MIN_FREQ, REINTRO_GAP: DEFAULTS.REINTRO_GAP };
  for (const a of args) {
    if (a === '--json') jsonMode = true;
    else if (a.startsWith('--min-freq=')) opts.MIN_FREQ = parseInt(a.slice(11), 10);
    else if (a.startsWith('--reintro-gap=')) opts.REINTRO_GAP = parseInt(a.slice(14), 10);
    else if (a.startsWith('--known=')) opts.knownFile = a.slice(8);
    else if (!a.startsWith('--')) bookDir = a;
  }
  if (!bookDir) {
    console.error('用法: node check-first-mention.js <书目录> [--json] [--min-freq=3] [--reintro-gap=2] [--known=<文件>]');
    process.exit(2);
  }
  const textDir = resolveTextDir(bookDir);
  if (!textDir || !fs.existsSync(textDir)) {
    console.error(`读取错误：找不到正文目录 ${bookDir}`);
    process.exit(2);
  }
  const chapters = collectChapters(textDir);
  if (chapters.length === 0) {
    console.error(`读取错误：${textDir} 下没有「第N章_*.md」章节`);
    process.exit(2);
  }
  if (!opts.knownFile) opts.knownFile = defaultKnownFile(textDir);
  const known = loadKnownEntities(opts.knownFile);
  opts.known = known;
  const findings = analyze(chapters, opts);
  const blocking = findings.filter((f) => f.severity === 'blocking');
  if (jsonMode) {
    console.log(JSON.stringify({
      chapters: chapters.length,
      knownEntities: known.size,
      blocking: blocking.length,
      findings,
    }, null, 2));
  } else {
    const knownNote = known.size ? `，已排除 ${known.size} 个声明的现实世界实体` : '';
    console.log(`专名首现交代检查 · 共 ${chapters.length} 章，候选 ${findings.length} 处（blocking ${blocking.length}）${knownNote}`);
    console.log('—'.repeat(70));
    for (const f of findings) {
      const tag = f.severity === 'blocking' ? '[blocking]' : '[advisory]';
      const reintro = f.reintroChapters.length ? ` 后续第${f.reintroChapters.join('/')}章再引用` : '';
      console.log(`${tag} 「${f.token}」首现于第${f.firstChapter}章:${f.firstLine}（全书出现${f.freq}次）${reintro}`);
      console.log(`           首现处零交代：${f.excerpt}`);
    }
    console.log('—'.repeat(70));
    console.log('判定口诀：这个专名第一次出现时，读者知道它是谁/是什么吗？blocking = 首现没交代又在后文当已知前提用。');
    console.log('能力边界：仅覆盖可机械判定子集，advisory 需人工复核；通过不代表读者一定看得懂。');
    if (!known.size) {
      console.log('提示：真实歌曲/影视/历史人物对读者本就已知，可在 正文/_已知实体.txt 每行声明一个，或用 --known=<文件>。');
    }
  }
  process.exit(blocking.length > 0 ? 1 : 0);
}

// 供测试调用
module.exports = {
  analyze, hasAnchor, extractCandidates, collectChapters, resolveTextDir,
  loadKnownEntities, defaultKnownFile, main,
};

if (require.main === module) main();
