#!/usr/bin/env node
/**
 * check-chapter-titles.js
 * 章节标题 AI 味 / 模板套路自动化扫描
 *
 * 用法:
 *   node check-chapter-titles.js --dir "正文目录路径"
 *   node check-chapter-titles.js --dir "法援律师：我专打赢不了的官司/正文" [--json]
 *
 * 输出: 按严重度分类的问题列表（blocking / advisory）
 */

const fs = require('fs');
const path = require('path');

// ─── CLI ────────────────────────────────────────────────────
const args = process.argv.slice(2);
let dir = '';
let jsonMode = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--dir' && args[i + 1]) dir = args[++i];
  if (args[i] === '--json') jsonMode = true;
}
if (!dir) {
  console.error('用法: node check-chapter-titles.js --dir "正文目录路径" [--json]');
  process.exit(1);
}

// ─── 收集章节文件 ──────────────────────────────────────────
function collectChapters(root) {
  const results = [];
  function walk(d) {
    for (const ent of fs.readdirSync(d, { withFileTypes: true })) {
      if (ent.isDirectory()) walk(path.join(d, ent.name));
      else if (ent.name.match(/^第\d+章_.*\.md$/)) {
        const m = ent.name.match(/^第(\d+)章_(.+)\.md$/);
        if (m) {
          results.push({
            file: path.join(d, ent.name),
            num: parseInt(m[1], 10),
            title: m[2],
          });
        }
      }
    }
  }
  walk(root);
  results.sort((a, b) => a.num - b.num);
  return results;
}

// ─── 检测规则 ──────────────────────────────────────────────

/**
 * 规则1: AI 金句对仗句式（blocking）
 * "这不是X，这是Y" / "X只是Y" / "X不会Y" / "X不是Y，是Z"
 */
const PATTERN_JINYU = [
  { re: /^这不是.+[，,]这是.+$/, desc: '"这不是X，这是Y"金句对仗' },
  { re: /^这不是.+[，,]而是.+$/, desc: '"这不是X，而是Y"金句对仗' },
  { re: /^.+不是.+[，,]是.+$/, desc: '"X不是Y，是Z"金句对仗' },
  { re: /^.+只是.{1,6}$/, desc: '"X只是Y"揭露式金句' },
  { re: /^.{1,4}不会.{1,4}$/, desc: '"X不会Y"拟人金句（短标题）' },
  { re: /^.{1,4}不能.{1,4}$/, desc: '"X不能Y"否定式金句（短标题）' },
];

/**
 * 规则1b: 偏正修饰从句 / 剧情摘要压缩句式（blocking）
 * 禁止将细纲梗概（如“刚出事就递笔”）压缩为“刚出事就递来的笔”这类 AI 偏正从句
 */
const PATTERN_RELATIVE_CLAUSE = [
  { re: /^(刚|一|在|从|被|把|死后|事后|出事|之前|之后).+?的.+$/, desc: '偏正修饰从句（"刚/从/被/把/死后...的..."剧情摘要腔，请改为具体名词或动作）' },
  { re: /^.+[，,].*?(与|和).+$/, desc: '散文式"X，与/和Y"并列句' },
  { re: /^.+二字[，,].+$/, desc: '"XX二字，"抽象口号句' },
  { re: /^谁.+谁.+谁.+$/, desc: '三段式排比设问句' },
  { re: /^.+不能再.+$/, desc: '大纲式叙事说明句' },
  { re: /^.+是谁[划抹删写弄].+$/, desc: '设问句式' },
  { re: /^(我也想|今晚看|单子不是|空海也|抢海的人|懂行的人).+$/, desc: '口语化/否定式大纲从句，请改为干脆硬质物证或动作' },
];

/**
 * 规则2: 抽象比喻与假大空套路词当标题（blocking）
 */
const ABSTRACT_METAPHORS = [
  /拼图/, /画线/, /余波/, /交锋/, /底色/, /暗涌/,
  /注脚/, /锚点/, /坐标/, /切面/, /刻度/,
  /余温/, /余烬/, /余响/, /回声/,
  /定鼎/, /称雄/, /破晓/, /暗流再起/,
];

/**
 * 规则3: 煽情/升华腔（blocking）
 */
const PATTERN_SHUANGQING = [
  { re: /^终于.+$/, desc: '"终于X"煽情收束' },
  { re: /^终于有人.+$/, desc: '"终于有人X"煽情收束' },
  { re: /^第一次[，,].+$/, desc: '"第一次，X"刻意煽情' },
  { re: /^在.+的地方.+$/, desc: '"在X的地方Y"文艺腔' },
  { re: /^人心.+$/, desc: '"人心X"主题升华' },
];

/**
 * 规则4: 过长标题（blocking，标准 2~6 字，严禁超过 7 字）
 */
const MAX_TITLE_LEN = 7;

/**
 * 规则5: 模板句式频次检测（advisory）
 */
const TEMPLATE_PATTERNS = [
  { re: /^把.+/, key: '"把X"祈使句开头' },
  { re: /^先.+[，,]再.+/, key: '"先X，再Y"句式' },
  { re: /^三[^卷章]/, key: '"三X"模板' },
  { re: /^.+[，,].+[，,].+$/, key: '双逗号多分句标题' },
];

/**
 * 规则6: 重复/撞车检测（blocking）
 */
function isSimilar(a, b) {
  const cleanA = a.replace(/[0-9，。！？、""''：；\s]/g, '');
  const cleanB = b.replace(/[0-9，。！？、""''：；\s]/g, '');
  if (cleanA.length >= 4 && cleanB.length >= 4) {
    if (cleanA.includes(cleanB) || cleanB.includes(cleanA)) return true;
  }
  const suffLen = 4;
  if (cleanA.length >= suffLen && cleanB.length >= suffLen) {
    if (cleanA.slice(-suffLen) === cleanB.slice(-suffLen)) return true;
  }
  return false;
}

// ─── 执行扫描 ──────────────────────────────────────────────

const chapters = collectChapters(path.resolve(dir));
if (chapters.length === 0) {
  console.error(`未在 ${dir} 下找到章节文件`);
  process.exit(1);
}

const findings = [];

for (const ch of chapters) {
  for (const p of PATTERN_JINYU) {
    if (p.re.test(ch.title)) {
      findings.push({ num: ch.num, title: ch.title, rule: '金句对仗', severity: 'blocking', desc: p.desc });
    }
  }
  for (const p of PATTERN_RELATIVE_CLAUSE) {
    if (p.re.test(ch.title)) {
      findings.push({ num: ch.num, title: ch.title, rule: '偏正从句/摘要腔', severity: 'blocking', desc: p.desc });
    }
  }
  for (const re of ABSTRACT_METAPHORS) {
    if (re.test(ch.title)) {
      findings.push({ num: ch.num, title: ch.title, rule: '抽象比喻', severity: 'blocking', desc: `含抽象比喻词「${ch.title.match(re)[0]}」` });
    }
  }
  for (const p of PATTERN_SHUANGQING) {
    if (p.re.test(ch.title)) {
      findings.push({ num: ch.num, title: ch.title, rule: '煽情升华', severity: 'blocking', desc: p.desc });
    }
  }
  if (ch.title.length > MAX_TITLE_LEN) {
    findings.push({ num: ch.num, title: ch.title, rule: '标题过长', severity: 'blocking', desc: `${ch.title.length}字，超过${MAX_TITLE_LEN}字上限（标准为2~6字，最长7字）` });
  }
  // 规则4b: 叠床架屋重字检测（如《海上海警》《断水断电》等4字内同字出现2次）
  if (ch.title.length <= 4 && !/^[0-9一二三四五六七八九十百千]+$/.test(ch.title)) {
    for (const c of ch.title) {
      if (ch.title.split(c).length - 1 >= 2) {
        findings.push({ num: ch.num, title: ch.title, rule: '叠字重字', severity: 'blocking', desc: `4字内包含重复单字「${c}」，属于叠床架屋式口水化命名` });
        break;
      }
    }
  }
}

// 规则5: 模板频次
const templateCounts = {};
for (const tp of TEMPLATE_PATTERNS) templateCounts[tp.key] = [];
for (const ch of chapters) {
  for (const tp of TEMPLATE_PATTERNS) {
    if (tp.re.test(ch.title)) templateCounts[tp.key].push(ch.num);
  }
}
const TEMPLATE_THRESHOLD = 4;
for (const [key, nums] of Object.entries(templateCounts)) {
  if (nums.length >= TEMPLATE_THRESHOLD) {
    findings.push({
      num: 0, title: `出现${nums.length}次`,
      rule: '模板频次', severity: 'advisory',
      desc: `${key}共${nums.length}次：第${nums.join('、')}章`,
    });
  }
}

// 规则6: 重复/撞车与相邻同质化检测
const MONEY_PATTERN = /[一二两三四五六七八九十百千万\d]+(万|千|百|块|元)/;
const STOP_CHARS = '的了一是个不没在有和与从到被把';

for (let i = 0; i < chapters.length; i++) {
  const chA = chapters[i];
  const cleanA = chA.title.replace(/[0-9，。！？、""''：；\s]/g, '');

  for (let j = i + 1; j < chapters.length; j++) {
    const chB = chapters[j];
    const cleanB = chB.title.replace(/[0-9，。！？、""''：；\s]/g, '');
    const dist = chB.num - chA.num;

    // 6.1 完全重名（blocking）
    if (chA.title === chB.title) {
      findings.push({
        num: chA.num, title: chA.title,
        rule: '标题完全重名', severity: 'blocking',
        desc: `与第${chB.num}章「${chB.title}」完全重名`,
      });
    }
    // 6.2 近距离子串复读（10章内，长度>=2的子串完全包含，blocking）
    else if (dist <= 10 && Math.min(cleanA.length, cleanB.length) >= 2 && (cleanA.includes(cleanB) || cleanB.includes(cleanA))) {
      findings.push({
        num: chA.num, title: chA.title,
        rule: '标题近距离子串复读', severity: 'blocking',
        desc: `与第${chB.num}章「${chB.title}」存在近距离子串重复（距离仅${dist}章），请拉开差异`,
      });
    }
    // 6.3 远距离高重合度（4字以上后缀或包含，blocking）
    else if (dist > 10 && isSimilar(chA.title, chB.title)) {
      findings.push({
        num: chA.num, title: chA.title,
        rule: '标题高度相似', severity: 'blocking',
        desc: `与第${chB.num}章「${chB.title}」高度相似`,
      });
    }

    // 6.4 相邻章节（3章内）金额数字连撞（blocking）
    if (dist <= 3 && MONEY_PATTERN.test(chA.title) && MONEY_PATTERN.test(chB.title)) {
      findings.push({
        num: chA.num, title: chA.title,
        rule: '相邻金额命名连撞', severity: 'blocking',
        desc: `与第${chB.num}章「${chB.title}」连续使用金额数字命名（距离${dist}章），形成模板疲劳，请改为硬物证或具体动作`,
      });
    }

    // 6.5 相邻章节（2章内）核心实词撞车（blocking）
    if (dist <= 2) {
      for (let k = 0; k < cleanA.length - 1; k++) {
        const gram = cleanA.substr(k, 2);
        if (STOP_CHARS.includes(gram[0]) || STOP_CHARS.includes(gram[1])) continue;
        if (cleanB.includes(gram)) {
          findings.push({
            num: chA.num, title: chA.title,
            rule: '相邻章节核心词撞车', severity: 'blocking',
            desc: `与第${chB.num}章「${chB.title}」共享词汇「${gram}」，请拉开命名差异`,
          });
          break;
        }
      }
    }
  }
}

// ─── 输出 ────────────────────────────────────────────────
if (jsonMode) {
  console.log(JSON.stringify({ total: chapters.length, findings }, null, 2));
} else {
  const blocking = findings.filter(f => f.severity === 'blocking');
  const advisory = findings.filter(f => f.severity === 'advisory');

  console.log(`\n📖 章节标题扫描：共 ${chapters.length} 章\n`);

  if (blocking.length > 0) {
    console.log(`🔴 Blocking（建议改）：${blocking.length} 条`);
    console.log('─'.repeat(60));
    for (const f of blocking) {
      const prefix = f.num > 0 ? `  第${String(f.num).padStart(3, '0')}章` : '  [全局]';
      console.log(`${prefix} │ ${f.rule} │ ${f.desc}`);
      if (f.num > 0) console.log(`${''.padStart(prefix.length)}   当前：${f.title}`);
    }
    console.log('');
  }

  if (advisory.length > 0) {
    console.log(`🟡 Advisory（留意）：${advisory.length} 条`);
    console.log('─'.repeat(60));
    for (const f of advisory) {
      const prefix = f.num > 0 ? `  第${String(f.num).padStart(3, '0')}章` : '  [全局]';
      console.log(`${prefix} │ ${f.rule} │ ${f.desc}`);
      if (f.num > 0) console.log(`${''.padStart(prefix.length)}   当前：${f.title}`);
    }
    console.log('');
  }

  if (findings.length === 0) {
    console.log('✅ 未发现章节标题问题\n');
  }

  process.exit(blocking.length > 0 ? 1 : 0);
}
