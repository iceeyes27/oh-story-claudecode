"use strict";

const QIDIAN_BOOK_FIELDS = Object.freeze([
  "rank",
  "title",
  "author",
  "genre",
  "status",
  "contractStatus",
  "chargeMode",
  "wordCount",
  "totalRecommend",
  "tags",
  "latestUpdate",
  "url",
  "description",
]);

function failCli(errors) {
  const error = new Error(`参数错误：\n- ${errors.join("\n- ")}`);
  error.code = "SCAN_CLI_INVALID";
  throw error;
}

/**
 * Parse a complete option grammar before the caller performs any I/O.
 * spec values: { type: "string"|"integer"|"enum"|"flag", default, min, max, values }.
 */
function parseCli(argv, spec) {
  const result = {};
  const seen = new Set();
  const errors = [];

  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (typeof token !== "string" || !token.startsWith("--") || token === "--") {
      errors.push(`不允许位置参数：${String(token)}`);
      continue;
    }

    const eq = token.indexOf("=");
    const name = eq >= 0 ? token.slice(0, eq) : token;
    const rule = spec[name];
    if (!rule) {
      errors.push(`未知参数 ${name}；合法参数：${Object.keys(spec).join("、")}`);
      continue;
    }
    if (seen.has(name)) {
      errors.push(`参数 ${name} 不得重复`);
      continue;
    }
    seen.add(name);

    if (rule.type === "flag") {
      if (eq >= 0) errors.push(`开关参数 ${name} 不接受值`);
      else result[name.slice(2)] = true;
      continue;
    }

    let value;
    if (eq >= 0) {
      value = token.slice(eq + 1);
    } else {
      const next = argv[i + 1];
      if (next === undefined || String(next).startsWith("--")) {
        errors.push(`参数 ${name} 缺少值`);
        continue;
      }
      value = next;
      i++;
    }
    if (value === "") {
      errors.push(`参数 ${name} 的值不能为空`);
      continue;
    }

    if (rule.type === "integer") {
      if (!/^[0-9]+$/.test(value)) {
        errors.push(`参数 ${name} 必须是整数 ${rule.min}-${rule.max}`);
        continue;
      }
      const n = Number(value);
      if (!Number.isSafeInteger(n) || n < rule.min || n > rule.max) {
        errors.push(`参数 ${name} 必须在 ${rule.min}-${rule.max} 之间`);
        continue;
      }
      result[name.slice(2)] = n;
    } else if (rule.type === "enum") {
      if (!rule.values.includes(value)) {
        errors.push(`参数 ${name} 的合法值：${rule.values.join("、")}`);
        continue;
      }
      result[name.slice(2)] = value;
    } else {
      result[name.slice(2)] = value;
    }
  }

  for (const [name, rule] of Object.entries(spec)) {
    const key = name.slice(2);
    if (!Object.prototype.hasOwnProperty.call(result, key)) {
      result[key] = rule.type === "flag" ? false : rule.default;
    }
  }
  if (errors.length) failCli(errors);
  return Object.freeze(result);
}

function truncateDescription(value, maxChars = 100) {
  const text = value == null ? "" : String(value).replace(/\s+/g, " ").trim();
  const chars = Array.from(text);
  if (chars.length <= maxChars) return text;
  return chars.slice(0, maxChars).join("") + "...";
}

function pad2(value) {
  return String(value).padStart(2, "0");
}

/** One Date instance supplies both the local filename date and timestamp. */
function createTimeSnapshot(now = new Date()) {
  const y = now.getFullYear();
  const m = pad2(now.getMonth() + 1);
  const d = pad2(now.getDate());
  const hh = pad2(now.getHours());
  const mm = pad2(now.getMinutes());
  const ss = pad2(now.getSeconds());
  const ms = String(now.getMilliseconds()).padStart(3, "0");
  const offsetMinutes = -now.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const offset = Math.abs(offsetMinutes);
  const zone = `${sign}${pad2(Math.floor(offset / 60))}:${pad2(offset % 60)}`;
  return Object.freeze({
    dateStamp: `${y}${m}${d}`,
    capturedAt: `${y}-${m}-${d}T${hh}:${mm}:${ss}.${ms}${zone}`,
  });
}

function present(value) {
  if (value == null || value === "") return null;
  if (Array.isArray(value)) return value.length ? value : null;
  return value;
}

function normalizeQidianBook(raw = {}) {
  const record = {};
  for (const field of QIDIAN_BOOK_FIELDS) {
    let value = present(raw[field]);
    if (field === "description" && value !== null) value = truncateDescription(value);
    record[field] = value;
  }
  record.missing_fields = QIDIAN_BOOK_FIELDS.filter((field) => record[field] === null);
  return record;
}

function summarizeMissing(records) {
  const counts = {};
  for (const record of records) {
    for (const field of record.missing_fields || []) counts[field] = (counts[field] || 0) + 1;
  }
  return Object.keys(counts).length
    ? Object.entries(counts).map(([field, count]) => `${field}:${count}`).join("，")
    : "none";
}

module.exports = {
  QIDIAN_BOOK_FIELDS,
  parseCli,
  truncateDescription,
  createTimeSnapshot,
  normalizeQidianBook,
  summarizeMissing,
};
