#!/usr/bin/env node
/**
 * check-paragraph-format.js
 * 正文段落格式 / 硬折行扫描（2026-08-24 从《法援律师》第1卷 44 章核查中固化）
 *
 * 背景与判据（实战验证，2026-08-24）：
 * 番茄发布脚本 extract_fanqie_chapter.py 把「每个非空行」当作一个独立段落 <p>。
 * 因此本地 md 里一行 = 番茄后台一段；被硬折成两行的句子，会在番茄渲染成断开的两段。
 * 本脚本只做「标记」，最终以人工逐句复核为准（机械扫描无法区分有意分段与硬折行）。
 *
 * 判定规则：
 * 1. 半截行（行尾是汉字/字母/数字、无任何标点结尾）→ blocking
 *    中文句子必然以句末标点（。！？…”』」…）收尾，行尾直接是汉字 = 句子被硬断，
 *    下一行必是续行，需并回一行。高置信硬折行。
 * 2. 段末分号（行尾「；」）→ advisory
 *    分号是句内标点，段末分号 = 语义未完。但「第一/第二/主题开头」逐条列表是网文
 *    常见的有意分段（短段节奏），机械无法区分「有意列表」与「拆行列表」，仅标记供复核。
 * 3. 冒号引列表（行尾「：」且下一行非对话开头）→ advisory
 *    冒号引出时间线/清单/列举（如 Ch008「时间链条：」+ 5 个时间点），需人工判断
 *    是「应并成一段」还是「有意逐条」。若下一行是「"」或「‘」开头的对话/引文，
 *    则为标准「冒号引对话」写法，有意分段，不报。
 *
 * 用法:
 *   node check-paragraph-format.js --dir "正文目录路径"
 *   node check-paragraph-format.js --dir "正文目录路径" --json
 *
 * 输出: blocking（半截行）/ advisory（段末分号、冒号引列表），退出码 1 = 有 blocking
 */

const fs = require('fs');
const path = require('path');

// ─── CLI ────────────────────────────────────────────────────
const args = process.argv.slice(2);
let dir = '';
let jsonMode = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--dir' && args[i + 1]) dir = args[++i];
  if (args[i] === '--json') jsonMode = true;
}
if (!dir) {
  console.error('用法: node check-paragraph-format.js --dir "正文目录路径" [--json]');
  process.exit(1);
}

// 句末标点（含闭合引号/括号后的句号式收尾）
const TERMINAL = new Set(['。', '！', '？', '…', '”', '’', '」', '』', '）', ')', '】']);
// 行尾标点集合（任何标点结尾都不算半截行）
const ANY_PUNCT = new Set(['。', '！', '？', '…', '”', '’', '」', '』', '）', ')', '】', '；', '，', '：', '、', '·', ',', ';', ':', '?', '!', '.', '"', "'", '—']);
// 半截行判据：仅行尾为汉字（中文句子必然以标点收尾；数字/字母结尾多为属性行/列表项，如「公理点 × 2」）
const CJK_END = /[\u4e00-\u9fff]$/;
const DIALOGUE_START = /^[“"‘']/;

// ─── 收集章节文件（递归）──────────────────────────────────
function collectChapters(root) {
  const results = [];
  function walk(d) {
    for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
      if (ent.isDirectory()) walk(path.join(d, ent.name));
      else if (ent.name.match(/^第\d+章_.*\.md$/)) results.push(path.join(d, ent.name));
    }
  }
  walk(root);
  results.sort();
  return results;
}

// ─── 单章扫描 ──────────────────────────────────────────────
function scanFile(file) {
  const raw = fs.readFileSync(file, 'utf-8');
  const lines = raw.split('\n');
  const findings = [];
  // 跳过文件头部 markdown 标题
  let startIdx = 0;
  for (let i = 0; i < Math.min(5, lines.length); i++) {
    if (/^#\s+第\d+章/.test(lines[i].trim())) { startIdx = i + 1; break; }
  }
  for (let i = startIdx; i < lines.length; i++) {
    const cur = lines[i].trim();
    if (!cur) continue;
    // 跳过 markdown 结构行
    if (/^#{1,6}\s/.test(cur) || /^```/.test(cur) || /^\|/.test(cur)) continue;

    const last = cur[cur.length - 1];
    const next = (i + 1 < lines.length) ? lines[i + 1].trim() : '';
    const lineno = i + 1;
    const preview = cur.length > 26 ? cur.slice(0, 26) + '…' : cur;
    const nextPreview = next.length > 26 ? next.slice(0, 26) + '…' : next;

    // 规则1：半截行（行尾汉字、无标点）→ blocking
    if (CJK_END.test(last) && !ANY_PUNCT.has(last)) {
      findings.push({
        lineno, type: '硬折行（半截行）', severity: 'blocking',
        preview, nextPreview,
        desc: '行尾是汉字且无标点，句子被硬断，下一行是续行，需并回一行',
      });
      continue;
    }

    // 规则2：段末分号 → advisory
    if (last === '；' || last === ';') {
      findings.push({
        lineno, type: '段末分号', severity: 'advisory',
        preview, nextPreview,
        desc: '段末以分号收尾（语义未完）。若是「第一/第二/主题开头」逐条列表的有意分段可保留；否则是列表拆行，需并回上一段',
      });
      continue;
    }

    // 规则3：冒号引列表 → advisory（下一行不是对话/引文时）
    if (last === '：' || last === ':') {
      if (!next || DIALOGUE_START.test(next)) {
        // 下一行是对话或引文 → 标准「冒号引对话」写法，有意分段，不报
        continue;
      }
      findings.push({
        lineno, type: '冒号引列表', severity: 'advisory',
        preview, nextPreview,
        desc: '冒号引出列举/时间线/清单。若是同一段的列举应并回一行；若是作者有意逐条短段可保留',
      });
    }
  }
  return findings;
}

// ─── 执行 ──────────────────────────────────────────────────
const root = path.resolve(dir);
if (!fs.existsSync(root)) {
  console.error(`目录不存在: ${root}`);
  process.exit(1);
}
const files = collectChapters(root);
if (files.length === 0) {
  console.error(`未在 ${dir} 下找到章节文件（需匹配 第NN章_*.md）`);
  process.exit(1);
}

const all = [];
for (const f of files) {
  const findings = scanFile(f);
  for (const fd of findings) {
    all.push({ file: path.basename(f), ...fd });
  }
}

const blocking = all.filter(f => f.severity === 'blocking');
const advisory = all.filter(f => f.severity === 'advisory');

if (jsonMode) {
  console.log(JSON.stringify({ total_files: files.length, blocking, advisory }, null, 2));
} else {
  console.log(`\n📄 段落格式 / 硬折行扫描：共 ${files.length} 章\n`);
  if (blocking.length > 0) {
    console.log(`🔴 Blocking（硬折行，需并回一行）：${blocking.length} 条`);
    console.log('─'.repeat(66));
    for (const f of blocking) {
      console.log(`  ${f.file} L${f.lineno} │ ${f.type}`);
      console.log(`     当前：${f.preview}`);
      console.log(`     下一：${f.nextPreview || '(无)'}`);
      console.log(`     ${f.desc}`);
    }
    console.log('');
  }
  if (advisory.length > 0) {
    console.log(`🟡 Advisory（人工复核：有意分段可保留）：${advisory.length} 条`);
    console.log('─'.repeat(66));
    for (const f of advisory) {
      console.log(`  ${f.file} L${f.lineno} │ ${f.type}`);
      console.log(`     当前：${f.preview}`);
      console.log(`     下一：${f.nextPreview || '(无)'}`);
      console.log(`     ${f.desc}`);
    }
    console.log('');
  }
  if (blocking.length === 0 && advisory.length === 0) {
    console.log('✅ 未发现段落格式问题\n');
  }
  process.exit(blocking.length > 0 ? 1 : 0);
}
