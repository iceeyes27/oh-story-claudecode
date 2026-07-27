#!/usr/bin/env node
'use strict';

// check-sop-dialogue.js
//
// 独立扫描器：检测小说正文里「SOP 式 / 极简词 / 说明书式」对白违规。
// 与 check-ai-patterns.js（Gate A 综合扫描）互补——后者已覆盖
// 「不是…是…」两段式（not-is / reverse-not-is）和通用动作清单（action-list-tic），
// 本脚本聚焦本次（2026-07-22《法援律师》全书 75 章对白体检）确证为违规、
// 但尚未被精准覆盖的四类模式：
//
//   1. 编号 SOP 步骤  blocking  ——「第一步…第二步…第三步」（第002章原稿违规）
//   2. 说明书式开场    blocking  ——「从现在开始 …」（第011/013章原稿违规）
//   3. 枚举清单        advisory  ——「一、二、三、」同句 ≥3；「其一/其二」≥2
//   4. 裸「看」枚举    advisory  ——同句 ≥3 个「看X」（看人、看门禁、看住宿、看食堂）
//   5. 压缩词          advisory  ——已发现并固化的压缩说法（能进门的 / 指位置 / …）
//
// 严重度约定：
//   blocking  = 几乎肯定违规，出现即需改写（与 check-ai-patterns 的 blocking 同义）。
//   advisory  = 候选，需人工读上下文判定（枚举/裸看在人物节拍或安抚技术里可保留，
//                如第005章韩克勤回调、第021章对受创未成年人「只问三个问题」）。
//
// 设计原则（与体检一致）：脚本只报候选，绝不自动改写；真正判定靠人。
// 报错基线：本脚本对「已修」的第002/013章应当零命中；对「原稿」应精准命中。
//
// 用法：node check-sop-dialogue.js [--json] [--fail-on=blocking|all] <文件或目录...>
//   - 目录会递归展开所有 *.md
//   - 默认 --fail-on=all：有任何 finding 即退出 1；--fail-on=blocking 仅 blocking 退出 1

const fs = require('fs');
const path = require('path');

const USAGE = `Usage: node check-sop-dialogue.js [--json] [--fail-on=blocking|all] <file-or-dir...>

Detect SOP-style / compressed-word / manual-style dialogue violations in novel prose:
  - numbered SOP steps (第一步…第二步…第三步)            [blocking]
  - manual-style opener (从现在开始 …)                    [blocking]
  - numbered enumeration (一、二、三、 / 其一·其二)       [advisory]
  - bare 看 enumeration (看人、看门禁、看住宿、看食堂)    [advisory]
  - compressed words (能进门的 / 指位置 / …)              [advisory]

Each finding carries severity: blocking (rewrite-now) or advisory (human review).
The script reports candidates only; it never rewrites text.
Calibration baseline: yields 0 hits on the fixed Ch002/Ch013, precise hits on the originals.`;

const options = {
  json: false,
  targets: [],
  failOn: 'all',
};

for (let i = 2; i < process.argv.length; i += 1) {
  const arg = process.argv[i];
  if (arg === '--json') {
    options.json = true;
  } else if (arg === '--check') {
    // symmetry with check-ai-patterns.js; detection is always check-only
  } else if (arg.startsWith('--fail-on=')) {
    const v = arg.slice('--fail-on='.length);
    if (v !== 'blocking' && v !== 'all') die(`--fail-on must be 'blocking' or 'all'`);
    options.failOn = v;
  } else if (arg === '-h' || arg === '--help') {
    process.stdout.write(`${USAGE}\n`);
    process.exit(0);
  } else if (arg.startsWith('-')) {
    die(`Unknown option: ${arg}`);
  } else {
    options.targets.push(arg);
  }
}

if (options.targets.length === 0) die('No files or directories provided');

let failed = false;
const allFindings = [];

for (const target of options.targets) {
  const abs = path.resolve(target);
  let stat;
  try {
    stat = fs.statSync(abs);
  } catch (error) {
    failed = true;
    if (!options.json) console.error(`${target}: unable to access (${error.message})`);
    continue;
  }
  const files = stat.isDirectory() ? expandDir(abs) : [abs];
  for (const file of files) {
    let input;
    try {
      input = fs.readFileSync(file, 'utf8');
    } catch (error) {
      failed = true;
      if (!options.json) console.error(`${file}: unable to read (${error.message})`);
      continue;
    }
    const findings = scanDocument(input).map((f) => ({ file, ...f }));
    allFindings.push(...findings);
  }
}

if (options.json) {
  process.stdout.write(`${JSON.stringify({ findings: allFindings }, null, 2)}\n`);
} else {
  if (allFindings.length === 0) {
    console.log('OK: no SOP-dialogue candidates found.');
  } else {
    for (const f of allFindings) {
      console.log(`${f.file}:${f.line}:${f.column}: [${f.severity}] ${f.type}: ${f.message} (${f.excerpt})`);
    }
  }
}

if (failed) process.exit(2);
const hasBlocking = allFindings.some((f) => f.severity === 'blocking');
if (options.failOn === 'blocking' ? hasBlocking : allFindings.length > 0) process.exit(1);

function die(message) {
  console.error(message);
  console.error(USAGE.trimEnd());
  process.exit(2);
}

function expandDir(dir) {
  const out = [];
  const walk = (cur) => {
    let entries;
    try {
      entries = fs.readdirSync(cur, { withFileTypes: true });
    } catch (e) {
      return;
    }
    for (const ent of entries) {
      const p = path.join(cur, ent.name);
      if (ent.isDirectory()) {
        walk(p);
      } else if (ent.isFile() && /\.md$/i.test(ent.name)) {
        out.push(p);
      }
    }
  };
  walk(dir);
  return out;
}

function scanDocument(input) {
  const lines = input.split(/\r?\n/);
  const findings = [];
  let inFrontMatter = hasYamlFrontMatter(lines);

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i];
    const trimmed = line.trim();
    if (inFrontMatter) {
      if (i > 0 && trimmed === '---') inFrontMatter = false;
      continue;
    }
    if (trimmed === '' || isDivider(trimmed) || isStructural(trimmed)) continue;

    const lineNo = i + 1;
    // 逐句检测（引号内台词也参与；本脚本的模式都是 SOP/说明书特征，
    // 台词里出现同样要报，与体检范围一致）。
    const sentences = splitSentences(trimmed);
    for (const sent of sentences) {
      findings.push(...scanSentence(sent, lineNo));
    }
  }
  findings.sort((a, b) => a.line - b.line || a.column - b.column);
  return findings;
}

function scanSentence(sent, lineNo) {
  const findings = [];

  // 1. 编号 SOP 步骤（blocking）：「第一步，…」「第二步：…」——步标签后接分隔符才是指令；
  //    「启动/走完第一步」里第一步是名词宾语，不误报（校准：Ch005「够启动第一步」、Ch026「只走第一步」不命中）。
  const STEP_RE = /第[一二三四五六七八九十百零\d]+步[，：。、]/g;
  let m;
  while ((m = STEP_RE.exec(sent)) !== null) {
    findings.push({
      line: lineNo,
      column: sent.indexOf(m[0]) + 1,
      type: 'sop-numbered-steps',
      severity: 'blocking',
      message: '编号 SOP 步骤「第X步」：流程手册腔；改成自然说话（先…再…），保留具体宾语。',
      excerpt: compact(sent),
    });
    break; // 一句只报一次
  }
  if (findings.length > 0) return findings;

  // 2. 说明书式开场（blocking）：从现在开始 …
  if (/从现在开始/.test(sent)) {
    findings.push({
      line: lineNo,
      column: sent.indexOf('从现在开始') + 1,
      type: 'sop-manual-opener',
      severity: 'blocking',
      message: '说明书式开场「从现在开始」：台词像在给读者讲规则；直接对眼前人说人话，去掉指令词。 ',
      excerpt: compact(sent),
    });
    return findings;
  }

  // 3. 枚举清单（advisory）：同句 「一、二、三、」≥3，或「其一/其二」≥2
  const enumHits = (sent.match(/[一二三四五六七八九十百零\d]+[、。．.]/g) || []).length;
  const qiHits = (sent.match(/其[一二三四五六]/g) || []).length;
  if (enumHits >= 3 || qiHits >= 2) {
    findings.push({
      line: lineNo,
      column: 1,
      type: 'sop-numbered-enum',
      severity: 'advisory',
      message: `编号枚举（${enumHits} 处编号 / ${qiHits} 处其X）：若是人物节拍或有后文呼应可保留，否则改成自然叙述。`,
      excerpt: compact(sent),
    });
    return findings;
  }

  // 4. 裸「看」枚举（advisory）：同句 ≥3 个「看X」（看后非持续/趋向补语，且非看看/看了 这类自然动词）
  const bareLook = (sent.match(/看(?!着|到|向|不|得|上|下|起|见|来|去|成|作|做|为|似|了|过|看)/g) || []).length;
  if (bareLook >= 3) {
    findings.push({
      line: lineNo,
      column: 1,
      type: 'sop-bare-look-enum',
      severity: 'advisory',
      message: `裸「看」枚举（${bareLook} 处）：清单式罗列；合并成「一样样看过来」式自然说法，或落到具体动作。`,
      excerpt: compact(sent),
    });
    return findings;
  }

  // 5. 压缩词（advisory）：已固化发现的压缩说法（能进门的 / 指位置 / …）
  const COMPRESSED = ['能进门的', '指位置', '指个位置', '报位置'];
  for (const phrase of COMPRESSED) {
    const idx = sent.indexOf(phrase);
    if (idx !== -1) {
      findings.push({
        line: lineNo,
        column: idx + 1,
        type: 'sop-compressed-word',
        severity: 'advisory',
        message: `压缩词「${phrase}」：动作/对象被省到要读者猜；补全具体动作和对象（如「能进门的」→「能拿钥匙开门进去的人」）。`,
        excerpt: compact(sent),
      });
      return findings;
    }
  }

  return findings;
}

function isDivider(trimmed) {
  return /^-{3,}$/.test(trimmed) || /^[*_]{3,}$/.test(trimmed);
}

function isStructural(trimmed) {
  return /^(#{1,6}\s|>\s?|[-*+]\s|\d+[.)]\s|\|)/.test(trimmed)
    || /^第[零一二三四五六七八九十百千万\d]+章(?:\s|_|$)/.test(trimmed);
}

function splitSentences(trimmed) {
  return trimmed
    .split(/[。！？!?]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

function hasYamlFrontMatter(lines) {
  if (!lines[0] || lines[0].trim() !== '---') return false;
  let sawField = false;
  for (let i = 1; i < Math.min(lines.length, 40); i += 1) {
    const trimmed = lines[i].trim();
    if (trimmed === '---') return sawField;
    if (/^[A-Za-z0-9_-]+:\s*/.test(trimmed)) sawField = true;
  }
  return false;
}

function compact(text) {
  const normalized = text.replace(/\s+/g, ' ').trim();
  return normalized.length > 80 ? `${normalized.slice(0, 77)}...` : normalized;
}
