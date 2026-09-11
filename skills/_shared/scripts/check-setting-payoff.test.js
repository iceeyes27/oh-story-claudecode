'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const { analyze, nameVariants } = require('./check-setting-payoff.js');

// ---------- fixture ----------
// 一个最小可用项目：11 号设定定义两个 App，看板把 SET-11A 排到第 1 章，
// 第 1 章细纲的兑现槽写了 SET-11A。各用例在此基础上单点破坏。
function fixture(over = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'setting-payoff-'));
  fs.mkdirSync(path.join(dir, '设定'), { recursive: true });
  fs.mkdirSync(path.join(dir, '大纲'), { recursive: true });
  fs.mkdirSync(path.join(dir, '追踪'), { recursive: true });

  const setting11 = over.setting11 ?? `# 终端 App 架构
### 1. 【天机】离线知识库
- 功能：海量快照库。
### 2. 【神算】魔药平衡器
- 功能：坩埚解算。
`;
  const setting02 = over.setting02 ?? `# 角色卡
## 核心配角
| 角色 | 定位 |
|---|---|
| 比尔·韦斯莱 | 引路学长 |
| 查理·韦斯莱 | 近程引路人 |
`;
  const board = over.board ?? `# 设定兑现看板

## 一、一次性交付设定排期表

| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 兑现简记 |
|---|---|---|---|---|---|
| **SET-11A** | 天机首秀 | 第 01 章 | 翻出条款 | \`[已排期-第1章]\` | — |

## 二、贯穿型设定核销表

| 设定编号 | 贯穿内容 | 核销口径 | 状态 | 记录 |
|---|---|---|---|---|
| **SET-02** | 性格样本 | 每章一条 | \`[贯穿循环]\` | — |

## 三、中后期池

- \`[待排期]\` **SET-11B（【神算】）**：卷 2 起。
`;
  const ch1 = over.ch1 ?? `# 细纲 第1章《开机》

## 设定兑现槽

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|
| **SET-11A** | 【天机】翻出的条款 | 主角当众念条款 | 记小本本 |

## 剧情流程
1. 略
`;

  fs.writeFileSync(path.join(dir, '设定', '11_终端App架构.md'), setting11);
  fs.writeFileSync(path.join(dir, '设定', '02_角色卡.md'), setting02);
  fs.writeFileSync(path.join(dir, '追踪', '设定兑现看板.md'), board);
  fs.writeFileSync(path.join(dir, '大纲', '细纲_第01章_开机.md'), ch1);
  if (over.extraFiles) for (const [rel, body] of Object.entries(over.extraFiles)) {
    fs.mkdirSync(path.dirname(path.join(dir, rel)), { recursive: true });
    fs.writeFileSync(path.join(dir, rel), body);
  }
  return dir;
}

const codes = (r) => r.findings.map((f) => f.check);
const blocking = (r) => r.findings.filter((f) => f.severity === 'blocking');

// ---------- 基线 ----------
test('干净项目：0 blocking，且两个角色都不算零落点', () => {
  const dir = fixture({
    ch1: `# 细纲 第1章《开机》

## 设定兑现槽

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|
| **SET-11A** | 【天机】翻出的条款 | 比尔和查理看着主角念条款 | 记小本本 |

## 剧情流程
1. 略
`,
  });
  const r = analyze(dir);
  assert.equal(blocking(r).length, 0);
  assert.ok(!codes(r).includes('setting.orphan-character'));
});

// ---------- 这次踩过的五类坑 ----------
test('状态词非法（[正文待写] 这类自造状态）→ blocking', () => {
  const dir = fixture({
    board: fixture.toString() && `# 看板
## 一、一次性交付设定排期表
| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 简记 |
|---|---|---|---|---|---|
| **SET-11A** | 天机首秀 | 第 01 章 | 翻出条款 | \`[正文待写]\` | — |
`,
  });
  const r = analyze(dir);
  assert.ok(codes(r).includes('board.state-vocab'));
  assert.ok(blocking(r).length > 0);
});

test('编号的两位数字没有对应设定文件 → blocking', () => {
  const dir = fixture({
    board: `# 看板
## 一、一次性交付设定排期表
| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 简记 |
|---|---|---|---|---|---|
| **SET-99A** | 不存在的设定 | 第 01 章 | 无 | \`[已排期-第1章]\` | — |
`,
  });
  const r = analyze(dir);
  assert.ok(codes(r).includes('board.id-orphan'));
});

test('看板排了但没有任何一章细纲写槽 → blocking', () => {
  const dir = fixture({
    ch1: `# 细纲 第1章《开机》

## 设定兑现槽

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|

## 剧情流程
1. 略
`,
  });
  const r = analyze(dir);
  assert.ok(codes(r).includes('board.outline-sync'));
});

test('看板排期章与槽位实际所在章不一致 → blocking', () => {
  const dir = fixture({
    board: `# 看板
## 一、一次性交付设定排期表
| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 简记 |
|---|---|---|---|---|---|
| **SET-11A** | 天机首秀 | 第 07 章 | 翻出条款 | \`[已排期-第7章]\` | — |
`,
  });
  const r = analyze(dir);
  assert.ok(codes(r).includes('board.schedule-match'));
});

test('三槽位没填满 → blocking', () => {
  const dir = fixture({
    ch1: `# 细纲 第1章《开机》

## 设定兑现槽

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|
| **SET-11A** | 【天机】翻出的条款 | — | [待补充] |

## 剧情流程
1. 略
`,
  });
  const r = analyze(dir);
  assert.ok(codes(r).includes('slot.three-columns'));
});

test('具名 App 零落点（本次的【天机】漏排）→ advisory，--strict 升 blocking', () => {
  // 槽位里改用【神算】，于是【天机】变成零落点——这正是"App 被错记成另一个 App"的可检测形态
  const ch1 = `# 细纲 第1章《开机》

## 设定兑现槽

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|
| **SET-11A** | 【神算】翻出的条款 | 主角当众念条款 | 记小本本 |

## 剧情流程
1. 略
`;
  const board = `# 看板
## 一、一次性交付设定排期表
| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 简记 |
|---|---|---|---|---|---|
| **SET-11A** | 首秀 | 第 01 章 | 翻出条款 | \`[已排期-第1章]\` | — |
`;
  const loose = analyze(fixture({ ch1, board }));
  const hit = loose.findings.filter((f) => f.check === 'setting.orphan-entity' && f.message.includes('天机'));
  assert.equal(hit.length, 1);
  assert.equal(hit[0].severity, 'advisory');

  const strict = analyze(fixture({ ch1, board }), { strict: true });
  assert.ok(strict.findings.some((f) => f.check === 'setting.orphan-entity' && f.severity === 'blocking'));
});

test('角色零落点（本次的查理漏排）→ advisory', () => {
  const dir = fixture(); // 默认 ch1 只提主角，比尔/查理都没出现
  const names = dir && analyze(dir).findings
    .filter((f) => f.check === 'setting.orphan-character')
    .map((f) => f.message);
  assert.ok(names.some((m) => m.includes('查理')));
  assert.ok(names.some((m) => m.includes('比尔')));
});

test('槽内引用了别的设定文件定义的能力 → advisory（跨设定联动需确认）', () => {
  const dir = fixture({
    setting02: `# 角色卡
## 核心配角
| 角色 | 定位 |
|---|---|
| 比尔·韦斯莱 | 引路学长 |
| 查理·韦斯莱 | 近程引路人 |

附：【某专属手法】只归 02 号。
`,
    ch1: `# 细纲 第1章《开机》

## 设定兑现槽

| 设定编号 | 物证 / 功能槽 | 角色交互动作槽 | 中式 / 梗落点槽 |
|---|---|---|---|
| **SET-11A** | 【天机】条款＋【某专属手法】 | 比尔和查理围观 | 记小本本 |

## 剧情流程
1. 略
`,
  });
  const r = analyze(dir);
  assert.ok(r.findings.some((f) => f.check === 'slot.capability-owner' && f.message.includes('某专属手法')));
});

// ---------- 噪音控制 ----------
test('别名归一化：全名/斜杠别名/括号旧称/并列合写，任一变体落地即不算零落点', () => {
  assert.ok(nameVariants('退灵符（驱逐符1.0）').includes('驱逐符'));
  assert.ok(nameVariants('保温符/温水符').includes('温水符'));
  assert.ok(nameVariants('尼法朵拉·唐克斯').includes('唐克斯'));
  assert.ok(nameVariants('亚瑟与玛莎·霍尔特').includes('亚瑟'));
  assert.ok(nameVariants('亚瑟与玛莎·霍尔特').includes('玛莎'));
});

test('属性表首列（本体/人格/语言）不得被当成角色名', () => {
  const dir = fixture({
    setting02: `# 角色卡
## AI 终端
| 项 | 设定 |
|---|---|
| 本体 | 魔改手机 |
| 人格 | 赛博老妈子 |
| 语言 | 中英混说 |

## 核心配角
| 角色 | 定位 |
|---|---|
| 比尔·韦斯莱 | 引路学长 |
`,
  });
  const msgs = analyze(dir).findings.filter((f) => f.check === 'setting.orphan-character').map((f) => f.message);
  for (const field of ['本体', '人格', '语言']) {
    assert.ok(!msgs.some((m) => m.includes(`「${field}」`)), `${field} 被误判为角色名`);
  }
});

test('_兑现豁免.txt 声明的条目不再报零落点', () => {
  const base = { extraFiles: { '设定/_兑现豁免.txt': '# 连招名，不单独排期\n【某连招】\n查理·韦斯莱\n' },
    setting11: `# 终端 App 架构
### 1. 【天机】离线知识库
### 2. 【神算】魔药平衡器
### 连招一：【某连招】
` };
  const r = analyze(fixture(base));
  const msgs = r.findings.filter((f) => /orphan/.test(f.check)).map((f) => f.message);
  assert.ok(!msgs.some((m) => m.includes('某连招')));
  assert.ok(!msgs.some((m) => m.includes('查理')));
});

test('细纲缺「## 设定兑现槽」小节 → blocking', () => {
  const dir = fixture({ ch1: `# 细纲 第1章《开机》\n\n## 剧情流程\n1. 略\n` });
  const r = analyze(dir);
  assert.ok(codes(r).includes('outline.slot-missing'));
});

test('未建看板的项目＝不适用，不是不合格（存量项目不被误伤）', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'setting-payoff-none-'));
  fs.mkdirSync(path.join(dir, '设定'), { recursive: true });
  fs.writeFileSync(path.join(dir, '设定', '世界观.md'), '# 无编号前缀的老设定\n');
  const r = analyze(dir);
  assert.equal(r.notApplicable, true);
  assert.equal(r.findings.length, 0);
});

test('已建看板但设定文件没有两位数字前缀 → blocking', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'setting-payoff-nopfx-'));
  fs.mkdirSync(path.join(dir, '设定'), { recursive: true });
  fs.mkdirSync(path.join(dir, '追踪'), { recursive: true });
  fs.mkdirSync(path.join(dir, '大纲'), { recursive: true });
  fs.writeFileSync(path.join(dir, '设定', '世界观.md'), '# 老设定\n');
  fs.writeFileSync(path.join(dir, '追踪', '设定兑现看板.md'), '# 看板\n## 一、排期表\n');
  const r = analyze(dir);
  assert.ok(r.findings.some((f) => f.check === 'project.settings' && f.severity === 'blocking'));
});

// ---------- 布局 B：导入书的目录式设定 + 看板编号映射 ----------
function importFixture(mapLine = '- **11** → 设定/世界观/App架构.md') {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'setting-payoff-import-'));
  fs.mkdirSync(path.join(dir, '设定', '世界观'), { recursive: true });
  fs.mkdirSync(path.join(dir, '追踪'), { recursive: true });
  fs.mkdirSync(path.join(dir, '大纲'), { recursive: true });
  fs.writeFileSync(path.join(dir, '设定', '世界观', 'App架构.md'), '# 架构\n### 【天机】离线库\n');
  fs.writeFileSync(path.join(dir, '追踪', '设定兑现看板.md'), `# 看板

## 编号映射
${mapLine}

## 一、一次性交付设定排期表
| 设定编号 | 模块 | 目标交付章节 | 兑现行为形态 | 当前状态 | 简记 |
|---|---|---|---|---|---|
| **SET-11A** | 天机首秀 | 第 01 章 | 翻出条款 | \`[已排期-第1章]\` | — |
`);
  fs.writeFileSync(path.join(dir, '大纲', '细纲_第01章_开机.md'), `# 细纲

## 设定兑现槽

| 设定编号 | 物证 | 动作 | 梗 |
|---|---|---|---|
| **SET-11A** | 【天机】条款 | 主角念条款 | 记小本本 |

## 剧情流程
1. 略
`);
  return dir;
}

test('导入书布局：看板「编号映射」把 NN 指到目录式设定文件，0 blocking', () => {
  const r = analyze(importFixture());
  assert.equal(r.findings.filter((f) => f.severity === 'blocking').length, 0);
});

test('编号映射指向不存在的文件 → blocking（防静默漏检）', () => {
  const r = analyze(importFixture('- **11** → 设定/世界观/不存在.md'));
  assert.ok(r.findings.some((f) => f.check === 'idmap.dangling' && f.severity === 'blocking'));
});
