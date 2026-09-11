#!/usr/bin/env node
/**
 * check-setting-payoff.js — 设定兑现闭环检测（设定 → 看板 → 细纲槽，确定性层）
 *
 * 背景：现有校验器各管一段——`check-outline-contract.js` 管细纲字段齐不齐，
 * `check-outline-causal.py` 管因果指向合不合法，`tracking_commit.py check` 管追踪一致性。
 * 没有一个管**「设定有没有真落到某一章上」**。结果是设定文件越写越厚，正文却只用到
 * 其中一小半，剩下的既没排期也没人发现——直到读者问「那个 App 呢」。
 *
 * 本脚本检查设定兑现的三层闭环：
 *   设定/NN_*.md（写了什么）→ 追踪/设定兑现看板.md（排到第几章）→ 大纲/细纲_*.md（本章怎么演）
 *
 * 能力边界（重要）：脚本只判**机械可判定**的部分——编号对得上吗、状态词合法吗、
 * 排期章与槽位章一致吗、具名实体有没有零落点。它**判不了语义**：
 *   - 判不出「用【神算】检索法条」是不是用错了 App（神算确实在 11 号文件里，职能对不对要人读）
 *   - 判不出「一年级用三年级的符」这种分阶冲突（需要理解能力分档）
 *   - 判不出兑现物是不是真的「动词化」了，还是又写成了说明书
 * 这三类交给人工复核与 `reader-first-writing.md` 的语义层。
 * **零落点检查是抓错配的主力**：能力 A 被错记成能力 B 时，A 会表现为零落点。
 *
 * 用法:
 *   node check-setting-payoff.js <书目录> [--json] [--strict]
 *   <书目录>：书根（含 设定/、大纲/、追踪/）
 *   --strict：把「具名实体零落点」从 advisory 升为 blocking
 *
 * 约定（与 story-setup 的看板模板一致）：
 *   - 编号格式 `SET-NN[字母]`。设定源支持两种布局：
 *       A 新书（story-write 建纲）：`设定/NN_名字.md`，NN 取文件名前缀，零配置
 *       B 导入书（story-import 反推）：`设定/世界观/*.md` 等目录结构，没有前缀，
 *         由看板的 `## 编号映射` 小节显式声明（`- **11** → 设定/世界观/App架构.md`）
 *     两者可混用，同号时文件名前缀优先；映射指向不存在的文件报 blocking
 *   - 状态四态：[待排期] / [已排期-第N章] / [正文已兑现] / [贯穿循环]
 *   - 看板「一、…一次性交付…」表的编号集合，须与全部细纲「## 设定兑现槽」的编号集合逐项一致
 *   - 贯穿型设定登记在「二、…贯穿型…」表，中后期设定登记在「三、…中后期池」
 *
 * 退出码：0 无 blocking / 1 有 blocking / 2 参数或读取错误
 */
'use strict';
const fs = require('fs');
const path = require('path');

const STATE_RE = /^\[(待排期|正文已兑现|贯穿循环|已排期-第\d+章)\]$/;
const ID_RE = /SET-(\d{2})([A-Z]?)/g;

// ---------- 读取 ----------
function readIf(p) {
  try { return fs.readFileSync(p, 'utf8'); } catch { return null; }
}

function listDir(dir) {
  try { return fs.readdirSync(dir); } catch { return []; }
}

function loadProject(root) {
  const settingDir = path.join(root, '设定');
  const outlineDir = path.join(root, '大纲');
  const boardPath = path.join(root, '追踪', '设定兑现看板.md');

  const board0 = readIf(boardPath);

  // 设定源有两种布局：
  //   A. 新书（story-write 建纲）：设定/NN_名字.md，编号直接取文件名前缀，零配置
  //   B. 导入书（story-import 反推）：设定/世界观/*.md、设定/角色/*.md 等目录结构，没有前缀
  // 布局 B 由看板里的「## 编号映射」小节显式声明 NN → 路径，否则无从建立映射。
  const settings = new Map(); // '11' -> {file, name, text}
  for (const f of listDir(settingDir)) {
    const m = /^(\d{2})_(.+)\.md$/.exec(f);
    if (!m) continue;
    settings.set(m[1], {
      file: `设定/${f}`,
      name: m[2],
      text: readIf(path.join(settingDir, f)) || '',
    });
  }
  for (const { num, rel } of parseIdMap(board0)) {
    if (settings.has(num)) continue;              // 文件名前缀优先
    const abs = path.join(root, rel);
    const text = readIf(abs);
    if (text == null) continue;                   // 指向不存在的文件 → 由 idmap.dangling 报
    settings.set(num, { file: rel, name: path.basename(rel, '.md'), text, mapped: true });
  }

  const outlines = []; // {chapter, file, text, slotBlock}
  for (const f of listDir(outlineDir)) {
    const m = /^细纲_第(\d+)章_(.+)\.md$/.exec(f);
    if (!m) continue;
    const text = readIf(path.join(outlineDir, f)) || '';
    outlines.push({
      chapter: parseInt(m[1], 10),
      file: `大纲/${f}`,
      text,
      slotBlock: sliceSlotBlock(text),
    });
  }
  outlines.sort((a, b) => a.chapter - b.chapter);

  return { root, settings, outlines, board: readIf(boardPath), boardPath: '追踪/设定兑现看板.md' };
}

// 看板可选小节「## 编号映射」：给没有 NN_ 前缀的设定布局（story-import 产出）显式建映射。
// 行格式：`- **11** → 设定/世界观/App架构.md`（箭头可用 → 或 -> ）
function parseIdMap(board) {
  const out = [];
  if (!board) return out;
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

// 截取细纲里的「## 设定兑现槽 … 」到下一个 `## ` 标题为止
function sliceSlotBlock(text) {
  const i = text.indexOf('## 设定兑现槽');
  if (i < 0) return null;
  const rest = text.slice(i + 3);
  const j = rest.search(/\n## /);
  return j < 0 ? text.slice(i) : text.slice(i, i + 3 + j);
}

// ---------- 看板分节 ----------
function splitBoard(board) {
  if (!board) return { once: '', recurring: '', pool: '' };
  const idx = (re) => { const m = re.exec(board); return m ? m.index : -1; };
  const a = idx(/^## 一、/m), b = idx(/^## 二、/m), c = idx(/^## 三、/m);
  return {
    once: a >= 0 ? board.slice(a, b >= 0 ? b : (c >= 0 ? c : board.length)) : '',
    recurring: b >= 0 ? board.slice(b, c >= 0 ? c : board.length) : '',
    pool: c >= 0 ? board.slice(c) : '',
  };
}

function idsIn(text) {
  const out = [];
  if (!text) return out;
  let m;
  const re = new RegExp(ID_RE.source, 'g');
  while ((m = re.exec(text))) out.push({ id: `SET-${m[1]}${m[2]}`, num: m[1] });
  return out;
}

// 表一每行：| **SET-xx** | 模块 | 目标交付章节 | 兑现行为 | 状态 | 简记 |
function parseOnceRows(onceSection) {
  const rows = [];
  for (const line of (onceSection || '').split('\n')) {
    if (!line.trim().startsWith('|')) continue;
    const cells = line.split('|').slice(1, -1).map((s) => s.trim());
    if (cells.length < 5) continue;
    const idm = /SET-(\d{2})([A-Z]?)/.exec(cells[0]);
    if (!idm) continue;
    const chm = /第\s*(\d+)\s*章/.exec(cells[2] || '');
    const stm = /`(\[[^\]]*\])`/.exec(cells[4] || '');
    rows.push({
      id: `SET-${idm[1]}${idm[2]}`,
      num: idm[1],
      chapter: chm ? parseInt(chm[1], 10) : null,
      state: stm ? stm[1] : null,
      raw: line.trim(),
    });
  }
  return rows;
}

// 细纲槽表每行：| **SET-xx** | 物证槽 | 动作槽 | 梗槽 |
function parseSlotRows(slotBlock) {
  const rows = [];
  for (const line of (slotBlock || '').split('\n')) {
    if (!line.trim().startsWith('|')) continue;
    const cells = line.split('|').slice(1, -1).map((s) => s.trim());
    if (cells.length < 2) continue;
    const idm = /SET-(\d{2})([A-Z]?)/.exec(cells[0]);
    if (!idm) continue;
    rows.push({
      id: `SET-${idm[1]}${idm[2]}`,
      num: idm[1],
      cols: cells.slice(1),
      raw: line.trim(),
    });
  }
  return rows;
}

// ---------- 具名实体 ----------
// 别名归一化：设定里常写全名（【退灵符（驱逐符1.0）】、【保温符/温水符】），
// 细纲里只写其中一个短名。任一变体落地即算落地，否则全是误报。
function nameVariants(raw) {
  const out = new Set([raw]);
  const noParen = raw.replace(/[（(][^）)]*[）)]/g, '').trim();
  if (noParen) out.add(noParen);
  for (const base of [raw, noParen]) {
    // `/` 别名、`·` 音译名姓、「与/和/、」并列合写（亚瑟与玛莎·霍尔特 → 亚瑟 / 玛莎 / 霍尔特）
    for (const part of base.split(/[\/｜|·与和、]/)) {
      const t = part.trim();
      if (t.length >= 2) out.add(t);
    }
    // 括号内的旧称也算（退灵符（驱逐符1.0）→ 驱逐符）
    for (const m of base.matchAll(/[（(]([^）)]+)[）)]/g)) {
      const t = m[1].replace(/[0-9.]+$/, '').trim();
      if (t.length >= 2) out.add(t);
    }
  }
  return [...out].filter(Boolean);
}

// 高精度信号：设定文件里用【】圈起来的具名能力/物件（App、符箓、模块）
function namedEntities(settings, exempt = new Set()) {
  const map = new Map(); // '天机' -> {num, file, variants}
  for (const [num, s] of settings) {
    const re = /【([^】\n]{1,16})】/g;
    let m;
    while ((m = re.exec(s.text))) {
      const name = m[1].trim();
      if (!name || /^[0-9]+$/.test(name) || exempt.has(name)) continue;
      if (!map.has(name)) map.set(name, { name, num, file: s.file, variants: nameVariants(name) });
    }
  }
  return map;
}

// 角色名：只认「表头首列是 角色/人物/姓名/名字」的那张表的首列。
// 角色卡里同时存在 `| 项 | 设定 |` 这类属性表，首列是"本体/人格/语言"等字段名，
// 按表头过滤才能把它们摘干净——用白名单堵是堵不完的。
const NAME_HEADER = /^(角色|人物|姓名|名字)$/;
function characterNames(settings, exempt = new Set()) {
  const names = new Map();
  for (const [num, s] of settings) {
    if (!/角色|人物|群像/.test(s.name)) continue;
    const lines = s.text.split('\n');
    let inNameTable = false;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line.startsWith('|')) { inNameTable = false; continue; }
      const cells = line.split('|').slice(1, -1).map((x) => x.trim());
      if (!cells.length) continue;
      // 分隔行 |---|---| 紧跟表头，用它确认上一行是表头
      if (/^:?-{2,}:?$/.test(cells[0])) continue;
      const head = cells[0].replace(/\*\*/g, '').trim();
      const next = (lines[i + 1] || '').trim();
      if (/^\|\s*:?-{2,}/.test(next)) {              // 本行是表头
        inNameTable = NAME_HEADER.test(head);
        continue;
      }
      if (!inNameTable) continue;
      const n = head;
      if (!n || exempt.has(n)) continue;
      if (n.length < 2 || n.length > 12) continue;
      if (!/^[一-龥·]+$/.test(n)) continue;          // 只收纯中文（含间隔号）
      if (!names.has(n)) names.set(n, { name: n, num, file: s.file, variants: nameVariants(n) });
    }
  }
  return names;
}

// 豁免清单：连招名、组合技、纯背景设定这类不需要单独排期的条目，
// 在 设定/_兑现豁免.txt 每行声明一个（# 开头为注释）。
function loadExempt(root) {
  const p = path.join(root, '设定', '_兑现豁免.txt');
  const txt = readIf(p);
  const set = new Set();
  if (!txt) return set;
  for (const line of txt.split('\n')) {
    const t = line.replace(/#.*$/, '').trim().replace(/^【|】$/g, '');
    if (t) set.add(t);
  }
  return set;
}

// ---------- 检查 ----------
function analyze(root, opts = {}) {
  const p = loadProject(root);
  const findings = [];
  const add = (severity, id, msg, where) => findings.push({ severity, check: id, message: msg, where: where || '' });

  // 未建看板＝本项目没启用这套机制，属「不适用」而不是「不合格」。
  // 存量项目和短篇不应被这道门拦住；启用与否由 Phase 3 建纲时决定。
  if (!p.board) return { findings, stats: { notApplicable: true }, notApplicable: true };

  // 编号映射表指向的文件必须存在——悬空映射会让该设定整个漏检。
  // 必须排在下面两个提前返回之前：悬空映射本身就会导致 settings 为空，
  // 先返回「找不到设定」会把真正的原因盖掉。
  for (const { num, rel } of parseIdMap(p.board)) {
    if (!fs.existsSync(path.join(p.root, rel))) {
      add('blocking', 'idmap.dangling', `看板「编号映射」把 ${num} 号指向 ${rel}，但该文件不存在`, p.boardPath);
    }
  }

  // 已建看板却拿不到设定/细纲，才是真的断链
  if (!p.settings.size) { add('blocking', 'project.settings', `已有设定兑现看板，却找不到设定源——新书用 设定/NN_*.md 两位数字前缀命名，导入书在看板加「## 编号映射」小节声明 NN → 路径`, '设定/'); return { findings, stats: {} }; }
  if (!p.outlines.length) { add('blocking', 'project.outlines', `已有设定兑现看板，却找不到 大纲/细纲_第N章_*.md`, '大纲/'); return { findings, stats: {} }; }

  const sec = splitBoard(p.board);
  const onceRows = parseOnceRows(sec.once);

  // 1. 状态词合法性
  const stateTokens = [...p.board.matchAll(/`(\[[^\]]*\])`/g)].map((m) => m[1]);
  const badStates = [...new Set(stateTokens.filter((t) => !STATE_RE.test(t) && t !== '[已排期-第N章]'))];
  for (const t of badStates) {
    add('blocking', 'board.state-vocab', `看板出现未定义状态词 \`${t}\`；只允许 [待排期] / [已排期-第N章] / [正文已兑现] / [贯穿循环]`, p.boardPath);
  }

  // 2. 编号格式与设定文件存在性
  const allIds = idsIn(p.board).concat(p.outlines.flatMap((o) => idsIn(o.slotBlock)));
  for (const { id, num } of allIds) {
    if (!p.settings.has(num)) {
      add('blocking', 'board.id-orphan', `编号 ${id} 的 ${num} 号找不到对应的 设定/${num}_*.md；编号的两位数字必须等于设定文件号`, p.boardPath);
    }
  }

  // 3. 表一编号重复
  const seen = new Map();
  for (const r of onceRows) {
    if (seen.has(r.id)) add('blocking', 'board.duplicate-id', `编号 ${r.id} 在一次性交付表出现多次`, p.boardPath);
    else seen.set(r.id, r);
  }

  // 4. 看板表一 ↔ 细纲槽 集合一致
  const slotIndex = new Map(); // id -> [chapter...]
  for (const o of p.outlines) {
    if (!o.slotBlock) { add('blocking', 'outline.slot-missing', `第${o.chapter}章细纲缺「## 设定兑现槽」小节`, o.file); continue; }
    for (const r of parseSlotRows(o.slotBlock)) {
      if (!slotIndex.has(r.id)) slotIndex.set(r.id, []);
      slotIndex.get(r.id).push(o.chapter);
    }
  }
  const boardIds = new Set(onceRows.map((r) => r.id));
  const slotIds = new Set(slotIndex.keys());
  for (const id of boardIds) if (!slotIds.has(id)) add('blocking', 'board.outline-sync', `看板排了 ${id}，但没有任何一章细纲的兑现槽里有它`, p.boardPath);
  for (const id of slotIds) if (!boardIds.has(id)) add('blocking', 'board.outline-sync', `细纲槽里有 ${id}（第${slotIndex.get(id).join('/')}章），但看板一次性交付表没有这一行`, '大纲/');

  // 5. 排期章 ↔ 槽位所在章 一致
  for (const r of onceRows) {
    const chs = slotIndex.get(r.id);
    if (!chs || r.chapter == null) continue;
    if (!chs.includes(r.chapter)) {
      add('blocking', 'board.schedule-match', `${r.id} 看板排在第${r.chapter}章，但它的兑现槽实际写在第${chs.join('/')}章`, p.boardPath);
    }
    if (r.state && /已排期-第(\d+)章/.test(r.state)) {
      const n = parseInt(/已排期-第(\d+)章/.exec(r.state)[1], 10);
      if (n !== r.chapter) add('blocking', 'board.state-chapter', `${r.id} 目标交付章是第${r.chapter}章，状态词却写 ${r.state}`, p.boardPath);
    }
  }

  // 6. 三槽位填满
  for (const o of p.outlines) {
    for (const r of parseSlotRows(o.slotBlock)) {
      const filled = r.cols.slice(0, 3).filter((c) => c && c !== '—' && c !== '-' && !/^\[待补充\]$/.test(c));
      if (filled.length < 3) {
        add('blocking', 'slot.three-columns', `第${o.chapter}章 ${r.id} 的三槽位未填满（物证/动作/梗只填了 ${filled.length} 个）`, o.file);
      }
    }
  }

  // 7. 槽内引用的具名能力，归属文件与本槽编号是否一致
  const exempt = loadExempt(p.root);
  const entities = namedEntities(p.settings, exempt);
  for (const o of p.outlines) {
    for (const r of parseSlotRows(o.slotBlock)) {
      const used = new Set([...r.raw.matchAll(/【([^】\n]{1,12})】/g)].map((m) => m[1].trim()));
      for (const name of used) {
        const e = entities.get(name);
        if (!e) continue; // 正文自造的称呼，不管
        if (e.num !== r.num) {
          add('advisory', 'slot.capability-owner', `第${o.chapter}章 ${r.id}（${r.num}号）引用了【${name}】，但它定义在 ${e.file}（${e.num}号）——要么换编号，要么确认是跨设定联动`, o.file);
        }
      }
    }
  }

  // 8. 具名实体零落点
  const landed = p.board + p.outlines.map((o) => o.text).join('\n');
  const orphanSeverity = opts.strict ? 'blocking' : 'advisory';
  const orphanEntities = [];
  for (const [name, e] of entities) {
    if (!e.variants.some((v) => landed.includes(v))) orphanEntities.push({ name, e });
  }
  for (const { name, e } of orphanEntities) {
    add(orphanSeverity, 'setting.orphan-entity', `【${name}】（${e.file}）在看板与全部细纲里零落点——没排期也没人演`, e.file);
  }

  const chars = characterNames(p.settings, exempt);
  const orphanChars = [];
  for (const [name, e] of chars) {
    if (!e.variants.some((v) => landed.includes(v))) orphanChars.push({ name, e });
  }
  for (const { name, e } of orphanChars) {
    add(orphanSeverity, 'setting.orphan-character', `角色「${name}」（${e.file}）在看板与全部细纲里零落点——设定里写了，没有任何一章用他`, e.file);
  }

  return {
    findings,
    stats: {
      settings: p.settings.size,
      chapters: p.outlines.length,
      boardOnceRows: onceRows.length,
      entities: entities.size,
      characters: chars.size,
      orphanEntities: orphanEntities.length,
      orphanCharacters: orphanChars.length,
    },
  };
}

// ---------- CLI ----------
function main() {
  const argv = process.argv.slice(2);
  const jsonMode = argv.includes('--json');
  const strict = argv.includes('--strict');
  const root = argv.find((a) => !a.startsWith('--'));
  if (!root) {
    console.error('用法: node check-setting-payoff.js <书目录> [--json] [--strict]');
    process.exit(2);
  }
  if (!fs.existsSync(root)) { console.error(`书目录不存在：${root}`); process.exit(2); }

  const result = analyze(root, { strict });
  const { findings, stats } = result;
  const blocking = findings.filter((f) => f.severity === 'blocking');

  if (result.notApplicable) {
    if (jsonMode) console.log(JSON.stringify({ notApplicable: true, blocking: 0, findings: [] }, null, 2));
    else console.log(`设定兑现闭环检查 · 本项目没有 追踪/设定兑现看板.md，未启用该机制，跳过（建纲时生成看板即可启用，见 story-write/references/setting-payoff.md）`);
    process.exit(0);
  }

  if (jsonMode) {
    console.log(JSON.stringify({ ...stats, blocking: blocking.length, findings }, null, 2));
  } else {
    console.log(`设定兑现闭环检查 · 设定 ${stats.settings || 0} 份 / 细纲 ${stats.chapters || 0} 章 / 看板一次性行 ${stats.boardOnceRows || 0} 条，findings ${findings.length}（blocking ${blocking.length}）`);
    console.log('—'.repeat(74));
    for (const f of findings) {
      const tag = f.severity === 'blocking' ? '[blocking]' : '[advisory]';
      console.log(`${tag} ${f.check} · ${f.message}`);
      if (f.where) console.log(`           ${f.where}`);
    }
    console.log('—'.repeat(74));
    console.log('blocking = 闭环断了（编号对不上、排期与槽位矛盾、三槽没填满、状态词非法）。');
    console.log('能力边界：只判机械可判定的部分。判不出「App 用错了」「一年级用了三年级的能力」「兑现物又写成说明书」——');
    console.log('          这三类交给人工与语义层。零落点是抓错配的主力：能力A被错记成能力B时，A 会表现为零落点。');
  }
  process.exit(blocking.length > 0 ? 1 : 0);
}

module.exports = { analyze, loadProject, splitBoard, parseIdMap, parseOnceRows, parseSlotRows, namedEntities, characterNames, nameVariants, loadExempt, sliceSlotBlock, main };

if (require.main === module) main();
