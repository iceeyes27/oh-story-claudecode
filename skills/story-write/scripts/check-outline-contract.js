#!/usr/bin/env node
/**
 * Deterministic 细纲 structural verifier for story-long-write.
 *
 * Usage:
 *   node scripts/check-outline-contract.js --json <细纲路径...>
 *   node scripts/check-outline-contract.js --json --project <书目录> --chapter N
 *   add --require-p1 to require and validate the P1 quality contract
 * Exit: 0 = pass, 1 = blocking contract failures, 2 = invalid invocation.
 *
 * Scope is structural only: it decides whether the blueprint carries the fields,
 * subsections and table shape the authoritative template names. It never judges
 * whether a value is good. The contract itself sets this granularity —
 * artifact-protocols.md 要求未知字段写 `[待补充]`，所以字段必须在场，值可以未知。
 */

'use strict'

const fs = require('fs')
const path = require('path')

// 权威模板：references/workflow-setup.md「细纲（全书每章）」
const FIELDS = [
  '核心事件', '字数目标', '字数口径', '阶段位置', '单元ID/位置', '目标情绪',
  '主角目标/关键选择', '结尾拍ID/类型', '期待ID/类型', '读者验收预期',
  '章节定位', '本章结构公式', '章首钩子', '爽点',
  '本章禁止提前释放', '契约风险',
]
const P1_FIELD = 'P1质量契约'
const SUBSECTIONS = ['内容概括', '情节安排', '人物关系和出场顺序', '情节细化']
const FIVE_ACT = ['起因', '发展', '转折', '高潮', '结尾']
const PLOT_HEADER_FIRST = /^(?:#|序号)$/
// 这两个字段实测直接影响正文质量，必须有实际内容
const INTENT_FIELDS = ['目标情绪', '主角目标/关键选择', '结尾拍ID/类型', '期待ID/类型', '读者验收预期']
const CALIBER = 'visible_chars_v1'
const EMOTION_VOCAB_PATH = path.join(__dirname, '..', '..', '_shared', 'references', 'target-emotion-vocab.md')

function loadEmotionVocab(file) {
  const text = fs.readFileSync(file, 'utf8')
  return new Set(
    text.split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.startsWith('- '))
      .map((line) => line.slice(2).trim())
      .filter(Boolean),
  )
}

function emotionToken(value) {
  return String(value || '').split(/[；;：:→\s]/).find(Boolean) || ''
}

function fieldPattern(name) {
  // 允许 -/*/+ 项目符号、可选 ** 加粗、全角或半角冒号
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return new RegExp(`^\\s*[-*+]\\s*\\*{0,2}${escaped}\\*{0,2}\\s*[：:]`, 'm')
}

function readUtf8(file) {
  try {
    const text = fs.readFileSync(file, 'utf8').replace(/^﻿/, '')
    return { ok: text.trim().length > 0, text }
  } catch (error) {
    return { ok: false, text: '', error: error.message }
  }
}

function makeCheck(id, ok, file, evidence, expected, repair) {
  return {
    id,
    ok,
    severity: 'blocking',
    file,
    evidence,
    expected,
    references: ['references/workflow-setup.md', 'references/artifact-protocols.md'],
    repair,
  }
}

function parseTableRow(line) {
  const trimmed = line.trim()
  if (!trimmed.startsWith('|') || !trimmed.endsWith('|')) return null
  return trimmed.slice(1, -1).split('|').map((cell) => cell.replace(/\*\*/g, '').replace(/`/g, '').trim())
}

function fieldValue(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = text.match(new RegExp(`^\\s*[-*+]\\s*\\*{0,2}${escaped}\\*{0,2}\\s*[：:]\\s*(.*)$`, 'm'))
  return match ? match[1].trim() : null
}

function parsePlotPoints(lines) {
  const headerIndex = lines.findIndex((line) => {
    const cells = parseTableRow(line)
    return cells && cells.length === 4 && PLOT_HEADER_FIRST.test(cells[0])
  })
  if (headerIndex < 0) return { header: null, points: [] }
  const header = parseTableRow(lines[headerIndex])
  const points = []
  for (let index = headerIndex + 1; index < lines.length; index++) {
    const cells = parseTableRow(lines[index])
    if (!cells) {
      if (points.length) break
      continue
    }
    if (/^:?-{3,}:?$/.test(cells[0])) continue
    if (!/^\d+$/.test(cells[0])) break
    points.push({ number: Number(cells[0]), cells })
  }
  return { header, points }
}

function validateP1Contract(text, plotPoints, requireP1) {
  const raw = fieldValue(text, P1_FIELD)
  if (raw === null) {
    return {
      present: false,
      ok: !requireP1,
      evidence: requireP1 ? '缺字段：P1质量契约' : 'legacy 细纲未启用 P1；按兼容模式跳过',
    }
  }
  let value
  try {
    value = JSON.parse(raw)
  } catch (error) {
    return { present: true, ok: false, evidence: `P1质量契约不是合法 JSON：${error.message}` }
  }
  if (!value || Array.isArray(value) || typeof value !== 'object') {
    return { present: true, ok: false, evidence: 'P1质量契约必须是 JSON 对象' }
  }
  const required = [
    'chapter_function', 'target_emotion_id', 'required_deliveries',
    'allowed_expectation_ids', 'allowed_hypothesis_ids', 'scene_catalog',
  ]
  const missing = required.filter((key) => !(key in value))
  if (missing.length) {
    return { present: true, ok: false, evidence: `P1质量契约缺字段：${missing.join('、')}` }
  }
  const catalog = value.scene_catalog
  if (!Array.isArray(catalog) || !catalog.length) {
    return { present: true, ok: false, evidence: 'scene_catalog 必须是非空数组' }
  }
  const expectedNumbers = plotPoints.map((row) => row.number)
  const expectedIndexes = expectedNumbers.map((_, index) => index + 1)
  const indexes = catalog.map((row) => row && row.scene_index)
  const ids = catalog.map((row) => row && row.scene_id)
  const expectedIds = expectedNumbers.map((number) => `scene-${number}`)
  const plotSequential = expectedNumbers.length > 0 && expectedNumbers.every((number, index) => number === index + 1)
  const indexesMatch = indexes.length === expectedIndexes.length && indexes.every((number, index) => number === expectedIndexes[index])
  const idsMatch = ids.length === expectedIds.length && ids.every((id, index) => id === expectedIds[index])
  const idsDistinct = ids.every((id) => typeof id === 'string' && id.trim()) && new Set(ids).size === ids.length
  const ok = plotSequential && indexesMatch && idsMatch && idsDistinct
  return {
    present: true,
    ok,
    evidence: ok
      ? `scene_catalog 与 ${plotPoints.length} 个情节点一一对应`
      : `情节点编号=${JSON.stringify(expectedNumbers)}；scene_id=${JSON.stringify(ids)}；scene_index=${JSON.stringify(indexes)}`,
  }
}

function verify(file, options = {}) {
  const name = path.basename(file)
  const read = readUtf8(file)
  const checks = []

  checks.push(makeCheck(
    'outline.readable',
    read.ok,
    name,
    read.ok ? '文件存在且非空' : (read.error || '文件为空'),
    '细纲文件存在且非空',
    '只补建缺失的细纲文件，不改动同批其他章。'
  ))
  if (!read.ok) return report(file, checks)
  const text = read.text

  const missingFields = FIELDS.filter((field) => !fieldPattern(field).test(text))
  checks.push(makeCheck(
    'outline.required-fields',
    missingFields.length === 0,
    name,
    missingFields.length ? `缺字段：${missingFields.join('、')}` : `${FIELDS.length} 个字段齐全`,
    `按权威模板列出全部字段：${FIELDS.join('、')}；值未知时写 [待补充]，不杜撰剧情`,
    '只补报告里缺的字段行；确实还定不下来的写 [待补充]，不为补字段新增副线或人物关系。'
  ))

  // 隔离实验（同章、同写作流程，只改细纲）：只补这两个字段就能复现补齐全部字段的收益，
  // 盲评 3/3 胜过不补；补满五个字段与只补这两个不可区分。所以这两个字段不接受占位符，
  // 其余字段仍按契约允许 [待补充]。
  const hollow = INTENT_FIELDS.filter((field) => {
    const match = text.match(new RegExp(`^\\s*[-*+]\\s*\\*{0,2}${field.replace('/', '\\/')}\\*{0,2}\\s*[：:]\\s*(.*)$`, 'm'))
    if (!match) return false
    const value = match[1].replace(/\[待补充\]/g, '').replace(/[\s、，,。;；]/g, '')
    return value.length === 0
  })
  checks.push(makeCheck(
    'outline.intent-fields-substantive',
    hollow.length === 0,
    name,
    hollow.length ? `只有占位符，没有实际内容：${hollow.join('、')}` : '写作意图、结尾拍、期待与读者验收都写了实际内容',
    '目标情绪与主角选择写实际变化；结尾拍/期待写 ID、类型与落点；读者验收写 must_know / may_believe / must_not_know / open_ids。这五项不接受 [待补充]',
    '只把报告点名字段替换成本章实际内容；其余字段不动。'
  ))

  const emotionRaw = fieldValue(text, '目标情绪')
  let vocab = null
  try {
    vocab = loadEmotionVocab(EMOTION_VOCAB_PATH)
  } catch (_error) {
    vocab = null
  }
  const token = emotionToken(emotionRaw)
  const vocabOk = emotionRaw === null || (vocab != null && vocab.has(token))
  checks.push(makeCheck(
    'outline.emotion-vocab',
    vocabOk,
    name,
    vocab == null
      ? `无法读取目标情绪词表：${EMOTION_VOCAB_PATH}`
      : (vocabOk ? `目标情绪词「${token}」在闭合词表内` : `目标情绪「${token || emotionRaw}」不在闭合词表`),
    '目标情绪必须取自 skills/_shared/references/target-emotion-vocab.md，可在词后追加说明',
    '只把目标情绪改成词表中的词；不要新增字段。'
  ))

  const endingTypes = 'goal|conflict|choice|relationship|payoff|aftermath|open_question'
  const endingOk = new RegExp(`结尾拍ID/类型\\s*[：:].*EB-[^\\s；;]+.*(?:${endingTypes})`, 'i').test(text)
  const expectationOk = new RegExp(`期待ID/类型\\s*[：:].*EX-[^\\s；;]+.*(?:${endingTypes})`, 'i').test(text)
  const oracleOk = ['must_know', 'may_believe', 'must_not_know', 'open_ids'].every((key) => new RegExp(`${key}\\s*=`).test(text))
  checks.push(makeCheck(
    'outline.reader-contract',
    endingOk && expectationOk && oracleOk,
    name,
    `ending_beat=${endingOk}；expectation=${expectationOk}；reader_oracle=${oracleOk}`,
    '结尾拍使用 EB-* + 七类之一；期待使用 EX-* + 七类之一；读者验收列全四个 oracle 集合',
    '只修结尾拍、期待或读者验收字段；不为满足检查新增剧情或强悬念。'
  ))

  const missingSubs = SUBSECTIONS.filter((sub) => !new RegExp(`^#{3,4}\\s*${sub}`, 'm').test(text))
  checks.push(makeCheck(
    'outline.subsections',
    missingSubs.length === 0,
    name,
    missingSubs.length ? `缺小节：${missingSubs.join('、')}` : '四个小节齐全',
    '包含 内容概括 / 情节安排 / 人物关系和出场顺序 / 情节细化 四个小节',
    '只补缺失的小节标题及其条目，不重写已成立的内容。'
  ))

  const missingActs = FIVE_ACT.filter((act) => !fieldPattern(act).test(text))
  checks.push(makeCheck(
    'outline.five-act',
    missingActs.length === 0,
    name,
    missingActs.length ? `五段式缺：${missingActs.join('、')}` : '五段式齐全',
    '内容概括写全 起因 / 发展 / 转折 / 高潮 / 结尾',
    '只补缺的那一段，不改其余四段。'
  ))

  const lines = text.split(/\r?\n/)
  const { header, points: plotPoints } = parsePlotPoints(lines)
  const headerOk = Boolean(header) && header[2].includes('功能标签') && header[3].includes('执行边界')
  checks.push(makeCheck(
    'outline.plotpoint-table',
    headerOk,
    name,
    header ? `表头：${header.join(' | ')}` : '未找到 | # | 情节点 | 功能标签 | 执行边界 | 表头',
    '情节细化使用四列表格：# / 情节点（谁做了什么） / 功能标签 / 执行边界',
    '只把情节点序列改成四列表格，逐点补功能标签与执行边界；不增删情节点本身。'
  ))

  const p1 = validateP1Contract(text, plotPoints, options.requireP1 === true)
  checks.push(makeCheck(
    p1.present ? 'outline.p1-quality-contract' : 'outline.p1-required',
    p1.ok,
    name,
    p1.evidence,
    'P1 模式下质量契约为合法 JSON，scene_catalog 按情节点表实际编号生成，ID 唯一、index 连续且数量/顺序一致；legacy 模式允许整行不存在',
    '不要虚构固定场景；按情节点表第 N 行生成 {"scene_id":"scene-N","scene_index":N}。旧纲未启用 P1 时不要只补空壳字段。'
  ))

  const targetMatch = text.match(/字数目标\s*[：:]\s*(?:约\s*)?([\d,，]+)/)
  const target = targetMatch ? Number(targetMatch[1].replace(/[,，]/g, '')) : null
  const caliberOk = new RegExp(`字数口径\\s*[：:]\\s*${CALIBER}`).test(text)
  checks.push(makeCheck(
    'outline.wordcount-target',
    Boolean(target) && Number.isFinite(target) && target >= 500 && target <= 20000 && caliberOk,
    name,
    `字数目标：${target === null ? '未识别' : target}；字数口径 ${CALIBER}：${caliberOk}`,
    `字数目标为 500-20000 的正整数，并声明 字数口径：${CALIBER}`,
    '只补字数目标或字数口径行，不调整情节安排。'
  ))

  return report(file, checks)
}

function report(file, checks) {
  const failures = checks.filter((check) => !check.ok)
  return {
    schema_version: 1,
    verifier: 'story-long-write.outline-contract',
    file: path.resolve(file),
    ok: failures.length === 0,
    checks,
    failures,
    repair_scope: failures.map((failure) => ({
      id: failure.id,
      file: failure.file,
      evidence: failure.evidence,
      expected: failure.expected,
      references: failure.references,
      repair: failure.repair,
    })),
  }
}

function resolveChapter(project, chapter) {
  const dir = path.join(project, '大纲')
  let entries
  try {
    entries = fs.readdirSync(dir)
  } catch (error) {
    return { error: `无法读取 ${dir}：${error.message}` }
  }
  const wanted = Number(chapter)
  const hit = entries.find((entry) => {
    const match = entry.match(/^细纲_第0*(\d+)章.*\.md$/)
    return match && Number(match[1]) === wanted
  })
  if (!hit) return { error: `${dir} 下没有第 ${wanted} 章细纲` }
  return { file: path.join(dir, hit) }
}

function parseArgs(argv) {
  const files = []
  let project = null
  let chapter = null
  let requireP1 = false
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index]
    if (arg === '--json') continue
    if (arg === '--require-p1') {
      requireP1 = true
      continue
    }
    if (arg === '--project' || arg === '--chapter') {
      if (index + 1 >= argv.length || argv[index + 1].startsWith('--')) return null
      const value = argv[++index]
      if (arg === '--project') project = value
      else chapter = value
      continue
    }
    if (arg.startsWith('--')) return null
    files.push(arg)
  }
  if (project || chapter) {
    if (!project || !chapter || files.length || !/^\d+$/.test(chapter)) return null
    return { project, chapter, requireP1 }
  }
  if (!files.length) return null
  return { files, requireP1 }
}

function main(argv) {
  const parsed = parseArgs(argv)
  if (!parsed) {
    process.stderr.write('用法: node scripts/check-outline-contract.js --json [--require-p1] <细纲路径...> | --json [--require-p1] --project <书目录> --chapter N\n')
    return 2
  }
  let targets = parsed.files
  if (!targets) {
    const resolved = resolveChapter(parsed.project, parsed.chapter)
    if (resolved.error) {
      process.stderr.write(`${resolved.error}\n`)
      return 2
    }
    targets = [resolved.file]
  }
  const reports = targets.map((file) => verify(file, { requireP1: parsed.requireP1 }))
  const ok = reports.every((entry) => entry.ok)
  process.stdout.write(`${JSON.stringify(reports.length === 1 ? reports[0] : reports, null, 2)}\n`)
  return ok ? 0 : 1
}

if (require.main === module) process.exitCode = main(process.argv.slice(2))

module.exports = { verify, FIELDS, P1_FIELD, SUBSECTIONS, FIVE_ACT }
