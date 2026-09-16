#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""volume-audit.py - 长篇小说卷级生命周期健康度审计工具

用法：
    python volume-audit.py --project <书目录> --volume <卷号> [--write] [--json] [--strict]
                           [--candidate <尚未并入正文的候选章>]
    python volume-audit.py --project <书目录> --ends-at <章号> --json

核心检查：
    1. 卷契约与主矛盾闭环 (Volume_Contract_Integrity)
    2. 下一卷承接动力自检 (Next_Volume_Drive)
    3. 伏笔债务与收束率 (Foreshadow_Debt_Health)
    4. 战力层级与通胀健康度 (Power_Inflation_Check)
    5. 核心角色成长与状态同步 (Character_Arc_Integrity)

`--ends-at` 是给采用门用的反查模式：返回「显式声明的章节范围正好终止于该章」的卷号。
卷纲没有声明章节范围时返回空列表——调用方据此判断本章是不是卷末，不猜测边界。

退出码：
    0: PASS（无 blocking，或非 strict 模式下仅有 advisory）；--ends-at 模式恒为 0
    1: FAIL（存在 blocking，或 strict 模式下有 advisory/warning）
    2: 参数或目录读取错误
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

if sys.stdout.encoding != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

CN_NUMS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


def parse_volume_number(val: str) -> Optional[int]:
    val = val.strip()
    if val.isdigit():
        return int(val)
    if val in CN_NUMS:
        return CN_NUMS[val]
    # Check "第1卷" or "第一卷"
    m = re.match(r"^第?([0-9]+|[一二三四五六七八九十]+)卷?$", val)
    if m:
        sub = m.group(1)
        if sub.isdigit():
            return int(sub)
        if sub in CN_NUMS:
            return CN_NUMS[sub]
    return None


def find_volume_outline(project_dir: Path, vol_num: int) -> Optional[Path]:
    outline_dir = project_dir / "大纲"
    if not outline_dir.is_dir():
        return None

    # Try exact matches
    candidates = [
        f"卷纲_第{vol_num}卷.md",
        f"卷纲_第0{vol_num}卷.md",
        f"卷纲_第{vol_num}卷_*.md",
    ]
    # Invert CN_NUMS
    inv_cn = {v: k for k, v in CN_NUMS.items()}
    if vol_num in inv_cn:
        candidates.append(f"卷纲_第{inv_cn[vol_num]}卷.md")
        candidates.append(f"卷纲_第{inv_cn[vol_num]}卷_*.md")

    for cand in candidates:
        matches = list(outline_dir.glob(cand))
        if matches:
            return matches[0]

    # Broad regex search in outline dir
    for f in outline_dir.iterdir():
        if f.is_file() and f.suffix == ".md" and "卷纲" in f.name:
            v = parse_volume_number(f.name.replace("卷纲", "").replace(".md", "").strip("_·- "))
            if v == vol_num:
                return f

    return None


# 带「章节范围」标签的显式声明，如 章节范围：第 1–约 30 章
RANGE_LABELED = re.compile(
    r"章节范围[：:\s|]*第?\s*(\d+)\s*[–~至到\-]\s*(?:约\s*)?第?\s*(\d+)\s*章"
)
# 整行只有一个范围的写法，如 `- 第1-20章` / `## 第 1–约 30 章`。
# 必须整行匹配：行内还有其他文字时不算范围声明，避免把「每 3~5 章一个爽点」
# 这类行文误当成卷的章节范围，静默算出错误的审计口径。
RANGE_LINE_ONLY = re.compile(
    r"^\s*(?:[-*+]\s*|#{1,6}\s*)?第\s*(\d+)\s*[–~至到\-]\s*(?:约\s*)?第?\s*(\d+)\s*章\s*$"
)


# 核心矛盾必须是一处结构化声明：标题行（`## 核心矛盾`，见 artifact-protocols.md
# 卷纲模板）或带冒号的字段行（`主矛盾：…`）。旧写法把 `##` 只绑在第一个分支上，
# 正文任意位置出现「核心冲突」二字就算通过，与提示语的要求不符。
CONFLICT_TERMS = r"(?:本卷)?(?:核心矛盾|主矛盾|核心冲突|主要矛盾)"
CONFLICT_DECLARATION = re.compile(
    rf"^\s*(?:#{{1,6}}\s*{CONFLICT_TERMS}\s*$|[-*+]?\s*\**{CONFLICT_TERMS}\**\s*[：:])",
    re.MULTILINE,
)


def extract_chapter_range(outline_text: str) -> Tuple[Optional[int], Optional[int]]:
    """从卷纲提取章节范围，如 第 1–约 30 章，第1-20章 等。

    只接受显式声明；无法确定时返回 (None, None)，由调用方降级为
    完整审计报告范围不明，不能宣称整卷通过，不猜测范围。
    """
    m = RANGE_LABELED.search(outline_text)
    if m:
        return int(m.group(1)), int(m.group(2))
    for line in outline_text.splitlines():
        m = RANGE_LINE_ONLY.match(line)
        if m:
            return int(m.group(1)), int(m.group(2))
    return None, None


def iter_volume_outlines(project_dir: Path) -> List[Tuple[int, Path]]:
    """枚举 大纲/ 下所有能解析出卷号的卷纲文件，按卷号升序。"""
    outline_dir = project_dir / "大纲"
    if not outline_dir.is_dir():
        return []
    found: List[Tuple[int, Path]] = []
    for f in sorted(outline_dir.iterdir()):
        if not (f.is_file() and f.suffix == ".md" and "卷纲" in f.name):
            continue
        stem = f.name.replace("卷纲", "").replace(".md", "")
        # 兼容 卷纲_第2卷_书名.md：卷号只取第一段，后面的书名不参与解析。
        head = stem.strip("_·- ").split("_")[0]
        v = parse_volume_number(head)
        if v is not None and v >= 1:
            found.append((v, f))
    return sorted(found, key=lambda item: item[0])


def find_volumes_ending_at(project_dir: Path, chapter: int) -> List[int]:
    """返回「显式声明的章节范围正好终止于 chapter」的卷号列表。

    只认卷纲里显式写出的章节范围。范围未声明（extract_chapter_range 返回 None）时
    不参与判定——采用门据此静默放行，不靠猜测的卷边界去阻断作者。
    """
    ending: List[int] = []
    for vol_num, path in iter_volume_outlines(project_dir):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        _, end_ch = extract_chapter_range(text)
        if end_ch is not None and end_ch == chapter:
            ending.append(vol_num)
    return sorted(set(ending))


def setting_payoff_due_findings(
    project_dir: Path, start_ch: Optional[int], end_ch: Optional[int], metrics: Dict[str, Any],
    projected_state: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, str]]:
    """未启用（无登记表或追踪未开记账）→ 空；登记表损坏 → 直接把检查器的 blocking 带出。"""
    registry = project_dir / "设定" / "_设定登记.md"
    if start_ch is None or end_ch is None:
        return []
    state_path = project_dir / "追踪" / "_tracking-state.json"
    try:
        state = projected_state if projected_state is not None else json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        if not registry.is_file():
            return []
        return [{"severity":"blocking", "code":"Setting_Payoff_State", "message":"设定追踪状态无法读取，不能完成卷审计"}]
    if not registry.is_file() and not (state.get("setting_payoff") or {}).get("enabled"):
        return []
    checker = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts" / "check-setting-payoff.js"
    if not checker.is_file():
        return [{"severity": "blocking", "code": "Setting_Payoff_Checker_Missing", "message": "找不到 _shared/scripts/check-setting-payoff.js，设定兑现到期未审"}]
    try:
        import subprocess
        completed = subprocess.run(["node", str(checker), str(project_dir), "--json"], capture_output=True, text=True, encoding="utf-8", check=False)
        data = json.loads(completed.stdout)
    except (OSError, ValueError) as exc:
        return [{"severity": "blocking", "code": "Setting_Payoff_Checker_Failed", "message": f"设定兑现检查器未能运行：{exc}"}]
    out: List[Dict[str, str]] = []
    for f in data.get("findings", []):
        if f.get("severity") == "blocking":
            out.append({"severity": "blocking", "code": "Setting_Payoff_Registry", "message": str(f.get("message"))})
    tracking = data.get("tracking") or {}
    if not tracking.get("enabled"):
        return out
    records = state.get("setting_payoffs") or {}
    last = int(state.get("last_committed_chapter") or 0)
    entries = ((data.get("registry") or {}).get("entries")) or {}
    due, overdue_recurring = [], []
    for sid, entry in entries.items():
        if entry.get("type") == "payoff":
            target = entry.get("target") or {}
            to = target.get("to")
            if to is None:
                target_volume = parse_volume_number(str(target.get("volume") or ""))
                current_volume = int(metrics.get("volume") or 0)
                if target_volume is None or target_volume > current_volume:
                    continue
                # Keep the real volume boundary: an in-progress cutoff is not a volume end.
                to = end_ch
                if target_volume < current_volume:
                    previous_outline = find_volume_outline(project_dir, target_volume)
                    previous_end = extract_chapter_range(previous_outline.read_text(encoding="utf-8"))[1] if previous_outline else None
                    to = previous_end if previous_end is not None else start_ch - 1
                if last < to:
                    continue
            elif int(to) > min(end_ch, last) or int(to) < int(tracking.get("since") or 1):
                continue
            ok = any(r.get("result") == "已兑现" and int(r.get("chapter", 0)) <= min(last, end_ch) for r in (records.get(sid) or {}).get("records", []))
            if not ok:
                due.append(f"{sid}「{entry.get('title') or ''}」目标第{target.get('from')}–{to}章")
        elif entry.get("type") == "recurring" and entry.get("window"):
            recs = (records.get(sid) or {}).get("records", [])
            last_hit = max((int(r["chapter"]) for r in recs if r.get("result") == "已兑现" and int(r["chapter"]) <= min(last, end_ch)), default=None)
            gap = min(last, end_ch) - (last_hit if last_hit is not None else int(tracking.get("since") or 1) - 1)
            if gap > int(entry["window"]["max"]):
                overdue_recurring.append(f"{sid}「{entry.get('title') or ''}」已 {gap} 章未记录（窗口每 {entry['window']['min']}–{entry['window']['max']} 章）")
    metrics["setting_payoff_due"] = len(due)
    if due:
        out.append({"severity": "blocking", "code": "Setting_Payoff_Due", "message": "截至本卷到期仍未完整兑现的设定：" + "；".join(due) + "。返回细纲补足剩余义务；延期须改登记目标并记录理由，放弃须改为 retired 并保留理由；部分兑现/条件未触发不销账"})
    if overdue_recurring:
        out.append({"severity": "advisory", "code": "Setting_Payoff_Recurring_Overdue", "message": "贯穿设定超窗：" + "；".join(overdue_recurring)})
    return out


def chapter_inventory(project_dir, start_ch, end_ch, extra_prose=None, projected_state=None, through_chapter=None):
    """Inventory formal prose recursively; never count candidate/history directories."""
    findings = []
    by_chapter = {}
    def add_finding(code, message):
        findings.append({"severity": "blocking", "code": code, "message": message})
    def add_file(file):
        file = file.resolve()
        if re.search(r"(?:_原稿(?:_|\.)|_历史_|_候选_)", file.name):
            return
        match = re.match(r"^第0*(\d+)章.*\.md$", file.name)
        if not match:
            return
        chapter = int(match.group(1))
        if chapter < 1:
            return
        if start_ch is not None and end_ch is not None and not start_ch <= chapter <= end_ch:
            return
        paths = by_chapter.setdefault(chapter, [])
        if file.resolve() not in [old.resolve() for old in paths]:
            paths.append(file)
    def walk_error(error):
        add_finding("Prose_Unreadable", str(error))
    for directory, dirs, names in os.walk(project_dir / "正文", onerror=walk_error):
        dirs[:] = sorted(name for name in dirs if not name.startswith((".", "_原稿"))
                         and name not in {"候选", "_历史", "历史", "原稿", "归档", "node_modules"}
                         and not (Path(directory) / name).is_symlink())
        for name in sorted(names):
            file = Path(directory) / name
            if not file.is_symlink():
                add_file(file)
    for file in extra_prose or []:
        add_file(file)
    state = projected_state
    state_path = project_dir / "追踪" / "_tracking-state.json"
    try:
        if state is None:
            state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
        if not isinstance(state, dict):
            raise ValueError("tracking state must be an object")
        last = state.get("last_committed_chapter", 0)
        if type(last) is not int or last < 0:
            raise ValueError("last_committed_chapter invalid")
        imported = state.get("imported_through_chapter", 0)
        if type(imported) is not int or not 0 <= imported <= last:
            raise ValueError("imported_through_chapter invalid")
        excluded = set()
        gaps = state.get("chapter_gaps", [])
        if not isinstance(gaps, list):
            raise ValueError("chapter_gaps invalid")
        for gap in gaps:
            lo, hi, declared = (gap.get(key) for key in ("start_chapter", "end_chapter", "declared_at_chapter"))
            if (any(type(n) is not int for n in (lo, hi, declared)) or not 1 <= lo <= hi
                    or lo <= imported or declared != hi + 1 or declared > last
                    or not isinstance(gap.get("reason"), str) or not gap["reason"].strip()):
                raise ValueError("chapter gap requires valid range, adoption point and reason")
            numbers = set(range(lo, hi + 1))
            if excluded.intersection(numbers):
                raise ValueError("overlapping chapter gaps")
            excluded.update(numbers)
    except (OSError, ValueError, TypeError, AttributeError) as error:
        add_finding("Prose_Tracking_Invalid", str(error))
        last, excluded = 0, set()
    for chapter, files in by_chapter.items():
        if len(files) > 1:
            add_finding("Prose_Chapter_Duplicate", f"第{chapter}章有多个文件：{', '.join(str(f) for f in files)}")
        if chapter in excluded:
            add_finding("Prose_Gap_Conflict", f"第{chapter}章同时存在正文与缺章声明")
    expected, future = set(), set()
    if start_ch is not None and end_ch is not None and 1 <= start_ch <= end_ch:
        if through_chapter is not None and (type(through_chapter) is not int or through_chapter < 0):
            raise ValueError("through_chapter must be a nonnegative integer")
        # Already adopted chapters remain required even when an earlier cutoff is requested.
        cutoff = end_ch if through_chapter is None else min(end_ch, max(through_chapter, last))
        expected = set(range(start_ch, cutoff + 1)) - excluded
        future = set(range(max(start_ch, cutoff + 1), end_ch + 1)) - excluded
    else:
        add_finding("Prose_Coverage_Unknown", "卷纲范围不明，不能声明完整卷审计")
    missing = sorted(expected - by_chapter.keys())
    if missing:
        add_finding("Prose_Chapter_Missing", f"应有正文缺失：{missing}")
    selected = [(ch, files[0]) for ch, files in sorted(by_chapter.items())
                if through_chapter is None or ch <= max(through_chapter, last)]
    for chapter, file in selected:
        try:
            file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            add_finding("Prose_Unreadable", f"第{chapter}章无法读取：{error}")
    return selected, findings, {
        "audit_scope": "complete_volume" if through_chapter is None else "in_progress",
        "existing_chapters_in_range": len(selected),
        "expected_chapters": sorted(expected), "missing_chapters": missing,
        "future_chapters": sorted(future),
        "excluded_chapters": sorted(n for n in excluded if start_ch is not None and end_ch is not None and start_ch <= n <= end_ch),
        "scanned_files": [str(file) for _, file in selected],
    }


def audit_volume(
    project_dir: Path,
    vol_num: int,
    strict: bool = False,
    extra_prose: Optional[List[Path]] = None,
    projected_state: Optional[Dict[str, Any]] = None,
    through_chapter: Optional[int] = None,
) -> Dict[str, Any]:
    findings: List[Dict[str, str]] = []
    metrics: Dict[str, Any] = {
        "volume": vol_num,
        "outline_found": False,
        "chapter_range": [None, None],
        "existing_chapters_in_range": 0,
        "foreshadow_total": 0,
        "foreshadow_active": 0,
        "foreshadow_resolved": 0,
        "inflation_risk_signals": 0,
    }

    # 1. 查找卷纲文件
    volume_file = find_volume_outline(project_dir, vol_num)
    if not volume_file:
        findings.append({
            "severity": "blocking",
            "code": "Volume_Outline_Missing",
            "message": f"未找到第 {vol_num} 卷的卷纲文件（例如：大纲/卷纲_第{vol_num}卷.md）"
        })
        return {
            "status": "FAIL",
            "volume": vol_num,
            "findings": findings,
            "metrics": metrics,
        }

    metrics["outline_found"] = True
    metrics["outline_file"] = str(volume_file.relative_to(project_dir))

    try:
        content = volume_file.read_text(encoding="utf-8")
    except Exception as e:
        findings.append({
            "severity": "blocking",
            "code": "Volume_Outline_Unreadable",
            "message": f"无法读取卷纲文件 {volume_file}: {e}"
        })
        return {
            "status": "FAIL",
            "volume": vol_num,
            "findings": findings,
            "metrics": metrics,
        }

    # 2. 检查核心矛盾与卷契约
    has_conflict = bool(CONFLICT_DECLARATION.search(content))
    if not has_conflict:
        findings.append({
            "severity": "blocking",
            "code": "Volume_Contract_Missing_Conflict",
            "message": "卷纲缺少核心矛盾定义（必须包含 ## 核心矛盾 或 主矛盾/核心冲突）"
        })

    # 提取章节范围
    start_ch, end_ch = extract_chapter_range(content)
    metrics["chapter_range"] = [start_ch, end_ch]
    if start_ch is None or end_ch is None:
        findings.append({
            "severity": "advisory",
            "code": "Volume_Range_Unclear",
            "message": "卷纲中未明确标出规范的章节范围（建议在核心信息中注明，如：第 1–30 章）"
        })

    # The declared range is an audit obligation, not a list inferred from files.
    prose_files, inventory_findings, inventory_metrics = chapter_inventory(
        project_dir, start_ch, end_ch, extra_prose, projected_state, through_chapter,
    )
    findings.extend(inventory_findings)
    metrics.update(inventory_metrics)

    # 4. 检查下一卷承接动力
    has_next_drive = bool(re.search(
        r"下一卷|新周期|新任务|新地图|后续续写|下卷|未来危机|更高境界|更大规模", content
    ))
    if not has_next_drive:
        findings.append({
            "severity": "advisory",
            "code": "Next_Volume_Drive_Missing",
            "message": "卷末未发现对下一卷核心驱动力/新周期的铺设或承接预留，换卷易出现动力断层"
        })

    # 5. 检查伏笔债务健康度
    foreshadow_file = project_dir / "追踪" / "伏笔.md"
    if foreshadow_file.is_file():
        try:
            fs_text = foreshadow_file.read_text(encoding="utf-8")
            # Parse foreshadow lines
            lines = [l.strip() for l in fs_text.splitlines() if l.strip().startswith("|") and not l.strip().startswith("|-")]
            active_count = 0
            resolved_count = 0
            for l in lines[1:]:  # skip header
                cols = [c.strip() for c in l.split("|")[1:-1]]
                if len(cols) >= 3:
                    status_col = "".join(cols)
                    if "已回收" in status_col or "已解决" in status_col:
                        resolved_count += 1
                    elif "已埋" in status_col or "活跃" in status_col:
                        active_count += 1
            metrics["foreshadow_total"] = active_count + resolved_count
            metrics["foreshadow_active"] = active_count
            metrics["foreshadow_resolved"] = resolved_count

            # If this is an advanced volume and active foreshadows exceed 15 without clear resolution
            if active_count > 15:
                findings.append({
                    "severity": "advisory",
                    "code": "Foreshadow_Debt_Accumulation",
                    "message": f"当前活跃伏笔积压达 {active_count} 条，建议在卷末前段收束部分支线，防伏笔烂尾炸仓"
                })
        except Exception:
            pass

    # 6. 检查战力与资源通胀规范
    power_rule_file = project_dir / "设定" / "世界观" / "战力与资源约束.md"
    if not power_rule_file.is_file():
        findings.append({
            "severity": "advisory",
            "code": "Power_Constraint_Missing",
            "message": "未在 设定/世界观/ 下建立 战力与资源约束.md，长篇中后期可能面临战力与通胀崩塌风险"
        })

    # 扫描正文中是否有剧烈通胀词（如跨度百亿千亿、属性暴增万倍）
    inflation_patterns = [
        (re.compile(r"(?:资产|身价|财富|金币|灵石).{0,6}(?:破|达到|超过|拥?有)\s*([0-9万亿百千]+(?:万亿|千亿|百亿|亿))"), "极端数值通胀风险"),
        (re.compile(r"战力.{0,4}(?:翻了|提升|暴涨)\s*(?:十倍|百倍|千倍|万倍)"), "战力倍率膨胀过快"),
    ]
    inflation_hits = []
    for ch, pf in prose_files:
        try:
            p_text = pf.read_text(encoding="utf-8")
            for pat, desc in inflation_patterns:
                m = pat.search(p_text)
                if m:
                    inflation_hits.append(f"第{ch}章: 发现「{m.group(0)}」（{desc}）")
        except Exception:
            continue

    metrics["inflation_risk_signals"] = len(inflation_hits)
    if inflation_hits:
        findings.append({
            "severity": "advisory",
            "code": "Power_Economic_Inflation_Signal",
            "message": f"正文检测到 {len(inflation_hits)} 处疑似极端通胀信号：{'; '.join(inflation_hits[:3])}"
        })

    # 7. 设定兑现到期（setting-payoff.md 第 6 节）：判截至本卷到期的 payoff，
    #    追踪里没有 已兑现 记录的条目（包括以前卷到期但未清的债） → blocking；recurring 超窗只 advisory。
    findings.extend(setting_payoff_due_findings(project_dir, start_ch, end_ch, metrics, projected_state))

    # 判定整体状态
    blocking_count = sum(1 for f in findings if f["severity"] == "blocking")
    advisory_count = sum(1 for f in findings if f["severity"] == "advisory")

    if blocking_count > 0:
        status = "FAIL"
    elif strict and advisory_count > 0:
        status = "FAIL"
    else:
        status = "PASS"

    return {
        "status": status,
        "volume": vol_num,
        "findings": findings,
        "metrics": metrics,
    }


def generate_markdown_report(result: Dict[str, Any]) -> str:
    vol = result["volume"]
    status = result["status"]
    metrics = result["metrics"]
    findings = result["findings"]

    start_ch, end_ch = metrics.get("chapter_range", [None, None])
    range_str = f"第 {start_ch} 章 ～ 第 {end_ch} 章" if start_ch and end_ch else "未明确标记"

    md = [
        f"# 卷级生命周期健康度审计报告：第 {vol} 卷",
        "",
        f"- **审计结论**：`Gate: {status}`",
        f"- **卷纲文件**：`{metrics.get('outline_file', '未找到')}`",
        f"- **涵盖章节范围**：{range_str}",
        f"- **范围内已成稿章节数**：{metrics.get('existing_chapters_in_range', 0)} 章",
        f"- **伏笔债务状态**：活跃 {metrics.get('foreshadow_active', 0)} 条 / 已回收 {metrics.get('foreshadow_resolved', 0)} 条",
        f"- **通胀敏感度信号**：{metrics.get('inflation_risk_signals', 0)} 处",
        "",
        "## Findings 清单",
        "",
        "| 严重度 | 错误码 | 详细说明 |",
        "|---|---|---|",
    ]

    if not findings:
        md.append("| - | NONE | 全项检查通过，无阻断与提示项 |")
    else:
        for f in findings:
            md.append(f"| {f['severity'].upper()} | `{f['code']}` | {f['message']} |")

    md.extend([
        "",
        "## 下一步健康度建议",
        "",
        "1. **换卷动力衔接**：确认本卷收束时，主角的核心欲望与主线矛盾已顺利平移至下一卷；",
        "2. **伏笔出清**：每卷结束前优先清算本卷已承诺的小悬念与配角线索，勿带入新卷；",
        "3. **战力与资源锚定**：进入新卷前复核《战力与资源约束规范》，确保主角升级与消费有强闭环支撑。",
        ""
    ])

    return "\n".join(md)


def main():
    parser = argparse.ArgumentParser(description="长篇小说卷级生命周期健康度审计工具")
    parser.add_argument("--project", "-p", default=".", help="小说项目根目录")
    parser.add_argument("--volume", "-v", help="要审计的卷号（数字或第一卷格式）")
    parser.add_argument(
        "--ends-at", type=int,
        help="反查模式：输出章节范围正好终止于该章的卷号（JSON），不执行审计",
    )
    parser.add_argument(
        "--candidate", action="append", default=[], metavar="PATH",
        help="把尚未并入 正文/ 的候选章一并纳入本卷扫描（可重复）",
    )
    parser.add_argument("--write", "-w", action="store_true", help="将审计报告落盘至 追踪/稳定性审计/")
    parser.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    parser.add_argument("--through-chapter", type=int, help="卷中检查截止章；省略即要求完整卷正文")
    parser.add_argument("--strict", action="store_true", help="严格模式（advisory 亦导致 FAIL）")

    args = parser.parse_args()
    if args.through_chapter is not None and args.through_chapter < 0:
        parser.error("--through-chapter must be nonnegative")

    project_dir = Path(args.project).resolve()
    if not project_dir.is_dir():
        sys.stderr.write(f"错误：项目目录不存在: {project_dir}\n")
        sys.exit(2)

    if args.ends_at is not None:
        if args.volume is not None:
            sys.stderr.write("错误：--ends-at 与 --volume 不能同时使用\n")
            sys.exit(2)
        if args.ends_at < 1:
            sys.stderr.write(f"错误：无效的章号: {args.ends_at}\n")
            sys.exit(2)
        print(json.dumps(
            {"chapter": args.ends_at, "volumes": find_volumes_ending_at(project_dir, args.ends_at)},
            ensure_ascii=False,
        ))
        sys.exit(0)

    if args.volume is None:
        sys.stderr.write("错误：必须提供 --volume 或 --ends-at\n")
        sys.exit(2)

    vol_num = parse_volume_number(args.volume)
    if vol_num is None or vol_num < 1:
        sys.stderr.write(f"错误：无效的卷号: {args.volume}\n")
        sys.exit(2)

    extra_prose: List[Path] = []
    for raw in args.candidate:
        path = Path(raw)
        if not path.is_file():
            sys.stderr.write(f"错误：候选章文件不存在: {raw}\n")
            sys.exit(2)
        extra_prose.append(path)

    result = audit_volume(project_dir, vol_num, strict=args.strict, extra_prose=extra_prose, through_chapter=args.through_chapter)

    if args.write:
        report_dir = project_dir / "追踪" / "稳定性审计"
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"卷_{vol_num}_生命周期审计.md"
        report_content = generate_markdown_report(result)
        report_file.write_text(report_content, encoding="utf-8")
        result["report_written"] = str(report_file)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(generate_markdown_report(result))

    sys.exit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
