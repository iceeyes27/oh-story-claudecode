#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node stability-audit.js [--write] [--json] [--dir <book-dir>] <start-chapter> [end-chapter]

长篇稳定性验收（确定性检查，不做语义判断）。逐章验证：
  - 细纲「稳定性契约」存在且含 B# 必须交付 beat（Contract_Missing）
  - 每个 beat 的关键词组全部出现在正文（Beat_Missing）
  - 「不得提前透露」禁词未出现在正文（Foreshadow_Early_Payoff）
  - 漂移门控存在、Gate: PASS、覆盖全部 B#、含 State Delta
    （Gate_Missing / Gate_Failed / Gate_Incomplete / State_Not_Updated）
  - 角色不变量 POV 感知扫描：行为红线/禁知短语（Motivation_Drift / Knowledge_Leak）
相邻章验证：交接包存在、Gate 为 PASS、继承关键词在下一章正文命中
    （Handoff_Missing / Continuity_Missing）

--write 落盘报告到 追踪/稳定性审计/日更_第{start}章_to_第{end}章.md
--json  输出机器可读结果（status/failures/checks/error_codes）
退出码：全部 PASS 为 0，任一 FAIL 为 1。
语义审查（Plot_Drift/Canon_Conflict 等）由漂移门控的 LLM 审查承担，
本脚本只验证承诺已落盘、且落盘承诺与正文字面一致。
格式约定见 references/longform-stability.md。`;

function die(msg) {
  process.stderr.write(`${msg}\n`);
  process.exit(2);
}

const options = { write: false, json: false, dir: process.cwd(), chapters: [] };

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--write') {
    options.write = true;
  } else if (arg === '--json') {
    options.json = true;
  } else if (arg === '--dir') {
    i += 1;
    if (!process.argv[i]) die('--dir requires a value');
    options.dir = process.argv[i];
  } else if (arg === '--help' || arg === '-h') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('-')) {
    die(`unknown option: ${arg}\n${USAGE}`);
  } else {
    options.chapters.push(arg);
  }
}

if (options.chapters.length < 1 || options.chapters.length > 2) die(USAGE);
const startNum = Number.parseInt(options.chapters[0], 10);
const endNum = Number.parseInt(options.chapters[1] || options.chapters[0], 10);
if (!Number.isInteger(startNum) || !Number.isInteger(endNum) || startNum < 1) die('章节号必须是正整数');
if (startNum > endNum) die('start-chapter 必须 <= end-chapter');
if (!fs.existsSync(options.dir) || !fs.statSync(options.dir).isDirectory()) die(`book dir not found: ${options.dir}`);

const BOOK = options.dir;

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

// 正文定位：正文/第{NNN}章_*.md 或 第{NNN}章.md，排除回炉备份（*_原稿_*）
function findBody(n) {
  const dir = path.join(BOOK, '正文');
  if (!fs.existsSync(dir)) return null;
  const id = pad3(n);
  const hits = fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.md') && !f.includes('原稿'))
    .filter((f) => f === `第${id}章.md` || f.startsWith(`第${id}章_`))
    .sort();
  return hits.length > 0 ? path.join(dir, hits[0]) : null;
}

function outlinePath(n) {
  return path.join(BOOK, '大纲', `细纲_第${pad3(n)}章.md`);
}

function gatePath(n) {
  return path.join(BOOK, '追踪', '漂移门控', `第${pad3(n)}章.md`);
}

function packPath(prev, next) {
  return path.join(BOOK, '追踪', '交接包', `第${pad3(prev)}章_to_第${pad3(next)}章.md`);
}

// 归档透明回退：活跃目录找不到时读 追踪/归档/ 同名文件（archive-stability.js 移入），
// 活跃目录优先——回炉重写的新门控/交接包写在活跃目录，覆盖归档里的旧版本
function readGate(n) {
  const active = readSafe(gatePath(n));
  if (active !== null) return active;
  return readSafe(path.join(BOOK, '追踪', '归档', '漂移门控', `第${pad3(n)}章.md`));
}

function readPack(prev, next) {
  const active = readSafe(packPath(prev, next));
  if (active !== null) return active;
  return readSafe(path.join(BOOK, '追踪', '归档', '交接包', `第${pad3(prev)}章_to_第${pad3(next)}章.md`));
}

// 从 markdown 中截取某标题起、到同级或更高级标题止的小节
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
  return out.join('\n');
}

// 顿号/逗号分隔的关键词，过滤模板占位符
function splitTerms(value) {
  return String(value || '')
    .split(/[、，,;；]/)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2 && !/[{}]/.test(t) && !/^(无|待补充|暂无|示例)$/.test(t));
}

// 细纲稳定性契约：beats [{id, keywords}] + 禁词 forbidden[]
function parseContract(outlineText) {
  const section = extractSection(outlineText, /^稳定性契约/);
  if (section === null) return null;
  const beats = [];
  const forbidden = [];
  for (const line of section.split(/\r?\n/)) {
    const beatMatch = line.match(/^\|\s*(B\d+)\s*\|/);
    if (beatMatch) {
      const cells = line.split('|').map((c) => c.trim());
      // cells: ['', 'B1', 情节点, 功能, 关键词组, '']
      beats.push({ id: beatMatch[1], keywords: splitTerms(cells[4]) });
      continue;
    }
    const forbidMatch = line.match(/不得提前透露[：:]\s*(.+)$/);
    if (forbidMatch) forbidden.push(...splitTerms(forbidMatch[1]));
  }
  return { beats, forbidden };
}

// POV 感知扫描视野：POV 标记前的公共叙述所有角色可见；
// `POV：名` / `视角：名` 之后的段落只计入该角色视野
function buildScanViews(bodyText) {
  const lines = bodyText.split(/\r?\n/);
  const publicLines = [];
  const povLines = new Map();
  let current = null;
  for (const line of lines) {
    const stripped = line.replace(/^[\s#>*-]+/, '');
    const m = stripped.match(/^(POV|视角)\s*[：:]\s*(\S+)/);
    if (m) {
      current = m[2].replace(/[#].*$/, '').trim();
      if (!povLines.has(current)) povLines.set(current, []);
      continue;
    }
    if (current === null) publicLines.push(line);
    else povLines.get(current).push(line);
  }
  return { publicText: publicLines.join('\n'), povLines };
}

function viewFor(views, name) {
  const own = views.povLines.get(name);
  return own ? `${views.publicText}\n${own.join('\n')}` : views.publicText;
}

// 角色不变量：{name, redlines[], forbiddenKnowledge[]}
function parseInvariant(file) {
  const text = readSafe(file);
  if (text === null) return null;
  const name = path.basename(file, '.md');
  const redlines = [];
  const forbiddenKnowledge = [];
  let section = '';
  for (const line of text.split(/\r?\n/)) {
    const heading = line.match(/^#{2,5}\s*(.+)$/);
    if (heading) {
      if (/^行为红线/.test(heading[1])) section = 'redline';
      else if (/^认知边界/.test(heading[1])) section = 'knowledge';
      else section = '';
      continue;
    }
    if (section === 'knowledge') {
      const m = line.match(/不能提前知道[：:]\s*(.+)$/);
      if (m) forbiddenKnowledge.push(...splitTerms(m[1]));
    } else if (section === 'redline') {
      const m = line.match(/^\s*-?\s*不会[：:]\s*(.+)$/);
      if (m) redlines.push(...splitTerms(m[1]));
    }
  }
  return { name, redlines, forbiddenKnowledge };
}

function listInvariants() {
  const dir = path.join(BOOK, '设定', '角色不变量');
  if (!fs.existsSync(dir)) return null;
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith('.md'))
    .sort()
    .map((f) => parseInvariant(path.join(dir, f)))
    .filter(Boolean);
}

const checks = [];

function addCheck(scope, check, problems) {
  const result = problems.length === 0 ? 'PASS' : 'FAIL';
  const codes = [...new Set(problems.map((p) => p.code))];
  checks.push({ scope, check, result, codes, diagnostics: problems.map((p) => p.message) });
  return result === 'PASS';
}

const invariants = listInvariants();

for (let n = startNum; n <= endNum; n += 1) {
  const scope = `第 ${pad3(n)} 章`;
  const bodyFile = findBody(n);
  const bodyText = bodyFile ? readSafe(bodyFile) : null;

  if (bodyText === null) {
    addCheck(scope, '正文', [{ code: 'Body_Missing', message: `正文缺失：正文/第${pad3(n)}章_*.md` }]);
    continue;
  }
  addCheck(scope, '正文', []);

  // 契约（细纲稳定性小节）
  const outlineText = readSafe(outlinePath(n));
  let contract = null;
  const contractProblems = [];
  if (outlineText === null) {
    contractProblems.push({ code: 'Contract_Missing', message: `细纲缺失：大纲/细纲_第${pad3(n)}章.md` });
  } else {
    contract = parseContract(outlineText);
    if (contract === null) {
      contractProblems.push({ code: 'Contract_Missing', message: '细纲缺「稳定性契约」小节（模板见 references/longform-stability.md）' });
    } else if (contract.beats.length === 0) {
      contractProblems.push({ code: 'Contract_Missing', message: '稳定性契约没有 B# 必须交付 beat' });
    } else {
      for (const beat of contract.beats) {
        if (beat.keywords.length === 0) {
          contractProblems.push({ code: 'Beat_Missing', message: `${beat.id} 缺可验证的关键词组（2-4 个具体词，顿号分隔）` });
          continue;
        }
        const missing = beat.keywords.filter((kw) => !bodyText.includes(kw));
        if (missing.length > 0) {
          contractProblems.push({ code: 'Beat_Missing', message: `${beat.id} 关键词未在正文出现：${missing.join('、')}` });
        }
      }
      for (const term of contract.forbidden) {
        if (bodyText.includes(term)) {
          contractProblems.push({ code: 'Foreshadow_Early_Payoff', message: `禁词提前出现在正文：${term}` });
        }
      }
    }
  }
  addCheck(scope, '契约与 beat 交付', contractProblems);

  // 漂移门控
  const gateText = readGate(n);
  const gateProblems = [];
  if (gateText === null) {
    gateProblems.push({ code: 'Gate_Missing', message: `漂移门控缺失：追踪/漂移门控/第${pad3(n)}章.md（追踪/归档/ 下也无）` });
  } else {
    if (!/Gate[：:]\s*PASS/.test(gateText)) {
      gateProblems.push({ code: 'Gate_Failed', message: '漂移门控结论不是 Gate: PASS，先修复再验收' });
    }
    if (!/State Delta/.test(gateText)) {
      gateProblems.push({ code: 'State_Not_Updated', message: '漂移门控缺 State Delta 小节（本章改变了什么）' });
    }
    if (contract) {
      for (const beat of contract.beats) {
        if (!new RegExp(`${beat.id}(?![0-9])`).test(gateText)) {
          gateProblems.push({ code: 'Gate_Incomplete', message: `漂移门控未覆盖 ${beat.id}（Beat 核对必须逐个列出）` });
        }
      }
    }
  }
  addCheck(scope, '漂移门控', gateProblems);

  // 角色不变量 POV 感知扫描
  const invariantProblems = [];
  if (invariants === null || invariants.length === 0) {
    invariantProblems.push({ code: 'Invariants_Missing', message: '设定/角色不变量/ 缺失或为空（启用稳定性验收后至少为主角建一份，见 references/character-invariants.md）' });
  } else {
    const views = buildScanViews(bodyText);
    for (const inv of invariants) {
      const view = viewFor(views, inv.name);
      for (const term of inv.forbiddenKnowledge) {
        if (view.includes(term)) {
          invariantProblems.push({ code: 'Knowledge_Leak', message: `${inv.name} 视野内出现禁知短语：${term}` });
        }
      }
      for (const term of inv.redlines) {
        if (view.includes(term)) {
          invariantProblems.push({ code: 'Motivation_Drift', message: `${inv.name} 视野内出现行为红线短语：${term}` });
        }
      }
    }
  }
  addCheck(scope, '角色不变量', invariantProblems);

  // 跨章交接继承（批量时对相邻对检查）
  if (n > startNum) {
    const pairScope = `第 ${pad3(n - 1)} 章 -> 第 ${pad3(n)} 章`;
    const packText = readPack(n - 1, n);
    const packProblems = [];
    if (packText === null) {
      packProblems.push({ code: 'Handoff_Missing', message: `交接包缺失：追踪/交接包/第${pad3(n - 1)}章_to_第${pad3(n)}章.md（追踪/归档/ 下也无；node scripts/handoff-pack.js --write ${n - 1}）` });
    } else {
      if (!/Gate[：:]\s*PASS/.test(packText)) {
        packProblems.push({ code: 'Gate_Failed', message: '交接包的源章节 Gate 不是 PASS，失败章节不得交接' });
      }
      const inheritLine = packText.match(/继承关键词[：:]\s*(.+)/);
      const terms = inheritLine ? splitTerms(inheritLine[1]) : [];
      if (terms.length === 0) {
        packProblems.push({ code: 'Continuity_Missing', message: '交接包缺「继承关键词」行（来源：上一章漂移门控）' });
      } else {
        const missing = terms.filter((t) => !bodyText.includes(t));
        if (missing.length > 0) {
          packProblems.push({ code: 'Continuity_Missing', message: `继承关键词未在本章正文出现：${missing.join('、')}` });
        }
      }
    }
    addCheck(pairScope, '跨章交接继承', packProblems);
  }
}

const failures = checks.filter((c) => c.result === 'FAIL').length;
const status = failures === 0 ? 'PASS' : 'FAIL';

function buildReport() {
  const lines = [];
  lines.push('## Longform Stability Audit');
  lines.push('');
  lines.push(`- 章节范围：第 ${pad3(startNum)} 章 - 第 ${pad3(endNum)} 章`);
  lines.push('');
  lines.push('### Checks');
  lines.push('| scope | check | result | error_codes |');
  lines.push('|---|---|---|---|');
  for (const c of checks) {
    lines.push(`| ${c.scope} | ${c.check} | ${c.result} | ${c.codes.join(', ')} |`);
  }
  lines.push('');
  lines.push('### 结论');
  lines.push(`- Audit: ${status}`);
  if (failures > 0) {
    lines.push(`- failures: ${failures}`);
    lines.push('');
    lines.push('### Diagnostics');
    for (const c of checks) {
      if (c.result !== 'FAIL') continue;
      lines.push('');
      lines.push(`#### ${c.scope} | ${c.check}`);
      for (const d of c.diagnostics) lines.push(`- ${d}`);
    }
    lines.push('');
    lines.push('修复分派与闭环见 references/longform-stability.md「修复分派与闭环」。');
  }
  lines.push('');
  return lines.join('\n');
}

let reportRelPath = null;
if (options.write) {
  const outDir = path.join(BOOK, '追踪', '稳定性审计');
  fs.mkdirSync(outDir, { recursive: true });
  reportRelPath = path.join('追踪', '稳定性审计', `日更_第${pad3(startNum)}章_to_第${pad3(endNum)}章.md`);
  fs.writeFileSync(path.join(BOOK, reportRelPath), buildReport(), 'utf8');
}

if (options.json) {
  process.stdout.write(`${JSON.stringify({
    status,
    failures,
    start_chapter: pad3(startNum),
    end_chapter: pad3(endNum),
    report_path: reportRelPath ? reportRelPath.split(path.sep).join('/') : null,
    checks: checks.map((c) => ({
      scope: c.scope,
      check: c.check,
      result: c.result,
      error_codes: c.codes,
      diagnostics: c.diagnostics,
    })),
  }, null, 2)}\n`);
} else {
  process.stdout.write(buildReport());
  if (reportRelPath) process.stdout.write(`WROTE: ${reportRelPath.split(path.sep).join('/')}\n`);
}

process.exit(failures === 0 ? 0 : 1);
