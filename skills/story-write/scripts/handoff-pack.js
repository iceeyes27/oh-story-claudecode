#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node handoff-pack.js [--write] [--dir <book-dir>] <chapter>

章节交接包生成：把第 N 章对第 N+1 章的继承约束压缩成可读取、可复查的交接材料。
只在第 N 章漂移门控为 Gate: PASS 且含「继承关键词」时生成——失败章节不得交接。

汇总来源（全部自动提取，不做语义生成）：
  - 追踪/漂移门控/第{N}章.md   → State Delta、继承关键词、Gate 结论
  - 大纲/细纲_第{N}章.md       → 结尾设定和钩子
  - 追踪/伏笔.md               → 状态为「已埋」的活跃伏笔行
  - 设定/角色不变量/*.md       → 本章出场且有不变量档案的角色

默认输出 Markdown 到 stdout；--write 落盘到 追踪/交接包/第{N}章_to_第{N+1}章.md。
规则与消费方式见 references/longform-stability.md「工件三：章节交接包」。`;

function die(msg) {
  process.stderr.write(`${msg}\n`);
  process.exit(2);
}

function fail(msg) {
  process.stderr.write(`FAIL: ${msg}\n`);
  process.exit(1);
}

const options = { write: false, dir: process.cwd(), chapter: null };

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--write') {
    options.write = true;
  } else if (arg === '--dir') {
    i += 1;
    if (!process.argv[i]) die('--dir requires a value');
    options.dir = process.argv[i];
  } else if (arg === '--help' || arg === '-h') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('-')) {
    die(`unknown option: ${arg}\n${USAGE}`);
  } else if (options.chapter === null) {
    options.chapter = arg;
  } else {
    die(USAGE);
  }
}

if (options.chapter === null) die(USAGE);
const chapterNum = Number.parseInt(options.chapter, 10);
if (!Number.isInteger(chapterNum) || chapterNum < 1) die('章节号必须是正整数');
if (!fs.existsSync(options.dir) || !fs.statSync(options.dir).isDirectory()) die(`book dir not found: ${options.dir}`);

const BOOK = options.dir;
const nextNum = chapterNum + 1;

function pad3(n) {
  return String(n).padStart(3, '0');
}

function readSafe(file) {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch (err) {
    return null;
  }
}

function findBody(n) {
  const dir = path.join(BOOK, '正文');
  if (!fs.existsSync(dir)) return null;
  const id = pad3(n);
  const hits = [];
  const visit = (current) => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const candidate = path.join(current, entry.name);
      if (entry.isDirectory()) {
        visit(candidate);
      } else if (
        entry.isFile()
        && entry.name.endsWith('.md')
        && !entry.name.includes('原稿')
        && (entry.name === `第${id}章.md` || entry.name.startsWith(`第${id}章_`))
      ) {
        hits.push(candidate);
      }
    }
  };
  visit(dir);
  hits.sort((a, b) => a.localeCompare(b, 'zh-Hans-CN'));
  return hits.length > 0 ? path.relative(BOOK, hits[0]) : null;
}

function extractSection(text, titleRe) {
  const lines = text.split(/\r?\n/);
  let start = -1;
  let level = 0;
  for (let i = 0; i < lines.length; i += 1) {
    const m = lines[i].match(/^(#{1,6})\s*(.+)$/);
    if (m && titleRe.test(m[2])) {
      start = i;
      level = m[1].length;
      break;
    }
  }
  if (start === -1) return null;
  const out = [];
  for (let i = start + 1; i < lines.length; i += 1) {
    const m = lines[i].match(/^(#{1,6})\s/);
    if (m && m[1].length <= level) break;
    out.push(lines[i]);
  }
  return out.join('\n').trim();
}

const id = pad3(chapterNum);
const nextId = pad3(nextNum);

const bodyRel = findBody(chapterNum);
if (bodyRel === null) fail(`正文缺失：正文/第${id}章_*.md`);
const bodyText = readSafe(path.join(BOOK, bodyRel));

// 归档透明回退：活跃目录优先（回炉重写的新门控在活跃目录），找不到再读归档
let gateRel = path.join('追踪', '漂移门控', `第${id}章.md`);
let gateText = readSafe(path.join(BOOK, gateRel));
if (gateText === null) {
  gateRel = path.join('追踪', '归档', '漂移门控', `第${id}章.md`);
  gateText = readSafe(path.join(BOOK, gateRel));
}
if (gateText === null) fail(`漂移门控缺失：追踪/漂移门控/第${id}章.md（追踪/归档/ 下也无；先按 longform-stability.md 模板写门控）`);
if (!/Gate[：:]\s*PASS/.test(gateText)) fail(`第 ${id} 章 Gate 不是 PASS，先修正文/契约/追踪文件，不得把失败章节交接到下一章`);

const inheritMatch = gateText.match(/继承关键词[：:]\s*(.+)/);
const inheritTerms = inheritMatch
  ? inheritMatch[1]
      .split(/[、，,;；]/)
      .map((t) => t.trim())
      .filter((t) => t.length >= 2 && !/[{}]/.test(t) && !/^(无|待补充|暂无)$/.test(t))
  : [];
if (inheritTerms.length === 0) fail(`第 ${id} 章漂移门控缺「继承关键词」（2-5 个具体词），补齐后重新生成交接包`);

const stateDelta = extractSection(gateText, /^State Delta/) || '- （门控未记录 State Delta，先补齐再交接）';

const outlineText = readSafe(path.join(BOOK, '大纲', `细纲_第${id}章.md`));
const endingSection = outlineText ? extractSection(outlineText, /^结尾设定和钩子/) : null;

// 活跃伏笔：伏笔状态表中状态为「已埋」的行
const foreshadowText = readSafe(path.join(BOOK, '追踪', '伏笔.md'));
const activeForeshadow = [];
if (foreshadowText) {
  for (const line of foreshadowText.split(/\r?\n/)) {
    if (!line.trim().startsWith('|')) continue;
    if (/\|\s*-{3,}/.test(line) || /\|\s*ID\s*\|/.test(line)) continue;
    if (line.includes('已埋')) activeForeshadow.push(line.trim());
  }
}

// 角色连续性：本章正文里出现、且有不变量档案的角色
const invariantDir = path.join(BOOK, '设定', '角色不变量');
const presentCharacters = [];
if (fs.existsSync(invariantDir)) {
  for (const f of fs.readdirSync(invariantDir).filter((x) => x.endsWith('.md')).sort()) {
    const name = path.basename(f, '.md');
    if (!bodyText || !bodyText.includes(name)) continue;
    const invText = readSafe(path.join(invariantDir, f));
    const goal = invText ? extractSection(invText, /^当前阶段目标/) : null;
    const goalLine = goal ? goal.split(/\r?\n/).map((l) => l.replace(/^\s*-\s*/, '').trim()).filter(Boolean)[0] : null;
    presentCharacters.push({ name, goal: goalLine || '（见不变量档案）', file: `设定/角色不变量/${name}.md` });
  }
}

const lines = [];
lines.push(`## Chapter Handoff Pack：第 ${id} 章 -> 第 ${nextId} 章`);
lines.push('');
lines.push('### 来源');
lines.push(`- 源正文：${bodyRel.split(path.sep).join('/')}`);
lines.push(`- 漂移门控：${gateRel.split(path.sep).join('/')}`);
lines.push('- Gate: PASS');
lines.push('');
lines.push('### 继承关键词');
lines.push(`- 继承关键词：${inheritTerms.join('、')}`);
lines.push('');
lines.push('### 最近 State Delta（本章改变了什么）');
lines.push(stateDelta);
lines.push('');
lines.push('### 章尾钩子与下一章期待');
if (endingSection) {
  lines.push(endingSection);
} else {
  lines.push(`- （细纲缺「结尾设定和钩子」小节：大纲/细纲_第${id}章.md）`);
}
lines.push('');
lines.push('### 活跃伏笔（状态：已埋）');
if (activeForeshadow.length > 0) {
  lines.push('| ID | 伏笔内容 | 埋设章节 | 预计回收章节 | 状态 | 重要度 |');
  lines.push('|----|---------|---------|-------------|------|--------|');
  lines.push(...activeForeshadow);
} else {
  lines.push('- 无（或 追踪/伏笔.md 缺失）');
}
lines.push('');
lines.push('### 角色连续性');
if (presentCharacters.length > 0) {
  for (const c of presentCharacters) {
    lines.push(`- ${c.name}：当前阶段目标 ${c.goal}；红线/认知边界见 ${c.file}`);
  }
} else {
  lines.push('- 本章无已建不变量档案的角色出场（新角色承担连续剧情功能时按 character-invariants.md 补建）');
}
lines.push('');
lines.push('### 下一章必读文件');
lines.push(`- 本交接包`);
lines.push(`- 大纲/细纲_第${nextId}章.md（含稳定性契约）`);
lines.push(`- ${bodyRel.split(path.sep).join('/')}`);
lines.push('- 追踪/伏笔.md、追踪/角色状态.md、追踪/情绪债务.md（如存在）');
for (const c of presentCharacters) lines.push(`- ${c.file}`);
lines.push('');
lines.push('### 交接规则');
lines.push(`- 先读本交接包，再定第 ${nextId} 章稳定性契约；继承关键词必须在第 ${nextId} 章正文出现（stability-audit.js 验证）。`);
lines.push(`- 不得在第 ${nextId} 章回退本章 State Delta。`);
lines.push('- 要删除或改写本章线索，先走大修流程并重跑稳定性复检。');
lines.push(`- 第 ${nextId} 章写完过门控后，重新生成新的交接包。`);
lines.push('');

const output = lines.join('\n');

if (options.write) {
  const outDir = path.join(BOOK, '追踪', '交接包');
  fs.mkdirSync(outDir, { recursive: true });
  const outRel = `追踪/交接包/第${id}章_to_第${nextId}章.md`;
  fs.writeFileSync(path.join(BOOK, '追踪', '交接包', `第${id}章_to_第${nextId}章.md`), output, 'utf8');
  process.stdout.write(`WROTE: ${outRel}\n`);
} else {
  process.stdout.write(output);
}
