'use strict';

// 伏笔欠账门：写第 N 章（首建）前，若有伏笔越过了自己排定的回收章仍未回收就拦下。
// 只拦「作者自己排了回收章又错过」这一类明确违约；悬空（从没排回收章）与冷藏（掉出续写热卡）
// 是 advisory，由 _shared/scripts/check-foreshadow-overdue.js 在建细纲批时报——本测试同时锁住
// 「不拦 advisory」这一半，避免日更被退化成全量伏笔审计（detect-story-gaps.sh 的既定设计）。

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const CORE = path.join(ROOT, 'skills/story-setup/references/templates/hooks/story_hook_core.js');
const CLI = path.join(ROOT, 'skills/story-setup/references/templates/hooks/story_hook_cli.js');
const CODEX = path.join(ROOT, 'skills/story-setup/references/codex/hooks/story_codex_hook.py');
const core = require(CORE);

const CHAPTER = 41;
const LAST_COMMITTED = 40;

function foreshadow(id, { planted = 1, importance = '高', planned = null, status = '已埋' } = {}) {
  return [id, {
    id, summary: `${id} 的内容`, status, importance,
    planted_chapter: planted, planned_resolution_chapter: planned, updated_chapter: planted,
  }];
}

// 构造一本能通过前两道门（细纲存在、追踪检查点成立）的书，好让第三道门成为唯一变量。
function makeBook({ rows = [], outlineHead = '', prevProse = null } = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'foreshadow-gate-'));
  const book = path.join(root, '测试书');
  fs.mkdirSync(path.join(book, '正文'), { recursive: true });
  fs.mkdirSync(path.join(book, '大纲'), { recursive: true });
  fs.mkdirSync(path.join(book, '追踪'), { recursive: true });
  fs.writeFileSync(
    path.join(book, '大纲', `细纲_第${CHAPTER}章.md`),
    `${outlineHead}# 第${CHAPTER}章 细纲\n\n本章要发生的事。\n`,
    'utf8',
  );
  fs.writeFileSync(path.join(book, '追踪', '_tracking-state.json'), JSON.stringify({
    schema_version: 4,
    book_title: '测试书',
    state_revision: 7,
    last_committed_chapter: LAST_COMMITTED,
    foreshadow: Object.fromEntries(rows),
  }), 'utf8');
  fs.writeFileSync(path.join(book, '追踪', '上下文.md'), '> 状态修订：7\n', 'utf8');
  if (prevProse !== null) {
    fs.writeFileSync(path.join(book, '正文', `第${LAST_COMMITTED}章_上一章.md`), prevProse, 'utf8');
  }
  return { root, book, target: path.join(book, '正文', `第${CHAPTER}章_新章.md`) };
}

function block(fixture) {
  return core.proseBlockReason(fixture.root, fixture.target);
}

function cleanup(fixture) {
  fs.rmSync(fixture.root, { recursive: true, force: true });
}

test('逾期伏笔拦住首建新章', () => {
  const f = makeBook({ rows: [foreshadow('F016', { planned: 30 })] });
  try {
    const reason = block(f);
    assert.ok(reason, '必须拦下');
    assert.match(reason, /伏笔已越过自己排定的回收章仍未回收/);
    assert.match(reason, /F016｜F016 的内容｜计划第30章回收，正文已到第40章/);
    assert.match(reason, /第 41 章/);
  } finally { cleanup(f); }
});

test('悬空（从没排回收章）不拦日更', () => {
  const f = makeBook({ rows: [foreshadow('F003', { planted: 1, planned: null })] });
  try {
    assert.equal(block(f), null, '没排回收章的伏笔是 advisory，不能拦写作');
  } finally { cleanup(f); }
});

test('回收章还没到、以及已回收/放弃的伏笔都不拦', () => {
  const future = makeBook({ rows: [foreshadow('F020', { planned: 60 })] });
  const done = makeBook({ rows: [foreshadow('F021', { planned: 30, status: '已回收' })] });
  const dropped = makeBook({ rows: [foreshadow('F022', { planned: 30, status: '放弃' })] });
  const expired = makeBook({ rows: [foreshadow('F023', { planned: 30, status: '已过期' })] });
  try {
    assert.equal(block(future), null);
    assert.equal(block(done), null);
    assert.equal(block(dropped), null);
    assert.equal(block(expired), null, '已显式标记过期的不再重复拦');
  } finally { [future, done, dropped, expired].forEach(cleanup); }
});

test('正好写到计划回收章那一章不算逾期', () => {
  const onTime = makeBook({ rows: [foreshadow('F016', { planned: LAST_COMMITTED })] });
  const late = makeBook({ rows: [foreshadow('F016', { planned: LAST_COMMITTED - 1 })] });
  try {
    assert.equal(block(onTime), null);
    assert.ok(block(late));
  } finally { cleanup(onTime); cleanup(late); }
});

test('细纲头部的 <!-- 伏笔:跳过 --> 豁免，超出头 6 行则无效', () => {
  const exempt = makeBook({
    rows: [foreshadow('F016', { planned: 30 })],
    outlineHead: '<!-- 伏笔:跳过 -->\n',
  });
  const tooLate = makeBook({
    rows: [foreshadow('F016', { planned: 30 })],
    outlineHead: '\n\n\n\n\n\n\n<!-- 伏笔:跳过 -->\n',
  });
  try {
    assert.equal(block(exempt), null, '显式豁免必须生效');
    assert.ok(block(tooLate), '豁免标记只认头 6 行，与去味门同规则');
  } finally { cleanup(exempt); cleanup(tooLate); }
});

test('伏笔欠账门排在毒句式欠账门之前', () => {
  const f = makeBook({
    rows: [foreshadow('F016', { planned: 30 })],
    prevProse: '# 第40章 上一章\n\n他放下麦克风朝台下鞠了一躬。\n没人知道，这才刚刚开头。\n',
  });
  try {
    const reason = block(f);
    assert.match(reason, /伏笔已越过自己排定的回收章/);
    assert.doesNotMatch(reason, /毒句式/, '两门同时命中时先报伏笔，顺序与 bash 守卫一致');
  } finally { cleanup(f); }
});

test('正文已存在（续写/改稿/回炉）不触发本门', () => {
  const f = makeBook({ rows: [foreshadow('F016', { planned: 30 })] });
  try {
    fs.writeFileSync(f.target, '# 第41章 新章\n\n已有正文。\n', 'utf8');
    assert.equal(block(f), null, '欠账门只针对首建新章');
  } finally { cleanup(f); }
});

test('状态损坏一律 fail-open，不因解析失败误伤写作', () => {
  assert.deepEqual(core.overdueForeshadowLines('/不存在的目录'), []);
  const f = makeBook({ rows: [foreshadow('F016', { planned: 30 })] });
  try {
    const statePath = path.join(f.book, '追踪', '_tracking-state.json');
    const good = JSON.parse(fs.readFileSync(statePath, 'utf8'));

    fs.writeFileSync(statePath, '{ 不是 JSON', 'utf8');
    assert.deepEqual(core.overdueForeshadowLines(f.book), []);

    fs.writeFileSync(statePath, JSON.stringify({ ...good, schema_version: 3 }), 'utf8');
    assert.deepEqual(core.overdueForeshadowLines(f.book), [], 'schema 不符时放行，交给追踪检查点门去报');

    fs.writeFileSync(statePath, JSON.stringify({ ...good, last_committed_chapter: '40' }), 'utf8');
    assert.deepEqual(core.overdueForeshadowLines(f.book), []);

    fs.writeFileSync(statePath, JSON.stringify({ ...good, foreshadow: [] }), 'utf8');
    assert.deepEqual(core.overdueForeshadowLines(f.book), []);
  } finally { cleanup(f); }
});

test('多条逾期只列前 6 条并给出完整体检出口', () => {
  const rows = [];
  for (let i = 1; i <= 9; i++) rows.push(foreshadow(`F${String(i).padStart(3, '0')}`, { planned: 30 }));
  const f = makeBook({ rows });
  try {
    const reason = block(f);
    assert.match(reason, /有 9 条伏笔/);
    assert.match(reason, /（另有 3 条，完整体检：node <skill>\/scripts\/check-foreshadow-overdue\.js --project 书目录）/);
    assert.equal(reason.split('\n').filter((line) => /^F\d+｜/.test(line)).length, 6);
  } finally { cleanup(f); }
});

test('CLI 子命令 foreshadow-debt 与核逐字一致', () => {
  const f = makeBook({ rows: [foreshadow('F016', { planned: 30 })] });
  try {
    const result = spawnSync(process.execPath, [CLI, 'foreshadow-debt', f.book, String(CHAPTER)], { encoding: 'utf8' });
    assert.equal(result.status, 0);
    assert.equal(result.stdout, block(f), 'bash 守卫走这条子命令，必须与核同一份文案');
  } finally { cleanup(f); }
});

test('js ↔ codex py 文案 parity', () => {
  const probe = spawnSync('python3', ['-c', 'print(1)'], { encoding: 'utf8' });
  if (probe.status !== 0) return; // 无 python3 运行时则跳过，与 test-prose-net-parity.sh 同策略

  const cases = [
    { name: '逾期', rows: [foreshadow('F016', { planned: 30 })] },
    { name: '多条逾期', rows: Array.from({ length: 9 }, (_, i) => foreshadow(`F${String(i + 1).padStart(3, '0')}`, { planned: 30 })) },
    { name: '悬空', rows: [foreshadow('F003', { planned: null })] },
    { name: '已回收', rows: [foreshadow('F021', { planned: 30, status: '已回收' })] },
  ];
  for (const item of cases) {
    const f = makeBook({ rows: item.rows });
    try {
      const js = block(f) || '-';
      const py = spawnSync('python3', ['-c', `
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("ch", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
reason = m.prose_block_reason(Path(sys.argv[2]), Path(sys.argv[3]))
sys.stdout.buffer.write((reason if reason else "-").encode("utf-8"))
`, CODEX, f.root, f.target], { encoding: 'utf8' });
      assert.equal(py.status, 0, py.stderr);
      assert.equal(py.stdout, js, `${item.name}：py 与 js 文案必须逐字一致`);
    } finally { cleanup(f); }
  }
});
