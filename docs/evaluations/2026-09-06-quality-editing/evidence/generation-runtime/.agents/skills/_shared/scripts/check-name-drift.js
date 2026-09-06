#!/usr/bin/env node
/**
 * Detect undeclared real-world product names and likely one-character name drift.
 *
 * Usage:
 *   node check-name-drift.js --json --project <book> [--chapter N] [--fail-on=blocking]
 * Exit: 0 = no blocking, 1 = blocking present, 2 = invocation/runtime error.
 */
'use strict'

const fs = require('fs')
const path = require('path')

const DICT_PATH = path.join(__dirname, '..', 'references', 'real-world-names.md')
const CHAPTER_RE = /^第0*(\d+)章_.*\.md$/
const OUTLINE_RE = /^细纲_第0*(\d+)章\.md$/
const HAN_NAME_RE = /^[\u3400-\u9fff]{3,4}$/u

function loadNames(file) {
  return fs.readFileSync(file, 'utf8').split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.startsWith('- '))
    .map((line) => line.slice(2).trim())
    .filter(Boolean)
    .sort((a, b) => b.length - a.length || a.localeCompare(b, 'zh-CN'))
}

function keepRealNames(project) {
  const topic = path.join(project, '设定', '题材定位.md')
  if (!fs.existsSync(topic)) return new Set()
  const text = fs.readFileSync(topic, 'utf8')
  const kept = new Set()
  for (const match of text.matchAll(/保留真名[：:]\s*(.+)$/gm)) {
    for (const item of match[1].split(/[、，,｜|]/)) {
      const name = item.trim()
      if (name) kept.add(name)
    }
  }
  return kept
}

function walkMarkdown(root, { skipHistory = false } = {}) {
  if (!fs.existsSync(root)) return []
  const files = []
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (entry.name.startsWith('.') || (skipHistory && entry.name === '_历史')) continue
    const target = path.join(root, entry.name)
    if (entry.isDirectory()) files.push(...walkMarkdown(target, { skipHistory }))
    else if (entry.isFile() && entry.name.endsWith('.md')) files.push(target)
  }
  return files.sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

function chapterFiles(project, chapter) {
  const files = []
  const outlineDir = path.join(project, '大纲')
  if (fs.existsSync(outlineDir)) {
    for (const entry of fs.readdirSync(outlineDir)) {
      const match = entry.match(OUTLINE_RE)
      if (!match || (chapter != null && Number(match[1]) !== chapter)) continue
      files.push(path.join(outlineDir, entry))
    }
  }
  const candidates = walkMarkdown(path.join(project, '候选'), { skipHistory: true })
  const prose = walkMarkdown(path.join(project, '正文'))
  for (const file of [...candidates, ...prose]) {
    const match = path.basename(file).match(CHAPTER_RE)
    if (!match || (chapter != null && Number(match[1]) !== chapter)) continue
    files.push(file)
  }
  return [...new Set(files)].sort((a, b) => a.localeCompare(b, 'zh-CN'))
}

function hitsIn(text, names) {
  const lines = text.split(/\r?\n/)
  const hits = []
  for (const name of names) {
    for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
      let from = 0
      while (from < lines[lineIndex].length) {
        const index = lines[lineIndex].indexOf(name, from)
        if (index < 0) break
        hits.push({ name, line: lineIndex + 1, excerpt: lines[lineIndex].trim().slice(0, 80) })
        from = index + name.length
      }
    }
  }
  return hits
}

function addCharacterName(names, value) {
  const candidate = String(value || '').trim().replace(/[｜|].*$/, '').trim()
  if (HAN_NAME_RE.test(candidate)) names.add(candidate)
}

function characterNames(project) {
  const names = new Set()
  for (const root of [path.join(project, '设定', '角色'), path.join(project, '追踪', '角色状态')]) {
    for (const file of walkMarkdown(root)) {
      addCharacterName(names, path.basename(file, '.md'))
      const text = fs.readFileSync(file, 'utf8')
      for (const match of text.matchAll(/^(?:name|姓名|本名|称呼|别名)[：:]\s*([^\r\n]+)$/gmi)) {
        for (const value of match[1].split(/[、，,｜|/]/)) addCharacterName(names, value)
      }
    }
  }
  const statePath = path.join(project, '追踪', '_tracking-state.json')
  if (fs.existsSync(statePath)) {
    const state = JSON.parse(fs.readFileSync(statePath, 'utf8'))
    const characters = state && typeof state.characters === 'object' ? state.characters : {}
    for (const name of Object.keys(characters || {})) addCharacterName(names, name)
  }
  return [...names].sort((a, b) => b.length - a.length || a.localeCompare(b, 'zh-CN'))
}

function nearNameHits(text, names) {
  const hits = []
  const seen = new Set()
  const lines = text.split(/\r?\n/)
  for (let lineIndex = 0; lineIndex < lines.length; lineIndex++) {
    const chars = [...lines[lineIndex]]
    for (const expected of names) {
      const expectedChars = [...expected]
      for (let index = 0; index <= chars.length - expectedChars.length; index++) {
        const actualChars = chars.slice(index, index + expectedChars.length)
        if (actualChars[0] !== expectedChars[0] || !actualChars.every((char) => /[\u3400-\u9fff]/u.test(char))) continue
        const distance = actualChars.reduce((count, char, offset) => count + Number(char !== expectedChars[offset]), 0)
        if (distance !== 1) continue
        const actual = actualChars.join('')
        const key = `${lineIndex}:${index}:${expected}:${actual}`
        if (seen.has(key)) continue
        seen.add(key)
        hits.push({ expected, actual, line: lineIndex + 1, excerpt: lines[lineIndex].trim().slice(0, 80) })
      }
    }
  }
  return hits
}

function parseArgs(argv) {
  let project = null
  let chapter = null
  let failOn = 'blocking'
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index]
    if (arg === '--json') continue
    if (arg.startsWith('--fail-on=')) {
      failOn = arg.slice('--fail-on='.length)
      continue
    }
    if (arg === '--project' || arg === '--chapter') {
      if (index + 1 >= argv.length || argv[index + 1].startsWith('--')) return null
      const value = argv[++index]
      if (arg === '--project') project = value
      else chapter = Number(value)
      continue
    }
    if (!arg.startsWith('--') && !project) project = arg
    else return null
  }
  if (!project || !['blocking', 'any', 'none'].includes(failOn)) return null
  if (chapter != null && (!Number.isInteger(chapter) || chapter < 1)) return null
  return { project: path.resolve(project), chapter, failOn }
}

function main(argv) {
  const parsed = parseArgs(argv)
  if (!parsed) {
    process.stderr.write('用法: node check-name-drift.js --json --project <书目录> [--chapter N] [--fail-on=blocking]\n')
    return 2
  }
  try {
    if (!fs.statSync(parsed.project).isDirectory()) throw new Error('书目录不是目录')
    const names = loadNames(DICT_PATH)
    const kept = keepRealNames(parsed.project)
    const active = names.filter((name) => !kept.has(name))
    const characters = characterNames(parsed.project)
    const findings = []
    for (const file of chapterFiles(parsed.project, parsed.chapter)) {
      const relative = path.relative(parsed.project, file).replace(/\\/g, '/')
      const text = fs.readFileSync(file, 'utf8')
      for (const hit of hitsIn(text, active)) {
        findings.push({
          id: 'name-drift.real-world', severity: 'blocking', file: relative,
          name: hit.name, line: hit.line,
          evidence: `${relative}:${hit.line} 出现现实专名「${hit.name}」：${hit.excerpt}`,
        })
      }
      for (const hit of nearNameHits(text, characters)) {
        findings.push({
          id: 'name-drift.character-near', severity: 'advisory', file: relative,
          expected: hit.expected, actual: hit.actual, line: hit.line,
          evidence: `${relative}:${hit.line} 疑似人名漂移「${hit.actual}」（角色名「${hit.expected}」）：${hit.excerpt}`,
        })
      }
    }
    const blocking = findings.filter((item) => item.severity === 'blocking')
    const report = {
      schema_version: 1, verifier: 'story-write.name-drift', ok: blocking.length === 0,
      dictionary: names, keep_real: [...kept].sort((a, b) => a.localeCompare(b, 'zh-CN')),
      character_names: characters, findings,
    }
    process.stdout.write(`${JSON.stringify(report, null, 2)}\n`)
    if (parsed.failOn === 'any' && findings.length) return 1
    if (parsed.failOn === 'blocking' && blocking.length) return 1
    return 0
  } catch (error) {
    process.stderr.write(`专名漂移检查无法执行：${error.message}\n`)
    return 2
  }
}

if (require.main === module) process.exitCode = main(process.argv.slice(2))
module.exports = { loadNames, keepRealNames, chapterFiles, characterNames, hitsIn, nearNameHits }
