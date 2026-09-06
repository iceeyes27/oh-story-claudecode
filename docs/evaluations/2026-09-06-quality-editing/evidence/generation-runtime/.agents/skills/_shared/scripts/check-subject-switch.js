#!/usr/bin/env node
/**
 * check-subject-switch.js — 主语歧义 / 视角断裂（段首"他/她"承接错位）段落级检测
 *
 * 背景：同一场景/相邻段里，叙述主语从角色 A 切到角色 B，但 B 仍用"他/她"指代且未点名，
 * 读者按就近原则会误读成 A（例：Ch001「周春来还坐在那里…」后紧接「他…三天。够了。」
 * ——"三天"实为江澈对韩克勤期限的回应，主语已切到江澈却未点名）。
 *
 * 用法：node check-subject-switch.js <file...|dir...>   （目录会递归收第*.md）
 *
 * 输出：advisory 疑似清单（含上段末句与本段首行），供人工复核，不自动判错——
 * 正常承接（段首"他/她"就是指上段主角，如「江澈把协议按平」→「他盯着…」）占绝大多数，
 * 不算病；只有"场景跳切/定格句后换人/独立短心声承接错人"才需要点名主语或加过渡。
 *
 * 严重度语义：仅 advisory。判定口诀——段首"他/她"的所指，能靠性别代词、场景连续、
 * 前文点名明确辨认的，豁免；读起来会误当成上段角色、或动作归属矛盾（如"攥协议/三天"），
 * 才是真错位，该点名/加过渡。
 */
const fs = require('fs');
const path = require('path');

const NAMES = ['江澈','苏青岚','周春来','李澜','韩克勤','老郑','张姐','周某','孙恒','陈叔',
  '方某','林晚','顾建民','周母','程文山','王世诚','彭晓蕊','主任','唐圆圆','许昭','赵敏','何嘉','周父'];
const SCENE = ['楼道','门口','走廊','门外','窗边','窗外','转过身','走出','推门','出了门',
  '进了门','走到','起身','站起来','往回走','离开','办公室','走廊尽头','转身'];
const FIX = ['还坐在那里','仍坐在那里','还站在原地','仍站在原地','站在原地','没动','愣在原地',
  '坐在那里没动','低头坐在','坐了很久','沉默着'];

function splitParas(lines) {
  const out = []; let cur = [];
  for (const l of lines) {
    const t = l.trim();
    if (!t) { if (cur.length) { out.push(cur); cur = []; } }
    else cur.push(t);
  }
  if (cur.length) out.push(cur);
  return out;
}

function isSubjectPronounStart(s) {
  return /^(他|她|他又|她仍|他没|她没|他更|她更|他只是|她只是)(?![们])/.test(s);
}

function collectFiles(args) {
  const files = [];
  for (const a of args) {
    try {
      const st = fs.statSync(a);
      if (st.isFile()) files.push(a);
      else if (st.isDirectory()) {
        const walk = (d) => {
          for (const e of fs.readdirSync(d, { withFileTypes: true })) {
            const p = path.join(d, e.name);
            if (e.isDirectory()) walk(p);
            else if (e.name.endsWith('.md') && /^第\d+章/.test(e.name)) files.push(p);
          }
        };
        walk(a);
      }
    } catch (_) { /* skip */ }
  }
  return files;
}

const results = [];
for (const file of collectFiles(process.argv.slice(2))) {
  const ps = splitParas(fs.readFileSync(file, 'utf-8').split('\n'));
  const fn = path.basename(file);
  for (let i = 0; i < ps.length; i++) {
    const p = ps[i];
    const first = p[0];
    if (!isSubjectPronounStart(first)) continue;
    if (NAMES.some((n) => first.includes(n))) continue; // 本段已点名，不算
    const head = p.length > 1 ? p[0] + p[1] : p[0];
    const sceneHit = SCENE.some((w) => head.includes(w));
    const prev = i > 0 ? ps[i - 1] : null;
    const prevLast = prev ? prev[prev.length - 1] : '';
    const prevNamed = prev ? NAMES.some((n) => prevLast.includes(n)) : false;
    const fixHit = prev ? FIX.some((w) => prevLast.includes(w)) : false;
    const shortHit = first.length <= 8 && prevNamed;
    const tag = sceneHit ? 'A-场景位移' : (fixHit ? 'C-上段定格' : (shortHit ? 'B-短段心声' : ''));
    if (tag) {
      results.push({
        file: fn, para: i + 1, tag,
        prev: prevLast.slice(0, 44), cur: first.slice(0, 44),
        hint: '请复核"他/她"是否仍指上段角色；若已切换视角/场景，请点名主语或加过渡。'
      });
    }
  }
}

if (results.length === 0) {
  console.log('Subject-switch audit: PASS (0 candidates)');
} else {
  console.log(`Subject-switch audit: ${results.length} candidate(s) — advisory, 需人工复核（正常承接豁免）\n`);
  for (const r of results) {
    console.log(`[${r.tag}] ${r.file} 段${r.para}\n  上段末：${r.prev}\n  本段首：${r.cur}\n  → ${r.hint}\n`);
  }
  process.exitCode = 2; // advisory
}
