#!/usr/bin/env python3
"""Adopt, recover, reject, or list author-review candidates.

Adoption is a recoverable project transaction. Every input is bound by digest
and checked before the first write. The persisted phases are:
``prepared -> prose_moved -> tracking_committed -> done``.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from project_lock import ProjectLockError, project_lock, unfinished_adoptions


BODY_DIR = "正文"
CANDIDATE_DIR = "候选"
HISTORY_DIR = "_历史"
TRACKING_STATE = "追踪/_tracking-state.json"
TRANSACTION_SUFFIX = "_追踪事务.json"
JOURNAL_PREFIX = "采用事务-"
QUALITY_PROFILE = "fanqie-long-v1"
PHASES = ("prepared", "prose_moved", "tracking_committed", "done")
CHAPTER_PREFIX = re.compile(r"^第0*(\d+)章")
EXEMPTION = re.compile(r"去味(：|:)跳过")
TRACKING_TOOL = Path(__file__).resolve().parent / "tracking_commit.py"
SKELETON_TOOL = Path(__file__).resolve().parent / "check-chapter-skeleton.js"
OUTLINE_COPY_TOOL = Path(__file__).resolve().parent / "check-outline-copy.js"
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"
TITLE_TOOL = SHARED_SCRIPTS / "check-chapter-titles.js"
SCAN_SCRIPTS = ("check-ai-patterns.js", "check-degeneration.js")


def _load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载运行时：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tracking = _load_module("candidate_tracking", TRACKING_TOOL)
wordcount = _load_module("candidate_wordcount", SHARED_SCRIPTS / "wordcount_core.py")


class CandidateError(RuntimeError):
    """Expected candidate operation failure."""


def emit(text: str, *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    stream.flush()
    stream.buffer.write((text + "\n").encode("utf-8"))
    stream.buffer.flush()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CandidateError(message)


def body_root(project: Path) -> Path:
    return project.resolve() / BODY_DIR


def candidate_root(project: Path) -> Path:
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


def _match_by_chapter(root: Path, chapter: int, predicate) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path for path in root.iterdir()
        if path.is_file() and predicate(path.name) and chapter_of(path.name) == chapter
    )


def find_prose_candidate(project: Path, chapter: int) -> Path:
    matches = _match_by_chapter(candidate_root(project), chapter, is_prose_candidate)
    require(matches, f"候选目录没有第{chapter}章正文（{candidate_root(project)}）")
    require(len(matches) == 1, f"第{chapter}章候选正文有多个匹配：{[path.name for path in matches]}")
    return matches[0]


def find_transaction(project: Path, chapter: int) -> Path | None:
    matches = _match_by_chapter(candidate_root(project), chapter, is_transaction)
    require(len(matches) <= 1, f"第{chapter}章追踪事务有多个匹配：{[path.name for path in matches]}")
    return matches[0] if matches else None


def find_final(project: Path, chapter: int) -> Path | None:
    matches = _match_by_chapter(body_root(project), chapter, is_prose_candidate)
    require(len(matches) <= 1, f"正文中第{chapter}章有多个匹配：{[path.name for path in matches]}")
    return matches[0] if matches else None


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise CandidateError(f"无法读取文件摘要：{path}: {exc}") from exc


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CandidateError(f"{label}不可读：{path}: {exc}") from exc
    require(isinstance(value, dict), f"{label}必须是 JSON 对象：{path}")
    return value


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    finally:
        try:
            os.unlink(name)
        except FileNotFoundError:
            pass


def project_relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError as exc:
        raise CandidateError(f"路径不在书项目内：{path}") from exc


def bound_path(project: Path, raw: object, label: str) -> Path:
    require(isinstance(raw, str) and raw.strip(), f"candidate_binding.{label}.path 缺失")
    root = project.resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise CandidateError(f"candidate_binding.{label}.path 越出书项目：{raw}") from exc
    require(candidate.is_file(), f"candidate_binding.{label}.path 不存在：{raw}")
    return candidate


def read_state(project: Path) -> dict[str, Any]:
    return read_json(project.resolve() / TRACKING_STATE, TRACKING_STATE)


def run_node(args: list[str], label: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    require(node is not None, f"未找到 node，无法执行{label}")
    try:
        return subprocess.run(
            [node, *args], capture_output=True, text=True, encoding="utf-8", check=False,
        )
    except OSError as exc:
        raise CandidateError(f"无法执行{label}：{exc}") from exc


def scan_gate(prose: Path) -> str | None:
    blocked: list[str] = []
    for name in SCAN_SCRIPTS:
        script = SHARED_SCRIPTS / name
        if not script.is_file():
            blocked.append(f"[{name}] 扫描器不存在：{script}")
            continue
        result = run_node([str(script), "--check", "--fail-on=blocking", str(prose)], name)
        if result.returncode != 0:
            blocked.append(f"[{name}]\n{(result.stdout or result.stderr).strip()}")
    return "\n\n".join(blocked) if blocked else None


def skeleton_coverage_ids(skeleton: Path) -> list[str]:
    text = skeleton.read_text(encoding="utf-8-sig")
    return [match.upper() for match in re.findall(r"^-\s+\[[xX]\]\s+(O\d+)\b", text, re.MULTILINE)]


def validate_titles(project: Path, prose: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="candidate-title-") as temporary:
        root = Path(temporary)
        for final in body_root(project).glob("第*章*.md") if body_root(project).is_dir() else []:
            shutil.copy2(final, root / final.name)
        shutil.copy2(prose, root / prose.name)
        result = run_node([str(TITLE_TOOL), "--dir", str(root)], "章节标题检查")
    require(result.returncode == 0, f"章节标题未通过：\n{(result.stdout or result.stderr).strip()}")


def validate_binding(
    project: Path, chapter: int, prose: Path, transaction: Path, document: dict[str, Any], *, skip_scan: bool,
) -> dict[str, Any]:
    state = read_state(project)
    expected = document.get("expected_state_revision")
    require(isinstance(expected, int), "追踪事务必须保存候选创建时的 expected_state_revision")
    require(expected == state.get("state_revision"), "候选已过期：tracking state changed since this candidate was prepared")
    require(document.get("chapter") == chapter, "追踪事务章号与候选章号不一致")

    binding = document.get("candidate_binding")
    require(isinstance(binding, dict) and binding.get("schema_version") == 1, "追踪事务缺少 candidate_binding v1")
    require(binding.get("quality_profile") == QUALITY_PROFILE, f"candidate_binding.quality_profile 必须是 {QUALITY_PROFILE}")
    prose_binding = binding.get("prose")
    outline_binding = binding.get("outline")
    skeleton_binding = binding.get("skeleton")
    require(all(isinstance(item, dict) for item in (prose_binding, outline_binding, skeleton_binding)), "candidate_binding 文件绑定不完整")
    bound_prose = bound_path(project, prose_binding.get("path"), "prose")
    outline = bound_path(project, outline_binding.get("path"), "outline")
    skeleton = bound_path(project, skeleton_binding.get("path"), "skeleton")
    require(bound_prose == prose.resolve(), "candidate_binding.prose.path 与候选文件不一致")

    hashes = {
        "candidate": sha256_file(prose),
        "transaction": sha256_file(transaction),
        "outline": sha256_file(outline),
        "skeleton": sha256_file(skeleton),
        "state_before": sha256_file(project.resolve() / TRACKING_STATE),
    }
    for key, value in (("prose", hashes["candidate"]), ("outline", hashes["outline"]), ("skeleton", hashes["skeleton"])):
        require(binding[key].get("sha256") == value, f"candidate_binding.{key}.sha256 已过期")

    skeleton_result = run_node([str(SKELETON_TOOL), str(skeleton)], "骨架检查")
    require(skeleton_result.returncode == 0, f"骨架未通过：\n{(skeleton_result.stdout or skeleton_result.stderr).strip()}")
    validate_titles(project, prose)
    length = wordcount.fanqie_length(prose.read_text(encoding="utf-8-sig"))
    require(length["status"] == "pass", f"番茄长篇字数必须为 2200–2800，有效字数为 {length['actual']}")

    coverage = binding.get("coverage")
    require(isinstance(coverage, list), "candidate_binding.coverage 必须是数组")
    expected_ids = skeleton_coverage_ids(skeleton)
    actual_ids: list[str] = []
    prose_text = prose.read_text(encoding="utf-8-sig")
    for item in coverage:
        require(isinstance(item, dict), "candidate_binding.coverage 每项必须是对象")
        item_id = str(item.get("id", "")).upper()
        evidence = item.get("evidence")
        require(re.fullmatch(r"O\d+", item_id) is not None, "candidate_binding.coverage.id 非法")
        require(isinstance(evidence, str) and evidence.strip(), f"{item_id} 缺少正文证据")
        require(evidence in prose_text, f"{item_id} 的证据未出现在候选正文")
        actual_ids.append(item_id)
    require(actual_ids == expected_ids and len(set(actual_ids)) == len(actual_ids), "candidate_binding.coverage 必须完整匹配骨架 O-ID")

    outline_result = run_node([str(OUTLINE_COPY_TOOL), "--outline", str(outline), str(prose)], "细纲照搬检查")
    require(outline_result.returncode == 0, f"候选存在未处理的细纲照搬：\n{(outline_result.stdout or outline_result.stderr).strip()}")
    head = "\n".join(prose_text.split("\n", 6)[:6])
    if not skip_scan and not EXEMPTION.search(head):
        findings = scan_gate(prose)
        require(findings is None, f"候选未通过采用前确定性检查：\n{findings}")

    tracking_payload = dict(document)
    tracking_payload.pop("candidate_binding", None)
    try:
        normalized = tracking.normalize_transaction(project, state, tracking_payload)
        next_state = tracking.merge_transaction(state, normalized)
    except Exception as exc:
        if exc.__class__.__name__ == "TrackingError":
            raise CandidateError(f"追踪事务预演失败：{exc}") from exc
        raise
    hashes["tracking_payload"] = sha256_bytes(canonical_json(tracking_payload))
    hashes["state_after"] = sha256_bytes(tracking.json_payload(next_state).encode("utf-8"))
    hashes["candidate_after_checks"] = sha256_file(prose)
    hashes["transaction_after_checks"] = sha256_file(transaction)
    hashes["outline_after_checks"] = sha256_file(outline)
    hashes["skeleton_after_checks"] = sha256_file(skeleton)
    require(hashes["candidate_after_checks"] == hashes["candidate"], "候选正文在检查期间发生变化")
    require(hashes["transaction_after_checks"] == hashes["transaction"], "追踪事务在检查期间发生变化")
    require(hashes["outline_after_checks"] == hashes["outline"], "细纲在检查期间发生变化")
    require(hashes["skeleton_after_checks"] == hashes["skeleton"], "骨架在检查期间发生变化")
    return {
        "expected_revision": expected,
        "expected_next_revision": next_state["state_revision"],
        "tracking_payload": tracking_payload,
        "hashes": hashes,
        "length": length,
        "outline": project_relative(project, outline),
        "skeleton": project_relative(project, skeleton),
    }


def journal_path(project: Path, operation_id: str) -> Path:
    return history_root(project) / f"{JOURNAL_PREFIX}{operation_id}.json"


def update_phase(path: Path, journal: dict[str, Any], phase: str) -> None:
    require(phase in PHASES, f"非法采用阶段：{phase}")
    current = journal.get("phase")
    require(current in PHASES, f"采用日志阶段非法：{current}")
    require(PHASES.index(phase) >= PHASES.index(current), "采用阶段不能倒退")
    journal["phase"] = phase
    journal["updated_at"] = datetime.now().astimezone().isoformat()
    atomic_json(path, journal)
    if os.environ.get("STORY_CANDIDATE_FAIL_AFTER") == phase:
        os._exit(97)


def create_journal(project: Path, chapter: int, prose: Path, transaction: Path, preflight: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    digest = sha256_bytes(canonical_json({
        "chapter": chapter,
        "candidate": preflight["hashes"]["candidate"],
        "transaction": preflight["hashes"]["transaction"],
        "expected_revision": preflight["expected_revision"],
    }))[:20]
    operation_id = f"c{chapter}-{digest}"
    path = journal_path(project, operation_id)
    archive = history_root(project) / f"{operation_id}-{transaction.name}"
    journal = {
        "schema_version": 1,
        "operation_id": operation_id,
        "phase": "prepared",
        "chapter": chapter,
        "expected_state_revision": preflight["expected_revision"],
        "expected_next_revision": preflight["expected_next_revision"],
        "paths": {
            "candidate": project_relative(project, prose),
            "final": project_relative(project, body_root(project) / prose.name),
            "transaction": project_relative(project, transaction),
            "archive_transaction": project_relative(project, archive),
            "outline": preflight["outline"],
            "skeleton": preflight["skeleton"],
        },
        "digests": preflight["hashes"],
        "tracking_payload": preflight["tracking_payload"],
        "length": preflight["length"],
        "created_at": datetime.now().astimezone().isoformat(),
        "updated_at": datetime.now().astimezone().isoformat(),
    }
    if path.exists():
        existing = read_json(path, "采用日志")
        require(existing.get("operation_id") == operation_id, "采用日志 operation_id 冲突")
        return path, existing
    atomic_json(path, journal)
    if os.environ.get("STORY_CANDIDATE_FAIL_AFTER") == "prepared":
        os._exit(97)
    return path, journal


def replay_tracking(project: Path, payload: dict[str, Any]) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(payload, handle, ensure_ascii=False)
        temp_input = Path(handle.name)
    env = os.environ.copy()
    env["STORY_WRITE_LOCK_HELD"] = "1"
    try:
        result = subprocess.run(
            [sys.executable, str(TRACKING_TOOL), "commit", "--project", str(project), "--input", str(temp_input)],
            capture_output=True, text=True, encoding="utf-8", env=env, check=False,
        )
    finally:
        temp_input.unlink(missing_ok=True)
    if result.returncode != 0:
        raise CandidateError(f"追踪事务回放失败：\n{(result.stderr or result.stdout).strip()}")


def recover_journal(project: Path, path: Path) -> dict[str, Any]:
    journal = read_json(path, "采用日志")
    require(journal.get("schema_version") == 1 and journal.get("phase") in PHASES, f"采用日志格式非法：{path}")
    paths = {key: (project.resolve() / value).resolve() for key, value in journal["paths"].items()}
    for resolved in paths.values():
        project_relative(project, resolved)
    candidate = paths["candidate"]
    final = paths["final"]
    transaction = paths["transaction"]
    archive = paths["archive_transaction"]
    digests = journal["digests"]

    if journal["phase"] == "prepared":
        if candidate.exists():
            require(sha256_file(candidate) == digests["candidate"], "候选摘要与采用日志不一致")
            require(not final.exists(), "候选和正稿同时存在，拒绝猜测")
            final.parent.mkdir(parents=True, exist_ok=True)
            candidate.replace(final)
        else:
            require(final.is_file() and sha256_file(final) == digests["candidate"], "候选移动状态无法确认")
        update_phase(path, journal, "prose_moved")

    if journal["phase"] == "prose_moved":
        require(final.is_file() and sha256_file(final) == digests["candidate"], "正稿摘要与采用日志不一致")
        state = read_state(project)
        revision = state.get("state_revision")
        if revision == journal["expected_state_revision"]:
            replay_tracking(project, journal["tracking_payload"])
            state = read_state(project)
            revision = state.get("state_revision")
        require(revision == journal["expected_next_revision"], "追踪状态不是采用前或预期采用后版本，拒绝恢复")
        require(sha256_file(project.resolve() / TRACKING_STATE) == digests["state_after"], "采用后追踪状态摘要不一致")
        update_phase(path, journal, "tracking_committed")

    if journal["phase"] == "tracking_committed":
        if transaction.exists():
            require(sha256_file(transaction) == digests["transaction"], "待归档事务摘要不一致")
            archive.parent.mkdir(parents=True, exist_ok=True)
            require(not archive.exists(), "事务原件和归档同时存在，拒绝覆盖")
            transaction.replace(archive)
        else:
            require(archive.is_file() and sha256_file(archive) == digests["transaction"], "事务归档状态无法确认")
        update_phase(path, journal, "done")

    require(final.is_file() and sha256_file(final) == digests["candidate"], "完成后的正稿摘要不一致")
    require(archive.is_file() and sha256_file(archive) == digests["transaction"], "完成后的事务归档摘要不一致")
    state = read_state(project)
    require(state.get("state_revision") == journal["expected_next_revision"], "完成后的追踪 revision 不一致")
    return {
        "action": "promote",
        "chapter": journal["chapter"],
        "prose": final.name,
        "state_revision": state["state_revision"],
        "operation_id": journal["operation_id"],
        "recovered": True,
    }


def pending_journals(project: Path, chapter: int | None = None) -> list[Path]:
    paths = unfinished_adoptions(project)
    if chapter is None:
        return paths
    result = []
    for path in paths:
        document = read_json(path, "采用日志")
        if document.get("chapter") == chapter:
            result.append(path)
    return result


def completed_journals(project: Path, chapter: int) -> list[Path]:
    history = history_root(project)
    if not history.is_dir():
        return []
    matches: list[Path] = []
    for path in sorted(history.glob(f"{JOURNAL_PREFIX}*.json"), reverse=True):
        try:
            document = read_json(path, "采用日志")
        except CandidateError:
            continue
        if document.get("chapter") == chapter and document.get("phase") == "done":
            matches.append(path)
    return matches


def promote_chapter(project: Path, chapter: int, *, skip_scan: bool = False) -> dict[str, Any]:
    project = project.resolve()
    with project_lock(project):
        pending = pending_journals(project)
        if pending:
            matching = pending_journals(project, chapter)
            require(len(pending) == 1 and len(matching) == 1, "存在其他未完成采用；先执行 recover")
            return recover_journal(project, matching[0])
        prose = find_prose_candidate(project, chapter)
        transaction = find_transaction(project, chapter)
        require(transaction is not None, f"第{chapter}章缺少追踪事务 JSON（{TRANSACTION_SUFFIX}）")
        require(find_final(project, chapter) is None, f"正稿已存在第{chapter}章，promote 不覆盖正稿")
        document = read_json(transaction, "追踪事务")
        preflight = validate_binding(project, chapter, prose, transaction, document, skip_scan=skip_scan)
        path, journal = create_journal(project, chapter, prose, transaction, preflight)
        result = recover_journal(project, path)
        result["recovered"] = False
        return result


def recover(project: Path, chapter: int | None) -> list[dict[str, Any]]:
    project = project.resolve()
    with project_lock(project):
        paths = pending_journals(project, chapter)
        if not paths and chapter is not None:
            paths = completed_journals(project, chapter)[:1]
        require(paths, "没有可恢复的候选采用事务")
        return [recover_journal(project, path) for path in paths]


def reject_chapter(project: Path, chapter: int, *, rewrite: bool) -> dict[str, Any]:
    project = project.resolve()
    with project_lock(project):
        require(not unfinished_adoptions(project), "存在未完成采用，拒绝归档候选")
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
        return {"action": "rewrite" if rewrite else "reject", "chapter": chapter, "archived": archived}


def list_candidates(project: Path) -> list[dict[str, Any]]:
    root = candidate_root(project)
    if not root.is_dir():
        return []
    pending_by_chapter: dict[int, str] = {}
    for journal_path_ in unfinished_adoptions(project):
        try:
            journal = read_json(journal_path_, "采用日志")
            pending_by_chapter[int(journal["chapter"])] = str(journal["phase"])
        except (CandidateError, KeyError, TypeError, ValueError):
            continue
    entries: list[dict[str, Any]] = []
    for path in sorted(root.iterdir()):
        if path.name == HISTORY_DIR or path.is_dir() or not is_prose_candidate(path.name):
            continue
        chapter = chapter_of(path.name)
        transaction = find_transaction(project, chapter) if chapter else None
        binding = None
        if transaction is not None:
            try:
                document = read_json(transaction, "追踪事务")
                binding = isinstance(document.get("candidate_binding"), dict)
                expected_revision = document.get("expected_state_revision")
            except CandidateError:
                binding = False
                expected_revision = None
        else:
            expected_revision = None
        entries.append({
            "chapter": chapter,
            "prose": path.name,
            "candidate_sha256": sha256_file(path),
            "has_transaction": transaction is not None,
            "has_binding": binding,
            "expected_state_revision": expected_revision,
            "final_exists": find_final(project, chapter) is not None if chapter else False,
            "adoption_phase": pending_by_chapter.get(chapter) if chapter else None,
        })
    return entries


def promote_all(project: Path, *, skip_scan: bool = False) -> list[dict[str, Any]]:
    chapters = sorted({entry["chapter"] for entry in list_candidates(project) if entry["chapter"] is not None})
    require(chapters, "候选目录没有可采用的正文")
    return [promote_chapter(project, chapter, skip_scan=skip_scan) for chapter in chapters]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="候选正文的采用、恢复、归档与列表")
    sub = parser.add_subparsers(dest="command", required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--project", type=Path, required=True)
    group = promote.add_mutually_exclusive_group(required=True)
    group.add_argument("--chapter", type=int)
    group.add_argument("--all", action="store_true")
    promote.add_argument("--no-scan", action="store_true", help="只跳过 AI 模式扫描，不跳过结构与状态门禁")
    recover_parser = sub.add_parser("recover")
    recover_parser.add_argument("--project", type=Path, required=True)
    recover_group = recover_parser.add_mutually_exclusive_group(required=True)
    recover_group.add_argument("--chapter", type=int)
    recover_group.add_argument("--all", action="store_true")
    reject = sub.add_parser("reject")
    reject.add_argument("--project", type=Path, required=True)
    reject.add_argument("--chapter", type=int, required=True)
    reject.add_argument("--rewrite", action="store_true")
    listing = sub.add_parser("list")
    listing.add_argument("--project", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "promote":
            result: Any = promote_all(args.project, skip_scan=args.no_scan) if args.all else promote_chapter(args.project, args.chapter, skip_scan=args.no_scan)
        elif args.command == "recover":
            result = recover(args.project, None if args.all else args.chapter)
        elif args.command == "reject":
            result = reject_chapter(args.project, args.chapter, rewrite=args.rewrite)
        else:
            result = list_candidates(args.project)
    except (CandidateError, ProjectLockError, OSError, UnicodeError) as exc:
        emit(f"ERROR: {exc}", error=True)
        return 2
    emit(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
