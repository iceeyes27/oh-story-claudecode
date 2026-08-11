"use strict"

const assert = require("node:assert/strict")
const crypto = require("node:crypto")
const fs = require("node:fs")
const os = require("node:os")
const path = require("node:path")
const test = require("node:test")

const { BoundaryError, validateProgress } = require("./chapter-boundary.js")

function fixture(rows, options = {}) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "story-boundary-"))
  fs.mkdirSync(path.join(root, "原文"))
  const source = options.source || "第一章 开端\n正文一\n第二章 转折\n正文二\n第三章 收束\n正文三\n"
  const sourceFile = path.join(root, "原文", "原文.txt")
  fs.writeFileSync(sourceFile, source)
  const bytes = Buffer.from(source)
  const sha = crypto.createHash("sha256").update(bytes).digest("hex")
  const progress = [
    "# 深度拆解进度：测试",
    `- schema_version: ${options.schema ?? 3}`,
    `- source_path: ${options.sourcePath ?? "原文/原文.txt"}`,
    `- source_bytes: ${options.bytes ?? bytes.length}`,
    `- source_sha256: ${options.sha ?? sha}`,
    "## 章节边界（Stage 0 章节边界子步骤产物，唯一权威）",
    "| 章号 | 标题 | 起始行 | 字数 |",
    "|------|------|--------|------|",
    ...rows.map((row) => `| ${row.join(" | ")} |`),
    "## 分块进度",
  ].join("\n")
  const progressFile = path.join(root, "_progress.md")
  fs.writeFileSync(progressFile, progress)
  return { root, sourceFile, progressFile }
}

function expectCode(rows, code, options) {
  const item = fixture(rows, options)
  assert.throws(() => validateProgress(item.progressFile), (error) => error instanceof BoundaryError && error.code === code)
}

test("有效 schema v3 返回来源指纹和唯一章节表", () => {
  const item = fixture([[1, "开端", 1, 100], [2, "转折", 3, 120], [3, "收束", 5, 90]])
  const result = validateProgress(item.progressFile)
  assert.equal(result.schema_version, 3)
  assert.equal(result.source.path, "原文/原文.txt")
  assert.equal(result.source.line_count, 6)
  assert.deepEqual(result.chapters.map((row) => row.start_line), [1, 3, 5])
})

test("重复章号快速失败", () => expectCode([[1, "一", 1, 10], [1, "又一", 3, 10]], "duplicate-chapter"))
test("缺号快速失败", () => expectCode([[1, "一", 1, 10], [3, "三", 3, 10]], "missing-chapter"))
test("起始行倒序快速失败", () => expectCode([[1, "一", 3, 10], [2, "二", 1, 10]], "non-increasing-line"))
test("起始行越界快速失败", () => expectCode([[1, "一", 99, 10]], "line-out-of-range"))
test("末尾换行不产生可用的 EOF 后空行", () => expectCode([[1, "一", 7, 10]], "line-out-of-range"))

test("损坏的末章数据行不得被静默忽略", () => {
  const item = fixture([[1, "一", 1, 10], [2, "二", 3, 10]])
  const text = fs.readFileSync(item.progressFile, "utf8").replace("## 分块进度", "| 三 | 损坏 | x | 10 |\n## 分块进度")
  fs.writeFileSync(item.progressFile, text)
  assert.throws(() => validateProgress(item.progressFile), (error) => error instanceof BoundaryError && error.code === "invalid-boundary-row")
})

test("丢失首个分隔符的章节行不得被静默忽略", () => {
  const item = fixture([[1, "一", 1, 10], [2, "二", 3, 10]])
  const text = fs.readFileSync(item.progressFile, "utf8").replace("## 分块进度", "3 | 损坏 | 5 | 10 |\n## 分块进度")
  fs.writeFileSync(item.progressFile, text)
  assert.throws(() => validateProgress(item.progressFile), (error) => error instanceof BoundaryError && error.code === "invalid-boundary-row")
})

test("来源相对路径不得逃出拆文输出目录", () => {
  expectCode([[1, "一", 1, 10]], "invalid-source-path", { sourcePath: "../原文.txt" })
})

test("来源路径不得使用绝对路径", () => {
  expectCode([[1, "一", 1, 10]], "invalid-source-path", { sourcePath: path.resolve("原文.txt") })
})

test("来源符号链接不得逃出拆文输出目录", (t) => {
  const item = fixture([[1, "一", 1, 10], [2, "二", 3, 10], [3, "三", 5, 10]])
  const externalRoot = fs.mkdtempSync(path.join(os.tmpdir(), "story-boundary-external-"))
  const externalSource = path.join(externalRoot, "原文.txt")
  fs.copyFileSync(item.sourceFile, externalSource)
  fs.unlinkSync(item.sourceFile)
  try {
    fs.symlinkSync(externalSource, item.sourceFile, "file")
  } catch (error) {
    if (error && (error.code === "EPERM" || error.code === "EACCES")) return t.skip("当前系统不允许创建文件符号链接")
    throw error
  }
  assert.throws(() => validateProgress(item.progressFile), (error) => error instanceof BoundaryError && error.code === "invalid-source-path")
})

test("原文字节数变化后指纹失效", () => {
  const item = fixture([[1, "一", 1, 10], [2, "二", 3, 10], [3, "三", 5, 10]])
  fs.appendFileSync(item.sourceFile, "新增内容\n")
  assert.throws(() => validateProgress(item.progressFile), (error) => error instanceof BoundaryError && error.code === "source-changed")
})

test("原文等字节修改后 SHA-256 失效", () => {
  const item = fixture([[1, "一", 1, 10], [2, "二", 3, 10], [3, "三", 5, 10]])
  const changed = fs.readFileSync(item.sourceFile, "utf8").replace("正文一", "正文甲")
  fs.writeFileSync(item.sourceFile, changed)
  assert.throws(() => validateProgress(item.progressFile), (error) => error instanceof BoundaryError && error.code === "source-changed")
})

for (const schema of [1, 2]) {
  test(`schema v${schema} 必须回到 Stage 0`, () => expectCode([[1, "一", 1, 10]], "old-schema", { schema }))
}

test("Stage 1/2/6 文档只消费同一校验器，Stage 6 不重切", () => {
  const skillRoot = path.resolve(__dirname, "..")
  const skill = fs.readFileSync(path.join(skillRoot, "SKILL.md"), "utf8")
  const pipeline = fs.readFileSync(path.join(skillRoot, "references", "pipeline-ops.md"), "utf8")
  const style = fs.readFileSync(path.join(skillRoot, "references", "style-profile-generator.md"), "utf8")
  assert.match(skill, /Stage 1、Stage 2、Stage 6[^\n]*chapter-boundary\.js validate/)
  for (const field of ["source_path", "source_bytes", "source_sha256"]) assert.match(pipeline, new RegExp(`^- ${field}:`, "m"))
  assert.match(style, /chapter-boundary\.js validate/)
  assert.doesNotMatch(style, /grep -nE '\^第/)
  assert.doesNotMatch(style, /调整 regex|重新识别章节|再次切片/)
})
