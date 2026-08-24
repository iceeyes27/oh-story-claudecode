#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node check-chapter-skeleton.js [--dir <骨架目录>] [--from N] [--to N] [--json] [files...]

验证长篇章节骨架的结构、细纲覆盖与场景字数预算。
exit 0: 无 blocking；exit 1: 有 blocking；exit 2: 参数或读取错误。`;

const CONTRACT_FIELDS = [
  '来源细纲',
  '最终正文字数目标',
  '目标情绪',
  '读者获得',
  '禁止提前释放',
  '开场动作',
  '章尾钩子',
];

const SCENE_FIELDS = [
  '时空与人物',
  '场景目标',
  '阻力',
  '动作链',
  '结果变化',
  '情绪转折',
  '信息/伏笔',
  '台词意图与潜台词',
  '正文字数预算',
];

const EXPANSION_FIELDS = [
  '人物声线',
  '事实红线',
  '允许自由发挥',
];

function fail(message) {
  process.stderr.write(`${message}\n${USAGE}\n`);
  process.exit(2);
}

function positiveInt(value, name) {
  if (!/^\d+$/.test(value) || Number(value) < 1) fail(`${name} must be a positive integer`);
  return Number(value);
}

const options = { dir: null, from: null, to: null, json: false };
const positional = [];
for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--dir') {
    if (!process.argv[i + 1]) fail('--dir requires a value');
    options.dir = process.argv[++i];
  } else if (arg === '--from') {
    if (!process.argv[i + 1]) fail('--from requires a value');
    options.from = positiveInt(process.argv[++i], '--from');
  } else if (arg === '--to') {
    if (!process.argv[i + 1]) fail('--to requires a value');
    options.to = positiveInt(process.argv[++i], '--to');
  } else if (arg === '--json') {
    options.json = true;
  } else if (arg === '--help' || arg === '-h') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('--')) {
    fail(`unknown option: ${arg}`);
  } else {
    positional.push(arg);
  }
}

if (options.from !== null && options.to !== null && options.from > options.to) {
  fail('--from cannot be greater than --to');
}

function chapterOfFile(file) {
  const match = path.basename(file).match(/^第0*(\d+)章_(.+)\.md$/);
  return match ? Number(match[1]) : null;
}

function collectFiles() {
  const found = [...positional];
  if (options.dir) {
    const root = path.resolve(options.dir);
    if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) fail(`dir not found: ${options.dir}`);
    for (const name of fs.readdirSync(root)) {
      const full = path.join(root, name);
      if (!fs.statSync(full).isFile() || !name.endsWith('.md')) continue;
      const chapter = chapterOfFile(full);
      if (chapter === null) continue;
      if (options.from !== null && chapter < options.from) continue;
      if (options.to !== null && chapter > options.to) continue;
      found.push(full);
    }
  }
  const unique = Array.from(new Set(found.map((file) => path.resolve(file)))).sort();
  if (unique.length === 0) fail('no skeleton files found');
  for (const file of unique) {
    try {
      if (!fs.statSync(file).isFile()) fail(`not a file: ${file}`);
      fs.accessSync(file, fs.constants.R_OK);
    } catch (error) {
      fail(`cannot read skeleton file: ${file} (${error.message})`);
    }
  }
  return unique;
}

function add(list, code, message) {
  list.push({ code, message });
}

function splitSections(text) {
  const sections = [];
  const heading = /^##\s+(.+?)\s*$/gm;
  let match;
  while ((match = heading.exec(text)) !== null) {
    sections.push({ title: match[1], start: match.index, bodyStart: heading.lastIndex });
  }
  for (let i = 0; i < sections.length; i += 1) {
    sections[i].body = text.slice(sections[i].bodyStart, sections[i + 1]?.start ?? text.length).trim();
  }
  return sections;
}

function fieldsOf(body) {
  const fields = new Map();
  for (const line of body.split('\n')) {
    const match = line.trim().match(/^-\s+([^：:]+)[：:]\s*(.*)$/);
    if (match && !fields.has(match[1].trim())) fields.set(match[1].trim(), match[2].trim());
  }
  return fields;
}

function numberIn(value) {
  const match = String(value || '').match(/\d+/);
  return match ? Number(match[0]) : null;
}

function validateFile(file) {
  const blocking = [];
  const advisory = [];
  const chapter = chapterOfFile(file);
  if (chapter === null) add(blocking, 'filename', '文件名必须是 第NNN章_章名.md');

  let text;
  try {
    text = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
  } catch (error) {
    add(blocking, 'unreadable', `无法读取文件：${error.message}`);
    return { file, chapter, blocking, advisory };
  }

  const sections = splitSections(text);
  const byTitle = new Map(sections.map((section) => [section.title, section]));
  for (const title of ['章节契约', '细纲覆盖', '扩写约束']) {
    if (!byTitle.has(title)) add(blocking, 'missing-section', `缺少 ## ${title}`);
  }

  const contractFields = fieldsOf(byTitle.get('章节契约')?.body || '');
  for (const field of CONTRACT_FIELDS) {
    if (!contractFields.get(field)) add(blocking, 'missing-contract-field', `章节契约缺少字段：${field}`);
  }
  const target = numberIn(contractFields.get('最终正文字数目标'));
  if (target === null || target < 1) add(blocking, 'invalid-target-budget', '最终正文字数目标必须包含正整数');

  const expansionFields = fieldsOf(byTitle.get('扩写约束')?.body || '');
  for (const field of EXPANSION_FIELDS) {
    if (!expansionFields.get(field)) add(blocking, 'missing-expansion-field', `扩写约束缺少字段：${field}`);
  }

  const scenes = sections
    .map((section) => {
      const match = section.title.match(/^场景\s*(\d+)(?:\s.*)?$/);
      return match ? { ...section, number: Number(match[1]) } : null;
    })
    .filter(Boolean);

  if (scenes.length < 3 || scenes.length > 6) {
    add(blocking, 'scene-count', `场景数量必须在 3～6，实际 ${scenes.length}`);
  }
  const sceneNumbers = scenes.map((scene) => scene.number);
  if (new Set(sceneNumbers).size !== sceneNumbers.length) add(blocking, 'duplicate-scene', '场景编号重复');
  for (let i = 0; i < sceneNumbers.length; i += 1) {
    if (sceneNumbers[i] !== i + 1) {
      add(blocking, 'scene-sequence', '场景编号必须从 1 连续递增');
      break;
    }
  }

  let budgetSum = 0;
  for (const scene of scenes) {
    const fields = fieldsOf(scene.body);
    for (const field of SCENE_FIELDS) {
      if (!fields.get(field)) add(blocking, 'missing-scene-field', `场景 ${scene.number} 缺少字段：${field}`);
    }
    const budget = numberIn(fields.get('正文字数预算'));
    if (budget === null || budget < 1) {
      add(blocking, 'invalid-scene-budget', `场景 ${scene.number} 的正文字数预算必须包含正整数`);
    } else {
      budgetSum += budget;
    }
    if (/[“「][^”」\n]{2,}[”」]/.test(scene.body)) {
      add(advisory, 'possible-finished-dialogue', `场景 ${scene.number} 疑似包含完整台词，请确认只保留台词意图与潜台词`);
    }
    for (const line of scene.body.split('\n')) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith('-') && trimmed.length > 120) {
        add(advisory, 'long-narrative-line', `场景 ${scene.number} 出现超过 120 字的连续段落`);
        break;
      }
    }
  }
  if (target !== null && budgetSum !== target) {
    add(blocking, 'budget-mismatch', `场景目标字数合计 ${budgetSum}，不等于章节目标 ${target}`);
  }

  const coverage = byTitle.get('细纲覆盖')?.body || '';
  const coverageLines = coverage.split('\n').filter((line) => /^-\s+\[[ xX]\]/.test(line.trim()));
  if (coverageLines.length === 0) add(blocking, 'missing-coverage', '细纲覆盖必须至少包含一个勾选项');
  const ids = [];
  for (const line of coverageLines) {
    const match = line.trim().match(/^-\s+\[([ xX])\]\s+(O\d+)\b(.*)$/i);
    if (!match) {
      add(blocking, 'invalid-coverage-line', `细纲覆盖格式错误：${line.trim()}`);
      continue;
    }
    const checked = match[1].toLowerCase() === 'x';
    const id = match[2].toUpperCase();
    ids.push(id);
    if (!checked) add(blocking, 'unchecked-coverage', `${id} 尚未映射到场景`);
    const sceneMatch = match[3].match(/(?:->|→)\s*场景\s*(\d+)/);
    if (!sceneMatch || !sceneNumbers.includes(Number(sceneMatch[1]))) {
      add(blocking, 'invalid-coverage-scene', `${id} 必须指向存在的场景`);
    }
  }
  const duplicateIds = ids.filter((id, index) => ids.indexOf(id) !== index);
  for (const id of Array.from(new Set(duplicateIds))) add(blocking, 'duplicate-coverage-id', `细纲覆盖 ID 重复：${id}`);
  const uniqueCoverageNumbers = Array.from(new Set(ids.map((id) => Number(id.slice(1))))).sort((left, right) => left - right);
  for (let i = 0; i < uniqueCoverageNumbers.length; i += 1) {
    if (uniqueCoverageNumbers[i] !== i + 1) {
      add(blocking, 'coverage-sequence', '细纲覆盖 ID 必须从 O1 连续递增');
      break;
    }
  }

  return { file, chapter, blocking, advisory };
}

const results = collectFiles().map(validateFile);
const summary = {
  files: results.length,
  blocking: results.reduce((sum, result) => sum + result.blocking.length, 0),
  advisory: results.reduce((sum, result) => sum + result.advisory.length, 0),
  results,
};

if (options.json) {
  process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
} else {
  for (const result of results) {
    const status = result.blocking.length === 0 ? 'PASS' : 'FAIL';
    process.stdout.write(`${status} ${result.file} blocking=${result.blocking.length} advisory=${result.advisory.length}\n`);
    for (const finding of result.blocking) process.stdout.write(`  BLOCKING [${finding.code}] ${finding.message}\n`);
    for (const finding of result.advisory) process.stdout.write(`  ADVISORY [${finding.code}] ${finding.message}\n`);
  }
  process.stdout.write(`Summary: files=${summary.files} blocking=${summary.blocking} advisory=${summary.advisory}\n`);
}

process.exit(summary.blocking > 0 ? 1 : 0);
