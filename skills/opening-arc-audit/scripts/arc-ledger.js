#!/usr/bin/env node
/**
 * arc-ledger.js — 开篇连读悬念收支表 + 故弄玄虚阈值裁决（确定性层）
 *
 * 读者是连着看十几章弃书的。现有检查全是逐章/相邻章，测不出「累计悬念只开不闭、
 * 主线原地打转」这个累积量——那正是「故弄玄虚」的本质。本脚本吃语义连读层产出的
 * ledger（每章 开了哪些悬念/闭了哪些/是否推进主线），做确定性累计与阈值裁决。
 *
 * 分工：悬念开/闭、主线推进/打转是语义判断（连读子代理产 ledger）；累计计算与阈值
 * 裁决是确定性的（本脚本），可回归测试。
 *
 * 用法:
 *   node arc-ledger.js <ledger.json> [--json] [--window=15] [--net-ratio=1] [--advance-floor=0.333]
 *
 * 退出码：0 无 blocking / 1 arc 级故弄玄虚 blocking / 2 ledger 错误或参数错误
 */
'use strict';
const fs = require('fs');

const DEFAULTS = { WINDOW: 15, NET_RATIO: 1, ADVANCE_FLOOR: 1 / 3 };

/**
 * 核心：吃 ledger 对象，返回 { report, errors }。纯函数，供测试直接调用。
 */
function computeLedger(ledger, opts = {}) {
  const errors = [];
  if (!ledger || !Array.isArray(ledger.chapters)) {
    return { errors: ['ledger 缺少 chapters 数组'], report: null };
  }
  const WINDOW = opts.WINDOW ?? ledger.window ?? DEFAULTS.WINDOW;
  const NET_RATIO = opts.NET_RATIO ?? DEFAULTS.NET_RATIO;
  const ADVANCE_FLOOR = opts.ADVANCE_FLOOR ?? DEFAULTS.ADVANCE_FLOOR;

  const chapters = [...ledger.chapters].sort((a, b) => a.num - b.num).filter((c) => c.num <= WINDOW);
  const window = Math.min(WINDOW, chapters.length);

  // 登记所有 open：id -> 开启章
  const openAt = new Map();
  const openQ = new Map();
  for (const ch of chapters) {
    for (const o of ch.opens || []) {
      if (openAt.has(o.id)) errors.push(`第${ch.num}章：open id「${o.id}」重复`);
      openAt.set(o.id, ch.num);
      openQ.set(o.id, o.q || o.id);
    }
  }

  // 处理 close，校验引用合法性，算延迟
  const closedIds = new Set();
  let delaySum = 0;
  let closeCount = 0;
  for (const ch of chapters) {
    for (const cid of ch.closes || []) {
      if (!openAt.has(cid)) { errors.push(`第${ch.num}章：close 引用不存在的 open id「${cid}」`); continue; }
      if (openAt.get(cid) > ch.num) { errors.push(`第${ch.num}章：close 引用了未来第${openAt.get(cid)}章才开的「${cid}」`); continue; }
      if (closedIds.has(cid)) { errors.push(`第${ch.num}章：「${cid}」被重复 close`); continue; }
      closedIds.add(cid);
      delaySum += ch.num - openAt.get(cid);
      closeCount++;
    }
  }
  if (errors.length) return { errors, report: null };

  const openCount = openAt.size;
  const netOpen = openCount - closeCount;
  const avgCloseDelay = closeCount ? +(delaySum / closeCount).toFixed(2) : null;
  const mainAdvanceSteps = chapters.filter((c) => c.mainAdvance === true).length;
  const advanceFloor = Math.ceil(window * ADVANCE_FLOOR);

  // 裁决：净悬空 > 已闭环 且 主线推进步数 < 下限 → 故弄玄虚
  const blocking = netOpen > closeCount * NET_RATIO && mainAdvanceSteps < advanceFloor;

  const known = [...closedIds].map((id) => openQ.get(id));
  const pending = [...openAt.keys()].filter((id) => !closedIds.has(id)).map((id) => openQ.get(id));

  return {
    errors: [],
    report: {
      book: ledger.book || '(未命名)',
      window, openCount, closeCount, netOpen, avgCloseDelay,
      mainAdvanceSteps, advanceFloor, blocking,
      known, pending,
    },
  };
}

function renderText(r) {
  const L = [];
  L.push(`开篇连读体检 · 《${r.book}》前 ${r.window} 章`);
  L.push('—'.repeat(60));
  L.push(`悬念开环累计   : ${r.openCount}`);
  L.push(`悬念闭环累计   : ${r.closeCount}`);
  L.push(`净悬空         : ${r.netOpen}`);
  L.push(`平均闭环延迟   : ${r.avgCloseDelay == null ? '—（无闭环）' : r.avgCloseDelay + ' 章'}`);
  L.push(`主线推进步数   : ${r.mainAdvanceSteps} / ${r.window}（打转判定下限 ${r.advanceFloor}）`);
  L.push('—'.repeat(60));
  L.push(`读者到第 ${r.window} 章已掌握（闭环）：`);
  L.push(r.known.length ? r.known.map((q) => `  ✓ ${q}`).join('\n') : '  （无）');
  L.push(`仍悬而未决（净悬空）：`);
  L.push(r.pending.length ? r.pending.map((q) => `  ? ${q}`).join('\n') : '  （无）');
  L.push('—'.repeat(60));
  if (r.blocking) {
    L.push(`[blocking] arc 级故弄玄虚：净悬空(${r.netOpen}) > 已闭环(${r.closeCount}) 且 主线推进(${r.mainAdvanceSteps}) < 下限(${r.advanceFloor})。`);
    L.push(`           读者连读到第 ${r.window} 章，悬念越攒越多、主线基本没动——这是「看了十几章看不下去」的量化信号。`);
    L.push(`           修法方向：闭掉几个早开的环 / 让主线目标发生可指认的推进，别只加铺垫。`);
  } else {
    L.push(`[ok] 开篇悬念收支与主线推进未触发故弄玄虚阈值（信号，非「一定好看」）。`);
  }
  return L.join('\n');
}

function main() {
  const args = process.argv.slice(2);
  let file = null;
  let jsonMode = false;
  const opts = {};
  for (const a of args) {
    if (a === '--json') jsonMode = true;
    else if (a.startsWith('--window=')) opts.WINDOW = parseInt(a.slice(9), 10);
    else if (a.startsWith('--net-ratio=')) opts.NET_RATIO = parseFloat(a.slice(12));
    else if (a.startsWith('--advance-floor=')) opts.ADVANCE_FLOOR = parseFloat(a.slice(16));
    else if (!a.startsWith('--')) file = a;
  }
  if (!file) {
    console.error('用法: node arc-ledger.js <ledger.json> [--json] [--window=15] [--net-ratio=1] [--advance-floor=0.333]');
    process.exit(2);
  }
  let ledger;
  try { ledger = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) { console.error(`读取/解析 ledger 失败：${e.message}`); process.exit(2); }

  const { errors, report } = computeLedger(ledger, opts);
  if (errors.length) {
    console.error('ledger 错误（语义层填表有误，先修 ledger）：');
    for (const e of errors) console.error('  - ' + e);
    process.exit(2);
  }
  if (jsonMode) console.log(JSON.stringify(report, null, 2));
  else console.log(renderText(report));
  process.exit(report.blocking ? 1 : 0);
}

module.exports = { computeLedger, renderText };

if (require.main === module) main();
