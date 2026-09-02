#!/usr/bin/env node
'use strict'

const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawnSync } = require('child_process')

const repoRoot = path.resolve(__dirname, '..')
const tool = path.join(repoRoot, 'skills/_shared/scripts/check-emotion-run.js')
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'emotion-run-'))

function writeBook(emotions) {
  const root = path.join(tmp, `book-${emotions.join('-')}`)
  fs.mkdirSync(path.join(root, '大纲'), { recursive: true })
  emotions.forEach((emotion, index) => {
    const chapter = index + 1
    fs.writeFileSync(
      path.join(root, '大纲', `细纲_第${String(chapter).padStart(3, '0')}章.md`),
      `- 目标情绪：${emotion}\n`,
      'utf8',
    )
  })
  return root
}

function run(project, chapter) {
  const args = [tool, '--json', '--project', project]
  if (chapter != null) args.push('--chapter', String(chapter))
  const result = spawnSync(process.execPath, args, { encoding: 'utf8' })
  return { ...result, report: result.stdout.trim() ? JSON.parse(result.stdout) : null }
}

const boundaryBook = writeBook(['打脸', '家国', '家国', '家国', '家国'])

const chapterTwo = run(boundaryBook, 2)
assert.strictEqual(chapterTwo.status, 0, chapterTwo.stderr)
assert.deepStrictEqual(chapterTwo.report.findings, [])

const chapterFour = run(boundaryBook, 4)
assert.strictEqual(chapterFour.status, 0, chapterFour.stderr)
assert.strictEqual(chapterFour.report.findings.length, 1)
assert.strictEqual(chapterFour.report.findings[0].severity, 'advisory')
assert.strictEqual(chapterFour.report.findings[0].length, 3)
assert.strictEqual(chapterFour.report.findings[0].end, 4)

const chapterFive = run(boundaryBook, 5)
assert.strictEqual(chapterFive.status, 1, chapterFive.stderr)
assert.strictEqual(chapterFive.report.findings.length, 1)
assert.strictEqual(chapterFive.report.findings[0].severity, 'blocking')
assert.strictEqual(chapterFive.report.findings[0].length, 4)
assert.strictEqual(chapterFive.report.findings[0].end, 5)

const fullBook = run(boundaryBook)
assert.strictEqual(fullBook.status, 1, fullBook.stderr)
assert.strictEqual(fullBook.report.findings[0].length, 4)

console.log('emotion-run thresholds: 3 advisory / 4 blocking')
