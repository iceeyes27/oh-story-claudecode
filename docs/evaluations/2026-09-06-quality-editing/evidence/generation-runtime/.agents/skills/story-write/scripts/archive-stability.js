#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node archive-stability.js [--keep N] [--dry-run] [--dir <book-dir>]

长篇稳定性工件归档：把活跃窗口之外的稳定性文件从活跃目录移入 追踪/归档/，
防止门控/交接包按章累积（500 章 ≈ 1000 个文件）污染目录列表。

  追踪/漂移门控/第{N}章.md            → 追踪/归档/漂移门控/     （N 在窗口外）
  追踪/交接包/第{N}章_to_第{M}章.md   → 追踪/归档/交接包/       （M 在窗口外，
                                        保留窗口首章的入向交接包）
  追踪/稳定性审计/日更_第X章_to_第Y章.md → 追踪/归档/稳定性审计/ （Y 在窗口外）

--keep N    活跃窗口大小：保留最近 N 章的工件（默认 20，按 正文/ 最大章号倒推）
--dry-run   只报告会移动什么，不实际移动

移动不删除，逐文件保留可回查。归档对验收透明：stability-audit.js 和
handoff-pack.js 在活跃目录找不到文件时自动回退读 追踪/归档/ 对应位置，
老章节回炉复检无需先取回；回炉重写的新门控/交接包照常写入活跃目录，
同名文件以活跃目录为权威。触发时机与 SKILL.md「追踪文件归档」相同：
每完成 50 章或一卷结束时运行一次。`;

function die(msg) {
  process.stderr.write(`${msg}\n`);
  process.exit(2);
}

const options = { keep: 20, dryRun: false, dir: process.cwd() };

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--keep') {
    i += 1;
    options.keep = Number.parseInt(process.argv[i], 10);
    if (!Number.isInteger(options.keep) || options.keep < 1) die('--keep 必须是正整数');
  } else if (arg === '--dry-run') {
    options.dryRun = true;
  } else if (arg === '--dir') {
    i += 1;
    if (!process.argv[i]) die('--dir requires a value');
    options.dir = process.argv[i];
  } else if (arg === '--help' || arg === '-h') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else {
    die(`unknown option: ${arg}\n${USAGE}`);
  }
}

const BOOK = options.dir;
if (!fs.existsSync(BOOK) || !fs.statSync(BOOK).isDirectory()) die(`book dir not found: ${BOOK}`);

function listDir(dir) {
  try {
    return fs.readdirSync(dir).filter((f) => f.endsWith('.md'));
  } catch (err) {
    return [];
  }
}

// 最新章号：正文/第{N}章*.md 的最大 N（排除回炉备份）
function latestChapter() {
  let latest = 0;
  for (const f of listDir(path.join(BOOK, '正文'))) {
    if (f.includes('原稿')) continue;
    const m = f.match(/^第(\d+)章(_|\.md$)/);
    if (m) latest = Math.max(latest, Number.parseInt(m[1], 10));
  }
  return latest;
}

const latest = latestChapter();
if (latest === 0) {
  process.stdout.write('正文/ 无章节，无需归档。\n');
  process.exit(0);
}
const windowStart = Math.max(1, latest - options.keep + 1);

// 归档判定：文件名解析出的“最后被需要的章号”落在窗口外即归档
const plans = [
  {
    label: '漂移门控',
    activeDir: path.join(BOOK, '追踪', '漂移门控'),
    archiveDir: path.join(BOOK, '追踪', '归档', '漂移门控'),
    // 第{N}章.md：N < windowStart 归档
    lastNeeded: (f) => {
      const m = f.match(/^第(\d+)章\.md$/);
      return m ? Number.parseInt(m[1], 10) : null;
    },
  },
  {
    label: '交接包',
    activeDir: path.join(BOOK, '追踪', '交接包'),
    archiveDir: path.join(BOOK, '追踪', '归档', '交接包'),
    // 第{N}章_to_第{M}章.md：M 是消费方章号，M < windowStart 归档
    // （窗口首章的入向交接包保持活跃，供窗口内批量审计做交接继承检查）
    lastNeeded: (f) => {
      const m = f.match(/^第(\d+)章_to_第(\d+)章\.md$/);
      return m ? Number.parseInt(m[2], 10) : null;
    },
  },
  {
    label: '稳定性审计',
    activeDir: path.join(BOOK, '追踪', '稳定性审计'),
    archiveDir: path.join(BOOK, '追踪', '归档', '稳定性审计'),
    // 日更_第X章_to_第Y章.md：Y < windowStart 归档
    lastNeeded: (f) => {
      const m = f.match(/_第(\d+)章_to_第(\d+)章\.md$/);
      return m ? Number.parseInt(m[2], 10) : null;
    },
  },
];

let moved = 0;
let kept = 0;
const lines = [];

for (const plan of plans) {
  const candidates = [];
  for (const f of listDir(plan.activeDir).sort()) {
    const n = plan.lastNeeded(f);
    if (n === null) continue; // 不认识的文件名不动
    if (n < windowStart) candidates.push(f);
    else kept += 1;
  }
  for (const f of candidates) {
    const src = path.join(plan.activeDir, f);
    const dest = path.join(plan.archiveDir, f);
    if (options.dryRun) {
      lines.push(`[dry-run] ${plan.label}/${f} -> 追踪/归档/${plan.label}/${f}`);
    } else {
      fs.mkdirSync(plan.archiveDir, { recursive: true });
      // 归档里已有同名旧副本时以本次活跃版本覆盖（活跃目录是权威）
      if (fs.existsSync(dest)) fs.unlinkSync(dest);
      fs.renameSync(src, dest);
      lines.push(`ARCHIVED ${plan.label}/${f}`);
    }
    moved += 1;
  }
}

process.stdout.write(`最新章号：第 ${String(latest).padStart(3, '0')} 章；活跃窗口：第 ${String(windowStart).padStart(3, '0')} 章起（--keep ${options.keep}）\n`);
for (const l of lines) process.stdout.write(`${l}\n`);
process.stdout.write(`${options.dryRun ? '将移动' : '已移动'} ${moved} 个文件，窗口内保留 ${kept} 个。归档对 stability-audit.js / handoff-pack.js 透明（自动回退读取）。\n`);
