#!/usr/bin/env python3
"""候选系统：把待批准正文并入正稿，或归档被拒/被替换的候选。

设计不变式（见任务 08-21-candidate-system-design/design.md）：
- 候选正文写在书根 ``候选/``（**不在 ``正文/`` 之下**），与正稿 ``正文/`` 物理隔离。
  放在书根而非 ``正文/候选/`` 是刻意的：写后 hook 的 longChapterInfo 会把任一
  ``正文`` 祖先下的 ``第N章*.md`` 认成正式章节、listChapterFiles 又递归遍历 ``正文/``，
  若候选在 ``正文/`` 下会被卷进章节序号/追踪欠账门/gap 检测，与「候选未提交追踪」冲突。
  放书根后 longChapterInfo 找不到 ``正文`` 祖先，hook 直接跳过候选文件。
- 候选章自带待回放的追踪事务 JSON（``第XXX章_追踪事务.json``）；``_tracking-state.json``
  只在采用（promote）时推进，永远只反映已批准正文。
- promote = 移动正文 + 回放追踪事务，采用「先移动、失败回滚」以保证可安全重跑。
- reject/rewrite 只归档候选（移入 ``候选/_历史/``），正稿与追踪不动。

本工具不生成正文、不手改派生视图；追踪推进一律委托给同目录的 ``tracking_commit.py``。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


BODY_DIR = "正文"
CANDIDATE_DIR = "候选"
HISTORY_DIR = "_历史"
TRACKING_STATE = "追踪/_tracking-state.json"
TRANSACTION_SUFFIX = "_追踪事务.json"

# 第001章_章名 / 第1章 —— 允许前导零，章号取阿拉伯数字。
CHAPTER_PREFIX = re.compile(r"^第0*(\d+)章")
TRACKING_TOOL = Path(__file__).resolve().parent / "tracking_commit.py"

# promote 质量门：采用前对候选正文跑现成扫描脚本，blocking 命中拒绝并入正稿。
# 确定性检查通过不代表正文自然或没有 AI 痕迹；候选仍需作者审读。
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"
SCAN_SCRIPTS = ("check-ai-patterns.js", "check-degeneration.js")
# 与写后 hook 一致的显式豁免：候选标题行下 6 行内含该标记则跳过质量门。
EXEMPTION = re.compile(r"去味(：|:)跳过")


def emit(text: str, *, error: bool = False) -> None:
    """直写 UTF-8 字节：Windows 文本 stdout 是 cp1252，含中文会 UnicodeEncodeError。"""
    stream = sys.stderr if error else sys.stdout
    stream.flush()
    stream.buffer.write((text + "\n").encode("utf-8"))
    stream.buffer.flush()


class CandidateError(RuntimeError):
    """预期内的候选操作错误。"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def body_root(project: Path) -> Path:
    return project.resolve() / BODY_DIR


def candidate_root(project: Path) -> Path:
    # 书根下的 候选/，刻意不放在 正文/ 之下（见模块 docstring）。
    return project.resolve() / CANDIDATE_DIR


def history_root(project: Path) -> Path:
    return candidate_root(project) / HISTORY_DIR


def chapter_of(name: str) -> int | None:
    match = CHAPTER_PREFIX.match(name)
    return int(match.group(1)) if match else None


def is_transaction(name: str) -> bool:
    return name.endswith(TRANSACTION_SUFFIX)


def is_prose_candidate(name: str) -> bool:
    return name.endswith(".md") and not is_transaction(name)


def list_candidates(project: Path) -> list[dict[str, Any]]:
    """列出候选目录里待审的正文（不含 _历史），带事务与正稿冲突标记。"""
    root = candidate_root(project)
    if not root.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(root.iterdir()):
        if path.name == HISTORY_DIR or path.is_dir():
            continue
        if not is_prose_candidate(path.name):
            continue
        chapter = chapter_of(path.name)
        entries.append(
            {
                "chapter": chapter,
                "prose": path.name,
                "has_transaction": find_transaction(project, chapter) is not None if chapter else False,
                "final_exists": find_final(project, chapter) is not None if chapter else False,
            }
        )
    return entries


def _match_by_chapter(root: Path, chapter: int, predicate) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and predicate(path.name) and chapter_of(path.name) == chapter
    )


def find_prose_candidate(project: Path, chapter: int) -> Path:
    matches = _match_by_chapter(candidate_root(project), chapter, is_prose_candidate)
    require(matches, f"候选目录没有第{chapter}章正文（{candidate_root(project)}）")
    require(len(matches) == 1, f"第{chapter}章候选正文有多个匹配，先清理：{[p.name for p in matches]}")
    return matches[0]


def find_transaction(project: Path, chapter: int) -> Path | None:
    matches = _match_by_chapter(candidate_root(project), chapter, is_transaction)
    return matches[0] if matches else None


def find_final(project: Path, chapter: int) -> Path | None:
    matches = _match_by_chapter(body_root(project), chapter, is_prose_candidate)
    return matches[0] if matches else None


def read_state_revision(project: Path) -> int | None:
    path = project.resolve() / TRACKING_STATE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:  # pragma: no cover - 环境异常
        raise CandidateError(f"无法读取 {TRACKING_STATE}: {exc}") from exc
    revision = data.get("state_revision")
    return revision if isinstance(revision, int) else None


def replay_tracking(project: Path, transaction_path: Path) -> None:
    """回放候选自带的追踪事务；expected_state_revision 刷新为当前值以支持延迟采用。

    章号顺序由 tracking_commit.py 自身校验，这里刷新 revision 只对齐「现在把这章应用到
    当前状态」的语义；乱序采用仍会被底层工具拒绝。
    """
    try:
        document = json.loads(transaction_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise CandidateError(f"追踪事务 JSON 不可读：{transaction_path}: {exc}") from exc
    require(isinstance(document, dict), f"追踪事务 JSON 必须是对象：{transaction_path}")

    revision = read_state_revision(project)
    if revision is not None:
        document["expected_state_revision"] = revision

    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False, dir=str(transaction_path.parent)
    ) as handle:
        json.dump(document, handle, ensure_ascii=False)
        temp_input = Path(handle.name)
    try:
        result = subprocess.run(
            [sys.executable, str(TRACKING_TOOL), "commit", "--project", str(project), "--input", str(temp_input)],
            capture_output=True,
            text=True,
        )
    finally:
        temp_input.unlink(missing_ok=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise CandidateError(f"追踪事务回放失败（追踪未推进，可修复后重跑同一 promote）：\n{detail}")


def scan_gate(prose: Path) -> str | None:
    """返回确定性检查失败信息；只有显式豁免或全部检查通过时返回 None。"""
    try:
        head = "\n".join(prose.read_text(encoding="utf-8").split("\n", 6)[:6])
    except OSError as error:
        return f"无法读取候选正文：{error}"
    if EXEMPTION.search(head):
        return None
    node = shutil.which("node")
    if node is None:
        return "未找到 node，无法执行采用前确定性检查；明确跳过时使用 --no-scan"
    blocked: list[str] = []
    for name in SCAN_SCRIPTS:
        script = SHARED_SCRIPTS / name
        if not script.exists():
            blocked.append(f"[{name}] 扫描器不存在：{script}")
            continue
        try:
            result = subprocess.run(
                [node, str(script), "--check", "--fail-on=blocking", str(prose)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
        except OSError as error:
            blocked.append(f"[{name}] 无法执行：{error}")
            continue
        if result.returncode != 0:
            blocked.append(f"[{name}]\n{(result.stdout or result.stderr or '').strip()}")
    return "\n\n".join(blocked) if blocked else None


def promote_chapter(project: Path, chapter: int, *, skip_scan: bool = False) -> dict[str, Any]:
    prose = find_prose_candidate(project, chapter)
    if not skip_scan:
        findings = scan_gate(prose)
        require(
            findings is None,
            f"第{chapter}章候选未通过采用前确定性检查，拒绝并入正稿。"
            f"先修正文或检查环境；明确跳过时，在标题后加 <!-- 去味:跳过 --> 或使用 --no-scan：\n{findings}",
        )
    transaction = find_transaction(project, chapter)
    require(
        transaction is not None,
        f"第{chapter}章缺少追踪事务 JSON（{TRANSACTION_SUFFIX}）；候选须自带事务，"
        "不能凭空推进追踪。请让 narrative-writer 在候选模式下补写事务后再采用。",
    )
    require(
        find_final(project, chapter) is None,
        f"正稿已存在第{chapter}章，promote 不覆盖正稿。若要替换，先处理既有正稿或走大修流程。",
    )

    target = body_root(project) / prose.name
    body_root(project).mkdir(parents=True, exist_ok=True)

    # 先移动正文（同盘 rename 原子），再回放追踪；回放失败则移回候选，保证可重跑。
    prose.replace(target)
    try:
        replay_tracking(project, transaction)
    except CandidateError:
        target.replace(prose)
        raise

    archive_transaction(project, transaction)
    return {"action": "promote", "chapter": chapter, "prose": target.name, "state_revision": read_state_revision(project)}


def archive_transaction(project: Path, transaction: Path) -> None:
    history = history_root(project)
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    transaction.replace(history / f"{transaction.stem}_{stamp}{transaction.suffix}")


def reject_chapter(project: Path, chapter: int, *, rewrite: bool) -> dict[str, Any]:
    prose = find_prose_candidate(project, chapter)
    transaction = find_transaction(project, chapter)
    history = history_root(project)
    history.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    archived_prose = history / f"{prose.stem}_{stamp}{prose.suffix}"
    prose.replace(archived_prose)
    archived = [archived_prose.name]
    if transaction is not None:
        target = history / f"{transaction.stem}_{stamp}{transaction.suffix}"
        transaction.replace(target)
        archived.append(target.name)

    return {
        "action": "rewrite" if rewrite else "reject",
        "chapter": chapter,
        "archived": archived,
    }


def promote_all(project: Path, *, skip_scan: bool = False) -> list[dict[str, Any]]:
    chapters = sorted(
        {entry["chapter"] for entry in list_candidates(project) if entry["chapter"] is not None}
    )
    require(chapters, "候选目录没有可采用的正文")
    return [promote_chapter(project, chapter, skip_scan=skip_scan) for chapter in chapters]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="候选正文的采用 / 归档 / 列表")
    sub = parser.add_subparsers(dest="command", required=True)

    promote = sub.add_parser("promote", help="采用候选正文并入正稿、回放追踪事务")
    promote.add_argument("--project", type=Path, required=True, help="书项目根目录（含 正文/、追踪/）")
    group = promote.add_mutually_exclusive_group(required=True)
    group.add_argument("--chapter", type=int, help="采用指定章号")
    group.add_argument("--all", action="store_true", help="按章号升序采用全部候选")
    promote.add_argument("--no-scan", action="store_true", help="显式跳过采用前确定性质量检查")

    reject = sub.add_parser("reject", help="归档被拒/被替换的候选（正稿与追踪不动）")
    reject.add_argument("--project", type=Path, required=True)
    reject.add_argument("--chapter", type=int, required=True)
    reject.add_argument("--rewrite", action="store_true", help="标记为重写意图（归档动作相同）")

    listing = sub.add_parser("list", help="列出候选目录待审项")
    listing.add_argument("--project", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "promote":
            result: Any = (
                promote_all(args.project, skip_scan=args.no_scan)
                if args.all
                else promote_chapter(args.project, args.chapter, skip_scan=args.no_scan)
            )
        elif args.command == "reject":
            result = reject_chapter(args.project, args.chapter, rewrite=args.rewrite)
        else:
            result = list_candidates(args.project)
    except CandidateError as exc:
        emit(f"ERROR: {exc}", error=True)
        return 2
    emit(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
