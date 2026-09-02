#!/usr/bin/env node
'use strict'

const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { spawnSync } = require('child_process')

const repoRoot = path.resolve(__dirname, '..')
const tool = path.join(repoRoot, 'skills/_shared/scripts/check-name-drift.js')
const demo = path.join(repoRoot, 'demo/长篇/让你管账号，你高燃混剪炸全网')

function run(args) {
  const result = spawnSync(process.execPath, [tool, '--json', ...args], { encoding: 'utf8' })
  return { ...result, report: result.stdout.trim() ? JSON.parse(result.stdout) : null }
}

const demoResult = run(['--project', demo])
assert.strictEqual(demoResult.status, 1, demoResult.stderr)
assert.ok(demoResult.report)
const demoBlocking = demoResult.report.findings.filter((item) => item.severity === 'blocking')
assert.deepStrictEqual([...new Set(demoBlocking.map((item) => item.file))].sort(), [
  '大纲/细纲_第011章.md',
  '正文/第011章_新任务：老兵的愿望.md',
  '正文/第020章_老兵的礼物.md',
])
assert(demoBlocking.every((item) => item.name === '抖音'), demoResult.stdout)
for (const allowed of ['微博', '微信', '知乎', '东风', '军报', '火箭军']) {
  assert(!demoBlocking.some((item) => item.name === allowed), `${allowed} 不应 blocking`)
}
assert(demoResult.report.findings.every((item) => !item.file.startsWith('设定/')))

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'name-drift-'))
try {
  fs.mkdirSync(path.join(tmp, '设定', '角色'), { recursive: true })
  fs.mkdirSync(path.join(tmp, '正文', '第一卷'), { recursive: true })
  fs.mkdirSync(path.join(tmp, '大纲'), { recursive: true })
  fs.writeFileSync(path.join(tmp, '设定', '题材定位.md'), '- 保留真名：抖音\n', 'utf8')
  fs.writeFileSync(path.join(tmp, '设定', '角色', '钟嘉嘉.md'), 'name: 钟嘉嘉\n', 'utf8')
  fs.writeFileSync(path.join(tmp, '正文', '第一卷', '第001章_测试.md'), '钟嘉佳打开抖音。\n', 'utf8')
  fs.writeFileSync(path.join(tmp, '大纲', '细纲_第001章.md'), '- 核心事件：钟嘉嘉打开抖音\n', 'utf8')
  const advisory = run(['--project', tmp, '--chapter', '1'])
  assert.strictEqual(advisory.status, 0, advisory.stderr)
  assert.strictEqual(advisory.report.ok, true)
  assert(advisory.report.findings.some((item) =>
    item.id === 'name-drift.character-near' && item.expected === '钟嘉嘉' && item.actual === '钟嘉佳'))
  assert(!advisory.report.findings.some((item) => item.severity === 'blocking'))

  fs.writeFileSync(path.join(tmp, '正文', '第一卷', '第002章_测试.md'), '他打开快手。\n', 'utf8')
  const nested = run(['--project', tmp, '--chapter', '2'])
  assert.strictEqual(nested.status, 1, nested.stderr)
  assert(nested.report.findings.some((item) =>
    item.id === 'name-drift.real-world' && item.file.includes('第一卷/第002章')))

  const missing = run(['--project', path.join(tmp, '不存在')])
  assert.strictEqual(missing.status, 2)
  assert.match(missing.stderr, /无法执行/)
} finally {
  fs.rmSync(tmp, { recursive: true, force: true })
}

console.log('name-drift: 现实专名、书级白名单、卷目录、人名近似与错误退出码通过')
