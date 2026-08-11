#!/usr/bin/env node
"use strict"

const assert = require("node:assert/strict")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const { spawnSync } = require("node:child_process")

const root = path.resolve(__dirname, "..")
const scripts = path.join(root, "skills/story-scan/scripts")
const contract = require(path.join(scripts, "scan-contract.js"))

function runInvalid(name, args) {
  const cwd = fs.mkdtempSync(path.join(os.tmpdir(), "scan-invalid-"))
  try {
    const result = spawnSync(process.execPath, [path.join(scripts, name), ...args], { cwd, encoding: "utf8", timeout: 5000 })
    assert.notEqual(result.status, 0, `${name} should reject ${JSON.stringify(args)}`)
    assert.deepEqual(fs.readdirSync(cwd), [], `${name} created files before rejecting ${JSON.stringify(args)}`)
    assert.match(result.stderr, /参数错误|SCAN_CLI_INVALID|Error:/)
  } finally {
    fs.rmSync(cwd, { recursive: true, force: true })
  }
}

const four = ["fanqie-rank-scraper.js", "jjwxc-rank-scraper.js", "qidian-rank-scraper.js", "qimao-rank-scraper.js"]
for (const name of four) {
  for (const args of [
    ["--unknown", "x"],
    ["--port", "0"],
    ["--port", "9222", "--port", "9223"],
    ["--outdir="],
    ["--port", "--type", "x"],
    ["unexpected"],
  ]) runInvalid(name, args)
}

for (const args of [["--channel", "bad"], ["--type", "bad"], ["--top", "101"]]) runInvalid("fanqie-rank-scraper.js", args)
for (const args of [["--channel", "bad"], ["--type", "bad"], ["--top", "0"], ["--detail-limit", "101"]]) runInvalid("jjwxc-rank-scraper.js", args)
for (const args of [["--type", "bad"], ["--mode", "bad"], ["--detail", "maybe"]]) runInvalid("qidian-rank-scraper.js", args)
for (const args of [["--channel", "bad"], ["--type", "bad"], ["--period", "week"], ["--type", "update", "--period", "month"]]) runInvalid("qimao-rank-scraper.js", args)

const long = "中".repeat(99) + "😀" + "尾"
const truncated = contract.truncateDescription(long)
assert.equal(Array.from(truncated.slice(0, -3)).length, 100)
assert.equal(truncated.endsWith("..."), true)
assert.equal(contract.truncateDescription("  中\n文  "), "中 文")

const fakeNow = {
  getFullYear: () => 2026, getMonth: () => 6, getDate: () => 27,
  getHours: () => 0, getMinutes: () => 1, getSeconds: () => 2,
  getMilliseconds: () => 3, getTimezoneOffset: () => -480,
}
assert.deepEqual(contract.createTimeSnapshot(fakeNow), {
  dateStamp: "20260727",
  capturedAt: "2026-07-27T00:01:02.003+08:00",
})

const normalized = contract.normalizeQidianBook({ rank: 1, title: "书", description: "😀".repeat(101) })
assert.deepEqual(Object.keys(normalized), [...contract.QIDIAN_BOOK_FIELDS, "missing_fields"])
assert.equal(Object.keys(normalized).length, 14)
for (const field of contract.QIDIAN_BOOK_FIELDS) {
  if (!["rank", "title", "description"].includes(field)) assert.equal(normalized[field], null)
}
assert(normalized.missing_fields.includes("author"))
assert.equal(normalized.missing_fields.includes("title"), false)

const qidian = require(path.join(scripts, "qidian-rank-scraper.js"))
const mobile = qidian.normalizeMobileBook({ bName: "甲", bid: "1", bAuth: "作者", desc: "简介" }, 0)
assert.deepEqual(Object.keys(mobile), [...contract.QIDIAN_BOOK_FIELDS, "missing_fields"])
const rendered = qidian.renderMarkdown({ label: "测试" }, [mobile], "https://example", "mobile-ssr")
assert.match(rendered, /数据质量：缺失字段/)
assert.match(rendered, /缺失字段：/)

const qimao = require(path.join(scripts, "qimao-rank-scraper.js"))
const snapshot = { dateStamp: "20260811", capturedAt: "x" }
const day = qimao.outputFilename("male", "hot", "day", snapshot)
const month = qimao.outputFilename("male", "hot", "month", snapshot)
const all = qimao.outputFilename("male", "hot", "all", snapshot)
assert.notEqual(day, month)
assert.notEqual(month, all)
assert.match(day, /日榜/)
assert.match(month, /月榜/)
assert.match(all, /总榜/)
const qimaoSource = fs.readFileSync(path.join(scripts, "qimao-rank-scraper.js"), "utf8")
assert.match(qimaoSource, /if \(!activatePeriod\(port, period\)\)/)
assert.match(qimaoSource, /isTabActive/)

console.log("OK: strict scan CLI, Unicode/time, Qidian schema, and Qimao period contracts passed")
