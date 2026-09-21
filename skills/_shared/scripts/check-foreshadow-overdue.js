#!/usr/bin/env node
/**
 * check-foreshadow-overdue.js — 伏笔逾期 / 悬空 / 冷藏告警（确定性层）
 *
 * `_tracking-state.json` 保证「不自相矛盾」（人物状态、时间线、读者认知边界都有程序兜底），
 * 但不保证「不烂尾」：伏笔 status 里有「已过期」这个取值，却没有任何东西提醒作者
 * 某条伏笔已经埋了很久还没回收。本脚本补的就是这个缺口。
 *
 * 三类发现：
 *   1. 逾期（blocking）——写了 planned_resolution_chapter，正文已经写过那一章，伏笔仍是「已埋」。
 *      这是明确违约：作者自己定了回收章，然后错过了。
 *   2. 悬空（advisory）——没写 planned_resolution_chapter，且埋下至今超过该重要度的阈值。
 *      不是错误，是提醒：要么排回收章，要么显式标「放弃」。
 *   3. 冷藏（advisory）——已经掉出 `追踪/上下文.md` 的活跃伏笔热卡（该卡按重要度只放前 8 条），
 *      且埋下已久。续写时模型看不见这条，全靠作者自己记得——最容易烂尾的一类。
 *
 * 分工：伏笔埋没埋、收没收是语义判断（写作时的追踪事务负责登记）；「埋了多久、还在不在
 * 模型眼前、有没有错过自己定的回收章」是确定性的（本脚本），可回归测试。
 *
 * 用法:
 *   node check-foreshadow-overdue.js --project <书目录> [--json] [--strict]
 *                                    [--high=30] [--mid=60] [--low=100] [--cold-after=20]
 *   node check-foreshadow-overdue.js --state <_tracking-state.json 路径> [...]
 *
 * 退出码：0 无 blocking / 1 存在逾期伏笔（--strict 时悬空、冷藏同样 blocking）/ 2 状态文件或参数错误
 */
'use strict';
const fs = require('fs');
const path = require('path');

// 与 tracking_commit.py 的 FORESHADOW_IMPORTANCE / active_foreshadow_lines 保持一致。
// 这两个常量是热卡渲染的唯一依据，改动必须两边同步，否则「冷藏」判定会失真。
const IMPORTANCE_ORDER = ['高', '中', '低'];
const HOT_CARD_SIZE = 8;
const ACTIVE_STATUS = '已埋';

const DEFAULTS = { high: 30, mid: 60, low: 100, coldAfter: 20 };

function danglingThreshold(importance, opts) {
  if (importance === '高') return opts.high;
  if (importance === '中') return opts.mid;
  return opts.low;
}

/**
 * 复刻 tracking_commit.py:active_foreshadow_lines 的排序与截断，得出哪些伏笔还在热卡里。
 * Python 侧 key 为 (重要度序, planned_resolution_chapter or 10**12, id)——`or` 让 null 排到最后，
 * 同重要度内旧伏笔（id 小）优先，这里逐条对齐。
 */
function hotCardIds(rows) {
  const active = rows.filter((row) => row.status === ACTIVE_STATUS);
  const sorted = [...active].sort((a, b) => {
    const ra = IMPORTANCE_ORDER.indexOf(a.importance);
    const rb = IMPORTANCE_ORDER.indexOf(b.importance);
    if (ra !== rb) return ra - rb;
    const pa = a.planned_resolution_chapter || 1e12;
    const pb = b.planned_resolution_chapter || 1e12;
    if (pa !== pb) return pa - pb;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
  return new Set(sorted.slice(0, HOT_CARD_SIZE).map((row) => row.id));
}

/**
 * 核心：吃 state 对象，返回 { report, errors }。纯函数，供测试直接调用。
 */
function computeOverdue(state, options = {}) {
  const errors = [];
  const opts = {
    high: options.high ?? DEFAULTS.high,
    mid: options.mid ?? DEFAULTS.mid,
    low: options.low ?? DEFAULTS.low,
    coldAfter: options.coldAfter ?? DEFAULTS.coldAfter,
    strict: options.strict ?? false,
  };
  for (const key of ['high', 'mid', 'low', 'coldAfter']) {
    if (!Number.isInteger(opts[key]) || opts[key] < 0) errors.push(`阈值 ${key} 必须是非负整数`);
  }
  if (!state || typeof state !== 'object' || Array.isArray(state)) {
    return { errors: ['state 不是对象'], report: null };
  }
  if (state.schema_version !== 4) {
    return { errors: [`_tracking-state.json 不是当前 schema_version=4（实际 ${state.schema_version}）`], report: null };
  }
  const lastChapter = state.last_committed_chapter;
  if (!Number.isInteger(lastChapter)) {
    return { errors: ['state 缺少整数 last_committed_chapter'], report: null };
  }
  if (!state.foreshadow || typeof state.foreshadow !== 'object' || Array.isArray(state.foreshadow)) {
    return { errors: ['state 缺少 foreshadow 对象'], report: null };
  }

  const rows = [];
  for (const [id, raw] of Object.entries(state.foreshadow)) {
    if (!raw || typeof raw !== 'object') { errors.push(`伏笔 ${id} 不是对象`); continue; }
    if (!Number.isInteger(raw.planted_chapter)) { errors.push(`伏笔 ${id} 缺少整数 planted_chapter`); continue; }
    if (!IMPORTANCE_ORDER.includes(raw.importance)) { errors.push(`伏笔 ${id} 的 importance「${raw.importance}」不在 ${IMPORTANCE_ORDER.join('/')} 内`); continue; }
    const planned = raw.planned_resolution_chapter;
    if (planned !== null && planned !== undefined && !Number.isInteger(planned)) {
      errors.push(`伏笔 ${id} 的 planned_resolution_chapter 既不是 null 也不是整数`);
      continue;
    }
    rows.push({
      id,
      summary: String(raw.summary ?? ''),
      status: String(raw.status ?? ''),
      importance: raw.importance,
      planted_chapter: raw.planted_chapter,
      planned_resolution_chapter: planned ?? null,
    });
  }
  if (errors.length) return { errors, report: null };

  const hot = hotCardIds(rows);
  const active = rows.filter((row) => row.status === ACTIVE_STATUS);
  const findings = [];

  for (const row of active) {
    const age = lastChapter - row.planted_chapter;
    const inHotCard = hot.has(row.id);
    const base = {
      id: row.id,
      summary: row.summary,
      importance: row.importance,
      planted_chapter: row.planted_chapter,
      planned_resolution_chapter: row.planned_resolution_chapter,
      age,
      in_hot_card: inHotCard,
    };
    if (row.planned_resolution_chapter !== null && lastChapter > row.planned_resolution_chapter) {
      findings.push({
        ...base,
        rule: '逾期',
        blocking: true,
        overdue_by: lastChapter - row.planned_resolution_chapter,
        detail: `计划第 ${row.planned_resolution_chapter} 章回收，正文已写到第 ${lastChapter} 章，仍是「已埋」`,
      });
    } else if (row.planned_resolution_chapter === null) {
      const threshold = danglingThreshold(row.importance, opts);
      if (age > threshold) {
        findings.push({
          ...base,
          rule: '悬空',
          blocking: opts.strict,
          threshold,
          detail: `埋于第 ${row.planted_chapter} 章、已过 ${age} 章仍未排回收章（${row.importance}·阈值 ${threshold}）`,
        });
      }
    }
    if (!inHotCard && age > opts.coldAfter) {
      findings.push({
        ...base,
        rule: '冷藏',
        blocking: opts.strict,
        threshold: opts.coldAfter,
        detail: `已掉出续写热卡（只放前 ${HOT_CARD_SIZE} 条）、埋后已过 ${age} 章——续写时模型看不见这条`,
      });
    }
  }

  const order = { 逾期: 0, 悬空: 1, 冷藏: 2 };
  findings.sort((a, b) => (order[a.rule] - order[b.rule]) || (b.age - a.age) || (a.id < b.id ? -1 : 1));

  const report = {
    book: String(state.book_title ?? ''),
    last_committed_chapter: lastChapter,
    thresholds: { 高: opts.high, 中: opts.mid, 低: opts.low, 冷藏: opts.coldAfter },
    strict: opts.strict,
    total_foreshadow: rows.length,
    active_count: active.length,
    hot_card_ids: [...hot],
    cold_count: active.filter((row) => !hot.has(row.id)).length,
    findings,
    counts: {
      逾期: findings.filter((f) => f.rule === '逾期').length,
      悬空: findings.filter((f) => f.rule === '悬空').length,
      冷藏: findings.filter((f) => f.rule === '冷藏').length,
    },
    blocking: findings.some((f) => f.blocking),
  };
  return { errors: [], report };
}

function renderText(r) {
  const L = [];
  L.push(`伏笔回收体检 · 《${r.book}》截至第 ${r.last_committed_chapter} 章`);
  L.push('—'.repeat(60));
  L.push(`伏笔总数       : ${r.total_foreshadow}`);
  L.push(`仍「已埋」     : ${r.active_count}`);
  L.push(`已掉出热卡     : ${r.cold_count} / ${r.active_count}（热卡只放前 ${HOT_CARD_SIZE} 条）`);
  L.push(`阈值           : 高 ${r.thresholds.高} / 中 ${r.thresholds.中} / 低 ${r.thresholds.低} 章，冷藏 ${r.thresholds.冷藏} 章`);
  L.push('—'.repeat(60));
  if (!r.findings.length) {
    L.push('[ok] 没有逾期、悬空或长期冷藏的伏笔（信号，非「伏笔设计得好」）。');
    return L.join('\n');
  }
  const mark = { 逾期: '✗', 悬空: '?', 冷藏: '·' };
  let current = null;
  for (const f of r.findings) {
    if (f.rule !== current) {
      current = f.rule;
      const n = r.counts[f.rule];
      const tag = f.rule === '逾期' ? '[blocking]' : r.strict ? '[blocking]' : '[advisory]';
      L.push(`${tag} ${f.rule}（${n} 条）`);
    }
    L.push(`  ${mark[f.rule]} ${f.id}｜${f.importance}｜${f.summary}`);
    L.push(`      ${f.detail}`);
  }
  L.push('—'.repeat(60));
  if (r.counts.逾期) {
    L.push(`逾期是明确违约：你自己定了回收章然后错过了。要么在本卷内回收，要么改 planned_resolution_chapter，`);
    L.push(`要么提交事务把 status 改成「放弃」/「已过期」——别让它一直挂在「已埋」。`);
  }
  if (r.counts.冷藏) {
    L.push(`冷藏的伏笔不在 追踪/上下文.md 里，续写时模型完全看不见。抬重要度、排回收章，或显式放弃。`);
  }
  L.push(`本脚本只报账，不改追踪状态；伏笔状态变更一律走 tracking_commit.py 事务。`);
  return L.join('\n');
}

function main() {
  const args = process.argv.slice(2);
  let project = null;
  let statePath = null;
  let jsonMode = false;
  const opts = {};
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === '--json') jsonMode = true;
    else if (a === '--strict') opts.strict = true;
    else if (a === '--project') project = args[++i];
    else if (a.startsWith('--project=')) project = a.slice(10);
    else if (a === '--state') statePath = args[++i];
    else if (a.startsWith('--state=')) statePath = a.slice(8);
    else if (a.startsWith('--high=')) opts.high = parseInt(a.slice(7), 10);
    else if (a.startsWith('--mid=')) opts.mid = parseInt(a.slice(6), 10);
    else if (a.startsWith('--low=')) opts.low = parseInt(a.slice(6), 10);
    else if (a.startsWith('--cold-after=')) opts.coldAfter = parseInt(a.slice(13), 10);
    else { console.error(`未知参数：${a}`); process.exit(2); }
  }
  if (!project && !statePath) {
    console.error('用法: node check-foreshadow-overdue.js --project <书目录> [--json] [--strict] [--high=30] [--mid=60] [--low=100] [--cold-after=20]');
    process.exit(2);
  }
  const target = statePath || path.join(project, '追踪', '_tracking-state.json');
  let state;
  try { state = JSON.parse(fs.readFileSync(target, 'utf8')); }
  catch (e) { console.error(`读取/解析 ${target} 失败：${e.message}`); process.exit(2); }

  const { errors, report } = computeOverdue(state, opts);
  if (errors.length) {
    console.error('追踪状态错误（先修 _tracking-state.json，不要手改派生视图）：');
    for (const e of errors) console.error('  - ' + e);
    process.exit(2);
  }
  if (jsonMode) console.log(JSON.stringify(report, null, 2));
  else console.log(renderText(report));
  process.exit(report.blocking ? 1 : 0);
}

module.exports = { computeOverdue, hotCardIds, renderText, main, HOT_CARD_SIZE, DEFAULTS };

if (require.main === module) main();
