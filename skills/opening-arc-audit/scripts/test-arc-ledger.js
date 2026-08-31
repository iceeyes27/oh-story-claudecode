#!/usr/bin/env node
/** test-arc-ledger.js — arc-ledger.js 回归测试 */
'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { execFileSync } = require('node:child_process');
const SCRIPT = path.resolve(__dirname, '..', '..', '_shared', 'scripts', 'arc-ledger.js');
const { computeLedger } = require(SCRIPT);

let pass = 0;
function ok(name, fn) {
  try { fn(); console.log(`  [PASS] ${name}`); pass++; }
  catch (e) { console.error(`  [FAIL] ${name}\n         ${e.message}`); process.exitCode = 1; }
}
function tmp(obj) {
  const f = path.join(os.tmpdir(), `ledger-${Date.now()}-${Math.random().toString(36).slice(2)}.json`);
  fs.writeFileSync(f, JSON.stringify(obj), 'utf8');
  return f;
}
function run(file, extra = []) {
  try { return { code: 0, out: execFileSync('node', [SCRIPT, file, ...extra], { encoding: 'utf8' }) }; }
  catch (e) { return { code: e.status, out: (e.stdout || '') + (e.stderr || '') }; }
}

// 健康：每开必闭、主线推进 → 不 blocking
ok('健康开篇不 blocking', () => {
  const { report, errors } = computeLedger({
    window: 4,
    chapters: [
      { num: 1, opens: [{ id: 'Q1', q: '涨粉能不能成' }], closes: [], mainAdvance: true },
      { num: 2, opens: [{ id: 'Q2', q: '记者为何来' }], closes: ['Q1'], mainAdvance: true },
      { num: 3, opens: [], closes: ['Q2'], mainAdvance: true },
      { num: 4, opens: [{ id: 'Q3', q: '下个任务' }], closes: [], mainAdvance: true },
    ],
  });
  assert.equal(errors.length, 0);
  assert.equal(report.blocking, false);
  assert.equal(report.closeCount, 2);
  assert.equal(report.mainAdvanceSteps, 4);
});

// 故弄玄虚：只开不闭 + 主线打转 → blocking
ok('只开不闭主线打转 → blocking', () => {
  const { report } = computeLedger({
    window: 6,
    chapters: [
      { num: 1, opens: [{ id: 'A' }], closes: [], mainAdvance: false },
      { num: 2, opens: [{ id: 'B' }], closes: [], mainAdvance: false },
      { num: 3, opens: [{ id: 'C' }], closes: [], mainAdvance: false },
      { num: 4, opens: [{ id: 'D' }], closes: [], mainAdvance: true },
      { num: 5, opens: [{ id: 'E' }], closes: [], mainAdvance: false },
      { num: 6, opens: [{ id: 'F' }], closes: [], mainAdvance: false },
    ],
  });
  assert.equal(report.blocking, true);
  assert.equal(report.netOpen, 6);
  assert.equal(report.mainAdvanceSteps, 1);
});

// avgCloseDelay 计算
ok('平均闭环延迟计算正确', () => {
  const { report } = computeLedger({
    window: 5,
    chapters: [
      { num: 1, opens: [{ id: 'A' }], closes: [], mainAdvance: true },
      { num: 4, opens: [], closes: ['A'], mainAdvance: true }, // 延迟 3
      { num: 2, opens: [{ id: 'B' }], closes: [], mainAdvance: true },
      { num: 3, opens: [], closes: ['B'], mainAdvance: true }, // 延迟 1
    ],
  });
  assert.equal(report.avgCloseDelay, 2); // (3+1)/2
});

// close 引用不存在 id → 错误
ok('close 引用不存在 id 报错', () => {
  const { errors, report } = computeLedger({
    window: 2,
    chapters: [{ num: 1, opens: [{ id: 'A' }], closes: ['ZZZ'], mainAdvance: true }],
  });
  assert.ok(errors.length > 0);
  assert.equal(report, null);
});

// close 引用未来章开的 id → 错误
ok('close 引用未来章 id 报错', () => {
  const { errors } = computeLedger({
    window: 3,
    chapters: [
      { num: 1, opens: [], closes: ['B'], mainAdvance: true },
      { num: 2, opens: [{ id: 'B' }], closes: [], mainAdvance: true },
    ],
  });
  assert.ok(errors.some((e) => /未来/.test(e)));
});

// 阈值可配：放宽 advance-floor 后不 blocking
ok('阈值可配', () => {
  const led = {
    window: 6,
    chapters: Array.from({ length: 6 }, (_, i) => ({
      num: i + 1, opens: [{ id: 'Q' + i }], closes: [], mainAdvance: i === 0,
    })),
  };
  assert.equal(computeLedger(led, {}).report.blocking, true);
  // advance-floor=0 → 下限 0，mainAdvanceSteps(1) < 0 为假 → 不 blocking
  assert.equal(computeLedger(led, { ADVANCE_FLOOR: 0 }).report.blocking, false);
});

// window 截断
ok('window 截断只算窗口内', () => {
  const { report } = computeLedger({
    chapters: [
      { num: 1, opens: [{ id: 'A' }], closes: [], mainAdvance: true },
      { num: 2, opens: [{ id: 'B' }], closes: [], mainAdvance: true },
      { num: 99, opens: [{ id: 'Z' }], closes: [], mainAdvance: true },
    ],
  }, { WINDOW: 2 });
  assert.equal(report.window, 2);
  assert.equal(report.openCount, 2); // Z 不计入
});

// CLI: blocking 退出码 1
ok('CLI blocking 退出码 1', () => {
  const f = tmp({ window: 3, chapters: [
    { num: 1, opens: [{ id: 'A' }], closes: [], mainAdvance: false },
    { num: 2, opens: [{ id: 'B' }], closes: [], mainAdvance: false },
    { num: 3, opens: [{ id: 'C' }], closes: [], mainAdvance: false },
  ] });
  assert.equal(run(f).code, 1);
});

// CLI: 健康退出码 0
ok('CLI 健康退出码 0', () => {
  const f = tmp({ window: 2, chapters: [
    { num: 1, opens: [{ id: 'A' }], closes: [], mainAdvance: true },
    { num: 2, opens: [], closes: ['A'], mainAdvance: true },
  ] });
  assert.equal(run(f).code, 0);
});

// CLI: 缺参数退出码 2
ok('CLI 缺参数退出码 2', () => {
  let code = 0;
  try { execFileSync('node', [SCRIPT], { encoding: 'utf8', stdio: 'pipe' }); }
  catch (e) { code = e.status; }
  assert.equal(code, 2);
});

// CLI: ledger 错误退出码 2
ok('CLI ledger 错误退出码 2', () => {
  const f = tmp({ chapters: [{ num: 1, opens: [], closes: ['X'], mainAdvance: true }] });
  assert.equal(run(f).code, 2);
});

// 示例 ledger 可算（AC1 fixture 自检）
ok('references/ledger-example.json 可计算', () => {
  const ex = path.join(__dirname, '..', 'references', 'ledger-example.json');
  if (!fs.existsSync(ex)) { console.log('    (跳过：示例文件未就绪)'); return; }
  const { errors, report } = computeLedger(JSON.parse(fs.readFileSync(ex, 'utf8')));
  assert.equal(errors.length, 0, '示例 ledger 不应有结构错误：' + errors.join('; '));
  assert.ok(report.window > 0);
});

console.log(`\n共通过 ${pass} 项。`);
if (process.exitCode) console.error('测试未全绿。');
else console.log('测试全绿。');
