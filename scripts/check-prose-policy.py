#!/usr/bin/env python3
"""Inventory prose rules and reject known global clarity/style conflicts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SEARCH_ROOTS = (
    ROOT / "skills",
)
CANDIDATE = re.compile(r"每章|每一章|每节|章尾|悬念|钩子|句长|短句|长句|省略|留白|极简|叙事混乱|因果|清零|身体反应|情绪")
FORBIDDEN = {
    "global-unresolved-ending": re.compile(r"每章结尾必须有至少一个未解|每章结尾让人物面临未解决的危险"),
    "global-two-suspense-lines": re.compile(r"任何时刻都有至少两条悬念线|每章至少两条悬念线"),
    "global-two-expectation-lines": re.compile(r"任何时刻保持至少两条期待线|至少两条期待线同时运行|同一时刻保持2-3条矛盾线"),
    "global-two-long-one-short": re.compile(r"确保读者脑中有三个好奇.{0,8}两长一短|两长一短不断"),
    "global-deceptive-mainline": re.compile(r"大结构是.{0,4}欺骗式的主线|欺骗式主线.{0,8}吊着读者"),
    "global-infinite-expectation": re.compile(r"一个勾着一个无限循环|每次回收至少保留或新建一条更长的期待线"),
    "global-suspense-minimum": re.compile(r"过渡章至少要达到1级|正文章至少2级|关键章至少3级"),
    "global-overfire": re.compile(r"宁(?:可)?过火.{0,8}(?:不|也不).{0,4}平淡|情绪宁烈不温|禁止温吞保守"),
    "global-comma-long-default": re.compile(r"叙述.{0,12}默认.{0,6}逗号长句|改写后叙述仍以逗号长句为主"),
    "global-sentence-band": re.compile(r"逗号之间\s*8-12\s*字|整句\s*20-30\s*字"),
    "global-punctuation-zero": re.compile(r"正文无破折号|正文.{0,12}(?:不使用|不出现|不得出现).{0,12}(?:……|破折号)|破折号清零|正文无禁用标点"),
    "global-emotion-show-only": re.compile(r"关键情绪节点无直接写.{0,20}用身体反应替代|每个情绪词后面都接.{0,8}反应|情绪不用.{0,12}用身体反应"),
    "global-psychology-count": re.compile(r"心理活动不超过2段"),
    "global-object-count": re.compile(r"每个物件出现\s*3\s*次|贯穿道具第\s*3\s*次"),
    "global-emotion-per-section": re.compile(r"每节至少拨一次|每节必须.{0,8}情绪"),
    "global-emotion-shape": re.compile(r"情绪不能一直升.{0,8}回落再升"),
    "global-opening-density": re.compile(r"前\s*100\s*字事件密度\s*>?=\s*3"),
    "global-body-part-count": re.compile(r"身体部位同一词全文\s*[≤<]=?\s*5\s*次|同一身体部位.{0,12}超过上限"),
    "global-body-part-question": re.compile(r"身体部位同一词是否超\s*\d+\s*次"),
    "global-punctuation-clean-question": re.compile(r"破折号是否已清理|省略号是否已清理"),
    "global-new-concept-count": re.compile(r"一章不超\s*\d+\s*个新概念|每章.{0,12}新概念.{0,8}(?:不超|≤|<=)"),
    "global-emotion-action-only": re.compile(r"情绪通过动作落地|情绪只能通过动作"),
    "global-filler-count": re.compile(r"同一个情绪写了\s*\d+\s*段以上|场景描写超过\s*\d+\s*字|连续\s*\d+\s*章以上没有冲突"),
    "global-opening-hook-count": re.compile(r"第一章前\s*\d+\s*字有钩子|前三章有至少\s*\d+\s*个爽点"),
    "global-rhythm-quota": re.compile(r"爽点间隔是否超过\s*\d+\s*字|低压\s*\+?\s*过场.{0,16}不超.{0,8}\d+\s*%"),
    "global-every-sentence-moves": re.compile(r"每个句子必须推动"),
    "global-section-payload-quota": re.compile(r"每(?:章|节).{0,10}(?:一个|至少一个).{0,10}(?:炸点|爆点|新信息|心动|背叛|笑点|反转)"),
    "global-hook-schedule": re.compile(r"(?:每\s*\d+(?:-\d+)?\s*(?:章|节)|每(?:章|节)).{0,10}(?:钩子|留钩)"),
    "global-dialogue-percentage": re.compile(r"对话(?:占比|密度).{0,12}\d+\s*[-–—~～到至]\s*\d+\s*%"),
    "global-paragraph-sentence-quota": re.compile(r"每段不超过\s*\d+\s*句"),
    "global-emotion-score": re.compile(r"(?:开头|结尾)?情绪强度.{0,8}(?:≥|>=)\s*\d"),
    "detector-clear-all": re.compile(r"须清零后再继续|复扫到净|命中即改.{0,12}改完再交付|AI\s*套话清零"),
    "direct-body-before-review": re.compile(r"每章写完直接写入\s*`?正文/|备份原文.{0,30}正文/.*_原稿_"),
    "optional-per-chapter-review": re.compile(r"本章写作完成。如需一致性检查|批量写作模式跳过此步骤，全部写完后再统一审查"),
}

# check-ai-patterns.js 内联 blocking 的唯一合法形态：免语境词表族
# （banned-words.md 加载的封闭词表类 + 规则加载失败本身）。风格类判定需要
# 作者语境裁决，只能 advisory——「是否需要语境」两分是 5007cb8 恢复的作者
# 裁意，取代 2026-08-31 的「检测器一律 advisory」方针。
DETECTOR_BLOCKING_LINE = re.compile(r"severity\s*:\s*['\"]blocking['\"]")
DETECTOR_TYPE_LINE = re.compile(r"type\s*:\s*['\"]([a-z0-9-]+)['\"]")
ALLOWED_BLOCKING_TYPES = {"rule-load-error"}
BLOCKING_TYPE_WINDOW = 6


def detector_blocking_allowed(last_type: str | None, distance: int) -> bool:
    return (
        last_type is not None
        and 0 < distance <= BLOCKING_TYPE_WINDOW
        and (last_type in ALLOWED_BLOCKING_TYPES or last_type.startswith("banned-word-"))
    )


def classify(path: Path, line: str) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative.endswith("prose-policy.md"):
        return "authority-or-explicit-negation"
    if relative.endswith("UPGRADING.md"):
        return "historical-record"
    if any(marker in line for marker in ("不强制", "不是全局", "不等于必须", "不要求", "不限定", "不设逐章", "不能用", "不得用", "不把每", "不为每", "不必", "不强求", "反例", "错误示例", "禁忌", "故弄玄虚")):
        return "explicitly-non-global"
    if relative.endswith("real-market-data.md"):
        return "observed-market-data"
    if "/genre-prose-cards/" in relative or "short-" in relative:
        return "genre-or-short-scoped"
    return "general-guidance"


def inventory() -> dict[str, object]:
    rows = []
    violations = []
    files_scanned = 0
    for root in SEARCH_ROOTS:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in {".md", ".toml", ".js", ".py", ".sh"}:
                continue
            files_scanned += 1
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeError:
                continue
            last_type = None
            last_type_line = 0
            for number, line in enumerate(lines, 1):
                if CANDIDATE.search(line):
                    rows.append({
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": number,
                        "classification": classify(path, line),
                        "text": line.strip(),
                    })
                if path.name == "prose-policy.md":
                    continue
                explicitly_non_global = classify(path, line) in {"explicitly-non-global", "observed-market-data", "historical-record"}
                for rule_id, pattern in FORBIDDEN.items():
                    if explicitly_non_global:
                        continue
                    if pattern.search(line):
                        violations.append({
                            "rule_id": rule_id,
                            "file": path.relative_to(ROOT).as_posix(),
                            "line": number,
                            "text": line.strip(),
                        })
                if path.name == "check-ai-patterns.js":
                    type_match = DETECTOR_TYPE_LINE.search(line)
                    if type_match:
                        last_type = type_match.group(1)
                        last_type_line = number
                    if DETECTOR_BLOCKING_LINE.search(line) and not detector_blocking_allowed(
                        last_type, number - last_type_line
                    ):
                        violations.append({
                            "rule_id": "detector-style-blocking",
                            "file": path.relative_to(ROOT).as_posix(),
                            "line": number,
                            "text": f"blocking severity needs a context-free wordlist type (banned-word-*/{sorted(ALLOWED_BLOCKING_TYPES)[0]}); nearest type: {last_type or 'none'} :: {line.strip()}",
                        })
    authority = ROOT / "skills/story-write/references/prose-policy.md"
    authority_text = authority.read_text(encoding="utf-8") if authority.is_file() else ""
    priority_ok = all(marker in authority_text for marker in (
        "当前场面可理解", "已接受事实与信息边界", "本书自定义文风与题材卡", "局部自然度与去 AI 味建议", "通用经验值",
    ))
    if not priority_ok:
        violations.append({"rule_id": "missing-priority-authority", "file": str(authority.relative_to(ROOT)), "line": 1, "text": "five-level prose priority is incomplete"})
    return {
        "schema": "story-prose-policy-inventory/v1",
        "ok": not violations,
        "files_scanned": files_scanned,
        "candidate_rules": len(rows),
        "priority_authority": priority_ok,
        "violations": violations,
        "inventory": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = inventory()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif result["ok"]:
        print(f"prose-policy: PASS ({result['candidate_rules']} candidate rules inventoried across {result['files_scanned']} files)")
    else:
        for row in result["violations"]:
            print(f"{row['rule_id']}: {row['file']}:{row['line']}: {row['text']}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
