#!/usr/bin/env node
/**
 * Cross-chapter 目标情绪 consecutive-run detector.
 *
 * Usage:
 *   node check-emotion-run.js --json --project <书目录> [--chapter N]
 * Exit: 0 = scan completed (findings are advisory), 2 = invalid/unreadable input.
 *
 * Three or more consecutive identical tokens prompt a reading review.
 * Tags alone cannot establish repetitive events or poor reader experience.
 */
'use strict'

const fs = require('fs')
const path = require('path')

const ADVISORY_RUN = 3
const VOCAB_PATH = path.join(__dirname, '..', 'references', 'target-emotion-vocab.md')

function loadVocab(file) {
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
  const token = String(value || '').split(/[；;：:→\s]/).find(Boolean) || ''
  return token
}

function fieldValue(text, name) {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = text.match(new RegExp(`^\\s*[-*+]\\s*\\*{0,2}${escaped}\\*{0,2}\\s*[：:]\\s*(.*)$`, 'm'))
  return match ? match[1].trim() : null
}

function listOutlines(project) {
  const dir = path.join(project, '大纲')
  const entries = fs.readdirSync(dir)
  const rows = []
  for (const entry of entries) {
    const match = entry.match(/^细纲_第0*(\d+)章\.md$/)
    if (!match) continue
    rows.push({ chapter: Number(match[1]), file: path.join(dir, entry) })
  }
  rows.sort((a, b) => a.chapter - b.chapter)
  return rows
}

function consecutiveRuns(sequence) {
  const runs = []
  let current = null
  for (const item of sequence) {
    if (!item.token) {
      current = null
      continue
    }
    if (current && current.token === item.token && item.chapter === current.end + 1) {
      current.end = item.chapter
      current.length += 1
      continue
    }
    current = { token: item.token, start: item.chapter, end: item.chapter, length: 1 }
    runs.push(current)
  }
  return runs
}

function parseArgs(argv) {
  let project = null
  let chapter = null
  for (let index = 0; index < argv.length; index++) {
    const arg = argv[index]
    if (arg === '--json') continue
    if (arg === '--project' || arg === '--chapter') {
      if (index + 1 >= argv.length || argv[index + 1].startsWith('--')) return null
      const value = argv[++index]
      if (arg === '--project') project = value
      else chapter = Number(value)
      continue
    }
    if (arg.startsWith('--')) return null
  }
  if (!project) return null
  if (chapter != null && (!Number.isInteger(chapter) || chapter < 1)) return null
  return { project, chapter }
}

function main(argv) {
  const parsed = parseArgs(argv)
  if (!parsed) {
    process.stderr.write('用法: node check-emotion-run.js --json --project <书目录> [--chapter N]\n')
    return 2
  }
  let vocab
  let outlines
  try {
    vocab = loadVocab(VOCAB_PATH)
    outlines = listOutlines(parsed.project)
  } catch (error) {
    process.stderr.write(`无法读取目标情绪检查输入：${error.message}\n`)
    return 2
  }
  const relevantOutlines = parsed.chapter == null
    ? outlines
    : outlines.filter((row) => row.chapter <= parsed.chapter)
  let sequence
  try {
    sequence = relevantOutlines.map((row) => {
      const text = fs.readFileSync(row.file, 'utf8')
      const raw = fieldValue(text, '目标情绪')
      const token = emotionToken(raw)
      return {
        chapter: row.chapter,
        token: vocab.has(token) ? token : '',
      }
    })
  } catch (error) {
    process.stderr.write(`无法读取目标情绪检查输入：${error.message}\n`)
    return 2
  }
  const findings = consecutiveRuns(sequence)
    .filter((run) => run.length >= ADVISORY_RUN)
    .filter((run) => parsed.chapter == null || (run.start <= parsed.chapter && parsed.chapter <= run.end))
    .map((run) => ({
      id: 'emotion.run',
      token: run.token,
      start: run.start,
      end: run.end,
      length: run.length,
      severity: 'advisory',
      evidence: `第${run.start}–${run.end}章连续 ${run.length} 章目标情绪为「${run.token}」`,
    }))
  const report = {
    schema_version: 1,
    verifier: 'story-write.emotion-run',
    ok: true,
    advisory_run: ADVISORY_RUN,
    blocking_run: null,
    findings,
  }
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`)
  return 0
}

if (require.main === module) process.exitCode = main(process.argv.slice(2))
module.exports = { loadVocab, emotionToken, consecutiveRuns, ADVISORY_RUN }
