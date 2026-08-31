'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');

const ROOT = path.resolve(__dirname, '..');
const CHECKER = path.join(ROOT, 'skills/_shared/scripts/check-foreshadow-overdue.js');
const { computeOverdue, hotCardIds } = require(CHECKER);

function foreshadow(id, planted, importance, planned = null, status = '已埋') {
  return [id, {
    id,
    summary: `${id} 的内容`,
    status,
    importance,
    planted_chapter: planted,
    planned_resolution_chapter: planned,
    updated_chapter: planted,
  }];
}

function state(lastChapter, rows) {
  return {
    schema_version: 4,
    book_title: '测试书',
    last_committed_chapter: lastChapter,
    state_revision: 0,
    foreshadow: Object.fromEntries(rows),
  };
}

function run(args) {
  const result = spawnSync(process.execPath, [CHECKER, ...args], { encoding: 'utf8' });
  return { status: result.status, stdout: result.stdout, stderr: result.stderr };
}

function writeProject(rows, lastChapter) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'foreshadow-'));
  fs.mkdirSync(path.join(root, '追踪'), { recursive: true });
  fs.writeFileSync(
    path.join(root, '追踪', '_tracking-state.json'),
    JSON.stringify(state(lastChapter, rows)),
    'utf8',
  );
  return root;
}

test('热卡复刻 tracking_commit.py 的排序：重要度 → 计划回收章 → id，未排期排最后', () => {
  const rows = [
    foreshadow('F900', 1, '低'),
    foreshadow('F001', 1, '中'),
    foreshadow('F002', 1, '高', 50),
    foreshadow('F003', 1, '高'),
    foreshadow('F004', 1, '高', 20),
  ].map(([id, row]) => ({ ...row, id }));

  const hot = [...hotCardIds(rows)];
  // 高 且 有计划章的按章号升序在前；高 未排期次之；再中；再低。
  assert.deepEqual(hot, ['F004', 'F002', 'F003', 'F001', 'F900']);
});

test('热卡只保留前 8 条，同重要度内旧伏笔（id 小）优先', () => {
  const rows = [];
  for (let i = 1; i <= 12; i++) {
    const id = `F${String(i).padStart(3, '0')}`;
    rows.push({ ...foreshadow(id, i, '高')[1], id });
  }
  const hot = hotCardIds(rows);
  assert.equal(hot.size, 8);
  assert.ok(hot.has('F001'), '最旧的伏笔必须留在热卡里，老债不能饿死');
  assert.ok(!hot.has('F012'), '第 9 条之后掉出热卡');
});

test('逾期是 blocking：定了回收章又错过', () => {
  const { errors, report } = computeOverdue(state(40, [foreshadow('F001', 5, '高', 30)]));
  assert.deepEqual(errors, []);
  assert.equal(report.counts.逾期, 1);
  assert.equal(report.blocking, true);
  const finding = report.findings.find((f) => f.rule === '逾期');
  assert.equal(finding.overdue_by, 10);
});

test('正好写到计划回收章那一章不算逾期，过了才算', () => {
  const onTime = computeOverdue(state(30, [foreshadow('F001', 5, '高', 30)])).report;
  assert.equal(onTime.counts.逾期, 0);
  const late = computeOverdue(state(31, [foreshadow('F001', 5, '高', 30)])).report;
  assert.equal(late.counts.逾期, 1);
});

test('悬空默认 advisory，--strict 下变 blocking', () => {
  const rows = [foreshadow('F001', 1, '高')];
  const loose = computeOverdue(state(40, rows)).report;
  assert.equal(loose.counts.悬空, 1);
  assert.equal(loose.blocking, false, '悬空默认只是提醒，不拦人');

  const strict = computeOverdue(state(40, rows), { strict: true }).report;
  assert.equal(strict.blocking, true);
});

test('悬空阈值按重要度分档', () => {
  const rows = [foreshadow('F001', 1, '中')];
  assert.equal(computeOverdue(state(40, rows)).report.counts.悬空, 0, '中级默认 60 章内不报');
  assert.equal(computeOverdue(state(70, rows)).report.counts.悬空, 1);
  assert.equal(computeOverdue(state(40, rows), { mid: 10 }).report.counts.悬空, 1, '阈值可调');
});

test('冷藏点名掉出热卡且埋了很久的伏笔', () => {
  const rows = [];
  for (let i = 1; i <= 9; i++) rows.push(foreshadow(`F${String(i).padStart(3, '0')}`, 1, '高'));
  // 第 9 条掉出热卡（热卡只放 8 条），埋后已过 30 章。
  const report = computeOverdue(state(31, rows), { high: 999 }).report;
  assert.equal(report.counts.冷藏, 1);
  const cold = report.findings.find((f) => f.rule === '冷藏');
  assert.equal(cold.id, 'F009');
  assert.equal(cold.in_hot_card, false);
});

test('已回收 / 放弃 / 已过期的伏笔不再计入活跃债务', () => {
  const rows = [
    foreshadow('F001', 1, '高', 5, '已回收'),
    foreshadow('F002', 1, '高', 5, '放弃'),
    foreshadow('F003', 1, '高', 5, '已过期'),
  ];
  const report = computeOverdue(state(80, rows)).report;
  assert.equal(report.active_count, 0);
  assert.deepEqual(report.findings, []);
  assert.equal(report.blocking, false);
});

test('非 schema_version 4 与损坏字段被拒绝，不猜测', () => {
  const old = computeOverdue({ ...state(10, [foreshadow('F001', 1, '高')]), schema_version: 3 });
  assert.equal(old.report, null);
  assert.match(old.errors[0], /schema_version=4/);

  const badImportance = computeOverdue(state(10, [foreshadow('F001', 1, '特高')]));
  assert.equal(badImportance.report, null);
  assert.match(badImportance.errors[0], /importance/);

  const badPlanned = computeOverdue(state(10, [foreshadow('F001', 1, '高', '第30章')]));
  assert.equal(badPlanned.report, null);
  assert.match(badPlanned.errors[0], /planned_resolution_chapter/);
});

test('CLI 退出码：0 干净 / 1 有逾期 / 2 参数或状态错误', () => {
  const clean = writeProject([foreshadow('F001', 1, '高', 30)], 10);
  const dirty = writeProject([foreshadow('F001', 1, '高', 30)], 40);
  try {
    assert.equal(run(['--project', clean]).status, 0);
    assert.equal(run(['--project', dirty]).status, 1);
    assert.equal(run([]).status, 2, '缺参数必须退 2');
    assert.equal(run(['--project', path.join(clean, '不存在')]).status, 2);
    assert.equal(run(['--project', clean, '--bogus']).status, 2, '未知参数不静默忽略');
  } finally {
    fs.rmSync(clean, { recursive: true, force: true });
    fs.rmSync(dirty, { recursive: true, force: true });
  }
});

test('--json 输出可解析且字段稳定', () => {
  const root = writeProject([foreshadow('F001', 1, '高', 30)], 40);
  try {
    const result = run(['--project', root, '--json']);
    assert.equal(result.status, 1);
    const report = JSON.parse(result.stdout);
    for (const key of ['book', 'last_committed_chapter', 'thresholds', 'findings', 'counts', 'blocking', 'hot_card_ids']) {
      assert.ok(key in report, `缺少字段 ${key}`);
    }
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

// 回归锚：热卡计算必须和 tracking_commit.py 真实渲染出的 上下文.md 逐条一致。
// 这条测试是本脚本正确性的地基——排序规则若与 Python 侧漂移，「冷藏」判定就会失真。
test('demo 书：热卡与已渲染的 追踪/上下文.md 逐条一致', () => {
  const book = path.join(ROOT, 'demo/长篇/让你管账号，你高燃混剪炸全网');
  const statePath = path.join(book, '追踪/_tracking-state.json');
  const contextPath = path.join(book, '追踪/上下文.md');
  if (!fs.existsSync(statePath) || !fs.existsSync(contextPath)) return;

  const report = computeOverdue(JSON.parse(fs.readFileSync(statePath, 'utf8'))).report;
  const rendered = [...fs.readFileSync(contextPath, 'utf8').matchAll(/^- (F\d+)｜/gm)].map((m) => m[1]);
  assert.deepEqual([...report.hot_card_ids].sort(), rendered.sort());
  assert.equal(report.cold_count, 6, 'demo 写到第 20 章时已有 6 条伏笔掉出热卡');
});
