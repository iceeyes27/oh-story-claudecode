#!/usr/bin/env node
/**
 * check-chapter-boundary.js — 跨章信息续接 / 章节边界连贯性检测（advisory）
 *
 * 背景：单章内文法问题有 check-ai-patterns / check-subject-switch 覆盖，
 * 但「上一章结尾 ↔ 下一章开头」的跨章续接没有检测手段。已踩坑：
 *   - Ch5 结尾说「明天先去医院」，Ch6/Ch7 实际去了工地食堂 → 计划悬空
 *   - Ch45 深夜「接进来」匿名热线，Ch46 未交代来电人 → 钩子悬空
 *   - Ch60 结尾与 Ch61 开头整句复读「三块互相遮掩的控制事实…」→ 跨章复读
 *   - Ch1 结尾江澈走到楼道尽头，Ch2 开头他已在桌边翻协议 → 人物位置断裂
 *
 * 用法：node check-chapter-boundary.js <书目录> [--tail=400 --head=300 --sim=0.42]
 *   <书目录>：书的根目录（含 正文/），自动递归收 正文 下各卷目录的 md，按章号排序
 *   --tail=N   上一章结尾取多少字符（默认 400）
 *   --head=N   下一章开头取多少字符（默认 300）
 *   --sim=F    跨章复读相似度阈值（默认 0.42，0–1）
 *
 * 输出：advisory 疑似清单，按章对分组，含类别 + 上章末句 + 下章首句，供人工复核。
 * 不自动判错——正常续接（顺承场景/换场有交代/跨天有标记）占绝大多数，不算病。
 *
 * 三类检测：
 *   ① 跨章复读   ：上章尾段与下章头段按「。！？!?」分句，跨句 6-gram 相似度 >= 阈值 → 提示
 *   ② 计划悬空   ：上章尾段出现「明天/明早/今晚/下一步/接下来/待会儿」+「去/先/查/找/办/问/谈/约」等计划动词，
 *                   把整句列出，人工核对下章是否兑现（或明确改口）
 *   ③ 动作/钩子收尾：上章以「接进来/拿起电话/推门/走出/挂断/合上/关了灯」等动作收尾 → 列出下章开头，人工核对该动作的
 *                   结果是否落地（人走了下章是否在场、电话接了是否有下文、灯关了是否换场）
 *
 * 严重度语义：仅 advisory。判定口诀——上一章收尾的动作/计划/状态，下一章开头是否直接接得上、
 * 或给了明确的换场/跨天标记？接得上 → 豁免；接不上（人凭空换位、计划被悄悄改掉、钩子无人认领）→ 补一句过渡/点名。
 */
const fs = require('fs');
const path = require('path');

// ---------- CLI ----------
const args = process.argv.slice(2);
let bookDir = null;
let TAIL = 400, HEAD = 300, SIM = 0.42;
for (let i = 0; i < args.length; i++) {
  const a = args[i];
  if (a.startsWith('--tail=')) TAIL = parseInt(a.slice(7), 10);
  else if (a.startsWith('--head=')) HEAD = parseInt(a.slice(7), 10);
  else if (a.startsWith('--sim=')) SIM = parseFloat(a.slice(6));
  else if (!a.startsWith('--')) bookDir = a;
}
if (!bookDir) {
  console.error('Usage: node check-chapter-boundary.js <bookDir> [--tail=400 --head=300 --sim=0.42]');
  process.exit(1);
}

// ---------- 收集章节 ----------
function chapterNo(fn) {
  const m = fn.match(/第(\d+)章/);
  return m ? parseInt(m[1], 10) : null;
}
function walk(dir, out) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, ent.name);
    if (ent.isDirectory()) walk(p, out);
    else if (ent.isFile() && ent.name.endsWith('.md') && ent.name !== '目录.md') {
      const n = chapterNo(ent.name);
      if (n) out.push({ n, p });
    }
  }
}
const chapters = [];
const zhengwen = path.join(bookDir, '正文');
if (fs.existsSync(zhengwen)) walk(zhengwen, chapters);
else walk(bookDir, chapters);
chapters.sort((a, b) => a.n - b.n);

// ---------- 文本工具 ----------
function read(p) { return fs.readFileSync(p, 'utf-8').replace(/^#\s+第\d+章.*$/m, ''); }
function splitSentences(t) {
  return t.split(/[。！？!?]/).map(s => s.trim()).filter(s => s.length >= 6);
}
function norm(s) { return s.replace(/[\s「」『』""''（）()——\-—,，、:：;；]/g, ''); }
function grams(s, n) {
  const g = new Set();
  for (let i = 0; i + n <= s.length; i++) g.add(s.slice(i, i + n));
  return g;
}
function jaccard(a, b) {
  const ga = grams(a, 6), gb = grams(b, 6);
  if (ga.size === 0 || gb.size === 0) return 0;
  let inter = 0;
  for (const x of ga) if (gb.has(x)) inter++;
  return inter / (ga.size + gb.size - inter);
}

// ---------- 检测器 ----------
const PLAN_RE = /(明天|明早|明晚|今晚|下一步|接下来|待会儿|待会|回头|到时候).{0,18}(去|先|查|找|办|谈|问|约|调|核|拿|跑|见)/;
const HOOK_RE = /(接进来|拿起电话|拨过去|挂了电话|把电话挂断|推门(走出去|进来)?|走出|转身离开|合上(卷宗|电脑|文件夹)?|关了灯|关掉台灯|关了机|关灯前|站起来就走|抬脚就走)$/;

function detect(ta, tb) {
  const findings = [];
  // ① 跨章复读：上章尾句 vs 下章头句
  const sa = splitSentences(ta);
  const sb = splitSentences(tb);
  if (sa.length && sb.length) {
    const lastA = norm(sa[sa.length - 1]);
    for (const s of sb.slice(0, 3)) {
      const nn = norm(s);
      if (lastA && nn && lastA.length >= 12 && nn.length >= 12) {
        const sim = jaccard(lastA, nn);
        if (sim >= SIM) {
          findings.push({
            kind: '跨章复读',
            tip: '上章末句与下章开头句高度相似（sim=' + sim.toFixed(2) + '），可能整句/意象跨章复读，删一侧',
            tail: sa[sa.length - 1],
            head: s,
          });
        }
      }
    }
  }
  // ② 计划悬空：上章尾段出现「明天/下一步…+ 计划动词」
  for (const s of sa.slice(-4)) {
    if (PLAN_RE.test(s)) {
      findings.push({
        kind: '计划悬空?',
        tip: '上章末段出现计划句，人工核对下章是否兑现（或明确改口），未兑现需交代',
        tail: s,
        head: sb[0] || '',
      });
    }
  }
  // ③ 动作/钩子收尾
  const lastRaw = ta.trim();
  for (const s of sa.slice(-3)) {
    if (HOOK_RE.test(s)) {
      findings.push({
        kind: '动作/钩子收尾?',
        tip: '上章以动作/钩子收尾，人工核对下章开头该动作的后续是否落地（人走了是否在场、电话是否有下文、换场是否有交代）',
        tail: s,
        head: sb[0] || '',
      });
    }
  }
  return findings;
}

// ---------- 主流程 ----------
let count = 0;
for (let i = 0; i < chapters.length - 1; i++) {
  const a = chapters[i], b = chapters[i + 1];
  const ta = read(a.p), tb = read(b.p);
  const tailTxt = ta.slice(-TAIL);
  const headTxt = tb.slice(0, HEAD);
  const finds = detect(tailTxt, headTxt);
  if (!finds.length) continue;
  count++;
  console.log(`\n===== Ch${a.n} → Ch${b.n} =====`);
  for (const f of finds) {
    console.log(`[${f.kind}] ${f.tip}`);
    console.log(`  上章尾: ${f.tail}`);
    if (f.head) console.log(`  下章头: ${f.head}`);
  }
}
console.log(`\n--- 共 ${count} 对疑似衔接需人工复核 / 总 ${chapters.length - 1} 对 ---`);
