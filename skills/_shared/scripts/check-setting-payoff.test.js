'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { analyze, migrate, parseWindow, parseTarget, nameVariants } = require('./check-setting-payoff.js');

// ---------- fixture ----------
// 最小 v2 项目：一份设定文件、一张登记表（四种类型各一）、两章细纲。各用例在此基础上单点破坏。
const SETTING = `# 终端 App 架构
### 1. 【天机】离线知识库
- 功能：海量快照库。
### 2. 【留影】录音
- 高保真静音采集外界声光信号，能当面回放。
### 3. 耗电
- 灵眸场扫描 5%/10 分钟。
### 4. 口癖
- 记小本本上了，别让我逮着。
`;

const REGISTRY = `# 设定登记

| 编号 | 类型 | 来源 | 一句话 | 触发条件 / 窗口 | 兑现目标（读者要理解什么） | 摘录锚点 |
|---|---|---|---|---|---|---|
| SET-001 | payoff | 设定/11_App.md#2. 【留影】录音 | 留影录音取证 | 第1章 | 录音能当面放出来压人 | \`能当面回放\` |
| SET-002 | constraint | 设定/11_App.md#3. 耗电 | AI 耗电 | 凡用灵眸的章 | 用了就得扣 | \`灵眸场扫描 5%/10 分钟\` |
| SET-003 | recurring | 设定/11_App.md#4. 口癖 | 记小本本 | 每 3–5 章 | 记仇不当场发作 | \`记小本本上了\` |
| SET-004 | reserve | 设定/11_App.md | 九宫锁元阵 | 卷4 | — | — |
| SET-005 | payoff | 设定/11_App.md#1. 【天机】离线知识库 | 天机首秀 | 第2章 | 它肚子里有一座库 | \`海量快照库\` |
`;

const CH1 = `# 细纲 第1章《开机》
- 目标情绪：打脸

#### 因果链
- 前因：开篇无前因

#### 设定兑现
| 编号 | 关系 | 本章呈现目标 | 备注 |
|---|---|---|---|
| SET-001 | 兑现 | 读者看到录音当面放出来 | |
| SET-002 | 涉及 | 用了留影，电量得掉 | |
| SET-003 | 兑现 | 五枚金币按桌上那一下 | 首现 |

## 剧情流程
1. 略
`;

const CH2 = `# 细纲 第2章《那顶帽子》

#### 设定兑现
| 编号 | 关系 | 本章呈现目标 | 备注 |
|---|---|---|---|
| SET-005 | 兑现 | 读者知道 AI 肚子里有库 | |
`;

function fixture(over = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'setting-payoff-'));
  for (const sub of ['设定', '大纲', '追踪']) fs.mkdirSync(path.join(dir, sub), { recursive: true });
  fs.writeFileSync(path.join(dir, '设定/11_App.md'), over.setting ?? SETTING, 'utf8');
  if (over.registry !== null) fs.writeFileSync(path.join(dir, '设定/_设定登记.md'), over.registry ?? REGISTRY, 'utf8');
  if (over.ch1 !== null) fs.writeFileSync(path.join(dir, '大纲/细纲_第01章_开机.md'), over.ch1 ?? CH1, 'utf8');
  if (over.ch2 !== null) fs.writeFileSync(path.join(dir, '大纲/细纲_第02章_那顶帽子.md'), over.ch2 ?? CH2, 'utf8');
  if (over.state) fs.writeFileSync(path.join(dir, '追踪/_tracking-state.json'), JSON.stringify(over.state), 'utf8');
  if (over.exempt) fs.writeFileSync(path.join(dir, '设定/_兑现豁免.txt'), over.exempt, 'utf8');
  if (over.board) fs.writeFileSync(path.join(dir, '追踪/设定兑现看板.md'), over.board, 'utf8');
  return dir;
}

const checks = (r, severity) => r.findings.filter((f) => !severity || f.severity === severity).map((f) => f.check);
const enabledState = (last = 0, since = 1) => ({ last_committed_chapter: last, setting_payoff: { enabled: true, schema_version: 1, since_chapter: since } });

// ---------- 解析 ----------
test('窗口与目标解析', () => {
  assert.deepEqual(parseWindow('每 3–5 章'), { min: 3, max: 5 });
  assert.deepEqual(parseWindow('每3-5章'), { min: 3, max: 5 });
  assert.deepEqual(parseWindow('每 2 章'), { min: 2, max: 2 });
  assert.equal(parseWindow('第3章'), null);
  assert.deepEqual(parseTarget('第12章'), { from: 12, to: 12 });
  assert.deepEqual(parseTarget('第 20–25 章'), { from: 20, to: 25 });
  assert.deepEqual(parseTarget('卷2'), { volume: '2' });
  assert.equal(parseTarget('凡用灵眸的章'), null);
});

test('别名归一化沿用 v1 口径', () => {
  assert.ok(nameVariants('退灵符（驱逐符1.0）').includes('驱逐符'));
  assert.ok(nameVariants('保温符/温水符').includes('温水符'));
});

// ---------- 适用判定 ----------
test('干净项目：模式 v2，0 blocking；未启用记账只是 advisory', () => {
  const r = analyze(fixture());
  assert.equal(r.mode, 'v2');
  assert.deepEqual(checks(r, 'blocking'), []);
  assert.ok(checks(r).includes('tracking.not-enabled'));
  assert.equal(Object.keys(r.registry.entries).length, 5);
  assert.equal(r.registry.entries['SET-003'].window.max, 5);
  assert.ok(r.registry.entries['SET-001'].excerpt.includes('能当面回放'));
});

test('既无登记表也无看板＝不适用', () => {
  const r = analyze(fixture({ registry: null }));
  assert.equal(r.notApplicable, true);
  assert.deepEqual(r.findings, []);
});

test('只有 v1 看板 → advisory 提示迁移，不阻断', () => {
  const r = analyze(fixture({ registry: null, board: '# 看板\n## 一、x\n' }));
  assert.equal(r.mode, 'legacy');
  assert.deepEqual(checks(r), ['legacy.board']);
});

test('追踪已启用记账却没有登记表 → blocking', () => {
  const r = analyze(fixture({ registry: null, state: enabledState() }));
  assert.deepEqual(checks(r, 'blocking'), ['registry.missing']);
});

// ---------- 登记表格式 ----------
test('来源文件、标题、锚点任一悬空 → blocking', () => {
  const dangling = REGISTRY
    .replace('设定/11_App.md#2. 【留影】录音', '设定/99_不存在.md#x')
    .replace('#3. 耗电', '#3. 没有这个标题')
    .replace('`记小本本上了`', '`来源里没有这句`');
  const r = analyze(fixture({ registry: dangling }));
  const b = checks(r, 'blocking');
  assert.ok(b.includes('registry.source-dangling'));
  assert.ok(b.includes('registry.heading-dangling'));
  assert.ok(b.includes('registry.anchor-dangling'));
});

test('编号重复、类型非法、编号格式错 → blocking', () => {
  const bad = REGISTRY
    + '| SET-001 | payoff | 设定/11_App.md | 重复 | 第3章 | x | — |\n'
    + '| SET-006 | magic | 设定/11_App.md | 类型错 | 第3章 | x | — |\n'
    + '| SETX-7 | payoff | 设定/11_App.md | 格式错 | 第3章 | x | — |\n';
  const r = analyze(fixture({ registry: bad }));
  const b = checks(r, 'blocking');
  assert.ok(b.includes('registry.duplicate-id'));
  assert.ok(b.includes('registry.type'));
  assert.ok(b.includes('registry.id-format'));
});

test('recurring 缺窗口、payoff 缺锚点/目标 → advisory 不阻断', () => {
  const soft = REGISTRY
    .replace('每 3–5 章', '常常')
    .replace('| 第1章 | 录音能当面放出来压人 | `能当面回放` |', '| 以后 | 录音能当面放出来压人 | — |');
  const r = analyze(fixture({ registry: soft }));
  assert.deepEqual(checks(r, 'blocking'), []);
  const a = checks(r, 'advisory');
  assert.ok(a.includes('registry.window-missing'));
  assert.ok(a.includes('registry.anchor-missing'));
  assert.ok(a.includes('registry.target-missing'));
});

test('登记表存在但没有可识别表头 → blocking', () => {
  const r = analyze(fixture({ registry: '# 设定登记\n\n没有表格。\n' }));
  assert.ok(checks(r, 'blocking').includes('registry.header'));
});

// ---------- 细纲小节 ----------
test('细纲引用未登记/已退役编号、关系词非法、重复 → blocking', () => {
  const retiredRegistry = REGISTRY.replace('| SET-005 | payoff |', '| SET-005 | retired |');
  const ch1 = CH1
    .replace('| SET-002 | 涉及 |', '| SET-002 | 顺带 |')
    .replace('| SET-003 | 兑现 | 五枚金币按桌上那一下 | 首现 |', '| SET-003 | 兑现 | x | |\n| SET-003 | 兑现 | y | |\n| SET-777 | 兑现 | z | |');
  const r = analyze(fixture({ registry: retiredRegistry, ch1 }));
  const b = checks(r, 'blocking');
  assert.ok(b.includes('outline.relation'));
  assert.ok(b.includes('outline.duplicate-id'));
  assert.ok(b.includes('outline.unknown-id'));
  assert.ok(b.includes('outline.retired-id'));
});

test('细纲缺小节：旧章 advisory，启用后的新写章 blocking；写「无」合法', () => {
  const missing = CH2.replace(/#### 设定兑现[\s\S]*$/, '');
  let r = analyze(fixture({ ch2: missing }));
  assert.ok(checks(r, 'advisory').includes('outline.section-missing'));
  assert.deepEqual(checks(r, 'blocking'), []);
  r = analyze(fixture({ ch2: missing, state: enabledState(1, 1) }));
  assert.ok(checks(r, 'blocking').includes('outline.section-missing'));
  r = analyze(fixture({ ch2: '# 第2章\n\n#### 设定兑现\n无\n', state: enabledState(1, 1) }));
  assert.deepEqual(checks(r, 'blocking'), []);
  assert.equal(r.chapters.find((c) => c.chapter === 2).none, true);
});

test('v1 三槽小节未迁移：新写章 blocking', () => {
  const v1 = '# 第2章\n\n## 设定兑现槽\n| 设定编号 | 物证 | 动作 | 梗 |\n|---|---|---|---|\n| **SET-005** | a | b | c |\n';
  const r = analyze(fixture({ ch2: v1, state: enabledState(1, 1) }));
  assert.ok(checks(r, 'blocking').includes('outline.legacy-slot'));
});

test('不适用不写原因、兑现不写目标 → advisory', () => {
  const ch1 = CH1
    .replace('| SET-001 | 兑现 | 读者看到录音当面放出来 | |', '| SET-001 | 不适用 | | |')
    .replace('| SET-003 | 兑现 | 五枚金币按桌上那一下 | 首现 |', '| SET-003 | 兑现 | | |');
  const r = analyze(fixture({ ch1 }));
  const a = checks(r, 'advisory');
  assert.ok(a.includes('outline.na-reason'));
  assert.ok(a.includes('outline.goal-missing'));
  assert.deepEqual(checks(r, 'blocking'), []);
});

// ---------- 排期一致性 ----------
test('payoff 目标章已在细纲范围内却没人排 → advisory，--strict 升 blocking；目标在未来只是普通 advisory', () => {
  let r = analyze(fixture({ ch2: CH2.replace('SET-005', 'SET-001') }));
  assert.ok(checks(r, 'advisory').includes('schedule.unscheduled-due'));
  r = analyze(fixture({ ch2: CH2.replace('SET-005', 'SET-001') }), { strict: true });
  assert.ok(checks(r, 'blocking').includes('schedule.unscheduled-due'));
  const future = REGISTRY.replace('| 第2章 | 它肚子里有一座库 |', '| 第9章 | 它肚子里有一座库 |');
  r = analyze(fixture({ registry: future, ch2: '# 第2章\n\n#### 设定兑现\n无\n' }), { strict: true });
  assert.ok(checks(r, 'advisory').includes('schedule.unscheduled'));
  assert.deepEqual(checks(r, 'blocking'), []);
});

test('reserve 被排入兑现、payoff 排在目标章之外 → advisory', () => {
  const ch2 = CH2 + '| SET-004 | 兑现 | 提前用阵 | |\n';
  const r = analyze(fixture({ ch2: ch2.replace('| SET-005 | 兑现 |', '| SET-005 | 兑现 |'), ch1: CH1.replace('| SET-003 | 兑现 | 五枚金币按桌上那一下 | 首现 |', '| SET-003 | 兑现 | 五枚金币按桌上那一下 | 首现 |\n| SET-005 | 兑现 | 提前到第1章 | |') }));
  const a = checks(r, 'advisory');
  assert.ok(a.includes('schedule.reserve-early'));
  assert.ok(a.includes('schedule.target-mismatch'));
  assert.deepEqual(checks(r, 'blocking'), []);
});

// ---------- 章级输出 ----------
test('--chapter 输出本章行、类型与规则摘录；找不到细纲 → blocking', () => {
  const r = analyze(fixture(), { chapter: 1 });
  assert.equal(r.chapter.rows.length, 3);
  const row = r.chapter.rows.find((x) => x.id === 'SET-002');
  assert.equal(row.type, 'constraint');
  assert.ok(row.excerpt.includes('灵眸场扫描'));
  const missing = analyze(fixture(), { chapter: 7 });
  assert.ok(checks(missing, 'blocking').includes('chapter.outline-missing'));
});

// ---------- 零落点 ----------
test('具名实体零落点 advisory；豁免清单可压掉；--strict 升 blocking', () => {
  const setting = SETTING + '### 5. 【万籁】局域魔波\n- 卷2解锁。\n';
  let r = analyze(fixture({ setting }));
  assert.ok(r.findings.some((f) => f.check === 'setting.orphan-entity' && f.message.includes('万籁')));
  r = analyze(fixture({ setting, exempt: '【万籁】\n' }));
  assert.ok(!r.findings.some((f) => f.message.includes('万籁')));
  r = analyze(fixture({ setting }), { strict: true });
  assert.ok(r.findings.some((f) => f.check === 'setting.orphan-entity' && f.severity === 'blocking'));
});

// ---------- 迁移 ----------
const V1_BOARD = `# 设定兑现看板

## 一、一次性交付设定排期表

| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 兑现简记 |
|---|---|---|---|---|---|
| **SET-11A** | 留影首秀 | 第 01 章 | 当众回放录音 | \`[已排期-第1章]\` | — |

## 二、贯穿型设定核销表

| 设定编号 | 贯穿内容 | 每章核销口径 | 状态 | 已兑现章次记录 |
|---|---|---|---|---|
| **SET-11** | 手机日常辅助 | 本章 AI 出场前算过电了吗 | \`[贯穿循环]\` | — |

## 三、暗线与高阶设定兑现备忘录（中后期池）

- \`[待排期]\` **SET-11F（【万籁】）**：局域魔波收发（预计卷 2）。
`;
const V1_CH1 = `# 细纲 第1章

## 设定兑现槽（写正文前必须填满）

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|
| **SET-11A** | 那段录音 | 主角按下外放 | "这笔记下了" |

**本章贯穿槽**：
- SET-11 演"报电量"：AI 说只剩 1%。

## 剧情流程
1. 略
`;

test('--migrate：v1 看板与三槽 → 登记表 + 「#### 设定兑现」，看板改名，复跑 0 blocking', () => {
  const dir = fixture({ registry: null, ch1: V1_CH1, ch2: null, board: V1_BOARD });
  const report = migrate(dir);
  assert.equal(report.registryRows, 3);
  assert.deepEqual(report.outlines, ['大纲/细纲_第01章_开机.md']);
  assert.ok(fs.existsSync(path.join(dir, '追踪/设定兑现看板_已退役.md')));
  assert.ok(!fs.existsSync(path.join(dir, '追踪/设定兑现看板.md')));
  const registry = fs.readFileSync(path.join(dir, '设定/_设定登记.md'), 'utf8');
  assert.match(registry, /\| SET-11A \| payoff \| 设定\/11_App\.md \| 留影首秀 \| 第1章 \|/);
  assert.match(registry, /\| SET-11 \| recurring \|/);
  assert.match(registry, /\| SET-11F \| reserve \|.*卷 2/);
  const ch1 = fs.readFileSync(path.join(dir, '大纲/细纲_第01章_开机.md'), 'utf8');
  assert.ok(ch1.includes('#### 设定兑现'));
  assert.ok(!ch1.includes('## 设定兑现槽'));
  assert.match(ch1, /\| SET-11A \| 兑现 \| 那段录音；主角按下外放；"这笔记下了" \| 由 v1 三槽迁移 \|/);
  assert.match(ch1, /\| SET-11 \| 兑现 \| .*报电量.* \| 由 v1 贯穿槽迁移 \|/);
  assert.ok(ch1.includes('## 剧情流程'));
  const r = analyze(dir);
  assert.equal(r.mode, 'v2');
  assert.deepEqual(checks(r, 'blocking'), []);
  assert.throws(() => migrate(dir), /已存在|无可迁移/);
});

const { sources, DIMENSIONS } = require('./setting-readiness.js');
function reviewReceipt(dir, issues = []) {
  const receipt = {
    schema: 'setting-readiness/v1', reviewer: 'fixture semantic reviewer', sources: sources(dir),
    checks: DIMENSIONS.map(id => ({ id, status: issues.some(i => i.dimension === id) ? 'open' : 'ready', reason: 'Fixture explicitly supplies stable rules and their dependencies.' })), issues,
  };
  fs.writeFileSync(path.join(dir, '设定/_设定审查.json'), JSON.stringify(receipt));
  return receipt;
}

test('写前门：缺少审查被拦，完成记录后通过，来源变更后过期', () => {
  const dir = fixture({state: enabledState()});
  try {
    assert.ok(checks(analyze(dir, {chapter: 1, readiness: true}), 'blocking').includes('readiness.missing'));
    reviewReceipt(dir);
    assert.equal(checks(analyze(dir, {chapter: 1, readiness: true}), 'blocking').length, 0);
    fs.appendFileSync(path.join(dir, '设定/11_App.md'), '\n新增规则');
    assert.ok(checks(analyze(dir, {chapter: 1, readiness: true}), 'blocking').includes('readiness.stale'));
  } finally { fs.rmSync(dir, {recursive:true, force:true}); }
});

test('写前门：未来缺口不挡当前，到受影响章必须回对应阶段', () => {
  const dir = fixture({state: enabledState()});
  try {
    reviewReceipt(dir, [{dimension:'closure',severity:'blocking',problem:'结局尚未裁决',from_chapter:2,to_chapter:null,return_to:'outline',next_action:'确定结局及代价'}]);
    assert.equal(checks(analyze(dir, {chapter:1,readiness:true}), 'blocking').length, 0);
    const result = analyze(dir,{chapter:2,readiness:true});
    assert.ok(result.findings.some(f => f.check === 'readiness.unresolved' && f.message.includes('outline')));
  } finally { fs.rmSync(dir,{recursive:true,force:true}); }
});

test('写前门：遗漏维度、无原因、open 无缺口都不能盖章', () => {
  const dir = fixture({state:enabledState()});
  try {
    const receipt = reviewReceipt(dir);
    receipt.checks.pop(); receipt.checks[0].status='open';receipt.checks[1].reason='';
    fs.writeFileSync(path.join(dir,'设定/_设定审查.json'),JSON.stringify(receipt));
    const result = checks(analyze(dir,{chapter:1,readiness:true}),'blocking');
    for (const id of ['readiness.dimension','readiness.issue-missing','readiness.conclusion']) assert.ok(result.includes(id));
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('写前门：删文件、新增文件都会使审查记录过期', () => {
  const dir=fixture({state:enabledState()});
  try {
    reviewReceipt(dir);fs.writeFileSync(path.join(dir,'设定/新地点.md'),'# 地点');
    assert.ok(checks(analyze(dir,{chapter:1,readiness:true})).includes('readiness.stale'));
    reviewReceipt(dir);fs.unlinkSync(path.join(dir,'设定/新地点.md'));
    assert.ok(checks(analyze(dir,{chapter:1,readiness:true})).includes('readiness.stale'));
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('写前门：不能把 legacy 或未启用解释为 PASS', () => {
  for (const over of [{registry:null,board:'# 看板'},{}]) {
    const dir=fixture(over);
    try {assert.ok(checks(analyze(dir,{chapter:1,readiness:true}),'blocking').includes('readiness.not-enabled'));}
    finally {fs.rmSync(dir,{recursive:true,force:true});}
  }
});

test('写前门：登记未排目标章、空目标、无效窗口不能通过', () => {
  const dir=fixture({state:enabledState(),registry:REGISTRY.replace('每 3–5 章','每 0 章').replace('录音能当面放出来压人','—'),ch1:CH1.replace('| SET-001 | 兑现 | 读者看到录音当面放出来 | |','')});
  try {
    reviewReceipt(dir);
    const result=checks(analyze(dir,{chapter:1,readiness:true}),'blocking');
    for(const id of ['registry.window-missing','registry.goal-missing','schedule.unscheduled-due']) assert.ok(result.includes(id));
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});
