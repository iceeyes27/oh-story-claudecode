#!/usr/bin/env node
'use strict'

const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawnSync } = require('child_process')

const repoRoot = path.resolve(__dirname, '..')
const verifier = path.join(repoRoot, 'skills/story-write/scripts/check-outline-contract.js')
const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), 'outline-contract-'))

const FIELDS = [
  ['核心事件', '江晨拿到伴奏后决定去老兵家里听故事'],
  ['字数目标', '2300 字'],
  ['字数口径', 'visible_chars_v1'],
  ['阶段位置', '收尾期 · 第2阶段第11章'],
  ['单元ID/位置', 'U03；单元内第 1 拍'],
  ['目标情绪', '家国；踏实的期待 → 被托付的沉重'],
  ['主角目标/关键选择', '要真实素材；在报批与先去听故事之间选一个'],
  ['结尾拍ID/类型', 'EB-01-021；relationship；老人把铁盒交给江晨'],
  ['期待ID/类型', 'EX-01-021；choice；江晨如何使用这份托付'],
  ['读者验收预期', 'must_know=[托付成立]；may_believe=[铁盒只关乎旧事]；must_not_know=[终局表彰]；open_ids=[EX-01-021]'],
  ['章节定位', '推进'],
  ['本章结构公式', '接到邀约 + 上门 + 老兵开口 + 立下承诺'],
  ['章首钩子', '悬念前置 — 老人把铁盒推过来'],
  ['爽点', '无显性爽点，功能是把宏大叙事落到具体的人身上'],
  ['本章禁止提前释放', '铁盒内容与终局表彰的关系'],
  ['契约风险', '契约安全'],
]

function outline(overrides = {}) {
  const fields = FIELDS
    .filter(([name]) => overrides.dropField !== name)
    .map(([name, value]) => `- ${name}：${overrides.fieldValues?.[name] ?? value}`)
  if (overrides.p1 !== undefined) {
    fields.splice(10, 0, `- P1质量契约：${JSON.stringify(overrides.p1)}`)
  }
  const table = overrides.plotTable ?? [
    '| # | 情节点（谁做了什么） | 功能标签 | 执行边界 |',
    '|---|---|---|---|',
    '| 1 | 江晨接到邀约 | 铺垫 | 只给邀约，不提铁盒 |',
    '| 2 | 老人推过铁盒 | 高潮 | 只讲当年，不评价当下 |',
  ].join('\n')
  const acts = ['起因', '发展', '转折', '高潮', '结尾']
    .filter((act) => overrides.dropAct !== act)
    .map((act) => `- ${act}：本章${act}内容`)
  return [
    '## 细纲（第 21 章）',
    '',
    '### 第 21 章：新的伴奏',
    ...fields,
    '',
    '#### 内容概括（五段式）',
    ...acts,
    '',
    '#### 情节安排（多线）',
    '- 主线推进：新作品素材来源确定',
    '- 辅线推进：无',
    '- 逻辑线：拿到伴奏 → 缺素材 → 接受邀约 → 背上承诺',
    '',
    '#### 人物关系和出场顺序',
    '- 出场顺序：江晨、赵大柱',
    '- 人物关系变化：陌生受访者 → 托付关系',
    '',
    '#### 情节细化',
    '- 情节点序列（逐行填下表）：',
    '',
    table,
    '',
  ].join('\n')
}

function writeCase(name, body) {
  const dir = path.join(tmpRoot, name, '大纲')
  fs.mkdirSync(dir, { recursive: true })
  if (body !== null) fs.writeFileSync(path.join(dir, '细纲_第021章.md'), body, 'utf8')
  return path.join(tmpRoot, name)
}

function run(project, chapter = '21', options = {}) {
  const args = [verifier, '--json']
  if (options.requireP1) args.push('--require-p1')
  args.push('--project', project, '--chapter', chapter)
  const result = spawnSync(process.execPath, args, {
    cwd: repoRoot,
    encoding: 'utf8',
  })
  let report = null
  if (result.stdout.trim()) report = JSON.parse(result.stdout)
  return { ...result, report }
}

const failureIds = (result) => result.report.failures.map((failure) => failure.id)

try {
  // 模板齐全的细纲必须通过 —— 这是误报防线，先测它。
  const good = run(writeCase('valid', outline()))
  assert.strictEqual(good.status, 0, good.stdout + good.stderr)
  assert.strictEqual(good.report.ok, true)
  assert.deepStrictEqual(good.report.failures, [])

  // legacy 细纲默认兼容；只有显式 P1 模式才要求 P1质量契约。
  const legacyRequired = run(writeCase('legacy-required', outline()), '21', { requireP1: true })
  assert.strictEqual(legacyRequired.status, 1)
  assert(failureIds(legacyRequired).includes('outline.p1-required'))

  const validP1 = {
    chapter_function: '推进',
    target_emotion_id: 'EMO-01-021',
    required_deliveries: ['choice-consequence'],
    allowed_expectation_ids: ['EX-01-021'],
    allowed_hypothesis_ids: [],
    intentional_ambiguity: false,
    scene_catalog: [
      { scene_id: 'scene-1', scene_index: 1 },
      { scene_id: 'scene-2', scene_index: 2 },
    ],
  }
  const p1Good = run(writeCase('p1-valid', outline({ p1: validP1 })), '21', { requireP1: true })
  assert.strictEqual(p1Good.status, 0, p1Good.stdout + p1Good.stderr)

  const missingCatalog = { ...validP1 }
  delete missingCatalog.scene_catalog
  const p1Missing = run(writeCase('p1-missing-catalog', outline({ p1: missingCatalog })), '21', { requireP1: true })
  assert.strictEqual(p1Missing.status, 1)
  assert(failureIds(p1Missing).includes('outline.p1-quality-contract'))

  const p1OutOfOrder = run(writeCase('p1-out-of-order', outline({
    p1: { ...validP1, scene_catalog: [
      { scene_id: 'scene-1', scene_index: 2 },
      { scene_id: 'scene-2', scene_index: 1 },
    ] },
  })), '21', { requireP1: true })
  assert.strictEqual(p1OutOfOrder.status, 1)

  const p1Duplicate = run(writeCase('p1-duplicate', outline({
    p1: { ...validP1, scene_catalog: [
      { scene_id: 'scene-1', scene_index: 1 },
      { scene_id: 'scene-1', scene_index: 2 },
    ] },
  })), '21', { requireP1: true })
  assert.strictEqual(p1Duplicate.status, 1)

  const p1TableMismatch = run(writeCase('p1-table-mismatch', outline({
    p1: { ...validP1, scene_catalog: [{ scene_id: 'scene-1', scene_index: 1 }] },
  })), '21', { requireP1: true })
  assert.strictEqual(p1TableMismatch.status, 1)

  // 值未定时写 [待补充] 是契约允许的写法，不能因此判失败。
  const pending = run(writeCase('pending-value', outline({
    fieldValues: { 契约风险: '[待补充]', 单元ID位置: '[待补充]' },
  })))
  assert.strictEqual(pending.status, 0, pending.stdout + pending.stderr)
  assert.strictEqual(pending.report.ok, true)

  // 加粗字段名与半角冒号也要认，否则会误伤正常写法。
  const boldHalfWidth = outline().replace('- 目标情绪：', '- **目标情绪**: ')
  const bold = run(writeCase('bold-halfwidth', boldHalfWidth))
  assert.strictEqual(bold.status, 0, bold.stdout + bold.stderr)

  // 目标情绪 / 主角目标·关键选择 实测直接影响正文，不接受占位符……
  const hollowIntent = run(writeCase('hollow-intent', outline({
    fieldValues: { 目标情绪: '[待补充]' },
  })))
  assert.strictEqual(hollowIntent.status, 1)
  assert(failureIds(hollowIntent).includes('outline.intent-fields-substantive'))
  assert.match(hollowIntent.report.failures.find((f) => f.id === 'outline.intent-fields-substantive').evidence, /目标情绪/)

  const hollowGoal = run(writeCase('hollow-goal', outline({
    fieldValues: { '主角目标/关键选择': '[待补充]' },
  })))
  assert.strictEqual(hollowGoal.status, 1)
  assert(failureIds(hollowGoal).includes('outline.intent-fields-substantive'))

  const badReaderContract = run(writeCase('bad-reader-contract', outline({
    fieldValues: { '期待ID/类型': '强悬念' },
  })))
  assert.strictEqual(badReaderContract.status, 1)
  assert(failureIds(badReaderContract).includes('outline.reader-contract'))

  // ……但其余字段仍按契约允许 [待补充]，不能因此判失败。
  const hollowOther = run(writeCase('hollow-other', outline({
    fieldValues: { 契约风险: '[待补充]', 章节定位: '[待补充]' },
  })))
  assert.strictEqual(hollowOther.status, 0, hollowOther.stdout + hollowOther.stderr)
  assert.strictEqual(hollowOther.report.ok, true)

  const dropped = run(writeCase('missing-field', outline({ dropField: '目标情绪' })))
  assert.strictEqual(dropped.status, 1)
  assert.deepStrictEqual(failureIds(dropped), ['outline.required-fields'])
  assert.match(dropped.report.failures[0].evidence, /目标情绪/)
  assert.strictEqual(dropped.report.repair_scope.length, 1)
  assert.match(dropped.report.repair_scope[0].repair, /\[待补充\]/)

  const noAct = run(writeCase('missing-act', outline({ dropAct: '转折' })))
  assert.strictEqual(noAct.status, 1)
  assert.deepStrictEqual(failureIds(noAct), ['outline.five-act'])

  // 情节点写成编号列表（当前最常见的偏离）必须被判出来。
  const listStyle = run(writeCase('plot-as-list', outline({
    plotTable: '1. 江晨接到邀约【铺垫】\n2. 老人推过铁盒【高潮】',
  })))
  assert.strictEqual(listStyle.status, 1)
  assert.deepStrictEqual(failureIds(listStyle), ['outline.plotpoint-table'])

  // 三列表格缺执行边界，也是偏离。
  const threeCol = run(writeCase('plot-three-col', outline({
    plotTable: '| # | 情节点 | 功能标签 |\n|---|---|---|\n| 1 | 江晨接到邀约 | 铺垫 |',
  })))
  assert.strictEqual(threeCol.status, 1)
  assert.deepStrictEqual(failureIds(threeCol), ['outline.plotpoint-table'])

  const badTarget = run(writeCase('bad-target', outline({ fieldValues: { 字数目标: '很多字' } })))
  assert.strictEqual(badTarget.status, 1)
  assert(failureIds(badTarget).includes('outline.wordcount-target'))

  const badEmotion = run(writeCase('bad-emotion', outline({ fieldValues: { 目标情绪: '家国泪目' } })))
  assert.strictEqual(badEmotion.status, 1)
  assert(failureIds(badEmotion).includes('outline.emotion-vocab'))

  const noCaliber = run(writeCase('no-caliber', outline({ fieldValues: { 字数口径: 'chars' } })))
  assert.strictEqual(noCaliber.status, 1)
  assert.deepStrictEqual(failureIds(noCaliber), ['outline.wordcount-target'])

  const missingFile = run(writeCase('missing-file', null))
  assert.strictEqual(missingFile.status, 2)
  assert.match(missingFile.stderr, /没有第 21 章细纲/)

  const invalid = spawnSync(process.execPath, [verifier, '--unknown'], { cwd: repoRoot, encoding: 'utf8' })
  assert.strictEqual(invalid.status, 2)
  assert.match(invalid.stderr, /用法/)

  process.stdout.write('outline-contract: all tests passed\n')
} finally {
  fs.rmSync(tmpRoot, { recursive: true, force: true })
}
