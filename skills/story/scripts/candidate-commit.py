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
QUALITY_PROFILE = "fanqie-long-v2"
BINDING_SCHEMA = 2
RC_IDS = ("rc-01", "rc-02", "rc-03")
ARC_IDS = ("arc-01", "arc-02")
SEMANTIC_RECEIPT_IDS = ("rc-01", "rc-02", "rc-03", "arc-01")
PHASES = ("prepared", "prose_moved", "tracking_committed", "done")
CHAPTER_PREFIX = re.compile(r"^第0*(\d+)章")
TRACKING_TOOL = Path(__file__).resolve().parent / "tracking_commit.py"
SKELETON_TOOL = Path(__file__).resolve().parent / "check-chapter-skeleton.js"
OUTLINE_CONTRACT_TOOL = Path(__file__).resolve().parent / "check-outline-contract.js"
OUTLINE_COPY_TOOL = Path(__file__).resolve().parent / "check-outline-copy.js"
CAUSAL_TOOL = Path(__file__).resolve().parent / "check-outline-causal.py"
INTENT_FIELDS = ("目标情绪", "主角目标/关键选择", "结尾拍ID/类型", "期待ID/类型", "读者验收预期")
SHARED_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "_shared" / "scripts"
EMOTION_RUN_TOOL = SHARED_SCRIPTS / "check-emotion-run.js"
NAME_DRIFT_TOOL = SHARED_SCRIPTS / "check-name-drift.js"
TITLE_TOOL = SHARED_SCRIPTS / "check-chapter-titles.js"
FIRST_MENTION_TOOL = SHARED_SCRIPTS / "check-first-mention.js"
ARC_LEDGER_TOOL = SHARED_SCRIPTS / "arc-ledger.js"
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


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        require(key not in value, f"JSON 含重复键：{key}")
        value[key] = item
    return value


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8-sig"), object_pairs_hook=reject_duplicate_keys,
        )
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


def run_python(args: list[str], label: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [sys.executable, *args], capture_output=True, text=True, encoding="utf-8", check=False,
        )
    except OSError as exc:
        raise CandidateError(f"无法执行{label}：{exc}") from exc


def run_node(args: list[str], label: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    require(node is not None, f"未找到 node，无法执行{label}")
    try:
        return subprocess.run(
            [node, *args], capture_output=True, text=True, encoding="utf-8", check=False,
        )
    except OSError as exc:
        raise CandidateError(f"无法执行{label}：{exc}") from exc


def chapter_is_new(state: dict[str, Any], chapter: int) -> bool:
    return chapter > int(state.get("imported_through_chapter") or 0)


def intent_field_value(text: str, name: str) -> str | None:
    escaped = re.escape(name)
    match = re.search(
        rf"^\s*[-*+]\s*\*{{0,2}}{escaped}\*{{0,2}}\s*[：:]\s*(.*)$",
        text,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def intent_fields_missing(text: str) -> list[str]:
    missing: list[str] = []
    for field in INTENT_FIELDS:
        value = intent_field_value(text, field)
        if value is None:
            missing.append(field)
            continue
        hollow = re.sub(r"[\s、，,。;；]", "", value.replace("[待补充]", ""))
        if not hollow:
            missing.append(field)
    return missing


def outline_contract_gate(project: Path, chapter: int, state: dict[str, Any]) -> None:
    result = run_node(
        [str(OUTLINE_CONTRACT_TOOL), "--json", "--project", str(project), "--chapter", str(chapter)],
        "细纲契约检查",
    )
    if result.returncode == 2:
        require(False, f"细纲契约检查无法执行：\n{(result.stdout or result.stderr).strip()}")
    report = parse_node_json(result, "细纲契约检查", {0, 1})
    checks = report.get("checks")
    require(isinstance(checks, list), "细纲契约检查结果缺少 checks")
    by_id = {item.get("id"): item for item in checks if isinstance(item, dict)}
    readable = by_id.get("outline.readable")
    if readable is not None and not readable.get("ok"):
        require(False, f"细纲不可读：{readable.get('evidence')}")
    emotion_vocab = by_id.get("outline.emotion-vocab")
    if emotion_vocab is not None and not emotion_vocab.get("ok") and chapter_is_new(state, chapter):
        require(False, f"目标情绪取值不在闭合词表：{emotion_vocab.get('evidence')}")
    outline_file = report.get("file")
    text = ""
    if isinstance(outline_file, str) and outline_file:
        try:
            text = Path(outline_file).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            require(False, f"无法读取细纲：{outline_file}: {exc}")
    missing = intent_fields_missing(text)
    advisory: list[str] = []
    for item in checks:
        if not isinstance(item, dict) or item.get("ok"):
            continue
        check_id = str(item.get("id") or "")
        if check_id in {"outline.readable", "outline.emotion-vocab"}:
            continue
        advisory.append(f"{check_id}：{item.get('evidence')}")
    if missing:
        message = f"细纲 INTENT_FIELDS 缺失或无实际内容：{'、'.join(missing)}"
        if chapter_is_new(state, chapter):
            require(False, message)
        advisory.insert(0, f"[历史章 advisory] {message}")
    if emotion_vocab is not None and not emotion_vocab.get("ok"):
        advisory.insert(0, f"[历史章 advisory] outline.emotion-vocab：{emotion_vocab.get('evidence')}")
    if advisory:
        emit("细纲契约 advisory：\n" + "\n".join(advisory), error=True)


def emotion_run_gate(project: Path, chapter: int, state: dict[str, Any]) -> None:
    result = run_node(
        [str(EMOTION_RUN_TOOL), "--json", "--project", str(project), "--chapter", str(chapter)],
        "目标情绪连排检查",
    )
    if result.returncode == 2:
        require(False, f"目标情绪连排检查无法执行：\n{(result.stdout or result.stderr).strip()}")
    report = parse_node_json(result, "目标情绪连排检查", {0, 1})
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    blocking = [item for item in findings if item.get("severity") == "blocking"]
    advisory = [item for item in findings if item.get("severity") != "blocking"]
    if blocking:
        message = "；".join(str(item.get("evidence") or item) for item in blocking)
        if chapter_is_new(state, chapter):
            require(False, f"目标情绪连排过长：{message}")
        advisory = blocking + advisory
    if advisory:
        emit(
            "目标情绪连排 advisory：\n" + "\n".join(str(item.get("evidence") or item) for item in advisory),
            error=True,
        )


def causal_gate(project: Path, chapter: int, state: dict[str, Any]) -> None:
    result = run_python(
        [
            str(CAUSAL_TOOL), str(project), "--json", "--strict",
            f"--from={chapter}", f"--to={chapter}",
        ],
        "细纲因果检查",
    )
    if result.returncode == 2:
        require(False, f"细纲因果检查无法执行：\n{(result.stdout or result.stderr).strip()}")
    require(result.returncode in {0, 1}, f"细纲因果检查执行失败：\n{(result.stdout or result.stderr).strip()}")
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CandidateError(f"细纲因果检查未返回合法 JSON：{(result.stdout or result.stderr).strip()}") from exc
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    blocking = [item for item in findings if item.get("severity") == "blocking"]
    advisory = [item for item in findings if item.get("severity") != "blocking"]
    if blocking:
        message = "；".join(str(item.get("msg") or item) for item in blocking)
        if chapter_is_new(state, chapter):
            require(False, f"细纲因果链未通过：{message}")
        advisory = blocking + advisory
    if advisory:
        emit(
            "细纲因果 advisory：\n" + "\n".join(str(item.get("msg") or item) for item in advisory),
            error=True,
        )


def name_drift_gate(project: Path, chapter: int, state: dict[str, Any]) -> None:
    result = run_node(
        [
            str(NAME_DRIFT_TOOL), "--json", "--project", str(project),
            "--chapter", str(chapter), "--fail-on=blocking",
        ],
        "专名漂移检查",
    )
    if result.returncode == 2:
        require(False, f"专名漂移检查无法执行：\n{(result.stdout or result.stderr).strip()}")
    report = parse_node_json(result, "专名漂移检查", {0, 1})
    findings = [item for item in report.get("findings", []) if isinstance(item, dict)]
    blocking = [item for item in findings if item.get("severity") == "blocking"]
    advisory = [item for item in findings if item.get("severity") != "blocking"]
    if chapter_is_new(state, chapter) and blocking:
        message = "；".join(str(item.get("evidence") or item) for item in blocking)
        require(False, f"正文/细纲出现未声明的现实专名：{message}")
    visible = advisory if chapter_is_new(state, chapter) else findings
    if visible:
        message = "；".join(str(item.get("evidence") or item) for item in visible)
        emit(f"专名漂移 advisory：{message}", error=True)


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
    profile = "fanqie"
    topic = project.resolve() / "设定" / "题材定位.md"
    if topic.is_file():
        try:
            match = re.search(r"^\s*-\s*标题档位\s*[：:]\s*(\S+)\s*$", topic.read_text(encoding="utf-8-sig"), re.MULTILINE)
        except (OSError, UnicodeError) as exc:
            raise CandidateError(f"无法读取标题档位：{topic}: {exc}") from exc
        if match:
            profile = match.group(1)
    require(profile in {"fanqie", "terse"}, f"标题档位非法：{profile}")
    with tempfile.TemporaryDirectory(prefix="candidate-title-") as temporary:
        root = Path(temporary)
        for final in body_root(project).glob("第*章*.md") if body_root(project).is_dir() else []:
            shutil.copy2(final, root / final.name)
        shutil.copy2(prose, root / prose.name)
        result = run_node([str(TITLE_TOOL), "--dir", str(root), "--profile", profile], "章节标题检查")
    require(result.returncode == 0, f"章节标题未通过：\n{(result.stdout or result.stderr).strip()}")


def reader_view_paths(project: Path, prose: Path) -> list[Path]:
    accepted = sorted(
        (
            path for path in body_root(project).glob("第*章*.md")
            if path.is_file() and chapter_of(path.name) is not None
        ),
        key=lambda path: (chapter_of(path.name) or 0, path.name),
    ) if body_root(project).is_dir() else []
    paths = [*accepted, prose.resolve()]
    known = body_root(project) / "_已知实体.txt"
    if known.is_file():
        paths.append(known.resolve())
    return paths


def prose_set_sha256(project: Path, paths: list[Path]) -> str:
    rows = sorted(
        f"{project_relative(project, path)}\0{sha256_file(path)}" for path in paths
    )
    return sha256_bytes("\n".join(rows).encode("utf-8"))


def validate_semantic_receipt(
    project: Path,
    receipt_id: str,
    receipt: object,
    prose: Path,
    candidate_sha256: str,
    expected_paths: list[Path],
) -> dict[str, Any]:
    require(isinstance(receipt, dict), f"candidate_binding.logic_checks.{receipt_id} 必须是对象")
    require(isinstance(receipt.get("run_id"), str) and receipt["run_id"].strip(), f"{receipt_id}.run_id 缺失")
    require(receipt.get("status") == "pass", f"{receipt_id}.status 必须是 pass")
    require(isinstance(receipt.get("findings"), list), f"{receipt_id}.findings 必须是数组")
    require(isinstance(receipt.get("evidence"), list) and receipt["evidence"], f"{receipt_id}.evidence 必须是非空数组")
    require(receipt.get("candidate_sha256") == candidate_sha256, f"{receipt_id}.candidate_sha256 已过期")
    for finding in receipt["findings"]:
        require(isinstance(finding, dict), f"{receipt_id}.findings 每项必须是对象")
        require(finding.get("severity") != "blocking", f"{receipt_id} 含 blocking finding")

    raw_files = receipt.get("prose_files")
    require(isinstance(raw_files, list), f"{receipt_id}.prose_files 必须是数组")
    actual_paths: list[Path] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_files):
        require(isinstance(item, dict), f"{receipt_id}.prose_files[{index}] 必须是对象")
        label = f"logic_checks.{receipt_id}.prose_files[{index}]"
        path = bound_path(project, item.get("path"), label)
        relative = project_relative(project, path)
        require(item.get("path") == relative, f"{receipt_id}.prose_files[{index}].path 必须是规范项目相对路径")
        require(relative not in seen, f"{receipt_id}.prose_files 含重复路径：{relative}")
        seen.add(relative)
        require(item.get("sha256") == sha256_file(path), f"{receipt_id}.prose_files[{index}].sha256 已过期")
        actual_paths.append(path)

    expected = {path.resolve() for path in expected_paths}
    require({path.resolve() for path in actual_paths} == expected, f"{receipt_id}.prose_files 未完整绑定实际读过的正文视图")
    require(receipt.get("prose_set_sha256") == prose_set_sha256(project, actual_paths), f"{receipt_id}.prose_set_sha256 已过期")
    files_by_relative = {project_relative(project, path): path for path in actual_paths}
    for index, item in enumerate(receipt["evidence"]):
        require(isinstance(item, dict), f"{receipt_id}.evidence[{index}] 必须是对象")
        label = f"logic_checks.{receipt_id}.evidence[{index}]"
        path = bound_path(project, item.get("path"), label)
        relative = project_relative(project, path)
        require(item.get("path") == relative, f"{receipt_id}.evidence[{index}].path 必须是规范项目相对路径")
        require(relative in files_by_relative, f"{receipt_id}.evidence[{index}].path 不属于 prose_files")
        anchor = item.get("anchor")
        require(isinstance(anchor, str) and anchor.strip(), f"{receipt_id}.evidence[{index}].anchor 缺失")
        try:
            source = files_by_relative[relative].read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            raise CandidateError(f"无法读取 {receipt_id} 证据正文：{relative}: {exc}") from exc
        require(anchor in source, f"{receipt_id}.evidence[{index}].anchor 无法在对应正文定位")
    return receipt


def parse_node_json(result: subprocess.CompletedProcess[str], label: str, allowed: set[int]) -> dict[str, Any]:
    require(result.returncode in allowed, f"{label}执行失败：\n{(result.stdout or result.stderr).strip()}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CandidateError(f"{label}未返回合法 JSON：{(result.stdout or result.stderr).strip()}") from exc
    require(isinstance(value, dict), f"{label}结果必须是 JSON 对象")
    return value


def rerun_rc01(project: Path, prose: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="candidate-reader-view-") as temporary:
        root = Path(temporary)
        for path in reader_view_paths(project, prose):
            shutil.copy2(path, root / path.name)
        result = run_node([str(FIRST_MENTION_TOOL), str(root), "--json"], "rc-01 专名首现检查")
    report = parse_node_json(result, "rc-01 专名首现检查", {0, 1})
    require(result.returncode == 0 and report.get("blocking") == 0, "rc-01 复验发现 blocking finding")
    return report


def rerun_arc02(ledger: dict[str, Any]) -> dict[str, Any]:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as handle:
        json.dump(ledger, handle, ensure_ascii=False)
        ledger_path = Path(handle.name)
    try:
        result = run_node([str(ARC_LEDGER_TOOL), str(ledger_path), "--json", "--window=15"], "arc-02 开篇阈值检查")
    finally:
        ledger_path.unlink(missing_ok=True)
    return parse_node_json(result, "arc-02 开篇阈值检查", {0, 1})


def validate_logic_checks(
    project: Path, chapter: int, prose: Path, binding: dict[str, Any], candidate_sha256: str,
) -> dict[str, str]:
    logic = binding.get("logic_checks")
    require(isinstance(logic, dict), "candidate_binding.logic_checks 必须是对象")
    required_ids = set(RC_IDS + (ARC_IDS if chapter == 15 else ()))
    require(set(logic) == required_ids, f"candidate_binding.logic_checks 必须精确包含：{', '.join(sorted(required_ids))}")
    expected_paths = reader_view_paths(project, prose)

    for receipt_id in RC_IDS:
        validate_semantic_receipt(
            project, receipt_id, logic[receipt_id], prose, candidate_sha256, expected_paths,
        )

    rc_report = rerun_rc01(project, prose)
    rc_digest = sha256_bytes(canonical_json(rc_report))
    require(logic["rc-01"].get("result_sha256") == rc_digest, "rc-01.result_sha256 与复验结果不一致")
    result = {"rc-01": rc_digest}

    if chapter != 15:
        return result

    accepted_numbers = sorted(
        chapter_of(path.name) for path in body_root(project).glob("第*章*.md")
        if path.is_file() and chapter_of(path.name) is not None
    )
    require(accepted_numbers == list(range(1, 15)), "第15章 arc 检查要求正文完整包含第1～14章")
    arc01 = validate_semantic_receipt(
        project, "arc-01", logic["arc-01"], prose, candidate_sha256, expected_paths,
    )
    ledger = arc01.get("ledger")
    require(isinstance(ledger, dict), "arc-01.ledger 必须是对象")
    ledger_chapters = ledger.get("chapters")
    require(
        isinstance(ledger_chapters, list)
        and [item.get("num") for item in ledger_chapters if isinstance(item, dict)] == list(range(1, 16)),
        "arc-01.ledger 必须按顺序完整覆盖第1～15章",
    )
    ledger_digest = sha256_bytes(canonical_json(ledger))
    require(arc01.get("ledger_sha256") == ledger_digest, "arc-01.ledger_sha256 已过期")

    arc02 = logic["arc-02"]
    require(isinstance(arc02, dict), "candidate_binding.logic_checks.arc-02 必须是对象")
    require(isinstance(arc02.get("run_id"), str) and arc02["run_id"].strip(), "arc-02.run_id 缺失")
    require(isinstance(arc02.get("findings"), list), "arc-02.findings 必须是数组")
    require(isinstance(arc02.get("evidence"), list), "arc-02.evidence 必须是数组")
    require(arc02.get("candidate_sha256") == candidate_sha256, "arc-02.candidate_sha256 已过期")
    require(arc02.get("ledger_sha256") == ledger_digest, "arc-02.ledger_sha256 已过期")
    arc_report = rerun_arc02(ledger)
    arc_digest = sha256_bytes(canonical_json(arc_report))
    require(arc02.get("result_sha256") == arc_digest, "arc-02.result_sha256 与复验结果不一致")
    if arc_report.get("blocking"):
        override = arc02.get("override")
        require(isinstance(override, dict), "arc-02 复验为 blocking，缺少作者批准")
        require(override.get("approved_by_author") is True, "arc-02 作者批准标记无效")
        require(override.get("result_sha256") == arc_digest, "arc-02 作者批准未绑定当前结果")
        require(isinstance(override.get("reason"), str) and override["reason"].strip(), "arc-02 作者批准缺少理由")
        require(arc02.get("status") == "blocking-approved", "arc-02 blocking 批准状态非法")
    else:
        require(arc02.get("status") == "pass", "arc-02.status 必须是 pass")
    result["arc-02"] = arc_digest
    return result


def validate_binding(
    project: Path, chapter: int, prose: Path, transaction: Path, document: dict[str, Any], *,
    skip_scan: bool, scan_skip_reason: str | None = None,
) -> dict[str, Any]:
    state = read_state(project)
    expected = document.get("expected_state_revision")
    require(isinstance(expected, int), "追踪事务必须保存候选创建时的 expected_state_revision")
    require(expected == state.get("state_revision"), "候选已过期：tracking state changed since this candidate was prepared")
    require(document.get("chapter") == chapter, "追踪事务章号与候选章号不一致")

    binding = document.get("candidate_binding")
    require(isinstance(binding, dict), "追踪事务缺少 candidate_binding")
    require(binding.get("schema_version") == BINDING_SCHEMA, "candidate_binding v1 已停止采用；请重新生成带逻辑证据的 v2 绑定")
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

    logic_results = validate_logic_checks(project, chapter, prose, binding, hashes["candidate"])
    rc01 = binding["logic_checks"]["rc-01"]
    reader_view_binding = {
        "prose_files": [dict(item) for item in rc01["prose_files"]],
        "prose_set_sha256": rc01["prose_set_sha256"],
    }

    skeleton_result = run_node([str(SKELETON_TOOL), str(skeleton)], "骨架检查")
    require(skeleton_result.returncode == 0, f"骨架未通过：\n{(skeleton_result.stdout or skeleton_result.stderr).strip()}")
    outline_contract_gate(project, chapter, state)
    emotion_run_gate(project, chapter, state)
    causal_gate(project, chapter, state)
    name_drift_gate(project, chapter, state)
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
    # 语言门禁只认 CLI 侧的显式豁免。正文里的 `<!-- 去味:跳过 -->` 由写正文的一方产出，
    # 不能用来决定检查自己的门是否运行；作者要跳过时用 promote --no-scan --reason，留痕可审计。
    scan_skip: dict[str, Any] | None = None
    if skip_scan:
        scan_skip = {"reason": scan_skip_reason, "skipped_at": datetime.now().astimezone().isoformat()}
    else:
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
        "logic_results": logic_results,
        "reader_view_binding": reader_view_binding,
        "scan_skip": scan_skip,
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


def operation_id_for(chapter: int, candidate_sha256: str, transaction_sha256: str, expected_revision: int) -> str:
    digest = sha256_bytes(canonical_json({
        "chapter": chapter,
        "candidate": candidate_sha256,
        "transaction": transaction_sha256,
        "expected_revision": expected_revision,
    }))[:20]
    return f"c{chapter}-{digest}"


def create_journal(project: Path, chapter: int, prose: Path, transaction: Path, preflight: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    operation_id = operation_id_for(
        chapter,
        preflight["hashes"]["candidate"],
        preflight["hashes"]["transaction"],
        preflight["expected_revision"],
    )
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
        "logic_results": preflight["logic_results"],
        "reader_view_binding": preflight["reader_view_binding"],
        "scan_skip": preflight["scan_skip"],
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


def verify_recovery_reader_view(
    project: Path,
    journal_path_: Path,
    journal: dict[str, Any],
    paths: dict[str, Path],
    digests: dict[str, str],
) -> None:
    expected_operation = operation_id_for(
        journal["chapter"],
        digests["candidate"],
        digests["transaction"],
        journal["expected_state_revision"],
    )
    require(journal.get("operation_id") == expected_operation, "采用日志 operation_id 与输入摘要不一致")
    require(journal_path_.name == f"{JOURNAL_PREFIX}{expected_operation}.json", "采用日志文件名与 operation_id 不一致")

    transaction = paths["transaction"]
    require(transaction.is_file(), "恢复采用前缺少原始追踪事务")
    require(sha256_file(transaction) == digests["transaction"], "恢复采用前追踪事务摘要不一致")
    document = read_json(transaction, "追踪事务")
    binding = document.get("candidate_binding")
    logic = binding.get("logic_checks") if isinstance(binding, dict) else None
    rc01 = logic.get("rc-01") if isinstance(logic, dict) else None
    require(isinstance(rc01, dict), "恢复采用缺少 rc-01 读者视图绑定")
    source_binding = {
        "prose_files": rc01.get("prose_files"),
        "prose_set_sha256": rc01.get("prose_set_sha256"),
    }
    snapshot = journal.get("reader_view_binding")
    require(snapshot == source_binding, "采用日志的读者视图绑定与原始事务不一致")
    require(isinstance(snapshot, dict) and isinstance(snapshot.get("prose_files"), list), "采用日志缺少读者视图绑定")

    candidate_relative = journal["paths"]["candidate"]
    final = paths["final"]
    candidate = paths["candidate"]
    seen: set[str] = set()
    rows: list[str] = []
    for index, item in enumerate(snapshot["prose_files"]):
        require(isinstance(item, dict), f"采用日志 prose_files[{index}] 必须是对象")
        relative = item.get("path")
        require(isinstance(relative, str) and relative not in seen, f"采用日志 prose_files[{index}].path 非法或重复")
        seen.add(relative)
        unresolved = (project.resolve() / relative).resolve()
        require(project_relative(project, unresolved) == relative, f"采用日志 prose_files[{index}].path 不是规范项目相对路径")
        actual = final if relative == candidate_relative and not candidate.exists() else unresolved
        require(actual.is_file(), f"恢复采用的读者正文缺失：{relative}")
        digest = sha256_file(actual)
        require(item.get("sha256") == digest, f"恢复采用的读者正文摘要已变化：{relative}")
        rows.append(f"{relative}\0{digest}")

    current_relatives = {
        candidate_relative if path.resolve() == final else project_relative(project, path)
        for path in body_root(project).glob("第*章*.md")
        if path.is_file() and chapter_of(path.name) is not None
    }
    current_relatives.add(candidate_relative)
    known = body_root(project) / "_已知实体.txt"
    if known.is_file():
        current_relatives.add(project_relative(project, known))
    require(seen == current_relatives, "恢复采用时读者正文文件集合已变化")
    current_set_sha = sha256_bytes("\n".join(sorted(rows)).encode("utf-8"))
    require(snapshot.get("prose_set_sha256") == current_set_sha, "恢复采用时 prose_set_sha256 已变化")


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

    if journal["phase"] in {"prepared", "prose_moved"}:
        verify_recovery_reader_view(project, path, journal, paths, digests)

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


def check_chapter(project: Path, chapter: int) -> dict[str, Any]:
    """Run promote preflight without moving files, taking a lock, or writing state."""
    project = project.resolve()
    prose = find_prose_candidate(project, chapter)
    transaction = find_transaction(project, chapter)
    require(transaction is not None, f"第{chapter}章缺少追踪事务 JSON（{TRANSACTION_SUFFIX}）")
    document = read_json(transaction, "追踪事务")
    preflight = validate_binding(
        project, chapter, prose, transaction, document,
        skip_scan=False,
    )
    return {
        "action": "check",
        "chapter": chapter,
        "ok": True,
        "outline": preflight["outline"],
        "skeleton": preflight["skeleton"],
        "expected_revision": preflight["expected_revision"],
    }


def promote_chapter(
    project: Path, chapter: int, *, skip_scan: bool = False, scan_skip_reason: str | None = None,
) -> dict[str, Any]:
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
        preflight = validate_binding(
            project, chapter, prose, transaction, document,
            skip_scan=skip_scan, scan_skip_reason=scan_skip_reason,
        )
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


def promote_all(project: Path, *, skip_scan: bool = False, scan_skip_reason: str | None = None) -> list[dict[str, Any]]:
    chapters = sorted({entry["chapter"] for entry in list_candidates(project) if entry["chapter"] is not None})
    require(chapters, "候选目录没有可采用的正文")
    require(len(chapters) == 1, "promote --all 不支持多个候选；请逐章采用，尚未修改任何正文或追踪")
    return [promote_chapter(project, chapters[0], skip_scan=skip_scan, scan_skip_reason=scan_skip_reason)]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="候选正文的采用、恢复、归档与列表")
    sub = parser.add_subparsers(dest="command", required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--project", type=Path, required=True)
    group = promote.add_mutually_exclusive_group(required=True)
    group.add_argument("--chapter", type=int)
    group.add_argument("--all", action="store_true", help="兼容单个待审候选；多个候选会在写入前拒绝")
    promote.add_argument("--no-scan", action="store_true", help="只跳过 AI 模式扫描，不跳过结构与状态门禁；必须同时给 --reason")
    promote.add_argument("--reason", help="使用 --no-scan 时必填：跳过语言门禁的理由，写入采用回执备查")
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
    check = sub.add_parser("check")
    check.add_argument("--project", type=Path, required=True)
    check.add_argument("--chapter", type=int, required=True)
    check.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "promote":
            reason = (args.reason or "").strip()
            require(not args.no_scan or reason, "--no-scan 必须同时给出 --reason（跳过语言门禁的理由会写入采用回执）")
            require(args.no_scan or not reason, "--reason 只在 --no-scan 时有意义")
            result: Any = (
                promote_all(args.project, skip_scan=args.no_scan, scan_skip_reason=reason or None)
                if args.all
                else promote_chapter(args.project, args.chapter, skip_scan=args.no_scan, scan_skip_reason=reason or None)
            )
        elif args.command == "recover":
            result = recover(args.project, None if args.all else args.chapter)
        elif args.command == "reject":
            result = reject_chapter(args.project, args.chapter, rewrite=args.rewrite)
        elif args.command == "check":
            result = check_chapter(args.project, args.chapter)
        else:
            result = list_candidates(args.project)
    except (CandidateError, ProjectLockError, OSError, UnicodeError) as exc:
        emit(f"ERROR: {exc}", error=True)
        return 1 if args.command == "check" and isinstance(exc, CandidateError) else 2
    emit(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
