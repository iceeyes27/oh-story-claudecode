#!/usr/bin/env node
// scripts/check-transaction-ledger.js
// 检查章节标题金额与正文交割金额一致性，防止虚假额度/未兑现空文算入标题成交额

const fs = require('fs');
const path = require('path');

const cnNums = { '零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9, '十': 10, '百': 100, '千': 1000, '万': 10000 };

function parseChineseNumber(str) {
  let total = 0;
  let r = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str[i];
    const val = cnNums[char];
    if (val === undefined) continue;
    if (val >= 10) {
      if (r === 0) r = 1;
      if (val === 10000) {
        total = (total + r) * 10000;
        r = 0;
      } else {
        total += r * val;
        r = 0;
      }
    } else {
      r = val;
    }
  }
  return total + r;
}

function checkChapter(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const lines = content.split(/\r?\n/);
  const titleLine = lines.find(l => l.startsWith('#') || l.startsWith('###')) || lines[0] || '';
  
  // 匹配标题中的金额，如《四万三千美金》《八千美金》《五万块》
  const titleMatch = titleLine.match(/([零一二两三四五六七八九十百千万]+)(美金|美元|盾|越盾|万盾|块)/);
  if (!titleMatch) return [];

  const titleDeclaredNum = parseChineseNumber(titleMatch[1]);
  const unit = titleMatch[2];
  const findings = [];

  // 检查正文中是否存在“虚空额度”、“看货额度”、“垫头不是定金”且与标题金额相关
  const quotaMatch = content.match(/([零一二两三四五六七八九十百千万]+)(?:美金|美元|盾)?(?:的)?(?:看货额度|额度就是空文|不是定金)/);
  if (quotaMatch) {
    const quotaNum = parseChineseNumber(quotaMatch[1]);
    findings.push({
      file: filePath,
      title: titleLine,
      declaredAmount: `${titleMatch[1]}${unit} (${titleDeclaredNum})`,
      issue: `标题声明交割金额为 ${titleMatch[1]}${unit}，但正文包含未兑现/虚空额度 [${quotaMatch[0]}]；若该额度 (${quotaNum}) 属于未来可能额度而非当场实际交割，则不能作为实收款计入成交标题。必须坐实款项（如定金/现金）或修正标题。`
    });
  }

  return findings;
}

function main() {
  const args = process.argv.slice(2);
  const targetDir = args[0] || '我在越南捞沉船/正文';
  let totalFindings = 0;

  function walk(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) walk(full);
      else if (e.isFile() && e.name.endsWith('.md')) {
        const findings = checkChapter(full);
        if (findings.length > 0) {
          totalFindings += findings.length;
          findings.forEach(f => {
            console.error(`[blocking] ${f.file}: ${f.issue}`);
          });
        }
      }
    }
  }

  if (fs.existsSync(targetDir)) {
    walk(targetDir);
  }

  if (totalFindings > 0) {
    console.error(`\nTotal transaction ledger discrepancies: ${totalFindings}`);
    process.exit(1);
  } else {
    console.log('Transaction ledger audit: PASS (0 discrepancies)');
  }
}

if (require.main === module) {
  main();
}
