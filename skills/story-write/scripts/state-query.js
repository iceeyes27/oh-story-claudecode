#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node state-query.js [--dir <book-dir>] [--json] <command> [args]

结构化状态库（实验性旁路）：追踪/状态库/ 下按 50 章分片的 JSONL 事件库，
提供 Markdown 追踪文件做不到的时点查询与机器矛盾检测。不替代追踪文件。

Commands:
  add '<json>'          追加一条事件（自动路由到正确分片，写前校验字段）
  snapshot <N>          第 N 章时点快照：各实体状态、认知清单、活跃伏笔
       [--entity <名>]  只看某个实体
  foreshadow <N>        第 N 章时点的活跃伏笔（含超期标记）
  check                 全库矛盾检测（死亡后活动、未埋先收、重复回收、分片错位…）
  log --entity <名>     某实体的全部事件时间线

事件格式（每行一个 JSON 对象）：
  状态  {"ch":12,"type":"状态","entity":"林岚","field":"位置","value":"营业厅"}
  认知  {"ch":12,"type":"认知","entity":"林岚","learns":"账单被人动过"}
  伏笔  {"ch":12,"type":"伏笔","op":"埋设","id":"F001","desc":"陌生号码警告","due":30}
        op ∈ 埋设/推进/回收/废弃；埋设必带 desc，due（预计回收章）可选

规则与消费方式见 references/state-store.md。`;

const SHARD_SIZE = 50;

function die(msg) {
  process.stderr.write(`${msg}\n`);
  process.exit(2);
}

const options = { dir: process.cwd(), json: false, entity: null };
const positional = [];

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--dir') {
    i += 1;
    if (!process.argv[i]) die('--dir requires a value');
    options.dir = process.argv[i];
  } else if (arg === '--json') {
    options.json = true;
  } else if (arg === '--entity') {
    i += 1;
    if (!process.argv[i]) die('--entity requires a value');
    options.entity = process.argv[i];
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
if (!fs.existsSync(options.dir) || !fs.statSync(options.dir).isDirectory()) die(`book dir not found: ${options.dir}`);

const BOOK = options.dir;
const STORE_DIR = path.join(BOOK, '追踪', '状态库');

function pad3(n) {
  return String(n).padStart(3, '0');
}

function shardRange(ch) {
  const start = Math.floor((ch - 1) / SHARD_SIZE) * SHARD_SIZE + 1;
  return { start, end: start + SHARD_SIZE - 1 };
}

function shardFile(ch) {
  const { start, end } = shardRange(ch);
  return path.join(STORE_DIR, `事件_第${pad3(start)}-${pad3(end)}章.jsonl`);
}

const FORESHADOW_OPS = ['埋设', '推进', '回收', '废弃'];

// 返回 null 表示合法，否则返回错误描述
function validateEvent(ev) {
  if (typeof ev !== 'object' || ev === null || Array.isArray(ev)) return '事件必须是 JSON 对象';
  if (!Number.isInteger(ev.ch) || ev.ch < 1) return 'ch 必须是正整数章号';
  if (ev.type === '状态') {
    if (!ev.entity || !ev.field || ev.value === undefined) return '状态事件必须有 entity/field/value';
  } else if (ev.type === '认知') {
    if (!ev.entity || !ev.learns) return '认知事件必须有 entity/learns';
  } else if (ev.type === '伏笔') {
    if (!FORESHADOW_OPS.includes(ev.op)) return `伏笔事件 op 必须是 ${FORESHADOW_OPS.join('/')}`;
    if (!ev.id) return '伏笔事件必须有 id';
    if (ev.op === '埋设' && !ev.desc) return '伏笔埋设必须有 desc';
    if (ev.due !== undefined && (!Number.isInteger(ev.due) || ev.due < 1)) return 'due 必须是正整数章号';
  } else {
    return `type 必须是 状态/认知/伏笔，得到：${JSON.stringify(ev.type)}`;
  }
  return null;
}

// 读全库：按分片文件名排序，逐行解析；坏行与分片错位记入 problems 而不是中断
function loadStore() {
  const events = [];
  const problems = [];
  if (!fs.existsSync(STORE_DIR)) return { events, problems };
  const files = fs
    .readdirSync(STORE_DIR)
    .filter((f) => /^事件_第\d{3}-\d{3}章\.jsonl$/.test(f))
    .sort();
  for (const f of files) {
    const m = f.match(/^事件_第(\d{3})-(\d{3})章\.jsonl$/);
    const lo = Number(m[1]);
    const hi = Number(m[2]);
    const lines = fs.readFileSync(path.join(STORE_DIR, f), 'utf8').split(/\r?\n/);
    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i].trim();
      if (line === '') continue;
      const where = `追踪/状态库/${f}:${i + 1}`;
      let ev;
      try {
        ev = JSON.parse(line);
      } catch (err) {
        problems.push({ code: 'JSON_Invalid', level: 'error', message: `${where} 不是合法 JSON` });
        continue;
      }
      const bad = validateEvent(ev);
      if (bad) {
        problems.push({ code: 'Event_Invalid', level: 'error', message: `${where} ${bad}` });
        continue;
      }
      if (ev.ch < lo || ev.ch > hi) {
        problems.push({ code: 'Shard_Mismatch', level: 'error', message: `${where} 第 ${ev.ch} 章事件放错分片（本片范围 ${lo}-${hi}）` });
      }
      events.push({ ...ev, _where: where, _seq: events.length });
    }
  }
  // 章号升序；同章按文件内先后（_seq）保持稳定
  events.sort((a, b) => a.ch - b.ch || a._seq - b._seq);
  return { events, problems };
}

// 折叠 ch <= n 的事件得到时点状态
function foldSnapshot(events, n) {
  const state = new Map(); // entity -> Map(field -> {value, ch})
  const knowledge = new Map(); // entity -> [{learns, ch}]
  const foreshadow = new Map(); // id -> {desc, due, plantedCh, lastOp, lastCh, closed}
  for (const ev of events) {
    if (ev.ch > n) break;
    if (ev.type === '状态') {
      if (!state.has(ev.entity)) state.set(ev.entity, new Map());
      state.get(ev.entity).set(ev.field, { value: ev.value, ch: ev.ch });
    } else if (ev.type === '认知') {
      if (!knowledge.has(ev.entity)) knowledge.set(ev.entity, []);
      knowledge.get(ev.entity).push({ learns: ev.learns, ch: ev.ch });
    } else if (ev.type === '伏笔') {
      if (ev.op === '埋设') {
        foreshadow.set(ev.id, { desc: ev.desc, due: ev.due, plantedCh: ev.ch, lastOp: '埋设', lastCh: ev.ch, closed: false });
      } else if (foreshadow.has(ev.id)) {
        const f = foreshadow.get(ev.id);
        f.lastOp = ev.op;
        f.lastCh = ev.ch;
        if (ev.op === '回收' || ev.op === '废弃') f.closed = true;
      }
    }
  }
  return { state, knowledge, foreshadow };
}

function activeForeshadows(snapshot, n) {
  const out = [];
  for (const [id, f] of snapshot.foreshadow) {
    if (f.closed) continue;
    out.push({ id, desc: f.desc, plantedCh: f.plantedCh, due: f.due, lastOp: f.lastOp, lastCh: f.lastCh, overdue: Number.isInteger(f.due) && f.due < n });
  }
  out.sort((a, b) => a.plantedCh - b.plantedCh);
  return out;
}

function parseChapterArg(arg) {
  const n = Number.parseInt(arg, 10);
  if (!Number.isInteger(n) || n < 1) die('章节号必须是正整数');
  return n;
}

// ---- add ----
if (command === 'add') {
  if (positional.length < 2) die('add 需要一个 JSON 事件参数\n' + USAGE);
  let ev;
  try {
    ev = JSON.parse(positional[1]);
  } catch (err) {
    die(`事件不是合法 JSON：${err.message}`);
  }
  const bad = validateEvent(ev);
  if (bad) die(`事件校验失败：${bad}`);
  fs.mkdirSync(STORE_DIR, { recursive: true });
  const file = shardFile(ev.ch);
  fs.appendFileSync(file, `${JSON.stringify(ev)}\n`, 'utf8');
  process.stdout.write(`ADDED: ${path.relative(BOOK, file).split(path.sep).join('/')}\n`);
  process.exit(0);
}

// ---- 读库命令 ----
const { events, problems } = loadStore();

if (command === 'snapshot') {
  if (positional.length < 2) die('snapshot 需要章节号\n' + USAGE);
  const n = parseChapterArg(positional[1]);
  const snap = foldSnapshot(events, n);
  const entities = options.entity ? [options.entity] : Array.from(new Set([...snap.state.keys(), ...snap.knowledge.keys()])).sort();
  if (options.json) {
    const out = { chapter: n, entities: {}, foreshadow: activeForeshadows(snap, n) };
    for (const e of entities) {
      out.entities[e] = {
        state: Object.fromEntries(Array.from(snap.state.get(e) || []).map(([k, v]) => [k, v])),
        knowledge: snap.knowledge.get(e) || [],
      };
    }
    process.stdout.write(`${JSON.stringify(out, null, 2)}\n`);
    process.exit(0);
  }
  const lines = [`## 状态快照：截至第 ${pad3(n)} 章`, ''];
  for (const e of entities) {
    lines.push(`### ${e}`);
    const st = snap.state.get(e);
    if (st && st.size > 0) {
      for (const [field, v] of st) lines.push(`- ${field}：${v.value}（第 ${v.ch} 章）`);
    }
    const kn = snap.knowledge.get(e);
    if (kn && kn.length > 0) {
      lines.push(`- 已知信息：`);
      for (const k of kn) lines.push(`  - ${k.learns}（第 ${k.ch} 章获知）`);
    }
    if ((!st || st.size === 0) && (!kn || kn.length === 0)) lines.push('- （无记录）');
    lines.push('');
  }
  const active = activeForeshadows(snap, n);
  lines.push(`### 活跃伏笔（${active.length}）`);
  for (const f of active) {
    const due = Number.isInteger(f.due) ? `，预计第 ${f.due} 章回收${f.overdue ? '【已超期】' : ''}` : '';
    lines.push(`- ${f.id} ${f.desc}（第 ${f.plantedCh} 章埋设${due}）`);
  }
  process.stdout.write(`${lines.join('\n')}\n`);
  process.exit(0);
}

if (command === 'foreshadow') {
  if (positional.length < 2) die('foreshadow 需要章节号\n' + USAGE);
  const n = parseChapterArg(positional[1]);
  const active = activeForeshadows(foldSnapshot(events, n), n);
  if (options.json) {
    process.stdout.write(`${JSON.stringify({ chapter: n, foreshadow: active }, null, 2)}\n`);
    process.exit(0);
  }
  process.stdout.write(`## 活跃伏笔：截至第 ${pad3(n)} 章（${active.length}）\n\n`);
  for (const f of active) {
    const due = Number.isInteger(f.due) ? `，预计第 ${f.due} 章回收${f.overdue ? '【已超期】' : ''}` : '';
    process.stdout.write(`- ${f.id} ${f.desc}（第 ${f.plantedCh} 章埋设${due}）\n`);
  }
  process.exit(0);
}

if (command === 'log') {
  if (!options.entity) die('log 需要 --entity <名>\n' + USAGE);
  const hits = events.filter((ev) => ev.entity === options.entity);
  if (options.json) {
    process.stdout.write(`${JSON.stringify(hits.map(({ _where, _seq, ...ev }) => ev), null, 2)}\n`);
    process.exit(0);
  }
  process.stdout.write(`## 事件时间线：${options.entity}（${hits.length} 条）\n\n`);
  for (const ev of hits) {
    if (ev.type === '状态') process.stdout.write(`- 第 ${ev.ch} 章 状态 ${ev.field}=${ev.value}\n`);
    else process.stdout.write(`- 第 ${ev.ch} 章 认知 ${ev.learns}\n`);
  }
  process.exit(0);
}

if (command === 'check') {
  const findings = [...problems];
  const latestCh = events.length > 0 ? events[events.length - 1].ch : 0;

  // 伏笔生命周期：未埋先动、重复埋设、关闭后再动（含重复回收）
  const seen = new Map(); // id -> {planted, closed}
  for (const ev of events) {
    if (ev.type !== '伏笔') continue;
    const s = seen.get(ev.id) || { planted: false, closed: false };
    if (ev.op === '埋设') {
      if (s.planted && !s.closed) {
        findings.push({ code: 'Foreshadow_Double_Plant', level: 'error', message: `${ev._where} 伏笔 ${ev.id} 重复埋设（前一次尚未回收/废弃）` });
      }
      seen.set(ev.id, { planted: true, closed: false });
      continue;
    }
    if (!s.planted) {
      findings.push({ code: 'Foreshadow_Not_Planted', level: 'error', message: `${ev._where} 伏笔 ${ev.id} 未埋设就「${ev.op}」` });
      continue;
    }
    if (s.closed) {
      findings.push({ code: 'Foreshadow_After_Close', level: 'error', message: `${ev._where} 伏笔 ${ev.id} 已回收/废弃后又「${ev.op}」` });
      continue;
    }
    if (ev.op === '回收' || ev.op === '废弃') s.closed = true;
    seen.set(ev.id, s);
  }

  // 死亡后活动：存活=死亡 之后同实体再有状态/认知事件（除非先把存活改回）
  const deadSince = new Map(); // entity -> ch
  for (const ev of events) {
    if (ev.type === '状态' && ev.field === '存活') {
      if (String(ev.value) === '死亡') deadSince.set(ev.entity, ev.ch);
      else deadSince.delete(ev.entity);
      continue;
    }
    if ((ev.type === '状态' || ev.type === '认知') && deadSince.has(ev.entity) && ev.ch > deadSince.get(ev.entity)) {
      findings.push({ code: 'Dead_Entity_Active', level: 'error', message: `${ev._where} ${ev.entity} 已于第 ${deadSince.get(ev.entity)} 章死亡，第 ${ev.ch} 章仍有${ev.type}事件` });
    }
  }

  // 重复认知：同实体同信息学两次
  const learned = new Set();
  for (const ev of events) {
    if (ev.type !== '认知') continue;
    const key = `${ev.entity} ${ev.learns}`;
    if (learned.has(key)) {
      findings.push({ code: 'Knowledge_Duplicate', level: 'warning', message: `${ev._where} ${ev.entity} 重复获知「${ev.learns}」` });
    }
    learned.add(key);
  }

  // 超期伏笔：仍活跃且 due < 最新章号
  for (const f of activeForeshadows(foldSnapshot(events, latestCh), latestCh)) {
    if (f.overdue) {
      findings.push({ code: 'Foreshadow_Overdue', level: 'warning', message: `伏笔 ${f.id}「${f.desc}」预计第 ${f.due} 章回收，最新已写到第 ${latestCh} 章仍未回收` });
    }
  }

  const errors = findings.filter((x) => x.level === 'error');
  if (options.json) {
    process.stdout.write(`${JSON.stringify({ result: errors.length === 0 ? 'PASS' : 'FAIL', events: events.length, findings }, null, 2)}\n`);
  } else {
    process.stdout.write(`## 状态库矛盾检测（${events.length} 条事件）\n\n`);
    if (findings.length === 0) {
      process.stdout.write('- 无矛盾\n');
    } else {
      for (const x of findings) process.stdout.write(`- [${x.level}] ${x.code}: ${x.message}\n`);
    }
    process.stdout.write(`\nCheck: ${errors.length === 0 ? 'PASS' : 'FAIL'}（error ${errors.length} / warning ${findings.length - errors.length}）\n`);
  }
  process.exit(errors.length === 0 ? 0 : 1);
}

die(`unknown command: ${command}\n${USAGE}`);
