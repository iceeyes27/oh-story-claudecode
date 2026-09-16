#!/usr/bin/env node
/**
 * check-setting-payoff.js — 设定兑现（setting-payoff/v1）确定性检查器
 *
 * 规则权威：story-write/references/setting-payoff.md。本脚本只管三层里"机械可判定"的部分：
 *   设定/_设定登记.md（编号唯一分配处）→ 大纲/细纲_第N章_*.md「#### 设定兑现」（排期）
 * 已发生的兑现记账在 _tracking-state.json.setting_payoffs（tracking_commit.py），候选举证在
 * candidate-commit.py；本脚本不碰追踪状态，只读它判断"是否启用 / 自第几章起"。
 *
 * 判什么：登记表格式（编号唯一、类型合法、来源文件与标题存在、锚点能在来源里找到、
 * recurring 有窗口）、细纲小节格式（编号存在、关系合法、不适用带原因）、排期一致性
 * （payoff 目标章有没有被某章排入、reserve 有没有被提前排入）、具名实体零落点（advisory）。
 *
 * 判不了什么：兑现物是不是真的兑现了、写手有没有写成说明书、约束有没有被违反——
 * 这些由候选举证的复核签名与 story-review 负责，脚本不从任何原句推断语义。
 *
 * 用法:
 *   node check-setting-payoff.js <书目录> [--json] [--strict] [--chapter N] [--readiness] [--migrate]
 *   --chapter N   附带输出第 N 章细纲的设定兑现行与每条设定的规则摘录（给 candidate-commit /
 *                 build_writer_prompt 消费）
 *   --strict      零落点与到期未排从 advisory 升 blocking
 *   --migrate     把 v1 的 追踪/设定兑现看板.md + 细纲「## 设定兑现槽」迁移成登记表与
 *                 「#### 设定兑现」小节；看板改名 设定兑现看板_已退役.md。登记表已存在时拒绝
 *
 * 适用判定：有 设定/_设定登记.md → 检查；只有 v1 看板 → advisory 提示迁移；两者皆无 → 不适用
 * （exit 0）。追踪状态已启用记账却没有登记表 → blocking。
 *
 * 退出码：0 无 blocking / 1 有 blocking / 2 参数或读取错误
 */
'use strict';
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { checkReadiness } = require('./setting-readiness.js');

const ID_RE = /SET-\d{2,3}[A-Z]?/;
const ID_RE_G = /SET-\d{2,3}[A-Z]?/g;
const TYPES = new Set(['payoff', 'constraint', 'recurring', 'reserve', 'retired']);
const RELATIONS = new Set(['兑现', '涉及', '不适用']);
const REGISTRY_REL = path.join('设定', '_设定登记.md');
const BOARD_REL = path.join('追踪', '设定兑现看板.md');
const BOARD_RETIRED_REL = path.join('追踪', '设定兑现看板_已退役.md');
const EXEMPT_REL = path.join('设定', '_兑现豁免.txt');
const STATE_REL = path.join('追踪', '_tracking-state.json');
const EMPTY_CELL = /^(?:—|-|无|N\/A|\[待补充\])?$/;

// ---------- 读取 ----------
function readIf(p) {
  try { return fs.readFileSync(p, 'utf8'); } catch { return null; }
}
function listDir(dir) {
  try { return fs.readdirSync(dir); } catch { return []; }
}
function sha256(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
}
function cellsOf(line) {
  return line.split('|').slice(1, -1).map((s) => s.trim());
}
function isTableLine(line) {
  return line.trim().startsWith('|');
}
function isSeparator(cells) {
  return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}
function stripMark(s) {
  return (s || '').replace(/\*\*/g, '').replace(/^`|`$/g, '').trim();
}
function normalizeAnchor(s) {
  const t = stripMark(s);
  return EMPTY_CELL.test(t) ? '' : t;
}
function normHeader(s) {
  return stripMark(s).replace(/\s+/g, '');
}

// ---------- 登记表 ----------
// 表头按列名定位，不按位置：作者调换列序或加列不应让整张表失效。
const HEADER_KEYS = [
  ['id', (h) => h === '编号'],
  ['type', (h) => h === '类型'],
  ['source', (h) => h === '来源'],
  ['title', (h) => h === '一句话' || h === '名称'],
  ['trigger', (h) => /触发|窗口/.test(h)],
  ['goal', (h) => /目标/.test(h)],
  ['anchor', (h) => /锚点|摘录/.test(h)],
];

function parseRegistry(text) {
  const lines = text.split('\n');
  const rows = [];
  let columns = null;
  const problems = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!isTableLine(line)) { columns = null; continue; }
    const cells = cellsOf(line);
    if (isSeparator(cells)) continue;
    const next = (lines[i + 1] || '').trim();
    if (/^\|\s*:?-{2,}/.test(next)) {
      // 本行是表头
      const headers = cells.map(normHeader);
      const map = {};
      for (const [key, test] of HEADER_KEYS) {
        const idx = headers.findIndex(test);
        if (idx >= 0) map[key] = idx;
      }
      if (map.id != null && map.type != null && map.source != null) columns = map;
      else columns = null;
      continue;
    }
    if (!columns) continue;
    const get = (key) => (columns[key] == null ? '' : stripMark(cells[columns[key]] || ''));
    const idRaw = get('id');
    if (!idRaw) continue;
    rows.push({
      id: idRaw,
      type: get('type').toLowerCase(),
      source: get('source'),
      title: get('title'),
      trigger: get('trigger'),
      goal: get('goal'),
      anchor: normalizeAnchor(get('anchor')),
      line: i + 1,
    });
  }
  if (!rows.length && !columns) problems.push('registry.header');
  return { rows, problems };
}

function parseWindow(trigger) {
  const m = /每\s*(\d+)\s*(?:[–\-~～至到]\s*(\d+))?\s*章/.exec(trigger || '');
  if (!m) return null;
  const low = parseInt(m[1], 10);
  const high = m[2] ? parseInt(m[2], 10) : low;
  return low > 0 && low <= high ? { min: low, max: high } : null;
}

function parseTarget(trigger) {
  const t = trigger || '';
  const range = /第\s*(\d+)\s*[–\-~～至到]\s*(\d+)\s*章/.exec(t);
  if (range) return { from: parseInt(range[1], 10), to: parseInt(range[2], 10) };
  const single = /第\s*(\d+)\s*章/.exec(t);
  if (single) return { from: parseInt(single[1], 10), to: parseInt(single[1], 10) };
  const vol = /卷\s*(\d+|[一二三四五六七八九十]+)/.exec(t);
  if (vol) return { volume: vol[1] };
  return null;
}

function findHeading(text, heading) {
  const want = heading.replace(/\s+/g, '');
  for (const line of text.split('\n')) {
    const m = /^\s*#{1,6}\s*(.+?)\s*#*\s*$/.exec(line);
    if (m && m[1].replace(/\s+/g, '') === want) return true;
  }
  return false;
}

function excerptAround(text, anchor, radius = 3) {
  if (!anchor) return '';
  const lines = text.split('\n');
  const idx = lines.findIndex((l) => l.includes(anchor));
  if (idx < 0) return '';
  const start = Math.max(0, idx - radius);
  const end = Math.min(lines.length, idx + radius + 1);
  const chunk = lines.slice(start, end).map((l) => l.trim()).filter(Boolean).join('\n');
  return chunk.length > 600 ? chunk.slice(0, 600) : chunk;
}

function loadRegistry(root) {
  const rel = REGISTRY_REL;
  const text = readIf(path.join(root, rel));
  if (text == null) return null;
  const { rows, problems } = parseRegistry(text);
  const entries = {};
  const findings = [];
  const add = (severity, check, message, where) => findings.push({ severity, check, message, where: where || rel });
  for (const p of problems) {
    if (p === 'registry.header') add('blocking', 'registry.header', '登记表找不到含「编号 / 类型 / 来源」表头的表格');
  }
  for (const row of rows) {
    const where = `${rel}:${row.line}`;
    if (!ID_RE.test(row.id) || row.id !== (row.id.match(ID_RE) || [''])[0]) {
      add('blocking', 'registry.id-format', `编号「${row.id}」不合法，须形如 SET-001（兼容 SET-11A）`, where);
      continue;
    }
    if (entries[row.id]) { add('blocking', 'registry.duplicate-id', `编号 ${row.id} 出现多次`, where); continue; }
    if (!TYPES.has(row.type)) {
      add('blocking', 'registry.type', `${row.id} 类型「${row.type}」不合法；只允许 payoff / constraint / recurring / reserve / retired`, where);
      continue;
    }
    const entry = {
      id: row.id, type: row.type, title: row.title, trigger: row.trigger, goal: row.goal,
      anchor: row.anchor, source: row.source, sourcePath: null, sourceHeading: null, excerpt: '', line: row.line,
      window: null, target: null,
    };
    if (row.type !== 'retired') {
      const hash = row.source.indexOf('#');
      const srcPath = (hash >= 0 ? row.source.slice(0, hash) : row.source).trim();
      const srcHeading = hash >= 0 ? row.source.slice(hash + 1).trim() : '';
      entry.sourcePath = srcPath;
      entry.sourceHeading = srcHeading || null;
      const srcText = srcPath ? readIf(path.join(root, srcPath)) : null;
      if (!srcPath) add('blocking', 'registry.source-missing', `${row.id} 没有来源`, where);
      else if (srcText == null) add('blocking', 'registry.source-dangling', `${row.id} 来源 ${srcPath} 不存在`, where);
      else {
        if (srcHeading && !findHeading(srcText, srcHeading)) {
          add('blocking', 'registry.heading-dangling', `${row.id} 来源标题「${srcHeading}」在 ${srcPath} 里找不到`, where);
        }
        if (row.anchor) {
          if (!srcText.includes(row.anchor)) add('blocking', 'registry.anchor-dangling', `${row.id} 摘录锚点在 ${srcPath} 里找不到原句：「${row.anchor}」`, where);
          else entry.excerpt = excerptAround(srcText, row.anchor);
        } else if (row.type === 'payoff' || row.type === 'constraint') {
          add('advisory', 'registry.anchor-missing', `${row.id}（${row.type}）没有摘录锚点，写手拿不到规则原句`, where);
        }
      }
      if (row.type === 'recurring') {
        entry.window = parseWindow(row.trigger);
        if (!entry.window) add('advisory', 'registry.window-missing', `${row.id}（recurring）没写窗口（形如「每 3–5 章」），超窗无法判断`, where);
      }
      if (row.type === 'payoff') {
        entry.target = parseTarget(row.trigger);
        if (!entry.target) add('advisory', 'registry.target-missing', `${row.id}（payoff）没写目标章/窗口/卷，卷末无法判到期`, where);
      }
      if (EMPTY_CELL.test(row.goal) && row.type !== 'reserve') add('advisory', 'registry.goal-missing', `${row.id} 没写兑现目标（读者要理解什么）`, where);
    }
    entries[row.id] = entry;
  }
  return { rel, text, sha256: sha256(text), entries, findings, rowCount: rows.length };
}

// ---------- 细纲 ----------
function sliceSection(text, headingRe) {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => headingRe.test(l));
  if (start < 0) return null;
  const level = (/^(#+)/.exec(lines[start]) || ['', '#'])[1].length;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    const m = /^(#+)\s/.exec(lines[i]);
    if (m && m[1].length <= level) { end = i; break; }
  }
  return { text: lines.slice(start, end).join('\n'), startLine: start + 1, endLine: end };
}

const V2_HEADING = /^#{2,4}\s*设定兑现\s*$/;
const V1_HEADING = /^#{2,4}\s*设定兑现槽/;

function parseOutlineSection(sectionText) {
  const rows = [];
  let none = false;
  for (const line of sectionText.split('\n')) {
    if (isTableLine(line)) {
      const cells = cellsOf(line);
      if (isSeparator(cells)) continue;
      const first = stripMark(cells[0] || '');
      if (first === '编号') continue;
      if (first === '无') { none = true; continue; }
      const idm = ID_RE.exec(first);
      if (!idm) continue;
      rows.push({
        id: idm[0],
        relation: stripMark(cells[1] || ''),
        goal: stripMark(cells[2] || ''),
        note: stripMark(cells[3] || ''),
        raw: line.trim(),
      });
    } else if (/^\s*(?:[-*]\s*)?无\s*$/.test(line)) {
      none = true;
    }
  }
  return { rows, none };
}

function loadOutlines(root) {
  const dir = path.join(root, '大纲');
  const outlines = [];
  for (const f of listDir(dir)) {
    const m = /^细纲_第(\d+)章(?:_(.+))?\.md$/.exec(f);
    if (!m) continue;
    const text = readIf(path.join(dir, f)) || '';
    const v2 = sliceSection(text, V2_HEADING);
    const v1 = sliceSection(text, V1_HEADING);
    outlines.push({
      chapter: parseInt(m[1], 10),
      file: `大纲/${f}`,
      text,
      v2: v2 ? { ...v2, ...parseOutlineSection(v2.text) } : null,
      v1,
    });
  }
  return outlines.sort((a, b) => a.chapter - b.chapter);
}

// ---------- 追踪状态（只读开关） ----------
function loadTrackingConfig(root) {
  const text = readIf(path.join(root, STATE_REL));
  if (text == null) return { present: false, enabled: false, since: null, last: 0 };
  try {
    const state = JSON.parse(text);
    const cfg = state.setting_payoff || {};
    return {
      present: true,
      enabled: cfg.enabled === true,
      since: cfg.since_chapter == null ? null : Number(cfg.since_chapter),
      last: Number(state.last_committed_chapter || 0),
    };
  } catch {
    return { present: true, corrupt: true, enabled: false, since: null, last: 0 };
  }
}

// ---------- 具名实体零落点（沿用 v1 的启发式，只 advisory） ----------
function nameVariants(raw) {
  const out = new Set([raw]);
  const noParen = raw.replace(/[（(][^）)]*[）)]/g, '').trim();
  if (noParen) out.add(noParen);
  for (const base of [raw, noParen]) {
    for (const part of base.split(/[\/｜|·与和、]/)) {
      const t = part.trim();
      if (t.length >= 2) out.add(t);
    }
    for (const m of base.matchAll(/[（(]([^）)]+)[）)]/g)) {
      const t = m[1].replace(/[0-9.]+$/, '').trim();
      if (t.length >= 2) out.add(t);
    }
  }
  return [...out].filter(Boolean);
}

function loadSettingFiles(root) {
  const out = [];
  const walk = (dir, rel) => {
    for (const f of listDir(dir)) {
      if (f.startsWith('_') || f.startsWith('.')) continue;
      const abs = path.join(dir, f);
      let st;
      try { st = fs.statSync(abs); } catch { continue; }
      if (st.isDirectory()) walk(abs, `${rel}/${f}`);
      else if (f.endsWith('.md')) out.push({ file: `${rel}/${f}`, text: readIf(abs) || '' });
    }
  };
  walk(path.join(root, '设定'), '设定');
  return out;
}

function namedEntities(files, exempt) {
  const map = new Map();
  for (const s of files) {
    const re = /【([^】\n]{1,16})】/g;
    let m;
    while ((m = re.exec(s.text))) {
      const name = m[1].trim();
      if (!name || /^[0-9]+$/.test(name) || exempt.has(name)) continue;
      if (!map.has(name)) map.set(name, { name, file: s.file, variants: nameVariants(name) });
    }
  }
  return map;
}

function loadExempt(root) {
  const txt = readIf(path.join(root, EXEMPT_REL));
  const set = new Set();
  if (!txt) return set;
  for (const line of txt.split('\n')) {
    const t = line.replace(/#.*$/, '').trim().replace(/^【|】$/g, '');
    if (t) set.add(t);
  }
  return set;
}

// ---------- 分析 ----------
function analyze(root, opts = {}) {
  const findings = [];
  const add = (severity, check, message, where) => findings.push({ severity, check, message, where: where || '' });
  const registry = loadRegistry(root);
  const boardText = readIf(path.join(root, BOARD_REL));
  const tracking = loadTrackingConfig(root);
  const outlines = loadOutlines(root);
  const result = { findings, registry: null, tracking, chapters: [], stats: {} };

  if (!registry) {
    if (opts.readiness) {
      add('blocking', 'readiness.not-enabled', '写前关卡未就绪：须建立 设定/_设定登记.md、审查记录并启用记账；legacy/跳过不是 PASS');
      result.mode = boardText != null ? 'legacy' : 'disabled';
      return result;
    }
    if (tracking.enabled) {
      add('blocking', 'registry.missing', `追踪状态已启用设定兑现记账（自第${tracking.since}章），但 ${REGISTRY_REL} 不存在`, REGISTRY_REL);
      return result;
    }
    if (boardText != null) {
      add('advisory', 'legacy.board', `检测到 v1 看板 ${BOARD_REL}；运行 --migrate 迁移到登记表与「#### 设定兑现」小节`, BOARD_REL);
      result.mode = 'legacy';
      return result;
    }
    result.notApplicable = true;
    return result;
  }
  result.mode = 'v2';
  result.registry = { path: registry.rel, sha256: registry.sha256, entries: registry.entries };
  findings.push(...registry.findings);
  if (opts.readiness) {
    if (!tracking.enabled) add('blocking', 'readiness.not-enabled', '尚未启用设定兑现记账，不能进入新版正文流程', STATE_REL);
    findings.push(...checkReadiness(root, opts.chapter));
    const required = new Set(['registry.anchor-missing', 'registry.window-missing', 'registry.target-missing', 'registry.goal-missing']);
    for (const f of findings) if (required.has(f.check)) f.severity = 'blocking';
  }
  if (tracking.corrupt) add('blocking', 'tracking.corrupt', `${STATE_REL} 不是合法 JSON`, STATE_REL);
  if (!tracking.enabled) add('advisory', 'tracking.not-enabled', '登记表存在但追踪未启用记账：新书在 init 输入带 setting_payoff，旧书运行 tracking_commit.py enable-setting-payoff', STATE_REL);
  if (boardText != null) add('advisory', 'legacy.board-remains', `登记表已存在，${BOARD_REL} 仍在；它不再被读取，请改名为 ${BOARD_RETIRED_REL} 或删除`, BOARD_REL);

  const entries = registry.entries;
  const scheduled = new Map(); // id -> [{chapter, relation}]
  for (const o of outlines) {
    const chapterInfo = { chapter: o.chapter, file: o.file, rows: [], none: false, missing: false, legacy: !!o.v1 };
    result.chapters.push(chapterInfo);
    if (!o.v2) {
      chapterInfo.missing = true;
      const isNew = tracking.enabled && tracking.since != null && o.chapter >= tracking.since && o.chapter > tracking.last;
      if (o.v1) add(isNew ? 'blocking' : 'advisory', 'outline.legacy-slot', `第${o.chapter}章细纲仍是 v1「设定兑现槽」，需迁移成「#### 设定兑现」（运行 --migrate）`, o.file);
      else add(isNew ? 'blocking' : 'advisory', 'outline.section-missing', `第${o.chapter}章细纲缺「#### 设定兑现」小节（没有要兑现的设定就写一行「无」）`, o.file);
      continue;
    }
    chapterInfo.none = o.v2.none;
    if (!o.v2.rows.length && !o.v2.none) add('advisory', 'outline.section-empty', `第${o.chapter}章「设定兑现」小节既没有行也没写「无」`, o.file);
    const seen = new Set();
    for (const r of o.v2.rows) {
      const where = `${o.file}`;
      if (!entries[r.id]) { add('blocking', 'outline.unknown-id', `第${o.chapter}章引用了登记表没有的编号 ${r.id}`, where); continue; }
      if (entries[r.id].type === 'retired') { add('blocking', 'outline.retired-id', `第${o.chapter}章引用了已退役的 ${r.id}`, where); continue; }
      if (!RELATIONS.has(r.relation)) { add('blocking', 'outline.relation', `第${o.chapter}章 ${r.id} 关系「${r.relation}」不合法；只允许 兑现 / 涉及 / 不适用`, where); continue; }
      if (seen.has(r.id)) add('blocking', 'outline.duplicate-id', `第${o.chapter}章 ${r.id} 在设定兑现小节出现两次`, where);
      seen.add(r.id);
      if (r.relation === '不适用' && EMPTY_CELL.test(r.note)) add(opts.readiness ? 'blocking' : 'advisory', 'outline.na-reason', `第${o.chapter}章 ${r.id} 标了不适用但没写原因`, where);
      if (r.relation === '兑现' && EMPTY_CELL.test(r.goal)) add(opts.readiness ? 'blocking' : 'advisory', 'outline.goal-missing', `第${o.chapter}章 ${r.id} 标了兑现但没写本章呈现目标`, where);
      if (r.relation === '兑现' && entries[r.id].type === 'reserve') add(opts.readiness ? 'blocking' : 'advisory', 'schedule.reserve-early', `第${o.chapter}章排入了 reserve 类型的 ${r.id}——确认是否该改类型为 payoff`, where);
      const e = entries[r.id];
      if (r.relation === '兑现' && e.type === 'payoff' && e.target && e.target.from != null) {
        if (o.chapter < e.target.from || o.chapter > e.target.to) {
          add('advisory', 'schedule.target-mismatch', `${r.id} 登记目标是第${e.target.from}${e.target.to !== e.target.from ? `–${e.target.to}` : ''}章，却排在第${o.chapter}章`, where);
        }
      }
      chapterInfo.rows.push({
        id: r.id, relation: r.relation, goal: r.goal, note: r.note, type: e.type, title: e.title,
        excerpt: e.excerpt, source: e.source,
      });
      if (!scheduled.has(r.id)) scheduled.set(r.id, []);
      scheduled.get(r.id).push({ chapter: o.chapter, relation: r.relation });
    }
  }

  // payoff 到期未排：目标章已在已建细纲范围内，却没有任何一章排它
  const lastOutline = outlines.length ? outlines[outlines.length - 1].chapter : 0;
  for (const e of Object.values(entries)) {
    if (e.type !== 'payoff' || !e.target || e.target.to == null) continue;
    const hits = (scheduled.get(e.id) || []).filter((h) => h.relation !== '涉及');
    if (hits.length) continue;
    const due = e.target.to <= lastOutline;
    add((opts.strict && due) || (opts.readiness && e.target.to === opts.chapter) ? 'blocking' : 'advisory', due ? 'schedule.unscheduled-due' : 'schedule.unscheduled',
      `${e.id}「${e.title}」目标第${e.target.from}${e.target.to !== e.target.from ? `–${e.target.to}` : ''}章，${due ? '细纲已建到那里但' : ''}没有任何一章把它排入「兑现」或「不适用」`, registry.rel);
  }

  // 具名实体零落点（登记表 + 全部细纲文本里都不出现）
  const exempt = loadExempt(root);
  const files = loadSettingFiles(root);
  const entities = namedEntities(files, exempt);
  const landed = registry.text + outlines.map((o) => o.text).join('\n');
  let orphan = 0;
  for (const [name, e] of entities) {
    if (e.variants.some((v) => landed.includes(v))) continue;
    orphan += 1;
    add(opts.strict ? 'blocking' : 'advisory', 'setting.orphan-entity', `【${name}】（${e.file}）既没登记也没有任何细纲提到——没排期也没人演`, e.file);
  }

  result.stats = {
    registryRows: registry.rowCount, chapters: outlines.length,
    scheduledIds: scheduled.size, entities: entities.size, orphanEntities: orphan,
  };
  if (opts.chapter != null) {
    const info = result.chapters.find((c) => c.chapter === opts.chapter);
    result.chapter = info || { chapter: opts.chapter, missing: true, rows: [], absent: true };
    if (!info) add('blocking', 'chapter.outline-missing', `找不到第${opts.chapter}章细纲`, '大纲/');
  }
  return result;
}

// ---------- v1 → v2 迁移 ----------
function splitBoard(board) {
  const idx = (re) => { const m = re.exec(board); return m ? m.index : -1; };
  const a = idx(/^## 一、/m), b = idx(/^## 二、/m), c = idx(/^## 三、/m);
  return {
    once: a >= 0 ? board.slice(a, b >= 0 ? b : (c >= 0 ? c : board.length)) : '',
    recurring: b >= 0 ? board.slice(b, c >= 0 ? c : board.length) : '',
    pool: c >= 0 ? board.slice(c) : '',
  };
}
function parseIdMap(board) {
  const out = [];
  const i = board.search(/^##+\s*编号映射/m);
  if (i < 0) return out;
  const rest = board.slice(i);
  const j = rest.slice(3).search(/\n##+\s/);
  const block = j < 0 ? rest : rest.slice(0, j + 3);
  for (const line of block.split('\n')) {
    const m = /^\s*[-*+]\s*\*{0,2}(\d{2})\*{0,2}\s*(?:→|->)\s*(\S+\.md)\s*$/.exec(line);
    if (m) out.push({ num: m[1], rel: m[2] });
  }
  return out;
}
function tableRows(section, minCells) {
  const rows = [];
  for (const line of (section || '').split('\n')) {
    if (!isTableLine(line)) continue;
    const cells = cellsOf(line);
    if (isSeparator(cells) || cells.length < minCells) continue;
    const idm = ID_RE.exec(cells[0]);
    if (!idm) continue;
    rows.push({ id: idm[0], cells: cells.map(stripMark) });
  }
  return rows;
}
function esc(s) { return (s || '').replace(/\|/g, '｜').replace(/\s+/g, ' ').trim(); }

function migrate(root) {
  const boardPath = path.join(root, BOARD_REL);
  const board = readIf(boardPath);
  if (board == null) throw new Error(`没有 ${BOARD_REL}，无可迁移`);
  if (readIf(path.join(root, REGISTRY_REL)) != null) throw new Error(`${REGISTRY_REL} 已存在，拒绝覆盖`);
  const settings = new Map();
  for (const f of listDir(path.join(root, '设定'))) {
    const m = /^(\d{2})_(.+)\.md$/.exec(f);
    if (m) settings.set(m[1], `设定/${f}`);
  }
  for (const { num, rel } of parseIdMap(board)) if (!settings.has(num)) settings.set(num, rel);
  const sourceOf = (id) => settings.get(/SET-(\d{2})/.exec(id)[1]) || '';

  const sec = splitBoard(board);
  const rows = [];
  const seen = new Set();
  const push = (row) => { if (!seen.has(row.id)) { seen.add(row.id); rows.push(row); } };
  for (const r of tableRows(sec.once, 5)) {
    const chm = /第\s*(\d+)\s*章/.exec(r.cells[2] || '');
    push({ id: r.id, type: 'payoff', source: sourceOf(r.id), title: r.cells[1], trigger: chm ? `第${parseInt(chm[1], 10)}章` : '', goal: r.cells[3] });
  }
  for (const r of tableRows(sec.recurring, 4)) {
    push({ id: r.id, type: 'recurring', source: sourceOf(r.id), title: r.cells[1], trigger: '每 ? 章', goal: r.cells[2] });
  }
  for (const line of sec.pool.split('\n')) {
    const m = /\*\*(SET-\d{2,3}[A-Z]?)\s*[（(]([^）)]*)[）)]\*\*\s*[:：]\s*(.*)$/.exec(line);
    if (!m) continue;
    const pre = /（预计([^）]*)）/.exec(m[3]);
    push({ id: m[1], type: 'reserve', source: sourceOf(m[1]), title: m[2], trigger: pre ? pre[1].trim() : '', goal: m[3].replace(/（预计[^）]*）/, '').trim() });
  }
  const lines = [
    '# 设定登记',
    '',
    '> setting-payoff/v1。编号只增不改；退役行改类型为 `retired` 并保留。由 v1 看板迁移生成：',
    '> ① recurring 的窗口写成「每 ? 章」，请改成真实窗口（如「每 3–5 章」）；② 摘录锚点为空，请补来源文件里的一句原文；',
    '> ③ 类型按 v1 三表映射（一次性→payoff，贯穿→recurring，中后期池→reserve），必须遵守的规则请改为 constraint。',
    '',
    '| 编号 | 类型 | 来源 | 一句话 | 触发条件 / 窗口 | 兑现目标（读者要理解什么） | 摘录锚点 |',
    '|---|---|---|---|---|---|---|',
  ];
  for (const r of rows) {
    lines.push(`| ${r.id} | ${r.type} | ${esc(r.source)} | ${esc(r.title)} | ${esc(r.trigger)} | ${esc(r.goal)} | — |`);
  }
  fs.writeFileSync(path.join(root, REGISTRY_REL), lines.join('\n') + '\n', 'utf8');

  const migratedOutlines = [];
  for (const o of loadOutlines(root)) {
    if (o.v2 || !o.v1) continue;
    const slotRows = tableRows(o.v1.text, 2);
    const out = ['#### 设定兑现', '', '| 编号 | 关系 | 本章呈现目标 | 备注 |', '|---|---|---|---|'];
    for (const r of slotRows) {
      const goal = r.cells.slice(1, 4).filter((c) => !EMPTY_CELL.test(c)).join('；');
      out.push(`| ${r.id} | 兑现 | ${esc(goal)} | 由 v1 三槽迁移 |`);
    }
    for (const line of o.v1.text.split('\n')) {
      const m = /^\s*[-*]\s*\*{0,2}(SET-\d{2,3}[A-Z]?)\*{0,2}\s*(.*)$/.exec(line);
      if (!m || slotRows.some((r) => r.id === m[1])) continue;
      out.push(`| ${m[1]} | 兑现 | ${esc(m[2].replace(/^[：:]\s*/, ''))} | 由 v1 贯穿槽迁移 |`);
    }
    if (out.length === 4) out.push('| 无 | | | |');
    const textLines = o.text.split('\n');
    const replaced = [...textLines.slice(0, o.v1.startLine - 1), ...out, '', ...textLines.slice(o.v1.endLine)];
    fs.writeFileSync(path.join(root, o.file), replaced.join('\n'), 'utf8');
    migratedOutlines.push(o.file);
  }
  fs.renameSync(boardPath, path.join(root, BOARD_RETIRED_REL));
  return { registryRows: rows.length, outlines: migratedOutlines, retiredBoard: BOARD_RETIRED_REL };
}

// ---------- CLI ----------
function main() {
  const argv = process.argv.slice(2);
  const jsonMode = argv.includes('--json');
  const strict = argv.includes('--strict');
  const doMigrate = argv.includes('--migrate');
  let chapter = null;
  const ci = argv.indexOf('--chapter');
  if (ci >= 0) {
    chapter = parseInt(argv[ci + 1], 10);
    if (!Number.isInteger(chapter) || chapter < 1) { console.error('--chapter 需要正整数'); process.exit(2); }
  }
  const root = argv.find((a, i) => !a.startsWith('--') && argv[i - 1] !== '--chapter');
  if (!root) {
    console.error('用法: node check-setting-payoff.js <书目录> [--json] [--strict] [--chapter N] [--readiness] [--migrate]');
    process.exit(2);
  }
  if (!fs.existsSync(root)) { console.error(`书目录不存在：${root}`); process.exit(2); }

  if (doMigrate) {
    try {
      const report = migrate(root);
      console.log(jsonMode ? JSON.stringify(report, null, 2) : `已迁移：登记 ${report.registryRows} 条，细纲 ${report.outlines.length} 章，旧看板 → ${report.retiredBoard}。请补窗口与锚点后复跑本检查。`);
      process.exit(0);
    } catch (error) {
      console.error(`迁移失败：${error.message}`);
      process.exit(2);
    }
  }

  const result = analyze(root, { strict, chapter, readiness: argv.includes("--readiness") });
  const blocking = result.findings.filter((f) => f.severity === 'blocking');
  if (result.notApplicable) {
    if (jsonMode) console.log(JSON.stringify({ notApplicable: true, blocking: 0, findings: [] }, null, 2));
    else console.log(`设定兑现检查 · 本项目没有 ${REGISTRY_REL}，未启用该机制，跳过（规则见 story-write/references/setting-payoff.md）`);
    return;
  }
  if (jsonMode) {
    const { findings, registry, tracking, chapters, stats, mode } = result;
    console.log(JSON.stringify({ mode, blocking: blocking.length, findings, registry, tracking, stats, chapters, chapter: result.chapter }, null, 2));
  } else {
    const s = result.stats;
    console.log(`设定兑现检查 · 模式 ${result.mode} · 登记 ${s.registryRows || 0} 条 / 细纲 ${s.chapters || 0} 章 / 已排期 ${s.scheduledIds || 0} 条，findings ${result.findings.length}（blocking ${blocking.length}）`);
    console.log('—'.repeat(74));
    for (const f of result.findings) {
      console.log(`${f.severity === 'blocking' ? '[blocking]' : '[advisory]'} ${f.check} · ${f.message}`);
      if (f.where) console.log(`           ${f.where}`);
    }
    console.log('—'.repeat(74));
    console.log('blocking = 登记表或细纲小节格式坏了、引用了不存在/已退役的编号、追踪已启用却没登记表。');
    console.log('本脚本不判兑现是否成立：那由候选举证的复核签名（candidate-commit.py）与 story-review 负责。');
  }
  // 大 JSON 走管道时 process.exit 会截断 stdout，改用 exitCode 自然退出。
  process.exitCode = blocking.length > 0 ? 1 : 0;
}

module.exports = {
  analyze, migrate, loadRegistry, parseRegistry, parseWindow, parseTarget, parseOutlineSection, loadOutlines,
  loadTrackingConfig, nameVariants, namedEntities, loadExempt, excerptAround, main,
};

if (require.main === module) main();
