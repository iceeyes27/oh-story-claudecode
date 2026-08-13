#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node flow-state.js [--dir <workspace-or-book>] [--json] <command> [args]

写作阶段披露状态工具。只判断 story-write 当前阶段和资料范围，不生成正文。

Commands:
  detect [--write]      从项目文件推断流程状态；--write 写入 追踪/写作流程状态.json
  read                  读取 追踪/写作流程状态.json；不存在时退出 1
  update '<json>'       合并字段后写回状态文件

规则见 references/progressive-disclosure.md。`;

function die(message, code = 2) {
  process.stderr.write(`${message}\n`);
  process.exit(code);
}

const options = { dir: process.cwd(), json: false, write: false };
const positional = [];

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--dir') {
    i += 1;
    if (!process.argv[i]) die('--dir requires a value');
    options.dir = process.argv[i];
  } else if (arg === '--json') {
    options.json = true;
  } else if (arg === '--write') {
    options.write = true;
  } else if (arg === '--help' || arg === '-h') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('--')) {
    die(`unknown option: ${arg}\n${USAGE}`);
  } else {
    positional.push(arg);
  }
}

if (positional.length === 0) die(USAGE);
const command = positional[0];

const VALID_MODES = new Set(['long', 'short']);
const VALID_PHASES = new Set(['topic', 'setting', 'outline', 'chapter_writing', 'revision', 'quality_check', 'publish_ready']);
const VALID_EXECUTION_STATUS = new Set(['ready', 'blocked', 'running', 'needs_repair', 'done']);
const VALID_NEXT_ACTIONS = new Set([
  'confirm_topic',
  'build_setting',
  'build_outline',
  'init_tracking',
  'write_chapter',
  'quality_check',
  'build_short_setting',
  'write_short_body',
  'revise_chapter',
  'publish',
]);
const VALID_UPDATE_FIELDS = new Set([
  'mode',
  'current_phase',
  'current_book',
  'current_chapter',
  'current_stage',
  'known_inputs',
  'missing_inputs',
  'artifacts',
  'execution_status',
  'next_action',
]);

function exists(p) {
  return fs.existsSync(p);
}

function isDir(p) {
  return exists(p) && fs.statSync(p).isDirectory();
}

function readTextIfExists(file) {
  if (!exists(file)) return '';
  return fs.readFileSync(file, 'utf8').trim();
}

function toSlash(p) {
  return p.split(path.sep).join('/');
}

function pad3(n) {
  return String(n).padStart(3, '0');
}

function findActiveBook(inputDir) {
  const root = path.resolve(inputDir);
  if (!isDir(root)) die(`dir not found: ${inputDir}`);

  const activeFile = path.join(root, '.active-book');
  if (exists(activeFile)) {
    const active = readTextIfExists(activeFile);
    if (!active) die('.active-book is empty');
    if (path.isAbsolute(active)) die(`.active-book must be a relative path inside the workspace: ${active}`);
    if (active.split(/[\\/]+/).includes('..')) die(`.active-book must not contain parent traversal: ${active}`);
    const book = path.resolve(root, active);
    const rel = path.relative(root, book);
    if (rel === '' || rel.startsWith('..') || path.isAbsolute(rel)) die(`.active-book points outside the workspace: ${active}`);
    if (!isDir(book)) die(`active book not found: ${active}`);
    return { workspace: root, book, activeBook: active };
  }

  if (isBookDir(root)) {
    return { workspace: path.dirname(root), book: root, activeBook: path.basename(root) };
  }

  die(`cannot locate a story book from: ${inputDir}`, 1);
}

function isBookDir(dir) {
  return (
    isDir(path.join(dir, '追踪')) ||
    isDir(path.join(dir, '设定')) ||
    isDir(path.join(dir, '正文')) ||
    isDir(path.join(dir, '大纲')) ||
    exists(path.join(dir, '正文.md'))
  );
}

function listMarkdownFiles(dir) {
  if (!isDir(dir)) return [];
  return fs.readdirSync(dir).filter((name) => name.endsWith('.md'));
}

function listChapterFiles(bodyDir) {
  const chapters = [];
  function walk(dir) {
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name.startsWith('.') || entry.name === 'node_modules') continue;
      const full = path.join(dir, entry.name);
      if (entry.isDirectory() && !entry.isSymbolicLink()) {
        walk(full);
        continue;
      }
      if (!entry.isFile() || entry.name.includes('_原稿_')) continue;
      const match = entry.name.match(/^第0*(\d{1,4})章.*\.md$/);
      if (match) chapters.push({ chapter: Number(match[1]), file: full });
    }
  }
  if (isDir(bodyDir)) walk(bodyDir);
  return chapters.sort((left, right) => left.chapter - right.chapter || left.file.localeCompare(right.file));
}

function detectMode(book) {
  if (exists(path.join(book, '正文.md'))) return 'short';
  return 'long';
}

function findHighestChapter(book) {
  const bodyDir = path.join(book, '正文');
  return listChapterFiles(bodyDir).reduce((max, item) => Math.max(max, item.chapter), 0);
}

function hasOutlineFor(book, chapter) {
  const outlineDir = path.join(book, '大纲');
  if (!isDir(outlineDir)) return false;
  const expected = `细纲_第${pad3(chapter)}章.md`;
  return exists(path.join(outlineDir, expected));
}

function detectLongState(book, activeBook) {
  const known = [];
  const missing = [];
  const artifacts = [];

  const topicFile = path.join(book, '设定', '题材定位.md');
  const stateFile = path.join(book, '追踪', '_tracking-state.json');
  const contextFile = path.join(book, '追踪', '上下文.md');

  if (exists(topicFile)) {
    known.push('题材定位');
    artifacts.push('设定/题材定位.md');
  }
  if (exists(stateFile)) {
    known.push('结构化追踪');
    artifacts.push('追踪/_tracking-state.json');
  }
  if (exists(contextFile)) {
    known.push('续写状态卡');
    artifacts.push('追踪/上下文.md');
  }

  const lastChapter = findHighestChapter(book);
  const currentChapter = lastChapter + 1;

  let currentPhase = 'topic';
  let currentStage = 'detect';
  let nextAction = 'confirm_topic';

  if (!isDir(path.join(book, '设定')) || !exists(topicFile)) {
    currentPhase = 'setting';
    currentStage = 'plan';
    nextAction = 'build_setting';
    missing.push('题材定位');
  } else if (!isDir(path.join(book, '大纲')) || !hasOutlineFor(book, currentChapter)) {
    currentPhase = 'outline';
    currentStage = 'plan';
    nextAction = 'build_outline';
    missing.push(`第${pad3(currentChapter)}章细纲`);
  } else if (!exists(stateFile)) {
    currentPhase = 'outline';
    currentStage = 'validate';
    nextAction = 'init_tracking';
    missing.push('结构化追踪');
  } else {
    currentPhase = 'chapter_writing';
    currentStage = lastChapter === 0 ? 'ready_first_chapter' : 'ready_next_chapter';
    nextAction = 'write_chapter';
    known.push(`第${pad3(currentChapter)}章细纲`);
    artifacts.push(`大纲/细纲_第${pad3(currentChapter)}章.md`);
    if (lastChapter > 0) {
      const matching = listChapterFiles(path.join(book, '正文')).filter((item) => item.chapter === lastChapter);
      const latest = matching[matching.length - 1];
      artifacts.push(latest ? path.relative(book, latest.file).split(path.sep).join('/') : `正文/**/第${pad3(lastChapter)}章_*.md`);
    }
  }

  return {
    schema_version: 1,
    mode: 'long',
    current_phase: currentPhase,
    current_book: activeBook,
    current_chapter: currentChapter,
    current_stage: currentStage,
    known_inputs: Array.from(new Set(known)),
    missing_inputs: missing,
    artifacts: Array.from(new Set(artifacts)),
    execution_status: missing.length > 0 ? 'blocked' : 'ready',
    next_action: nextAction,
  };
}

function detectShortState(book, activeBook) {
  const known = [];
  const missing = [];
  const artifacts = [];

  if (exists(path.join(book, '设定.md'))) {
    known.push('短篇设定');
    artifacts.push('设定.md');
  } else {
    missing.push('短篇设定');
  }
  if (exists(path.join(book, '小节大纲.md'))) {
    known.push('小节大纲');
    artifacts.push('小节大纲.md');
  } else {
    missing.push('小节大纲');
  }
  if (exists(path.join(book, '正文.md'))) {
    known.push('正文');
    artifacts.push('正文.md');
  }

  const hasBody = exists(path.join(book, '正文.md')) && readTextIfExists(path.join(book, '正文.md')).length > 0;
  const currentPhase = hasBody ? 'quality_check' : missing.length > 0 ? 'setting' : 'chapter_writing';

  return {
    schema_version: 1,
    mode: 'short',
    current_phase: currentPhase,
    current_book: activeBook,
    current_stage: hasBody ? (missing.length > 0 ? 'validate_with_gaps' : 'validate') : missing.length > 0 ? 'plan' : 'draft',
    known_inputs: Array.from(new Set(known)),
    missing_inputs: missing,
    artifacts: Array.from(new Set(artifacts)),
    execution_status: hasBody ? 'ready' : missing.length > 0 ? 'blocked' : 'ready',
    next_action: hasBody ? 'quality_check' : missing.length > 0 ? 'build_short_setting' : 'write_short_body',
  };
}

function detectState(bookInfo) {
  if (detectMode(bookInfo.book) === 'short') return detectShortState(bookInfo.book, bookInfo.activeBook);
  return detectLongState(bookInfo.book, bookInfo.activeBook);
}

function statePath(book) {
  return path.join(book, '追踪', '写作流程状态.json');
}

function writeState(book, state) {
  validateState(state);
  const file = statePath(book);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(state, null, 2)}\n`, 'utf8');
  return file;
}

function readState(book) {
  const file = statePath(book);
  if (!exists(file)) die(`flow state not found: ${toSlash(path.relative(book, file))}`, 1);
  return JSON.parse(fs.readFileSync(file, 'utf8'));
}

function printState(state) {
  if (options.json) {
    process.stdout.write(`${JSON.stringify(state, null, 2)}\n`);
    return;
  }
  process.stdout.write(`已识别：${state.mode === 'short' ? '短篇写作' : '长篇写作'}\n`);
  process.stdout.write(`当前阶段：${state.current_phase}/${state.current_stage}\n`);
  process.stdout.write(`已有资料：${state.known_inputs.length ? state.known_inputs.join('、') : '无'}\n`);
  process.stdout.write(`当前缺少：${state.missing_inputs.length ? state.missing_inputs.join('、') : '无'}\n`);
  process.stdout.write(`本次执行：${state.next_action}\n`);
}

function validateRelPathList(values, field) {
  if (!Array.isArray(values)) die(`${field} must be an array`);
  for (const value of values) {
    if (typeof value !== 'string' || value.trim() === '') die(`${field} must contain non-empty strings`);
    const normalized = value.replace(/\\/g, '/');
    const parts = normalized.split('/');
    if (
      path.isAbsolute(value) ||
      /^[A-Za-z]:/.test(value) ||
      normalized === '..' ||
      normalized.startsWith('../') ||
      normalized.includes('/../') ||
      parts.includes('..')
    ) {
      die(`${field} contains an unsafe path: ${value}`);
    }
  }
}

function validateStringList(values, field) {
  if (!Array.isArray(values)) die(`${field} must be an array`);
  for (const value of values) {
    if (typeof value !== 'string' || value.trim() === '') die(`${field} must contain non-empty strings`);
  }
}

function validateState(state) {
  if (typeof state !== 'object' || state === null || Array.isArray(state)) die('flow state must be a JSON object');
  if (state.schema_version !== 1) die('schema_version must be 1');
  if (!VALID_MODES.has(state.mode)) die(`mode must be one of: ${Array.from(VALID_MODES).join(', ')}`);
  if (!VALID_PHASES.has(state.current_phase)) die(`current_phase must be one of: ${Array.from(VALID_PHASES).join(', ')}`);
  if (state.current_chapter !== undefined && (!Number.isInteger(state.current_chapter) || state.current_chapter < 1)) die('current_chapter must be a positive integer');
  for (const field of ['current_book', 'current_stage', 'next_action']) {
    if (typeof state[field] !== 'string' || state[field].trim() === '') die(`${field} must be a non-empty string`);
  }
  if (!VALID_NEXT_ACTIONS.has(state.next_action)) die(`next_action must be one of: ${Array.from(VALID_NEXT_ACTIONS).join(', ')}`);
  validateStringList(state.known_inputs, 'known_inputs');
  validateStringList(state.missing_inputs, 'missing_inputs');
  validateRelPathList(state.artifacts, 'artifacts');
  if (!VALID_EXECUTION_STATUS.has(state.execution_status)) die(`execution_status must be one of: ${Array.from(VALID_EXECUTION_STATUS).join(', ')}`);
}

function validateUpdatePatch(patch) {
  for (const key of Object.keys(patch)) {
    if (!VALID_UPDATE_FIELDS.has(key)) die(`unknown update field: ${key}`);
  }
}

const bookInfo = findActiveBook(options.dir);

if (command === 'detect') {
  const state = detectState(bookInfo);
  if (options.write) writeState(bookInfo.book, state);
  printState(state);
  process.exit(state.execution_status === 'blocked' ? 1 : 0);
}

if (command === 'read') {
  printState(readState(bookInfo.book));
  process.exit(0);
}

if (command === 'update') {
  if (positional.length < 2) die('update requires a JSON object');
  let patch;
  try {
    patch = JSON.parse(positional[1]);
  } catch (err) {
    die(`update payload is not valid JSON: ${err.message}`);
  }
  if (typeof patch !== 'object' || patch === null || Array.isArray(patch)) die('update payload must be a JSON object');
  validateUpdatePatch(patch);
  const current = exists(statePath(bookInfo.book)) ? readState(bookInfo.book) : detectState(bookInfo);
  const next = { ...current, ...patch, schema_version: 1 };
  writeState(bookInfo.book, next);
  printState(next);
  process.exit(next.execution_status === 'blocked' ? 1 : 0);
}

die(`unknown command: ${command}\n${USAGE}`);
