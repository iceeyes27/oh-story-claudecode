#!/usr/bin/env node
"use strict"

const crypto = require("node:crypto")
const fs = require("node:fs")
const path = require("node:path")

const CURRENT_SCHEMA_VERSION = 3

class BoundaryError extends Error {
  constructor(code, message) {
    super(message)
    this.name = "BoundaryError"
    this.code = code
  }
}

function fail(code, message) {
  throw new BoundaryError(code, message)
}

function uniqueField(text, name) {
  const matches = [...text.matchAll(new RegExp(`^-\\s*${name}:\\s*(.*?)\\s*$`, "gm"))]
  if (matches.length !== 1 || !matches[0][1]) fail("invalid-metadata", `${name} 必须出现且只能出现一次`)
  return matches[0][1]
}

function sourceLineCount(buffer) {
  if (!buffer.length) return 0
  const text = buffer.toString("utf8")
  const lines = text.split(/\r\n|\n|\r/)
  // 末尾换行结束最后一条实际文本行，不会凭空创建一个可作为章节起点的 EOF 后空行。
  return /(?:\r\n|\n|\r)$/.test(text) ? lines.length - 1 : lines.length
}

function parseBoundaryRows(text) {
  const heading = /^##\s+章节边界(?:\s*（.*?）)?\s*$/m.exec(text)
  if (!heading) fail("missing-boundaries", "缺少章节边界表")
  const rows = []
  for (const line of text.slice(heading.index + heading[0].length).split(/\r?\n/).slice(1)) {
    if (/^##\s+/.test(line)) break
    if (!line.trim() || /^\|\s*章号\s*\|/.test(line) || /^\|\s*-+\s*\|/.test(line)) continue
    const match = line.match(/^\|\s*(\d+)\s*\|\s*(.*?)\s*\|\s*(\d+)\s*\|\s*(\d+)\s*\|\s*$/)
    // 表中的损坏数据行不能被静默忽略；尤其是最后一章损坏时，忽略后仍可能形成一张
    // 看似连续的短表，使 Stage 1/2/6 在没有完整边界的情况下继续消费。
    if (!match) {
      if (line.trim().startsWith("|") || /^\s*\d+\s*\|/.test(line)) {
        fail("invalid-boundary-row", `无法解析章节边界行：${line.trim()}`)
      }
      continue
    }
    rows.push({
      chapter: Number(match[1]),
      title: match[2],
      start_line: Number(match[3]),
      word_count: Number(match[4]),
    })
  }
  if (!rows.length) fail("missing-boundaries", "章节边界表没有数据行")
  return rows
}

function resolveSource(progressPath, sourcePath) {
  if (path.isAbsolute(sourcePath) || /^[A-Za-z]:[\\/]/.test(sourcePath)) {
    fail("invalid-source-path", "source_path 必须是相对 _progress.md 的路径")
  }
  const base = path.dirname(progressPath)
  const resolved = path.resolve(base, sourcePath)
  const relation = path.relative(base, resolved)
  if (relation === ".." || relation.startsWith(`..${path.sep}`) || path.isAbsolute(relation)) {
    fail("invalid-source-path", "source_path 不得离开拆文输出目录")
  }
  // 词法范围检查不足以阻止目录内符号链接指向外部文件；读取前按真实路径再检查一次。
  // 来源不存在仍由调用方报告 unreadable-source，避免把两类错误混在一起。
  try {
    const realBase = fs.realpathSync(base)
    const realSource = fs.realpathSync(resolved)
    const realRelation = path.relative(realBase, realSource)
    if (realRelation === ".." || realRelation.startsWith(`..${path.sep}`) || path.isAbsolute(realRelation)) {
      fail("invalid-source-path", "source_path 的真实路径不得离开拆文输出目录")
    }
  } catch (error) {
    if (error instanceof BoundaryError) throw error
  }
  return resolved
}

function validateProgress(progressFile) {
  const progressPath = path.resolve(progressFile)
  let text
  try { text = fs.readFileSync(progressPath, "utf8") } catch { fail("unreadable-progress", `无法读取 ${progressPath}`) }

  const schemaRaw = uniqueField(text, "schema_version")
  if (!/^\d+$/.test(schemaRaw) || Number(schemaRaw) !== CURRENT_SCHEMA_VERSION) {
    fail("old-schema", `只接受 schema_version: ${CURRENT_SCHEMA_VERSION}；v1/v2 必须回到 Stage 0 重建`)
  }
  const sourcePath = uniqueField(text, "source_path")
  const bytesRaw = uniqueField(text, "source_bytes")
  const sha256 = uniqueField(text, "source_sha256").toLowerCase()
  if (!/^\d+$/.test(bytesRaw)) fail("invalid-metadata", "source_bytes 必须是非负整数")
  if (!/^[a-f0-9]{64}$/.test(sha256)) fail("invalid-metadata", "source_sha256 必须是 64 位 SHA-256")

  const absoluteSource = resolveSource(progressPath, sourcePath)
  let source
  try { source = fs.readFileSync(absoluteSource) } catch { fail("unreadable-source", `无法读取来源文件 ${sourcePath}`) }
  if (source.length !== Number(bytesRaw)) fail("source-changed", `来源字节数已变化：记录 ${bytesRaw}，当前 ${source.length}`)
  const actualSha256 = crypto.createHash("sha256").update(source).digest("hex")
  if (actualSha256 !== sha256) fail("source-changed", "来源 SHA-256 已变化")

  const lineCount = sourceLineCount(source)
  const chapters = parseBoundaryRows(text)
  const seen = new Set()
  let previousChapter = 0
  let previousLine = 0
  for (const row of chapters) {
    if (seen.has(row.chapter)) fail("duplicate-chapter", `章号 ${row.chapter} 重复`)
    seen.add(row.chapter)
    if (row.chapter !== previousChapter + 1) fail("missing-chapter", `章号必须从 1 连续递增；${previousChapter} 后出现 ${row.chapter}`)
    if (row.start_line <= previousLine) fail("non-increasing-line", `第 ${row.chapter} 章起始行未严格递增`)
    if (row.start_line < 1 || row.start_line > lineCount) fail("line-out-of-range", `第 ${row.chapter} 章起始行 ${row.start_line} 超出原文 1-${lineCount}`)
    previousChapter = row.chapter
    previousLine = row.start_line
  }

  return {
    schema_version: CURRENT_SCHEMA_VERSION,
    source: {
      path: sourcePath,
      bytes: source.length,
      sha256: actualSha256,
      line_count: lineCount,
    },
    chapters,
  }
}

function main(argv) {
  if (argv.length !== 2 || argv[0] !== "validate") {
    process.stderr.write("Usage: node chapter-boundary.js validate <_progress.md>\n")
    return 2
  }
  try {
    process.stdout.write(JSON.stringify(validateProgress(argv[1]), null, 2) + "\n")
    return 0
  } catch (error) {
    if (error instanceof BoundaryError) {
      process.stderr.write(`ERROR [${error.code}] ${error.message}。停止 Stage 1/2/6，并从 Stage 0 重建 _progress.md。\n`)
      return 1
    }
    throw error
  }
}

if (require.main === module) process.exitCode = main(process.argv.slice(2))

module.exports = { BoundaryError, CURRENT_SCHEMA_VERSION, validateProgress }
