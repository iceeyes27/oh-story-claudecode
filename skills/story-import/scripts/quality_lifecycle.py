#!/usr/bin/env python3
"""Immutable chapter review, reader-chain, and accepted-generation lifecycle.

The accepted HEAD is the logical commit point.  ``正文/`` and ``追踪/`` are
materialized projections and can be rebuilt from the generation named by HEAD.
No candidate becomes accepted until deterministic chapter checks, a complete
six-view review packet, reader-cohort evidence, and post-hoc extraction pass.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from typing import Any, Iterator

if os.name == "nt":
    import msvcrt
else:
    import fcntl


SCHEMA = "story-quality-lifecycle/v1"
PACKET_SCHEMA = "story-quality-review/v1"
EXPERIMENT_SCHEMA = "story-quality-longitudinal/v1"
EXPERIMENT_SCHEMA_V2 = "story-quality-longitudinal/v2"
SYSTEM_EXPERIMENT_SCHEMA = "story-quality-system-experiment/v1"
REPLAY_SCHEMA = "story-quality-replay/v1"
READER_SCHEMA_V2 = "story-reader-evidence/v2"
READER_SCHEMA_V3 = "story-reader-evidence/v3"
POLICY_SCHEMA = "story-quality-policy/v1"
CALIBRATION_SCHEMA = "story-quality-calibration/v1"
CHECKPOINT_SCHEMA = "story-quality-checkpoint/v1"
REOPEN_SCHEMA = "story-quality-reopen/v1"
OUTLINE_SEARCH_SCHEMA = "story-outline-search/v1"
STRUCTURAL_BENCHMARK_SCHEMA = "story-structural-benchmark/v1"
GOLDEN_THREE_SCHEMA = "story-golden-three-plan/v1"
EXPERIMENT_PREREG_SCHEMA = "story-quality-experiment-preregistration/v1"
EXPERIMENT_PREREG_RECORD_SCHEMA = "story-quality-experiment-preregistration-record/v1"
REVISION_APPEAL_PREREG_SCHEMA = "story-revision-appeal-preregistration/v1"
REVISION_APPEAL_EXPERIMENT_SCHEMA = "story-revision-appeal-between-subject/v1"
AUTHOR_VOICE_EFFECT_PREREG_SCHEMA = "story-author-voice-effect-preregistration/v1"
AUTHOR_VOICE_EFFECT_SCHEMA = "story-author-voice-effect/v1"
EVIDENCE_BUNDLE_SCHEMA = "story-quality-evidence-bundle/v1"
EVIDENCE_RECORD_SCHEMA = "story-quality-evidence-record/v1"
TREATMENT_RUN_SCHEMA = "story-quality-treatment-run/v1"
QUALITY_DIR = ".story-quality"
TRACKING_RUNTIME_FILES = frozenset({Path(".tracking-commit.lock"), Path(".story-write.lock")})
PERSPECTIVES = {
    "story-logic",
    "character-arc",
    "reader-comprehension",
    "reader-retention",
    "prose-style",
    "continuity",
}
CORRECTNESS_GATES = {"causality", "facts", "present_action", "mystery_legitimacy"}
DISPOSITIONS = {"FIXED_VERIFIED", "PRESERVED_WITH_FUNCTION", "FALSE_POSITIVE", "OVERRIDDEN"}
SEVERITIES = {"S1", "S2", "S3", "S4"}
EVENT_KINDS = {
    "fact", "knowledge_source", "knowledge", "relation", "arc", "commitment",
    "open_question", "rule", "exception",
}
ENDING_TYPES = {"goal", "conflict", "choice", "relationship", "payoff", "aftermath", "open_question"}
STRENGTH_MODES = {"SHADOW", "ENFORCE"}
STRENGTH_STATUSES = {"PASS", "FLAT", "INSUFFICIENT_EVIDENCE"}
REVISION_INTENTS = {"defect_repair", "strength_reopen", "rollback"}
KNOWLEDGE_STATES = {"knows", "believes", "suspects", "misbelieves", "denies"}
FRICTION_KINDS = {"comprehension", "patience", "orientation", "tone", "productive_pressure"}
CALIBRATION_PURPOSES = {"reference_instrument", "development_thresholds", "held_out_validation"}
EVIDENCE_KINDS = {
    "story_package", "human_reader_import", "misfire_control",
    "reopen_validation", "threshold_derivation", "workflow_run",
    "between_subject_arm",
}
REVISION_SECONDARY_ENDPOINTS = frozenset({
    "first_friction", "strongest_read_on", "cumulative_confusion",
    "cumulative_fatigue", "mystery_fatigue", "voice_loss",
})
VOICE_SECONDARY_ENDPOINTS = frozenset({"comprehension", "continuity", "voice_loss"})
VOICE_FROZEN_CONDITION_KEYS = frozenset({
    "plot_sha256", "model_sha256", "context_sha256", "budget_sha256", "stop_rule_sha256",
})
CHAPTER_RE = re.compile(r"^第0*(\d+)章(?:_|\b).+\.md$")
SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}


class QualityError(ValueError):
    """Expected lifecycle or validation failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise QualityError(message)


def emit(payload: dict[str, Any]) -> None:
    sys.stdout.buffer.write((json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))


def read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QualityError(f"unable to read {label}: {exc}") from exc
    require(isinstance(value, dict), f"{label} must be a JSON object")
    return value


def payload(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_file(path: Path) -> str:
    try:
        return sha_bytes(path.read_bytes())
    except OSError as exc:
        raise QualityError(f"unable to hash {path}: {exc}") from exc


def sha_json(value: object) -> str:
    return sha_bytes(payload(value).encode("utf-8"))


def is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def tracking_event_fingerprint(event: dict[str, Any]) -> str:
    """Bind a quality event to the semantic fields in the tracking ledger."""
    legacy_keys = (
        "id", "story_time", "objective_fact", "reader_knowledge",
        "reveal_status", "reveal_chapter", "characters",
    )
    # Preserve the exact P0/v1 digest for events that predate kind/order/knowledge.
    # Adding null fields would silently invalidate every historical certificate.
    if all(key not in event for key in ("kind", "occurrence_order", "knowledge")):
        return sha_json({key: event.get(key) for key in legacy_keys})
    return sha_json({
        "fingerprint_version": 2,
        **{key: event.get(key) for key in legacy_keys},
        "kind": event.get("kind"),
        "occurrence_order": event.get("occurrence_order"),
        "knowledge": event.get("knowledge"),
    })


def parse_utc_timestamp(value: object, label: str) -> datetime:
    text = nonempty_text(value, label)
    require(text.endswith("Z"), f"{label} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise QualityError(f"{label} is not a valid ISO-8601 timestamp") from exc
    require(parsed.tzinfo is not None and parsed.utcoffset() == timezone.utc.utcoffset(parsed), f"{label} must be UTC")
    return parsed


def tracking_event_bindings(events: list[dict[str, Any]], chapter: int) -> dict[str, dict[str, Any]]:
    return {
        event["id"]: {"chapter": chapter, "fingerprint": tracking_event_fingerprint(event), "event": copy.deepcopy(event)}
        for event in events
        if event.get("action", "upsert") != "delete"
    }


def safe_component(value: object, label: str) -> str:
    text = nonempty_text(value, label)
    require(SAFE_COMPONENT_RE.fullmatch(text) is not None and text not in {".", ".."}, f"{label} is not a safe path component")
    require(not text.endswith(".") and text.split(".", 1)[0].upper() not in WINDOWS_RESERVED, f"{label} is not portable across filesystems")
    return text


def number(value: object, label: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    require(isinstance(value, (int, float)) and not isinstance(value, bool), f"{label} must be numeric")
    result = float(value)
    if minimum is not None:
        require(result >= minimum, f"{label} must be at least {minimum}")
    if maximum is not None:
        require(result <= maximum, f"{label} must be at most {maximum}")
    return result


def integer(value: object, label: str, *, minimum: int | None = None, maximum: int | None = None) -> int:
    require(isinstance(value, int) and not isinstance(value, bool), f"{label} must be an integer")
    if minimum is not None:
        require(value >= minimum, f"{label} must be at least {minimum}")
    if maximum is not None:
        require(value <= maximum, f"{label} must be at most {maximum}")
    return value


def require_fresh(manifest: dict[str, Any], action: str) -> None:
    stale = manifest.get("stale", {})
    require(not any(value is not None for value in stale.values()), f"cannot {action} while accepted HEAD requires sequential replay")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def quality_root(project: Path) -> Path:
    return project.resolve() / QUALITY_DIR


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, payload(value))


@contextmanager
def lifecycle_lock(project: Path) -> Iterator[None]:
    """Cross-process lock whose ownership is released by the operating system."""
    project = project.resolve()
    require_safe_projection_target(project, project / QUALITY_DIR, f"{QUALITY_DIR} projection")
    root = quality_root(project)
    root.mkdir(parents=True, exist_ok=True)
    lock = root / ".write.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    if os.name == "nt":
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"\0")
    deadline = time.monotonic() + 10
    while True:
        try:
            if os.name == "nt":
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (BlockingIOError, OSError):
            if time.monotonic() >= deadline:
                os.close(descriptor)
                raise QualityError("quality lifecycle is locked by another live writer")
            time.sleep(0.05)
    os.ftruncate(descriptor, 0)
    os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
    os.fsync(descriptor)
    try:
        yield
    finally:
        if os.name == "nt":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def require_safe_projection_target(root: Path, target: Path, label: str) -> None:
    """Reject lexical escape and every symlink component before projection I/O."""
    root = root.resolve()
    try:
        relative = target.absolute().relative_to(root)
    except ValueError as exc:
        raise QualityError(f"{label} escapes its projection root") from exc
    current = root
    for component in relative.parts:
        current = current / component
        require(not current.is_symlink(), f"{label} contains a symbolic-link component: {current}")
    try:
        target.parent.resolve(strict=False).relative_to(root)
    except ValueError as exc:
        raise QualityError(f"{label} resolves outside its projection root") from exc


def require_projection_roots_safe(project: Path) -> None:
    project = project.resolve()
    for name in ("正文", "追踪", QUALITY_DIR):
        require_safe_projection_target(project, project / name, f"{name} projection")


def chapter_number(path: Path) -> int | None:
    match = CHAPTER_RE.match(path.name)
    return int(match.group(1)) if match else None


def chapter_files(project: Path, chapter: int | None = None) -> list[Path]:
    body_dir = project / "正文"
    rows: list[Path] = []
    if not body_dir.is_dir():
        return rows
    for path in body_dir.glob("*.md"):
        number = chapter_number(path)
        if number is not None and (chapter is None or number == chapter):
            rows.append(path)
    return sorted(rows)


def outline_file(project: Path, chapter: int) -> Path:
    hits = []
    for path in (project / "大纲").glob("细纲_第*章*.md"):
        match = re.match(r"^细纲_第0*(\d+)章", path.name)
        if match and int(match.group(1)) == chapter:
            hits.append(path)
    require(len(hits) == 1, f"chapter {chapter} must have exactly one fine outline")
    return hits[0]


def outline_contract(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    ending = re.search(r"^- 结尾拍ID/类型：\s*([^；;\s]+)\s*[；;]\s*([^；;\s]+)", text, re.MULTILINE)
    expectation = re.search(r"^- 期待ID/类型：\s*([^；;\s]+)\s*[；;]\s*([^；;\s]+)", text, re.MULTILINE)
    require(ending is not None and expectation is not None, "fine outline lacks ending/expectation contract fields")
    contract: dict[str, Any] = {
        "ending_beat_id": ending.group(1),
        "ending_beat_type": ending.group(2),
        "expectation_id": expectation.group(1),
        "expectation_type": expectation.group(2),
    }
    oracle = re.search(r"^- 读者验收预期：\s*(.+)$", text, re.MULTILINE)
    if oracle is not None:
        reader_oracle: dict[str, str] = {}
        for key in ("must_know", "may_believe", "must_not_know", "open_ids"):
            match = re.search(rf"{key}\s*=\s*(\[[^\]]*\])", oracle.group(1))
            require(match is not None, f"fine outline reader oracle lacks {key}")
            reader_oracle[key] = match.group(1)
        contract["reader_oracle"] = reader_oracle
        contract["reader_oracle_sha256"] = sha_json(reader_oracle)
    p1 = re.search(r"^- P1质量契约：\s*(\{.+\})\s*$", text, re.MULTILINE)
    if p1 is None:
        return contract
    try:
        value = json.loads(p1.group(1))
    except json.JSONDecodeError as exc:
        raise QualityError(f"fine outline P1 quality contract is invalid JSON: {exc}") from exc
    require(isinstance(value, dict), "fine outline P1 quality contract must be an object")
    required = {
        "chapter_function", "target_emotion_id", "required_deliveries",
        "allowed_expectation_ids", "allowed_hypothesis_ids", "scene_catalog",
    }
    require(required <= set(value), f"fine outline P1 quality contract missing: {', '.join(sorted(required - set(value)))}")
    nonempty_text(value.get("chapter_function"), "P1 chapter_function")
    nonempty_text(value.get("target_emotion_id"), "P1 target_emotion_id")
    for key in ("required_deliveries", "allowed_expectation_ids", "allowed_hypothesis_ids"):
        require(isinstance(value.get(key), list), f"P1 {key} must be a list")
        require(all(isinstance(item, str) and item.strip() for item in value[key]), f"P1 {key} values must be non-empty strings")
    require(value["required_deliveries"], "P1 required_deliveries must not be empty")
    require(value["allowed_expectation_ids"], "P1 allowed_expectation_ids must not be empty")
    require(contract["expectation_id"] in value["allowed_expectation_ids"], "P1 allowed expectations must include the chapter expectation ID")
    require(isinstance(value.get("intentional_ambiguity", False), bool), "P1 intentional_ambiguity must be boolean")
    scene_catalog = value.get("scene_catalog")
    require(isinstance(scene_catalog, list) and scene_catalog, "P1 scene_catalog must be a non-empty list")
    require(
        [row.get("scene_index") for row in scene_catalog if isinstance(row, dict)] == list(range(1, len(scene_catalog) + 1)),
        "P1 scene_catalog indexes must be contiguous from one",
    )
    scene_ids = [safe_component(row.get("scene_id"), "P1 scene_catalog scene_id") for row in scene_catalog]
    require(len(set(scene_ids)) == len(scene_ids), "P1 scene_catalog scene IDs must be distinct")
    plot_numbers: list[int] = []
    table_started = False
    for line in text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            if table_started and plot_numbers:
                break
            continue
        cells = [cell.replace("**", "").replace("`", "").strip() for cell in stripped[1:-1].split("|")]
        if not table_started:
            if len(cells) == 4 and cells[0] in {"#", "序号"}:
                table_started = True
            continue
        if all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        if len(cells) != 4 or not cells[0].isdigit():
            if plot_numbers:
                break
            continue
        plot_numbers.append(int(cells[0]))
    require(plot_numbers == list(range(1, len(plot_numbers) + 1)) and plot_numbers, "P1 fine-outline plot rows must be sequential from one")
    require(
        len(scene_catalog) == len(plot_numbers)
        and scene_ids == [f"scene-{number}" for number in plot_numbers],
        "P1 scene_catalog must exactly match the final fine-outline plot rows",
    )
    contract["p1"] = copy.deepcopy(value)
    return contract


def tree_hash(root: Path) -> str:
    require(root.is_dir(), f"missing directory: {root}")
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def generation_id(seed: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"g-{stamp}-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:10]}"


def revision_paths(root: Path, chapter: int, revision: str) -> tuple[Path, Path]:
    directory = root / "revisions" / f"chapter-{chapter:06d}"
    return directory / f"{revision}.md", directory / f"{revision}.json"


def store_revision(
    root: Path,
    chapter: int,
    source: Path,
    *,
    parent: str | None,
    kind: str,
    finding_ids: list[str] | None = None,
    impact_regions: list[str] | None = None,
    repair_scope: str | None = None,
    author_authorization: str | None = None,
    revision_intent: str | None = None,
    reopen_case_id: str | None = None,
    reopen_arm_id: str | None = None,
    strength_certificate_sha256: str | None = None,
) -> tuple[str, str]:
    data = source.read_bytes()
    require(data.strip(), "candidate body must not be empty")
    revision = sha_bytes(data)
    body, metadata = revision_paths(root, chapter, revision)
    record = {
        "schema": SCHEMA,
        "chapter": chapter,
        "revision": revision,
        "parent_revision": parent,
        "kind": kind,
        "source_name": source.name,
        "finding_ids": finding_ids or [],
        "impact_regions": impact_regions or [],
        "repair_scope": repair_scope,
        "author_authorization": author_authorization,
        "revision_intent": revision_intent,
        "reopen_case_id": reopen_case_id,
        "reopen_arm_id": reopen_arm_id,
        "strength_certificate_sha256": strength_certificate_sha256,
        "created_at": now(),
    }
    if kind == "revision":
        require(parent is not None, "a revision requires an accepted parent revision")
        intent = revision_intent or "defect_repair"
        require(intent in REVISION_INTENTS - {"rollback"}, "staged revision_intent is invalid")
        record["revision_intent"] = intent
        require(bool(record["impact_regions"]), "a revision must name its impact regions")
        require(repair_scope in {"local", "structural", "full"}, "invalid repair scope")
        if intent == "defect_repair":
            require(bool(record["finding_ids"]), "a defect repair must name the finding IDs it repairs")
            require(reopen_case_id is None and reopen_arm_id is None and strength_certificate_sha256 is None, "defect repair cannot bind strength reopen fields")
        else:
            require(not record["finding_ids"], "strength reopen must not fabricate finding IDs")
            safe_component(reopen_case_id, "reopen_case_id")
            safe_component(reopen_arm_id, "reopen_arm_id")
            require(is_sha256(strength_certificate_sha256), "strength reopen must bind the flat certificate SHA-256")
        if repair_scope in {"structural", "full"}:
            require(bool(author_authorization), "structural/full rewrite requires author authorization")
    elif kind == "draft" and revision_intent == "strength_reopen":
        require(parent is None, "reopened draft cannot have an accepted parent")
        require(not record["finding_ids"], "strength reopen must not fabricate finding IDs")
        require(bool(record["impact_regions"]), "strength reopen must name its evidence regions")
        require(repair_scope in {"local", "structural", "full"}, "invalid strength reopen scope")
        safe_component(reopen_case_id, "reopen_case_id")
        safe_component(reopen_arm_id, "reopen_arm_id")
        require(is_sha256(strength_certificate_sha256), "strength reopen must bind the flat certificate SHA-256")
        if repair_scope in {"structural", "full"}:
            require(bool(author_authorization), "structural/full rewrite requires author authorization")
    if body.exists() and metadata.exists():
        require(body.read_bytes() == data, "revision hash collision")
        existing = read_json(metadata, "revision metadata")
        # Creation time is not semantic.  Re-staging the same immutable revision is idempotent.
        for key in set(record) - {"created_at"}:
            require(existing.get(key) == record[key], f"immutable revision metadata differs at {key}")
    elif body.exists():
        require(body.read_bytes() == data, "revision hash collision")
        atomic_json(metadata, record)
    elif metadata.exists():
        existing = read_json(metadata, "revision metadata")
        for key in set(record) - {"created_at"}:
            require(existing.get(key) == record[key], f"immutable revision metadata differs at {key}")
        atomic_bytes(body, data)
    else:
        body.parent.mkdir(parents=True, exist_ok=True)
        atomic_bytes(body, data)
        atomic_json(metadata, record)
    return revision, source.name


def head_record(project: Path) -> dict[str, Any]:
    path = quality_root(project) / "HEAD.json"
    require(path.is_file(), "quality lifecycle is not initialized")
    head = read_json(path, "accepted HEAD")
    generation = safe_component(head.get("generation_id"), "HEAD generation_id")
    manifest_path = quality_root(project) / "generations" / generation / "manifest.json"
    require(manifest_path.is_file(), "HEAD points to a missing generation")
    require(sha_file(manifest_path) == head.get("manifest_sha256"), "HEAD manifest hash mismatch")
    return head


def manifest_for(project: Path, generation: str | None = None) -> dict[str, Any]:
    if generation is None:
        generation = str(head_record(project)["generation_id"])
    generation = safe_component(generation, "generation_id")
    return read_json(quality_root(project) / "generations" / generation / "manifest.json", "generation manifest")


def generation_dir(project: Path, generation: str) -> Path:
    return quality_root(project) / "generations" / safe_component(generation, "generation_id")


def write_certificate_tree(root: Path, certificate: dict[str, Any]) -> None:
    packet = certificate["packet"]
    chapter = packet["chapter"]
    revision = packet["revision"]
    certificate_key = certificate["packet_sha256"]
    stem = f"{revision}-{certificate_key[:12]}.json"
    atomic_json(root / "reviews" / f"chapter-{chapter:06d}" / stem, certificate)
    atomic_json(root / "events" / f"chapter-{chapter:06d}" / stem, packet["posthoc_extraction"])
    for state in packet["reader_evidence"]["cohort"]:
        reader_name = f"chapter-{chapter:06d}-{revision[:12]}-{certificate_key[:12]}.json"
        atomic_json(root / "readers" / state["reader_id"] / reader_name, state)


def create_generation(
    project: Path,
    manifest: dict[str, Any],
    tracking_source: Path,
    *,
    quality_source: Path | None = None,
    certificates: list[dict[str, Any]] | None = None,
) -> Path:
    root = quality_root(project)
    target = root / "generations" / manifest["generation_id"]
    require(not target.exists(), "generation already exists")
    staging = root / "generations" / f".{manifest['generation_id']}.tmp"
    require(not staging.exists(), "stale generation staging directory exists")
    staging.mkdir(parents=True)
    try:
        shutil.copytree(
            tracking_source,
            staging / "tracking",
            ignore=shutil.ignore_patterns(*(path.name for path in TRACKING_RUNTIME_FILES)),
        )
        if quality_source is not None and quality_source.is_dir():
            shutil.copytree(quality_source, staging / "quality")
        else:
            (staging / "quality").mkdir()
        for certificate in certificates or []:
            write_certificate_tree(staging / "quality", certificate)
        manifest["tracking_tree_sha256"] = tree_hash(staging / "tracking")
        manifest["quality_tree_sha256"] = tree_hash(staging / "quality")
        atomic_json(staging / "manifest.json", manifest)
        os.replace(staging, target)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def switch_head(project: Path, manifest: dict[str, Any]) -> None:
    path = generation_dir(project, manifest["generation_id"]) / "manifest.json"
    atomic_json(
        quality_root(project) / "HEAD.json",
        {"schema": SCHEMA, "generation_id": manifest["generation_id"], "manifest_sha256": sha_file(path)},
    )


def default_policy(*, generation: str | None = None) -> dict[str, Any]:
    return {
        "schema": POLICY_SCHEMA,
        "policy_version": "p0-compat-shadow-v2",
        "strength_mode": "SHADOW",
        "reader_measurement_schema": READER_SCHEMA_V3,
        "calibration_id": None,
        "calibration_sha256": None,
        "required_personas": [],
        "thresholds": {
            "early_friction_ratio": 0.15,
            "severe_friction": 3,
            "corroborated_quit_readers": 2,
            "minimum_read_on_intensity": 3,
            "minimum_emotion_intensity": 2,
            "minimum_confidence": 0.5,
        },
        "function_rules": {
            "*": {
                "control_kind": "standard",
                "allowed_deliveries": ["*"],
                "require_delivery_consensus": True,
                "require_emotion_majority": True,
                "require_expectation_consensus": True,
            }
        },
        "reopen_protocol_version": REOPEN_SCHEMA,
        "activated_from_generation": generation,
        "activated_from_chapter": 1,
    }


def validate_policy(value: dict[str, Any], *, require_calibration: bool = False) -> dict[str, Any]:
    require(value.get("schema") == POLICY_SCHEMA, f"quality policy schema must be {POLICY_SCHEMA}")
    safe_component(value.get("policy_version"), "policy_version")
    require(value.get("strength_mode") in STRENGTH_MODES, "quality policy strength_mode must be SHADOW/ENFORCE")
    reader_schema = value.get("reader_measurement_schema")
    require(reader_schema in {READER_SCHEMA_V2, READER_SCHEMA_V3}, "quality policy reader measurement schema is unsupported")
    if value.get("strength_mode") == "ENFORCE":
        require(reader_schema == READER_SCHEMA_V3, f"ENFORCE policy must use {READER_SCHEMA_V3}; v2 remains read-only SHADOW")
    require(value.get("reopen_protocol_version") == REOPEN_SCHEMA, "quality policy reopen protocol mismatch")
    personas = value.get("required_personas")
    require(isinstance(personas, list), "quality policy required_personas must be a list")
    persona_ids: set[str] = set()
    for index, row in enumerate(personas):
        require(isinstance(row, dict), "quality policy persona requirements must be objects")
        persona_id = safe_component(row.get("persona_id"), f"required_personas[{index}].persona_id")
        require(persona_id not in persona_ids, "quality policy persona IDs must be distinct")
        persona_ids.add(persona_id)
        integer(row.get("minimum_independent"), f"required_personas[{index}].minimum_independent", minimum=2)
        profile = row.get("persona_profile")
        require(isinstance(profile, dict), f"required_personas[{index}] requires persona_profile")
        require(profile.get("genre_familiarity") in {"low", "medium", "high"}, "policy persona genre_familiarity is invalid")
        require(profile.get("reading_history") in {"fresh", "sequential", "full_prefix"}, "policy persona reading_history is invalid")
        require(row.get("persona_profile_sha256") == sha_json(profile), "policy persona profile hash mismatch")
        evidence_types = row.get("evidence_types", ["llm_proxy", "human"])
        require(isinstance(evidence_types, list) and evidence_types, "persona evidence_types must be a non-empty list")
        require(set(evidence_types) <= {"llm_proxy", "human"}, "persona evidence_types are invalid")
    thresholds = value.get("thresholds")
    require(isinstance(thresholds, dict), "quality policy thresholds must be an object")
    number(thresholds.get("early_friction_ratio"), "early_friction_ratio", minimum=0, maximum=1)
    integer(thresholds.get("severe_friction"), "severe_friction", minimum=1, maximum=4)
    integer(thresholds.get("corroborated_quit_readers"), "corroborated_quit_readers", minimum=2)
    integer(thresholds.get("minimum_read_on_intensity"), "minimum_read_on_intensity", minimum=1, maximum=5)
    integer(thresholds.get("minimum_emotion_intensity"), "minimum_emotion_intensity", minimum=0, maximum=5)
    number(thresholds.get("minimum_confidence"), "minimum_confidence", minimum=0, maximum=1)
    function_rules = value.get("function_rules")
    require(isinstance(function_rules, dict) and function_rules, "quality policy requires chapter function rules")
    control_kinds = {"standard", "low_pressure", "aftermath", "intentional_ambiguity", "quiet_transition"}
    for function_name, rule in function_rules.items():
        nonempty_text(function_name, "chapter function rule name")
        require(isinstance(rule, dict), f"chapter function rule {function_name} must be an object")
        require(rule.get("control_kind") in control_kinds, f"chapter function rule {function_name} control kind is invalid")
        deliveries = rule.get("allowed_deliveries")
        require(isinstance(deliveries, list) and deliveries and all(isinstance(item, str) and item.strip() for item in deliveries), f"chapter function rule {function_name} requires allowed deliveries")
        for key in ("require_delivery_consensus", "require_emotion_majority", "require_expectation_consensus"):
            require(isinstance(rule.get(key), bool), f"chapter function rule {function_name} requires boolean {key}")
    integer(value.get("activated_from_chapter"), "activated_from_chapter", minimum=1)
    if value.get("activated_from_generation") is not None:
        safe_component(value.get("activated_from_generation"), "activated_from_generation")
    if require_calibration or value["strength_mode"] == "ENFORCE":
        safe_component(value.get("calibration_id"), "calibration_id")
        require(is_sha256(value.get("calibration_sha256")), "ENFORCE policy requires a calibration SHA-256")
        require(personas, "ENFORCE policy requires decision personas")
        require("*" not in function_rules, "ENFORCE policy requires explicit chapter-function rules")
    return copy.deepcopy(value)


def persist_policy_version(project: Path, value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    normalized = validate_policy(value)
    digest = sha_json(normalized)
    root = quality_root(project)
    target = root / "policies" / f"{digest}.json"
    if target.exists():
        require(read_json(target, "immutable quality policy") == normalized, "quality policy hash collision")
    else:
        atomic_json(target, normalized)
    return normalized, digest


def store_policy(project: Path, value: dict[str, Any]) -> tuple[dict[str, Any], str]:
    normalized, digest = persist_policy_version(project, value)
    root = quality_root(project)
    atomic_json(root / "POLICY.json", {"schema": POLICY_SCHEMA, "policy_sha256": digest})
    return normalized, digest


def active_policy(project: Path) -> tuple[dict[str, Any], str]:
    root = quality_root(project)
    pointer = root / "POLICY.json"
    if not pointer.is_file():
        generation = head_record(project).get("generation_id") if (root / "HEAD.json").is_file() else None
        policy = default_policy(generation=generation)
        return policy, sha_json(policy)
    record = read_json(pointer, "quality policy pointer")
    digest = record.get("policy_sha256")
    require(is_sha256(digest), "quality policy pointer hash is invalid")
    path = root / "policies" / f"{digest}.json"
    policy = read_json(path, "active quality policy")
    require(sha_json(policy) == digest, "active quality policy hash mismatch")
    normalized = validate_policy(policy)
    if normalized["strength_mode"] == "ENFORCE":
        calibration_id = safe_component(normalized.get("calibration_id"), "calibration_id")
        calibration_path = root / "calibration" / f"{calibration_id}.json"
        require(calibration_path.is_file(), "active ENFORCE policy calibration is missing")
        calibration = validate_calibration_document(read_json(calibration_path, "active policy calibration"), project)
        require(sha_json(calibration) == normalized.get("calibration_sha256"), "active ENFORCE policy calibration hash mismatch")
    return normalized, str(digest)


def policy_by_hash(project: Path, digest: object) -> tuple[dict[str, Any], str]:
    require(is_sha256(digest), "quality policy hash is invalid")
    path = quality_root(project) / "policies" / f"{digest}.json"
    policy = read_json(path, "versioned quality policy")
    require(sha_json(policy) == digest, "versioned quality policy hash mismatch")
    return validate_policy(policy), str(digest)


def effective_policy(project: Path, chapter: int) -> tuple[dict[str, Any], str]:
    policy, digest = active_policy(project)
    if policy["strength_mode"] == "ENFORCE" and chapter < policy["activated_from_chapter"]:
        compatibility = default_policy(generation=head_record(project).get("generation_id"))
        return persist_policy_version(project, compatibility)
    return policy, digest


def derive_reopen_case_history(project: Path, case_id: object) -> dict[str, Any]:
    identifier = safe_component(case_id, "reopen validation case_id")
    root = quality_root(project) / "reopen-cases" / identifier
    snapshots = []
    for path in (root / "history").glob("*.json"):
        snapshot = read_json(path, "reopen validation case snapshot")
        require(path.stem == sha_json(snapshot), "reopen case history filename/hash mismatch")
        require(snapshot.get("case_id") == identifier, "reopen case history identity mismatch")
        timestamp = parse_utc_timestamp(snapshot.get("updated_at"), "reopen case history updated_at")
        snapshots.append((timestamp, snapshot))
    require(snapshots, "reopen validation case has no lifecycle history")
    snapshots.sort(key=lambda item: item[0])
    levels = {snapshot.get("level") for _, snapshot in snapshots}
    require(len(levels) == 1 and next(iter(levels)) in {"L1", "L2", "L3"}, "reopen validation case level is invalid")
    states: list[str] = []
    for _, snapshot in snapshots:
        state = nonempty_text(snapshot.get("state"), "reopen case state")
        if not states or states[-1] != state:
            states.append(state)
    require(states[0] == "OPEN", "reopen validation history must begin OPEN")
    return {"case_id": identifier, "level": next(iter(levels)), "states": states}


def validate_evidence_bundle(document: dict[str, Any], project: Path | None = None) -> dict[str, Any]:
    require(document.get("schema") == EVIDENCE_BUNDLE_SCHEMA, f"evidence bundle schema must be {EVIDENCE_BUNDLE_SCHEMA}")
    safe_component(document.get("evidence_id"), "evidence_id")
    kind = document.get("kind")
    require(kind in EVIDENCE_KINDS, "evidence bundle kind is invalid")
    source_kind = document.get("source_kind")
    require(source_kind in {"development_original", "held_out_original", "human_blind_import", "accepted_lifecycle", "reference_instrument", "synthetic_fixture", "frozen_study_artifact"}, "evidence source_kind is invalid")
    synthetic = document.get("synthetic")
    require(isinstance(synthetic, bool), "evidence bundle synthetic flag must be boolean")
    require(synthetic is (source_kind == "synthetic_fixture"), "synthetic evidence must be explicitly marked synthetic_fixture")
    parse_utc_timestamp(document.get("collected_at"), "evidence collected_at")
    nonempty_text(document.get("producer_run_id"), "evidence producer_run_id")
    artifact = document.get("artifact")
    require(isinstance(artifact, dict) and artifact, "evidence bundle requires an artifact object")
    require(document.get("artifact_sha256") == sha_json(artifact), "evidence artifact hash mismatch")

    if kind == "story_package":
        require(source_kind in {"development_original", "held_out_original", "reference_instrument", "synthetic_fixture"}, "story package evidence source is invalid")
        safe_component(artifact.get("story_package_id"), "story_package_id")
        chapters = artifact.get("chapters")
        require(isinstance(chapters, list) and [row.get("chapter") for row in chapters if isinstance(row, dict)] == list(range(1, 16)), "story package evidence must bind chapters 1-15")
        for row in chapters:
            require_bound_text_artifact(row, text_key="body", hash_key="revision", label="story package chapter body")
            require_bound_text_artifact(row, text_key="outline", hash_key="outline_sha256", label="story package chapter outline")
        creative_package = artifact.get("creative_package")
        require(isinstance(creative_package, dict) and creative_package, "story package evidence requires the frozen creative package")
        require(artifact.get("creative_package_sha256") == sha_json(creative_package), "story package creative package hash mismatch")
    elif kind == "between_subject_arm":
        require(source_kind == "frozen_study_artifact" and synthetic is False, "between-subject arms must be frozen non-synthetic study artifacts")
        safe_component(artifact.get("study_id"), "between-subject arm study_id")
        study_kind = artifact.get("study_kind")
        require(study_kind in {"revision_appeal", "author_voice_effect"}, "between-subject arm study_kind is invalid")
        safe_component(artifact.get("blind_label"), "between-subject arm blind_label")
        chapters = artifact.get("chapter_artifacts")
        require(isinstance(chapters, list) and len(chapters) == 15, "between-subject arm requires exactly 15 chapter artifacts")
        chapter_numbers = [row.get("chapter") for row in chapters if isinstance(row, dict)]
        require(
            len(chapter_numbers) == 15
            and all(isinstance(chapter, int) and not isinstance(chapter, bool) for chapter in chapter_numbers)
            and chapter_numbers == list(range(chapter_numbers[0], chapter_numbers[0] + 15))
            and chapter_numbers[0] >= 1,
            "between-subject arm chapters must be 15 consecutive positive chapter numbers",
        )
        for row in chapters:
            require_bound_text_artifact(row, text_key="body", hash_key="revision", label="between-subject arm chapter body")
        arm_binding: dict[str, Any] = {
            "chapters": [{"chapter": row["chapter"], "revision": row["revision"]} for row in chapters],
        }
        if study_kind == "author_voice_effect":
            common_conditions = artifact.get("common_conditions")
            require(isinstance(common_conditions, dict) and set(common_conditions) == VOICE_FROZEN_CONDITION_KEYS, "voice arm must freeze plot, model, context, budget, and stop rule")
            require(all(is_sha256(value) for value in common_conditions.values()), "voice arm frozen conditions must be SHA-256 values")
            treatment = artifact.get("treatment")
            require(isinstance(treatment, dict) and set(treatment) == {"voice_enabled", "voice_profile_sha256"}, "voice arm treatment may contain only voice_enabled and voice_profile_sha256")
            require(isinstance(treatment["voice_enabled"], bool), "voice arm voice_enabled must be boolean")
            if treatment["voice_enabled"]:
                require(is_sha256(treatment["voice_profile_sha256"]), "enabled voice treatment requires a voice profile SHA-256")
            else:
                require(treatment["voice_profile_sha256"] is None, "disabled voice treatment cannot carry a voice profile")
            arm_binding.update({"common_conditions": common_conditions, "treatment": treatment})
        else:
            require("common_conditions" not in artifact and "treatment" not in artifact, "revision appeal arms cannot add unregistered treatment fields")
        require(artifact.get("arm_sha256") == sha_json(arm_binding), "between-subject arm hash mismatch")
    elif kind == "human_reader_import":
        require(source_kind in {"human_blind_import", "synthetic_fixture"}, "human reader evidence source is invalid")
        story_ids = artifact.get("story_package_ids")
        require(isinstance(story_ids, list) and story_ids and len(set(story_ids)) == len(story_ids), "human evidence requires distinct story package IDs")
        readers = artifact.get("readers")
        require(isinstance(readers, list) and readers, "human evidence requires reader records")
        reader_ids: set[str] = set()
        for row in readers:
            require(isinstance(row, dict), "human evidence reader records must be objects")
            reader_id = safe_component(row.get("reader_id"), "human evidence reader_id")
            require(reader_id not in reader_ids, "human evidence reader IDs must be distinct")
            reader_ids.add(reader_id)
            require(row.get("evidence_type") == "human", "human evidence records must declare evidence_type=human")
            raw_observations = row.get("raw_observations")
            require(isinstance(raw_observations, dict) and raw_observations, "human evidence record requires imported raw observations")
            require(row.get("raw_observation_sha256") == sha_json(raw_observations), "human evidence record raw observation hash mismatch")
            nonempty_text(row.get("blind_code"), "human evidence blind_code")
            safe_component(row.get("persona_id"), "human evidence persona_id")
            profile = row.get("persona_profile")
            require(isinstance(profile, dict), "human evidence reader requires persona_profile")
            require(profile.get("genre_familiarity") in {"low", "medium", "high"} and profile.get("reading_history") in {"fresh", "sequential", "full_prefix"}, "human evidence persona profile is invalid")
            require(row.get("persona_profile_sha256") == sha_json(profile), "human evidence persona profile hash mismatch")
        require(artifact.get("reader_count") == len(readers), "human evidence reader_count mismatch")
        calibration_observations = artifact.get("calibration_observations")
        if calibration_observations is not None:
            require(
                isinstance(calibration_observations, list)
                and [row.get("chapter") for row in calibration_observations if isinstance(row, dict)] == list(range(1, 16)),
                "human calibration observations must cover chapters 1-15",
            )
            imported_hashes = {
                sha_json(measurement)
                for reader in readers
                for measurements in reader["raw_observations"].get("chapter_measurements", {}).values()
                if isinstance(measurements, list)
                for measurement in measurements
                if isinstance(measurement, dict)
            }
            for reader in readers:
                chapter_measurements = reader["raw_observations"].get("chapter_measurements")
                require(isinstance(chapter_measurements, dict) and chapter_measurements, "calibration human import requires actual chapter measurements")
                for story_id, measurements in chapter_measurements.items():
                    require(story_id in story_ids, "calibration human measurement cites an unknown story package")
                    require(isinstance(measurements, list) and [row.get("chapter") for row in measurements if isinstance(row, dict)] == list(range(1, 16)), "calibration human measurements must cover chapters 1-15")
            for row in calibration_observations:
                hashes = row.get("reader_measurement_sha256s")
                require(isinstance(hashes, list) and hashes and all(is_sha256(value) for value in hashes), "calibration observation requires reader measurement hashes")
                require(set(hashes) <= imported_hashes, "calibration observation cites a measurement outside the human import")
    elif kind == "misfire_control":
        require(source_kind in {"human_blind_import", "synthetic_fixture"}, "misfire control source is invalid")
        require(artifact.get("control_kind") in {"low_pressure", "aftermath", "intentional_ambiguity", "quiet_transition"}, "misfire control kind is invalid")
        safe_component(artifact.get("story_package_id"), "misfire control story_package_id")
        require(is_sha256(artifact.get("reader_evidence_bundle_sha256")), "misfire control requires a human reader evidence bundle")
        reader_results = artifact.get("reader_results")
        require(isinstance(reader_results, list) and len(reader_results) >= 2, "misfire control requires at least two reader results")
        result_ids = [safe_component(row.get("reader_id") if isinstance(row, dict) else None, "misfire control reader_id") for row in reader_results]
        require(len(set(result_ids)) == len(result_ids), "misfire control reader results must be distinct")
        for row in reader_results:
            result = row.get("result")
            require(isinstance(result, dict), "misfire control result must be an object")
            require(isinstance(result.get("function_delivered"), bool) and isinstance(result.get("false_positive_detected"), bool), "misfire control result booleans are invalid")
            require(row.get("result_sha256") == sha_json(result), "misfire control result hash mismatch")
        derived_status = "PASS" if all(row["result"]["function_delivered"] and not row["result"]["false_positive_detected"] for row in reader_results) else "FAIL"
        require(artifact.get("status") == derived_status, "misfire control status is not derived from reader results")
        nonempty_text(artifact.get("function_rule_name"), "misfire control function_rule_name")
        if project is not None:
            human = evidence_by_hash(project, artifact["reader_evidence_bundle_sha256"])
            require(human["kind"] == "human_reader_import" and human["source_kind"] == source_kind, "misfire control reader bundle source mismatch")
            require(artifact["story_package_id"] in human["artifact"]["story_package_ids"], "misfire control reader bundle story mismatch")
            imported = {row["reader_id"]: row for row in human["artifact"]["readers"]}
            for row in reader_results:
                require(row["reader_id"] in imported, "misfire control cites a reader outside its human import")
                controls = imported[row["reader_id"]]["raw_observations"].get("control_results", {})
                require(controls.get(artifact["control_kind"]) == row["result"], "misfire control result differs from the imported raw observation")
    elif kind == "reopen_validation":
        require(source_kind in {"accepted_lifecycle", "synthetic_fixture"}, "reopen validation source is invalid")
        levels = artifact.get("levels_validated")
        require(isinstance(levels, list) and set(levels) == {"L1", "L2", "L3"}, "reopen validation must cover L1/L2/L3")
        case_histories = artifact.get("case_histories")
        require(isinstance(case_histories, list) and len(case_histories) >= 3, "reopen validation requires complete case history artifacts")
        history_levels = set()
        for history in case_histories:
            require(isinstance(history, dict), "reopen validation histories must be objects")
            safe_component(history.get("case_id"), "reopen validation case_id")
            require(history.get("level") in {"L1", "L2", "L3"}, "reopen validation history level is invalid")
            history_levels.add(history["level"])
            states = history.get("states")
            require(isinstance(states, list) and states and states[0] == "OPEN", "reopen validation history must begin OPEN")
        require(history_levels == {"L1", "L2", "L3"}, "reopen validation histories do not cover L1/L2/L3")
        histories = artifact.get("case_history_sha256s")
        require(histories == [sha_json(history) for history in case_histories] and len(set(histories)) == len(histories), "reopen validation case history hashes are not bound to their artifacts")
        if source_kind == "accepted_lifecycle":
            require(project is not None, "accepted reopen validation must resolve the project CASE tree")
            actual_histories = [derive_reopen_case_history(project, history["case_id"]) for history in case_histories]
            require(actual_histories == case_histories, "reopen validation histories differ from the project CASE tree")
        pass_exit = any("SELECTED" in history["states"] for history in case_histories)
        all_flat = any("L2_PROPOSAL_REQUIRED" in history["states"] or "L3_PROPOSAL_REQUIRED" in history["states"] for history in case_histories)
        require(artifact.get("pass_exit_observed") is pass_exit and artifact.get("all_flat_escalation_observed") is all_flat and pass_exit and all_flat, "reopen validation must derive both PASS exit and all-flat escalation")
    elif kind == "threshold_derivation":
        require(source_kind in {"accepted_lifecycle", "synthetic_fixture"}, "threshold derivation source is invalid")
        inputs = artifact.get("input_evidence_sha256s")
        require(isinstance(inputs, list) and inputs and len(set(inputs)) == len(inputs) and all(is_sha256(value) for value in inputs), "threshold derivation requires distinct evidence hashes")
        nonempty_text(artifact.get("method"), "threshold derivation method")
        thresholds = artifact.get("thresholds")
        function_rules = artifact.get("function_rules")
        golden_budget = artifact.get("golden_three_budget")
        require(isinstance(thresholds, dict) and isinstance(function_rules, dict) and function_rules, "threshold derivation requires thresholds and function rules")
        require(isinstance(golden_budget, list) and [row.get("chapter") for row in golden_budget if isinstance(row, dict)] == [1, 2, 3], "threshold derivation requires a chapter 1-3 golden budget")
        for row in golden_budget:
            integer(row.get("outline_variants"), "derived golden outline_variants", minimum=2, maximum=3)
            integer(row.get("prose_variants_per_outline"), "derived golden prose_variants_per_outline", minimum=1, maximum=3)
            nonempty_text(row.get("stop_rule"), "derived golden stop_rule")
        require(artifact.get("input_fingerprint") == sha_json(inputs), "threshold derivation input fingerprint mismatch")
        require(artifact.get("output_fingerprint") == sha_json({"thresholds": thresholds, "function_rules": function_rules, "golden_three_budget": golden_budget}), "threshold derivation output fingerprint mismatch")
    elif kind == "workflow_run":
        require(source_kind in {"accepted_lifecycle", "synthetic_fixture"}, "workflow run source is invalid")
        safe_component(artifact.get("story_package_id"), "workflow run story_package_id")
        require(artifact.get("treatment") in {"P0", "P1"}, "workflow run treatment is invalid")
        nonempty_text(artifact.get("workflow_version"), "workflow run version")
        safe_component(artifact.get("run_id"), "workflow run_id")
        parse_utc_timestamp(artifact.get("started_at"), "workflow run started_at")
        parse_utc_timestamp(artifact.get("completed_at"), "workflow run completed_at")
        require(is_sha256(artifact.get("story_package_evidence_sha256")), "workflow run requires story package evidence")
        outputs = artifact.get("outputs")
        require(isinstance(outputs, list) and [row.get("chapter") for row in outputs if isinstance(row, dict)] == list(range(1, 16)), "workflow run outputs must cover chapters 1-15")
        require(all(is_sha256(row.get("revision")) for row in outputs), "workflow run outputs require revision hashes")
        budgets = artifact.get("variant_budget")
        require(isinstance(budgets, dict) and set(budgets) == {"P0", "P1"}, "workflow run variant budget is invalid")
        shared_max_visible_chars = integer(artifact.get("shared_max_visible_chars"), "workflow shared_max_visible_chars", minimum=500)
        require(is_sha256(artifact.get("common_control_sha256")), "workflow run requires a frozen common-control fingerprint")
        common_provenance = artifact.get("common_provenance")
        require(isinstance(common_provenance, dict) and set(common_provenance) == {
            "creative_package_sha256", "author_identity_sha256", "writer_identity_sha256", "model_identity_sha256", "context_sha256",
        }, "workflow run common provenance is invalid")
        require(all(is_sha256(value) for value in common_provenance.values()), "workflow run common provenance must contain SHA-256 values")
        require(is_sha256(artifact.get("treatment_budget_sha256")), "workflow run requires a frozen treatment-budget fingerprint")
        outline_sha256s = artifact.get("outline_sha256s")
        require(isinstance(outline_sha256s, list) and len(outline_sha256s) == 15 and all(is_sha256(value) for value in outline_sha256s), "workflow run requires 15 frozen outline hashes")
        nonempty_text(artifact.get("stop_rule"), "workflow run stop_rule")
        require(artifact.get("output_fingerprint") == sha_json(outputs), "workflow run output fingerprint mismatch")
        if project is not None:
            package = evidence_by_hash(project, artifact["story_package_evidence_sha256"])
            require(package["kind"] == "story_package" and package["artifact"]["story_package_id"] == artifact["story_package_id"], "workflow run story package evidence mismatch")
        if source_kind == "accepted_lifecycle":
            require(project is not None, "accepted workflow run must resolve its lifecycle project")
            treatment = artifact["treatment"]
            run_ids = artifact.get("treatment_run_ids")
            require(isinstance(run_ids, list) and len(run_ids) == 15 and len(set(run_ids)) == 15, "accepted workflow run requires 15 distinct treatment start boundaries")
            runs = [load_treatment_run(project, run_id, require_closed=True) for run_id in run_ids]
            require([run["open"]["chapter"] for run in runs] == list(range(1, 16)), "workflow treatment runs must cover chapters 1-15 in order")
            require(all(run["open"]["treatment"] == treatment for run in runs), "workflow treatment runs differ from the declared treatment")
            derived_outputs = [
                {"chapter": run["open"]["chapter"], "revision": run["close"]["selected_body_sha256"]}
                for run in runs
            ]
            require(outputs == derived_outputs, "workflow outputs differ from closed treatment runs")
            opens = [run["open"] for run in runs]
            require(all(opened["treatment_version"] == artifact["workflow_version"] for opened in opens), "workflow version differs from treatment start boundaries")
            require(all(opened["common_base"]["story_package_sha256"] == package["artifact_sha256"] for opened in opens), "workflow story package differs from treatment start boundaries")
            derived_outlines = [opened["outline_sha256"] for opened in opens]
            require(outline_sha256s == derived_outlines, "workflow outline hashes differ from treatment start boundaries")
            control_rows = [
                {
                    "chapter": opened["chapter"],
                    "reference_sha256": opened["common_base"]["reference_sha256"],
                    "agent_sha256": opened["common_base"]["agent_sha256"],
                    "model_sha256": opened["common_base"]["model_sha256"],
                    "context_sha256": opened["common_base"]["context_sha256"],
                    "story_package_sha256": opened["common_base"]["story_package_sha256"],
                    "creative_package_sha256": opened["common_base"]["creative_package_sha256"],
                    "author_identity_sha256": opened["common_base"]["author_identity_sha256"],
                    "writer_identity_sha256": opened["common_base"]["writer_identity_sha256"],
                    "outline_sha256": opened["outline_sha256"],
                    "max_visible_chars": opened["budget"]["max_visible_chars"],
                }
                for opened in opens
            ]
            require(artifact["common_control_sha256"] == sha_json(control_rows), "workflow common-control fingerprint is not derived from treatment starts")
            derived_common = {
                "creative_package_sha256": opens[0]["common_base"]["creative_package_sha256"],
                "author_identity_sha256": opens[0]["common_base"]["author_identity_sha256"],
                "writer_identity_sha256": opens[0]["common_base"]["writer_identity_sha256"],
                "model_identity_sha256": opens[0]["common_base"]["model_sha256"],
                "context_sha256": sha_json([opened["common_base"]["context_sha256"] for opened in opens]),
            }
            require(all({opened["common_base"][key] for opened in opens} == {opens[0]["common_base"][key]} for key in ("creative_package_sha256", "author_identity_sha256", "writer_identity_sha256", "model_sha256")), "workflow static common provenance changed between chapters")
            require(common_provenance == derived_common, "workflow common provenance is not derived from treatment starts")
            treatment_budgets = [opened["budget"] for opened in opens]
            require(all(budget == treatment_budgets[0] for budget in treatment_budgets), "workflow treatment budget changed between chapters")
            require(artifact["treatment_budget_sha256"] == sha_json(treatment_budgets[0]), "workflow treatment-budget fingerprint mismatch")
            require(shared_max_visible_chars == treatment_budgets[0]["max_visible_chars"], "workflow shared visible-character budget differs from treatment starts")
            actual_variant_budget = treatment_budgets[0]["creative_attempts"] if treatment == "P0" else treatment_budgets[0]["pass_a_attempts"] + treatment_budgets[0]["pass_b_attempts"]
            require(budgets[treatment] == actual_variant_budget, "workflow variant budget differs from treatment starts")
            accepted_generation_id = safe_component(artifact.get("accepted_generation_id"), "workflow accepted_generation_id")
            accepted_manifest_path = generation_dir(project, accepted_generation_id) / "manifest.json"
            require(accepted_manifest_path.is_file(), "workflow accepted generation is missing")
            require(artifact.get("accepted_manifest_sha256") == sha_file(accepted_manifest_path), "workflow accepted manifest hash mismatch")
            head = head_record(project)
            require(head["generation_id"] == accepted_generation_id and head["manifest_sha256"] == artifact["accepted_manifest_sha256"], "workflow receipt must bind the current final accepted HEAD")
            accepted = manifest_for(project, accepted_generation_id)
            accepted_rows = []
            for chapter, run in enumerate(runs, 1):
                chapter_entry = accepted.get("chapters", {}).get(str(chapter))
                require(isinstance(chapter_entry, dict), "workflow accepted generation lacks a chapter 1-15 output")
                provenance = chapter_entry.get("treatment_provenance")
                require(isinstance(provenance, dict), "workflow accepted chapter lacks immutable treatment provenance")
                require(provenance == {
                    "treatment": treatment,
                    "run_id": run["open"]["run_id"],
                    "start_boundary_sha256": run["open"]["start_boundary_sha256"],
                    "close_boundary_sha256": run["close"]["close_boundary_sha256"],
                }, "workflow accepted chapter treatment provenance mismatch")
                require(chapter_entry.get("revision") == run["close"]["selected_body_sha256"], "workflow accepted chapter is not the closed treatment winner")
                accepted_rows.append({"chapter": chapter, "revision": chapter_entry["revision"]})
            require(outputs == accepted_rows, "workflow outputs differ from the final accepted generation")
            require(all(run["open"]["stop_rule"] == artifact["stop_rule"] for run in runs), "workflow stop rule differs from treatment start boundaries")
            package_rows = package["artifact"]["chapters"]
            require([row["outline_sha256"] for row in package_rows] == [opened["outline_artifact_sha256"] for opened in opens], "workflow outlines differ from the frozen story package")
            require(package["artifact"]["creative_package_sha256"] == common_provenance["creative_package_sha256"], "workflow creative package differs from the frozen story package")
            started = min(parse_utc_timestamp(run["open"]["received_at"], "treatment run received_at") for run in runs)
            completed = max(parse_utc_timestamp(run["close"]["received_at"], "treatment close received_at") for run in runs)
            require(parse_utc_timestamp(artifact["started_at"], "workflow run started_at") == started, "workflow started_at is not derived from treatment boundaries")
            require(parse_utc_timestamp(artifact["completed_at"], "workflow run completed_at") == completed, "workflow completed_at is not derived from treatment boundaries")
    return copy.deepcopy(document)


def record_evidence_bundle(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    require(check(project)["status"] in {"pass", "replay_required"}, "quality project must be internally consistent")
    document = validate_evidence_bundle(read_json(input_path, "quality evidence bundle"), project)
    digest = sha_json(document)
    target = quality_root(project) / "evidence" / f"{digest}.json"
    if target.exists():
        record = evidence_record_by_hash(project, digest)
        require(record["evidence"] == document, "evidence bundle hash collision")
    else:
        record = {
            "schema": EVIDENCE_RECORD_SCHEMA,
            "evidence_sha256": digest,
            "recorded_by_lifecycle_at": now(),
            "evidence": document,
        }
        atomic_json(target, record)
    return {
        "schema": SCHEMA,
        "status": "evidence_recorded",
        "evidence_id": document["evidence_id"],
        "evidence_sha256": digest,
        "recorded_by_lifecycle_at": record["recorded_by_lifecycle_at"],
        "kind": document["kind"],
        "synthetic": document["synthetic"],
    }


def evidence_record_by_hash(project: Path, digest: object) -> dict[str, Any]:
    require(is_sha256(digest), "evidence bundle SHA-256 is invalid")
    path = quality_root(project) / "evidence" / f"{digest}.json"
    record = read_json(path, "recorded quality evidence")
    require(record.get("schema") == EVIDENCE_RECORD_SCHEMA, "quality evidence record schema mismatch")
    require(record.get("evidence_sha256") == digest, "quality evidence record pointer mismatch")
    parse_utc_timestamp(record.get("recorded_by_lifecycle_at"), "quality evidence lifecycle receipt")
    require(isinstance(record.get("evidence"), dict), "quality evidence record lacks its bundle")
    document = validate_evidence_bundle(record["evidence"], project)
    require(sha_json(document) == digest, "recorded evidence bundle hash mismatch")
    return {**record, "evidence": document}


def evidence_by_hash(project: Path, digest: object) -> dict[str, Any]:
    return evidence_record_by_hash(project, digest)["evidence"]


def configure_policy(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    require(check(project)["status"] in {"pass", "replay_required"}, "quality project must be internally consistent")
    policy = read_json(input_path, "quality policy")
    policy["activated_from_generation"] = head_record(project)["generation_id"]
    if policy.get("strength_mode") == "ENFORCE":
        validate_policy(policy, require_calibration=True)
        calibration_id = safe_component(policy.get("calibration_id"), "calibration_id")
        calibration_path = quality_root(project) / "calibration" / f"{calibration_id}.json"
        calibration = validate_calibration_document(read_json(calibration_path, "held-out calibration"), project)
        require(sha_json(calibration) == policy.get("calibration_sha256"), "policy calibration hash mismatch")
        require(calibration.get("purpose") == "held_out_validation", "production ENFORCE requires held-out calibration")
        require(calibration.get("controls_passed") is True and calibration.get("human_validation") is True, "production ENFORCE requires passed controls and human validation")
        require(calibration.get("minimum_reopen_loop_validated") is True, "production ENFORCE requires a validated L1/L2/L3 exit path")
        require(policy.get("reader_measurement_schema") == calibration.get("reader_measurement_schema") == READER_SCHEMA_V3, "ENFORCE policy/calibration must use reader evidence v3")
        require(policy.get("thresholds") == calibration.get("thresholds"), "ENFORCE policy thresholds must equal the held-out calibration")
        require(policy.get("function_rules") == calibration.get("function_rules"), "ENFORCE chapter-function rules must equal the held-out calibration")
        require(policy.get("required_personas") == calibration.get("required_personas"), "ENFORCE personas must equal the held-out calibration")
        last_chapter = max((int(key) for key in manifest_for(project).get("chapters", {})), default=0)
        require(policy.get("activated_from_chapter") >= last_chapter + 1, "ENFORCE must activate at or after the next unwritten chapter")
    normalized, digest = store_policy(project, policy)
    return {"schema": SCHEMA, "status": "policy_configured", "policy_sha256": digest, "policy": normalized}


THRESHOLD_METRICS = {
    "early_friction_ratio": ("observed_first_friction_ratio", "visible_ratio<=threshold", False, 0, 1),
    "severe_friction": ("observed_friction_severity", "severity>=threshold", True, 1, 4),
    "minimum_read_on_intensity": ("observed_read_on_intensity", "intensity>=threshold", True, 1, 5),
    "minimum_emotion_intensity": ("observed_emotion_intensity", "intensity>=threshold", True, 0, 5),
    "minimum_confidence": ("observed_confidence", "confidence>=threshold", False, 0, 1),
}


def linear_quantile(values: list[float], quantile: float) -> float:
    require(values, "quantile requires observations")
    require(0 <= quantile <= 1, "quantile must be within 0..1")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def validate_threshold_spec(value: object) -> dict[str, Any]:
    require(isinstance(value, dict), "threshold_spec must be an object")
    require(value.get("algorithm_version") == "directional-reader-story-quantiles-v1", "threshold algorithm version is unsupported")
    require(value.get("aggregation_unit") == "reader_x_story", "threshold aggregation unit must be reader_x_story")
    require(value.get("story_weighting") == "equal", "threshold story weighting must be equal")
    require(value.get("interpolation") == "linear", "threshold interpolation must be linear")
    require(value.get("missing_rule") == "natural-quit-preserved-no-imputation", "threshold missing/quit rule is invalid")
    metrics = value.get("metrics")
    require(isinstance(metrics, dict) and set(metrics) == set(THRESHOLD_METRICS), "threshold metric registry is incomplete")
    for name, (source, comparison, integer_output, _, _) in THRESHOLD_METRICS.items():
        row = metrics[name]
        require(isinstance(row, dict), f"threshold metric {name} must be an object")
        require(row.get("source") == source and row.get("comparison") == comparison, f"threshold metric {name} direction/source mismatch")
        number(row.get("quantile"), f"threshold metric {name} quantile", minimum=0, maximum=1)
        require(row.get("rounding") == ("nearest" if integer_output else "six_decimals"), f"threshold metric {name} rounding is invalid")
    return copy.deepcopy(value)


def derive_thresholds_from_human_import(
    human_artifact: dict[str, Any],
    corroborated_readers: int,
    threshold_spec: dict[str, Any],
) -> dict[str, Any]:
    spec = validate_threshold_spec(threshold_spec)
    per_story: dict[str, dict[str, list[float]]] = {}
    for reader in human_artifact["readers"]:
        chapter_measurements = reader["raw_observations"].get("chapter_measurements", {})
        require(isinstance(chapter_measurements, dict), "threshold reader measurements must be grouped by story")
        for story_id, rows in chapter_measurements.items():
            safe_component(story_id, "threshold story_package_id")
            require(isinstance(rows, list) and rows, "threshold reader/story cell has no chapter observations")
            story = per_story.setdefault(story_id, {name: [] for name in THRESHOLD_METRICS})
            for name, (source, _, _, minimum, maximum) in THRESHOLD_METRICS.items():
                values = [number(row.get(source), f"calibration {source}", minimum=minimum, maximum=maximum) for row in rows if isinstance(row, dict)]
                require(len(values) == len(rows), f"calibration {source} is missing from a reader/story chapter")
                # Chapters from one reader/story are repeated observations, not
                # independent samples.  Collapse them before any quantile.
                story[name].append(sum(values) / len(values))
    require(per_story, "threshold derivation has no imported reader/story measurements")
    thresholds: dict[str, Any] = {"corroborated_quit_readers": corroborated_readers}
    for name, (_, _, integer_output, _, _) in THRESHOLD_METRICS.items():
        quantile = float(spec["metrics"][name]["quantile"])
        story_estimates = [linear_quantile(values[name], quantile) for values in per_story.values()]
        equal_story_value = sum(story_estimates) / len(story_estimates)
        thresholds[name] = int(round(equal_story_value)) if integer_output else round(equal_story_value, 6)
    return thresholds


def calibration_by_hash(project: Path, digest: object) -> dict[str, Any]:
    require(is_sha256(digest), "calibration reference must be SHA-256")
    matches = []
    for path in (quality_root(project) / "calibration").glob("*.json"):
        document = read_json(path, "recorded calibration")
        if sha_json(document) == digest:
            matches.append(document)
    require(len(matches) == 1, "referenced calibration is absent or ambiguous")
    return matches[0]


def validate_calibration_document(document: dict[str, Any], project: Path | None = None) -> dict[str, Any]:
    require(document.get("schema") == CALIBRATION_SCHEMA, f"calibration schema must be {CALIBRATION_SCHEMA}")
    safe_component(document.get("calibration_id"), "calibration_id")
    purpose = document.get("purpose")
    require(purpose in CALIBRATION_PURPOSES, "calibration purpose is invalid")
    chapters = document.get("chapters")
    require(isinstance(chapters, list) and chapters == list(range(1, 16)), "calibration must cover sequential chapters 1-15")
    reader_schema = document.get("reader_measurement_schema")
    require(reader_schema in {READER_SCHEMA_V2, READER_SCHEMA_V3}, "calibration reader evidence schema is unsupported")
    if reader_schema == READER_SCHEMA_V2:
        require(purpose == "reference_instrument" and document.get("production_thresholds") is False, "reader evidence v2 is historical SHADOW input only")
        threshold_spec = None
    else:
        threshold_spec = validate_threshold_spec(document.get("threshold_spec"))
    story_packages = document.get("story_packages")
    require(isinstance(story_packages, list) and story_packages, "calibration requires story packages")
    package_ids = [safe_component(row.get("story_package_id") if isinstance(row, dict) else None, "story_package_id") for row in story_packages]
    require(len(set(package_ids)) == len(package_ids), "calibration story packages must be distinct")
    if purpose == "reference_instrument":
        require(document.get("temporary_project") is True and document.get("real_book_untouched") is True, "reference calibration must run in a temporary project")
        require(document.get("causal_baseline") is False and document.get("production_thresholds") is False, "reference calibration is descriptive only")
    if purpose == "development_thresholds":
        require(project is not None, "development calibration must resolve recorded evidence from its quality project")
        require(len(story_packages) >= 2, "development thresholds require multiple independent story packages")
        require(document.get("held_out") is False, "development thresholds cannot claim held-out status")
    if purpose == "held_out_validation":
        require(project is not None, "held-out calibration must resolve recorded evidence from its quality project")
        require(len(story_packages) >= 2, "held-out validation requires multiple independent story packages")
        require(document.get("held_out") is True, "held-out calibration must declare held_out=true")
        require(document.get("human_validation") is True, "held-out calibration requires human validation")
        require(integer(document.get("human_reader_count"), "human_reader_count", minimum=4) >= 4, "held-out calibration needs human readers")
        controls = document.get("misfire_controls")
        require(isinstance(controls, list), "held-out calibration requires misfire controls")
        required_controls = {"low_pressure", "aftermath", "intentional_ambiguity", "quiet_transition"}
        require(required_controls <= set(controls), "held-out calibration lacks low-intensity/multiple-reading controls")
        require(document.get("controls_passed") is True, "held-out misfire controls did not pass")
        require(document.get("minimum_reopen_loop_validated") is True, "held-out calibration did not validate the minimum reopen loop")
        development = calibration_by_hash(project, document.get("development_calibration_sha256"))
        require(development.get("purpose") == "development_thresholds", "held-out thresholds must come from a development calibration")
        require(document.get("thresholds") == development.get("thresholds"), "held-out validation cannot retune development thresholds")
        require(document.get("threshold_spec") == development.get("threshold_spec"), "held-out validation threshold algorithm differs from development")
        require(document.get("function_rules") == development.get("function_rules"), "held-out validation function rules differ from development")
        require(document.get("required_personas") == development.get("required_personas"), "held-out validation personas differ from development")
        require(document.get("golden_three_budget") == development.get("golden_three_budget"), "held-out validation budget differs from development")
    thresholds = document.get("thresholds")
    require(isinstance(thresholds, dict), "calibration thresholds must be an object")
    for key in ("early_friction_ratio", "minimum_confidence"):
        number(thresholds.get(key), f"calibration {key}", minimum=0, maximum=1)
    for key, maximum in (("severe_friction", 4), ("minimum_read_on_intensity", 5), ("minimum_emotion_intensity", 5)):
        integer(thresholds.get(key), f"calibration {key}", minimum=0, maximum=maximum)
    integer(thresholds.get("corroborated_quit_readers"), "calibration corroborated_quit_readers", minimum=2)
    function_rules = document.get("function_rules")
    required_personas = document.get("required_personas")
    if purpose in {"development_thresholds", "held_out_validation"}:
        require(isinstance(required_personas, list) and required_personas, "calibrated thresholds require persona requirements")
    probe_policy = default_policy()
    probe_policy.update({"reader_measurement_schema": reader_schema, "thresholds": thresholds, "function_rules": function_rules, "required_personas": required_personas or []})
    validate_policy(probe_policy)
    observations = document.get("observations")
    require(isinstance(observations, list) and observations, "calibration observations must be non-empty")
    require(all(isinstance(row, dict) and row.get("chapter") in range(1, 16) for row in observations), "calibration observations must bind chapters 1-15")
    require({row["chapter"] for row in observations} == set(range(1, 16)), "calibration observations must cover every chapter 1-15")
    if purpose == "development_thresholds":
        assert project is not None and threshold_spec is not None
        evidence = document.get("evidence")
        require(isinstance(evidence, dict), "development calibration requires recorded evidence references")
        package_hashes = evidence.get("story_package_sha256s")
        require(isinstance(package_hashes, list) and len(package_hashes) >= 2 and len(set(package_hashes)) == len(package_hashes), "development calibration requires distinct story packages")
        packages = [evidence_by_hash(project, digest) for digest in package_hashes]
        require(all(row["kind"] == "story_package" and row["source_kind"] == "development_original" and row["synthetic"] is False for row in packages), "development story packages must be recorded non-synthetic originals")
        require([row["artifact"]["story_package_id"] for row in packages] == package_ids, "development package IDs do not match recorded evidence")
        human_hash = evidence.get("human_reader_import_sha256")
        human = evidence_by_hash(project, human_hash)
        require(human["kind"] == "human_reader_import" and human["source_kind"] == "human_blind_import" and human["synthetic"] is False, "development calibration requires recorded human observations")
        require(set(human["artifact"]["story_package_ids"]) == set(package_ids), "development human evidence package mismatch")
        require(document.get("observations") == human["artifact"].get("calibration_observations"), "development observations differ from the immutable human import")
        derived = derive_thresholds_from_human_import(
            human["artifact"],
            max(int(requirement["minimum_independent"]) for requirement in required_personas),
            threshold_spec,
        )
        require(document.get("thresholds") == derived, "development thresholds are not derived from reader/story aggregates")
        evidence_input = {"story_package_sha256s": package_hashes, "human_reader_import_sha256": human_hash}
        require(evidence.get("input_fingerprint") == sha_json(evidence_input), "development evidence fingerprint mismatch")
    if purpose == "held_out_validation":
        assert project is not None
        evidence = document.get("evidence")
        require(isinstance(evidence, dict), "held-out calibration requires recorded evidence references")
        package_hashes = evidence.get("story_package_sha256s")
        require(isinstance(package_hashes, list) and len(package_hashes) >= 2 and len(set(package_hashes)) == len(package_hashes), "held-out calibration requires distinct story package evidence")
        packages = [evidence_by_hash(project, digest) for digest in package_hashes]
        require(all(row["kind"] == "story_package" and row["source_kind"] == "held_out_original" and row["synthetic"] is False for row in packages), "production calibration story packages must be non-synthetic held-out originals")
        recorded_ids = [row["artifact"]["story_package_id"] for row in packages]
        require(recorded_ids == package_ids, "calibration story package IDs do not match recorded artifacts")

        human_hash = evidence.get("human_reader_import_sha256")
        human = evidence_by_hash(project, human_hash)
        require(human["kind"] == "human_reader_import" and human["source_kind"] == "human_blind_import" and human["synthetic"] is False, "production calibration requires a non-synthetic human reader import")
        require(set(human["artifact"]["story_package_ids"]) == set(package_ids), "human evidence story packages do not match calibration packages")
        development_evidence = development.get("evidence")
        require(isinstance(development_evidence, dict), "held-out calibration cannot resolve development evidence")
        development_packages = [evidence_by_hash(project, digest) for digest in development_evidence.get("story_package_sha256s", [])]
        require(development_packages, "held-out calibration cannot resolve development story packages")
        development_package_ids = {row["artifact"]["story_package_id"] for row in development_packages}
        require(development_package_ids.isdisjoint(package_ids), "held-out calibration reuses a development story package ID")
        development_creative = {row["artifact"]["creative_package_sha256"] for row in development_packages}
        heldout_creative = {row["artifact"]["creative_package_sha256"] for row in packages}
        require(development_creative.isdisjoint(heldout_creative), "held-out calibration reuses a development creative package")
        development_content = {
            digest
            for row in development_packages
            for chapter in row["artifact"]["chapters"]
            for digest in (chapter["revision"], chapter["outline_sha256"])
        }
        heldout_content = {
            digest
            for row in packages
            for chapter in row["artifact"]["chapters"]
            for digest in (chapter["revision"], chapter["outline_sha256"])
        }
        require(development_content.isdisjoint(heldout_content), "held-out calibration reuses development body or outline content")
        development_human = evidence_by_hash(project, development_evidence.get("human_reader_import_sha256"))
        development_readers = development_human["artifact"]["readers"]
        heldout_readers = human["artifact"]["readers"]
        for key in ("reader_id", "blind_code", "raw_observation_sha256"):
            require({row[key] for row in development_readers}.isdisjoint({row[key] for row in heldout_readers}), f"held-out calibration reuses development participant evidence: {key}")
        require(document.get("human_reader_count") == human["artifact"]["reader_count"], "calibration human reader count is not derived from imported evidence")
        require(document.get("observations") == human["artifact"].get("calibration_observations"), "calibration observations are not the immutable human import observations")
        persona_counts: dict[tuple[str, str], int] = {}
        for reader in human["artifact"]["readers"]:
            key = (reader["persona_id"], reader["persona_profile_sha256"])
            persona_counts[key] = persona_counts.get(key, 0) + 1
        for requirement in required_personas:
            key = (requirement["persona_id"], requirement["persona_profile_sha256"])
            require(persona_counts.get(key, 0) >= requirement["minimum_independent"], f"calibration lacks independent human evidence for persona {requirement['persona_id']}")
        control_hashes = evidence.get("misfire_control_sha256s")
        require(isinstance(control_hashes, dict) and set(control_hashes) == {"low_pressure", "aftermath", "intentional_ambiguity", "quiet_transition"}, "held-out calibration requires four named control evidence bundles")
        controls_by_kind = {kind: evidence_by_hash(project, digest) for kind, digest in control_hashes.items()}
        for kind, bundle in controls_by_kind.items():
            require(bundle["kind"] == "misfire_control" and bundle["source_kind"] == "human_blind_import" and bundle["synthetic"] is False, f"control {kind} must use non-synthetic human evidence")
            require(bundle["artifact"]["control_kind"] == kind and bundle["artifact"]["status"] == "PASS", f"control {kind} did not pass")
            function_name = bundle["artifact"]["function_rule_name"]
            require(function_name in function_rules and function_rules[function_name]["control_kind"] == kind, f"control {kind} is not bound to its chapter-function rule")

        reopen_hash = evidence.get("reopen_validation_sha256")
        reopen = evidence_by_hash(project, reopen_hash)
        require(reopen["kind"] == "reopen_validation" and reopen["source_kind"] == "accepted_lifecycle" and reopen["synthetic"] is False, "production calibration requires recorded non-synthetic reopen validation")

        evidence_fingerprint_input = {
            "story_package_sha256s": package_hashes,
            "human_reader_import_sha256": human_hash,
            "misfire_control_sha256s": control_hashes,
            "reopen_validation_sha256": reopen_hash,
        }
        require(evidence.get("input_fingerprint") == sha_json(evidence_fingerprint_input), "calibration evidence fingerprint mismatch")
    return copy.deepcopy(document)


def record_calibration(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    require(check(project)["status"] in {"pass", "replay_required"}, "quality project must be internally consistent")
    document = validate_calibration_document(read_json(input_path, "quality calibration"), project)
    digest = sha_json(document)
    target = quality_root(project) / "calibration" / f"{safe_component(document['calibration_id'], 'calibration_id')}.json"
    if target.exists():
        require(read_json(target, "immutable calibration") == document, "calibration ID is immutable")
    else:
        atomic_json(target, document)
    return {"schema": SCHEMA, "status": "calibration_recorded", "calibration_id": document["calibration_id"], "calibration_sha256": digest, "purpose": document["purpose"]}


def initialize(project: Path) -> dict[str, Any]:
    project = project.resolve()
    require_projection_roots_safe(project)
    root = quality_root(project)
    require(not (root / "HEAD.json").exists(), "quality lifecycle is already initialized")
    tracking = project / "追踪"
    require((tracking / "_tracking-state.json").is_file(), "initialize tracking before quality lifecycle")
    load_tracking_module().check_project(project)
    root.mkdir(parents=True, exist_ok=True)
    chapters: dict[str, Any] = {}
    for source in chapter_files(project):
        chapter = chapter_number(source)
        assert chapter is not None
        require(str(chapter) not in chapters, f"multiple accepted body files for chapter {chapter}")
        revision, filename = store_revision(root, chapter, source, parent=None, kind="legacy_import")
        _, metadata = revision_paths(root, chapter, revision)
        chapters[str(chapter)] = {"revision": revision, "filename": filename, "metadata_sha256": sha_file(metadata)}
    gid = generation_id("initialize:" + tree_hash(tracking))
    audit_from = min((int(key) for key in chapters), default=None)
    manifest = {
        "schema": SCHEMA,
        "generation_id": gid,
        "previous_generation": None,
        "created_at": now(),
        "reason": "legacy_import",
        "status": "accepted",
        "chapters": chapters,
        "quality_certificates": {},
        "reader_chains": {},
        "event_index": {},
        "stale": {"reader_from": audit_from, "quality_from": audit_from, "semantic_replay_from": audit_from},
        "invalidation": None,
        "legacy_audit_required": audit_from is not None,
    }
    create_generation(project, manifest, tracking)
    switch_head(project, manifest)
    store_policy(project, default_policy(generation=gid))
    atomic_json(root / "PROJECTION.json", {"generation_id": gid, "materialized_at": now()})
    return {"schema": SCHEMA, "status": "initialized", "generation_id": gid, "chapters": len(chapters)}


def stage(
    project: Path,
    chapter: int,
    candidate: Path,
    transaction: Path,
    *,
    kind: str,
    resolution: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    project = project.resolve()
    root = quality_root(project)
    head = head_record(project)
    current = manifest_for(project)
    require_fresh(current, "stage a chapter")
    require(check(project)["status"] == "pass", "accepted projections differ from HEAD; run rebuild before staging")
    previous = current["chapters"].get(str(chapter))
    require(kind in {"draft", "revision"}, "kind must be draft or revision")
    if kind == "draft":
        require(previous is None, "an accepted chapter must be staged as revision")
    else:
        require(previous is not None, "cannot revise a chapter without an accepted parent")
    revision_intent = metadata.get("revision_intent", "defect_repair" if kind == "revision" else None)
    reopen_case: dict[str, Any] | None = None
    if revision_intent == "strength_reopen":
        reopen_case = load_reopen_case(project, safe_component(metadata.get("reopen_case_id"), "reopen_case_id"))
        require(reopen_case.get("state") in {"SELECTED", "OUTLINE_REVISION_RECORDED"}, "strength reopen case must have a selected arm")
        require(reopen_case.get("base_generation") == head["generation_id"], "strength reopen case is based on stale HEAD")
        require(reopen_case.get("chapter") == chapter, "strength reopen case chapter mismatch")
        require(reopen_case.get("selected_arm_id") == metadata.get("reopen_arm_id"), "staged reopen arm was not selected")
        arm = next((row for row in reopen_case.get("arms", []) if row.get("arm_id") == metadata.get("reopen_arm_id")), None)
        require(isinstance(arm, dict), "selected reopen arm is missing")
        require(arm.get("strength_status") == "PASS", "selected reopen arm lacks a PASS strength evaluation")
        require(sha_file(candidate) == arm.get("body_sha256"), "staged body does not match the selected reopen arm")
        require(reopen_case.get("strength_certificate_sha256") == metadata.get("strength_certificate_sha256"), "strength reopen certificate binding mismatch")
        if reopen_case.get("level") in {"L2", "L3"}:
            metadata.setdefault("author_authorization", reopen_case.get("author_authorization"))
        if reopen_case.get("level") == "L3":
            if not reopen_case.get("simulation_only"):
                require(sha_file(outline_file(project, chapter)) == arm.get("outline_sha256"), "selected L3 outline must be author-approved and active before staging")
        require(metadata.get("simulation_only", False) is reopen_case.get("simulation_only", False), "reopen simulation scope mismatch")
    require(chapter_number(candidate) == chapter, "candidate filename must identify the staged chapter")
    treatment_run: dict[str, Any] | None = None
    treatment_run_id = metadata.get("treatment_run_id")
    if treatment_run_id is not None:
        treatment_run = load_treatment_run(project, treatment_run_id, require_closed=True)
        opened = treatment_run["open"]
        closed = treatment_run["close"]
        assert isinstance(closed, dict)
        require(opened["treatment"] in {"P0", "P1"}, "staged treatment run treatment is invalid")
        require(opened["base_generation"] == head["generation_id"], "staged treatment run is based on stale HEAD")
        require(opened["chapter"] == chapter, "staged treatment run chapter mismatch")
        require(opened["outline_sha256"] == sha_file(outline_file(project, chapter)), "staged treatment run outline mismatch")
        require(closed["selected_body_sha256"] == sha_file(candidate), "only the treatment run selected body may enter stage")
    revision, filename = store_revision(
        root,
        chapter,
        candidate,
        parent=previous["revision"] if previous else None,
        kind=kind,
        finding_ids=metadata.get("finding_ids"),
        impact_regions=metadata.get("impact_regions"),
        repair_scope=metadata.get("repair_scope"),
        author_authorization=metadata.get("author_authorization"),
        revision_intent=revision_intent,
        reopen_case_id=metadata.get("reopen_case_id"),
        reopen_arm_id=metadata.get("reopen_arm_id"),
        strength_certificate_sha256=metadata.get("strength_certificate_sha256"),
    )
    _, revision_metadata = revision_paths(root, chapter, revision)
    outline = outline_file(project, chapter)
    staged_outline_sha256 = sha_file(outline)
    staged_outline_contract = outline_contract(outline)
    if reopen_case is not None and reopen_case.get("level") == "L3" and reopen_case.get("simulation_only"):
        staged_outline_sha256 = arm["outline_sha256"]
        staged_outline_contract = copy.deepcopy(arm["outline_contract"])
    policy, policy_sha256 = effective_policy(project, chapter)
    if reopen_case is not None:
        require(policy_sha256 == reopen_case.get("quality_policy_sha256"), "reopen case policy is no longer active for this chapter")
    document = read_json(transaction, "tracking transaction")
    require(document.get("chapter") == chapter, "tracking transaction chapter mismatch")
    require(resolution in {"within_user_band", "accepted_current_length"}, "invalid length resolution")
    pending_id = generation_id(f"pending:{head['generation_id']}:{chapter}:{revision}").replace("g-", "p-", 1)
    pending_dir = root / "pending" / pending_id
    pending_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(transaction, pending_dir / "tracking-transaction.json")
    record = {
        "schema": SCHEMA,
        "pending_id": pending_id,
        "base_generation": head["generation_id"],
        "chapter": chapter,
        "revision": revision,
        "parent_revision": previous["revision"] if previous else None,
        "kind": kind,
        "filename": filename,
        "outline_name": outline.name,
        "outline_sha256": staged_outline_sha256,
        "outline_contract": staged_outline_contract,
        "tracking_transaction_sha256": sha_file(pending_dir / "tracking-transaction.json"),
        "revision_metadata_sha256": sha_file(revision_metadata),
        "finding_ids": list(metadata.get("finding_ids", [])) if kind == "revision" else [],
        "impact_regions": list(metadata.get("impact_regions", [])) if kind == "revision" or revision_intent == "strength_reopen" else [],
        "repair_scope": metadata.get("repair_scope") if kind == "revision" or revision_intent == "strength_reopen" else None,
        "revision_intent": revision_intent,
        "reopen_case_id": metadata.get("reopen_case_id") if revision_intent == "strength_reopen" else None,
        "reopen_arm_id": metadata.get("reopen_arm_id") if revision_intent == "strength_reopen" else None,
        "strength_certificate_sha256": metadata.get("strength_certificate_sha256") if revision_intent == "strength_reopen" else None,
        "author_authorization": metadata.get("author_authorization") if kind == "revision" or revision_intent == "strength_reopen" else None,
        "simulation_only": metadata.get("simulation_only", False) if revision_intent == "strength_reopen" else False,
        "reopen_reserved_run_ids": list(reopen_case.get("reserved_run_ids", [])) if reopen_case is not None else [],
        "treatment_run_id": opened["run_id"] if treatment_run is not None else None,
        "treatment": opened["treatment"] if treatment_run is not None else None,
        "treatment_start_boundary_sha256": opened["start_boundary_sha256"] if treatment_run is not None else None,
        "treatment_close_boundary_sha256": treatment_run["close"]["close_boundary_sha256"] if treatment_run is not None else None,
        "quality_policy": policy,
        "quality_policy_sha256": policy_sha256,
        "length_resolution": resolution,
        "created_at": now(),
    }
    atomic_json(pending_dir / "pending.json", record)
    return {"schema": SCHEMA, "status": "staged", **record}


def stage_rollback(
    project: Path,
    chapter: int,
    revision: str,
    transaction: Path,
    *,
    reason: str,
    resolution: str,
) -> dict[str, Any]:
    project = project.resolve()
    root = quality_root(project)
    head = head_record(project)
    current = manifest_for(project)
    require_fresh(current, "stage a rollback")
    previous = current["chapters"].get(str(chapter))
    require(previous is not None, "cannot roll back a chapter that is not accepted")
    require(previous["revision"] != revision, "rollback target is already accepted")
    require(is_sha256(revision), "rollback revision must be a SHA-256 revision ID")
    body, metadata_path = revision_paths(root, chapter, revision)
    require(body.is_file() and metadata_path.is_file(), "rollback target is not an immutable known revision")
    metadata = read_json(metadata_path, "rollback revision metadata")
    document = read_json(transaction, "tracking transaction")
    require(document.get("chapter") == chapter and document.get("mode") == "revision", "rollback requires a same-chapter revision tracking transaction")
    nonempty_text(reason, "rollback reason")
    require(resolution in {"within_user_band", "accepted_current_length"}, "invalid length resolution")
    outline = outline_file(project, chapter)
    policy, policy_sha256 = effective_policy(project, chapter)
    pending_id = generation_id(f"rollback:{head['generation_id']}:{chapter}:{revision}").replace("g-", "p-", 1)
    pending_dir = root / "pending" / pending_id
    pending_dir.mkdir(parents=True, exist_ok=False)
    shutil.copy2(transaction, pending_dir / "tracking-transaction.json")
    record = {
        "schema": SCHEMA,
        "pending_id": pending_id,
        "base_generation": head["generation_id"],
        "chapter": chapter,
        "revision": revision,
        "parent_revision": previous["revision"],
        "kind": "revision",
        "filename": metadata["source_name"],
        "outline_name": outline.name,
        "outline_sha256": sha_file(outline),
        "outline_contract": outline_contract(outline),
        "tracking_transaction_sha256": sha_file(pending_dir / "tracking-transaction.json"),
        "revision_metadata_sha256": sha_file(metadata_path),
        "revision_intent": "rollback",
        "quality_policy": policy,
        "quality_policy_sha256": policy_sha256,
        "length_resolution": resolution,
        "rollback_reason": reason,
        "created_at": now(),
    }
    atomic_json(pending_dir / "pending.json", record)
    return {"schema": SCHEMA, "status": "rollback_staged", **record}


def treatment_run_root(project: Path, run_id: str) -> Path:
    return quality_root(project) / "treatment-runs" / safe_component(run_id, "treatment_run_id")


def load_treatment_run(project: Path, run_id: object, *, require_closed: bool = False) -> dict[str, Any]:
    identifier = safe_component(run_id, "treatment_run_id")
    root = treatment_run_root(project, identifier)
    opened = read_json(root / "open.json", "treatment run start boundary")
    require(opened.get("schema") == TREATMENT_RUN_SCHEMA and opened.get("run_id") == identifier, "treatment run start boundary is invalid")
    require(opened.get("start_boundary_sha256") == sha_json({key: value for key, value in opened.items() if key != "start_boundary_sha256"}), "treatment run start boundary hash mismatch")
    closed_path = root / "close.json"
    if not closed_path.is_file():
        require(not require_closed, "treatment run is not closed")
        return {"open": opened, "close": None}
    closed = read_json(closed_path, "treatment run close boundary")
    require(closed.get("schema") == TREATMENT_RUN_SCHEMA and closed.get("run_id") == identifier, "treatment run close boundary is invalid")
    require(closed.get("start_boundary_sha256") == opened["start_boundary_sha256"], "treatment run close does not bind its start boundary")
    require(closed.get("close_boundary_sha256") == sha_json({key: value for key, value in closed.items() if key != "close_boundary_sha256"}), "treatment run close boundary hash mismatch")
    treatment = opened.get("treatment")
    require(treatment in {"P0", "P1"} and closed.get("treatment") == treatment, "treatment run treatment boundary is invalid")
    if treatment == "P1":
        require(closed.get("artifacts") == {"pass_a": "artifacts/pass-a.md", "pass_b": "artifacts/pass-b.md"}, "P1 treatment run artifact paths are invalid")
        for label, filename in (("pass_a", "pass-a.md"), ("pass_b", "pass-b.md")):
            pass_record = closed.get(label)
            require(isinstance(pass_record, dict), f"treatment run {label} record is invalid")
            body = root / "artifacts" / filename
            require(body.is_file(), f"treatment run {label} artifact is missing")
            require(sha_file(body) == pass_record.get("body_sha256"), f"treatment run {label} artifact hash mismatch")
        selected_label = closed.get("selected_label")
        require(selected_label in {"A", "B"}, "treatment run selected label is invalid")
        selected_key = "pass_a" if selected_label == "A" else "pass_b"
        require(closed.get("selected_body_sha256") == closed[selected_key]["body_sha256"], "treatment run selected body hash mismatch")
    else:
        artifacts = closed.get("artifacts")
        require(isinstance(artifacts, dict), "P0 treatment run artifacts are invalid")
        single = closed.get("single_draft")
        require(isinstance(single, dict), "P0 treatment run single_draft record is invalid")
        version_hashes = single.get("version_body_sha256s")
        require(isinstance(version_hashes, list) and version_hashes and all(is_sha256(item) for item in version_hashes), "P0 treatment run version hashes are invalid")
        expected_versions = ["artifacts/single-original.md"] + [
            f"artifacts/single-repair-{index:03d}.md" for index in range(1, len(version_hashes))
        ]
        require(artifacts == {"single_draft": "artifacts/single-draft.md", "versions": expected_versions}, "P0 treatment run artifact paths are invalid")
        for relative, digest in zip(expected_versions, version_hashes):
            version_body = root / relative
            require(version_body.is_file(), "P0 treatment run version artifact is missing")
            require(sha_file(version_body) == digest, "P0 treatment run version artifact hash mismatch")
        body = root / "artifacts" / "single-draft.md"
        require(body.is_file(), "P0 treatment run single-draft artifact is missing")
        require(sha_file(body) == single.get("body_sha256"), "P0 treatment run single-draft artifact hash mismatch")
        require(closed.get("selected_label") == "single_draft", "P0 treatment run selected label is invalid")
        require(closed.get("selected_body_sha256") == single.get("body_sha256"), "P0 treatment run selected body hash mismatch")
    return {"open": opened, "close": closed}


def open_treatment_run(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    require(check(project)["status"] == "pass", "quality project must be fresh before opening a treatment run")
    document = read_json(input_path, "treatment run start")
    require(document.get("schema") == TREATMENT_RUN_SCHEMA, f"treatment run schema must be {TREATMENT_RUN_SCHEMA}")
    run_id = safe_component(document.get("run_id"), "treatment_run_id")
    chapter = integer(document.get("chapter"), "treatment chapter", minimum=1)
    treatment = document.get("treatment")
    require(treatment in {"P0", "P1"}, "treatment run must explicitly select P0 or P1")
    nonempty_text(document.get("treatment_version"), "treatment_version")
    common_base = document.get("common_base")
    require(isinstance(common_base, dict), "treatment run requires common_base")
    nonempty_text(common_base.get("version"), "common_base.version")
    for key in (
        "reference_sha256", "agent_sha256", "model_sha256", "context_sha256",
        "story_package_sha256", "creative_package_sha256",
        "author_identity_sha256", "writer_identity_sha256",
    ):
        require(is_sha256(common_base.get(key)), f"common_base.{key} must be SHA-256")
    budget = document.get("budget")
    require(isinstance(budget, dict), "treatment run requires a frozen budget")
    if treatment == "P1":
        require(set(budget) == {"pass_a_attempts", "pass_b_attempts", "max_visible_chars"}, "P1 treatment budget fields are invalid")
        require(integer(budget.get("pass_a_attempts"), "budget.pass_a_attempts", minimum=1, maximum=1) == 1, "P1 Pass A permits exactly one creative attempt")
        require(integer(budget.get("pass_b_attempts"), "budget.pass_b_attempts", minimum=1, maximum=1) == 1, "P1 Pass B permits exactly one constrained rewrite attempt")
    else:
        require(set(budget) == {"creative_attempts", "max_defect_repairs", "max_visible_chars"}, "P0 single_draft budget fields are invalid")
        require(integer(budget.get("creative_attempts"), "budget.creative_attempts", minimum=1, maximum=1) == 1, "P0 single_draft permits exactly one creative attempt")
        integer(budget.get("max_defect_repairs"), "budget.max_defect_repairs", minimum=0, maximum=3)
    integer(budget.get("max_visible_chars"), "budget.max_visible_chars", minimum=500)
    stop_rule = nonempty_text(document.get("stop_rule"), "treatment stop_rule")
    premise = document.get("premise_interest_pre_read")
    require(isinstance(premise, dict) and premise.get("status") in {"recorded", "not_collected"}, "premise_interest_pre_read status is invalid")
    if premise["status"] == "recorded":
        number(premise.get("score"), "premise_interest_pre_read.score", minimum=0, maximum=5)
        safe_component(premise.get("respondent_id"), "premise_interest_pre_read.respondent_id")
        parse_utc_timestamp(premise.get("recorded_at"), "premise_interest_pre_read.recorded_at")
    else:
        nonempty_text(premise.get("reason"), "premise_interest_pre_read.reason")

    outline = outline_file(project, chapter)
    contract = outline_contract(outline)
    beats: list[dict[str, Any]] | None = None
    if treatment == "P1":
        p1 = contract.get("p1")
        require(isinstance(p1, dict), "P1 treatment requires a fine-outline P1 quality contract")
        require(isinstance(contract.get("reader_oracle"), dict), "P1 treatment requires the chapter reader oracle")
        catalog = p1["scene_catalog"]
        beats_value = document.get("causal_beats")
        require(isinstance(beats_value, list) and len(beats_value) == len(catalog), "causal beats must cover every scene_catalog row exactly once")
        beats = beats_value
        required_beat_fields = ("actor", "goal", "known_basis", "cause_or_trigger", "action_or_choice", "result")
        for index, (beat, scene) in enumerate(zip(beats, catalog), 1):
            require(isinstance(beat, dict), "causal beats must be objects")
            require(beat.get("scene_id") == scene["scene_id"] and beat.get("source_scene_id") == scene["scene_id"], f"causal beat {index} is not bound to its source scene")
            integer(beat.get("scene_index"), f"causal beat {index} scene_index", minimum=1)
            require(beat["scene_index"] == scene["scene_index"], f"causal beat {index} order differs from scene_catalog")
            for key in required_beat_fields:
                nonempty_text(beat.get(key), f"causal beat {index}.{key}")
    else:
        require(document.get("causal_beats") is None, "P0 single_draft cannot smuggle in P1 causal-beat treatment")

    root = treatment_run_root(project, run_id)
    require(not root.exists(), "treatment run ID is immutable")
    head = head_record(project)
    opened = {
        "schema": TREATMENT_RUN_SCHEMA,
        "run_id": run_id,
        "chapter": chapter,
        "treatment": treatment,
        "treatment_version": document["treatment_version"],
        "common_base": copy.deepcopy(common_base),
        "base_generation": head["generation_id"],
        "outline_name": outline.name,
        "outline_sha256": sha_file(outline),
        "outline_artifact_sha256": sha_bytes(nonempty_text(outline.read_text(encoding="utf-8"), "treatment outline").encode("utf-8")),
        "budget": copy.deepcopy(budget),
        "stop_rule": stop_rule,
        "premise_interest_pre_read": copy.deepcopy(premise),
        "mode": "SHADOW",
        "received_at": now(),
    }
    if treatment == "P1":
        assert beats is not None
        opened.update({
            "reader_oracle": copy.deepcopy(contract["reader_oracle"]),
            "reader_oracle_sha256": contract["reader_oracle_sha256"],
            "causal_beats": copy.deepcopy(beats),
            "causal_beats_sha256": sha_json(beats),
        })
    opened["start_boundary_sha256"] = sha_json(opened)
    atomic_json(root / "open.json", opened)
    return {"schema": SCHEMA, "status": "treatment_run_opened", "run_id": run_id, "treatment": treatment, "start_boundary_sha256": opened["start_boundary_sha256"], "mode": "SHADOW"}


def _validate_treatment_pass(label: str, value: object, body_sha256: str) -> tuple[dict[str, Any], bool, str, str]:
    require(isinstance(value, dict), f"treatment pass {label} must be an object")
    writer_run_id = nonempty_text(value.get("writer_run_id"), f"treatment pass {label} writer_run_id")
    evaluator_run_id = nonempty_text(value.get("evaluator_run_id"), f"treatment pass {label} evaluator_run_id")
    require(value.get("generation_attempts") == 1, f"treatment pass {label} must record exactly one generation attempt")
    require(value.get("body_sha256") == body_sha256, f"treatment pass {label} body hash mismatch")
    anchors = value.get("evidence_anchors")
    require(isinstance(anchors, list) and anchors and all(isinstance(item, str) and item.strip() for item in anchors), f"treatment pass {label} requires evidence anchors")
    checks = value.get("checks")
    require(isinstance(checks, dict), f"treatment pass {label} checks must be an object")
    positive = ("causal_spine", "current_action_clear", "scene_grounded", "pov_stable", "characters_distinct")
    negative = ("explanation_bloat", "voice_loss")
    require(set(checks) == set(positive) | set(negative), f"treatment pass {label} check set is invalid")
    eligible = all(checks[key] is True for key in positive) and all(checks[key] is False for key in negative)
    return copy.deepcopy(value), eligible, writer_run_id, evaluator_run_id


def _validate_p0_single_draft(
    value: object,
    body_sha256: str,
    budget: dict[str, Any],
    version_hashes: list[str],
) -> dict[str, Any]:
    require(isinstance(value, dict), "P0 treatment single_draft must be an object")
    require(value.get("body_sha256") == body_sha256, "P0 treatment single_draft body hash mismatch")
    nonempty_text(value.get("writer_run_id"), "P0 single_draft writer_run_id")
    require(value.get("generation_attempts") == 1, "P0 single_draft must record exactly one creative generation attempt")
    initial_hash = value.get("initial_body_sha256")
    require(is_sha256(initial_hash), "P0 single_draft must bind its initial creative body")
    require(version_hashes and version_hashes[0] == initial_hash, "P0 original body artifact differs from the recorded creative body")
    repairs = value.get("defect_repairs")
    require(isinstance(repairs, list), "P0 single_draft defect_repairs must be a list")
    require(len(repairs) <= budget["max_defect_repairs"], "P0 single_draft exceeded its frozen defect-repair budget")
    require(len(version_hashes) == len(repairs) + 1, "P0 version artifacts must contain the original plus every repair output")
    previous_after = str(initial_hash)
    repair_ids: set[str] = set()
    for index, repair in enumerate(repairs, 1):
        require(isinstance(repair, dict), "P0 defect repair records must be objects")
        require(repair.get("repair_index") == index, "P0 defect repair records must be consecutive and ordered")
        repair_id = safe_component(repair.get("repair_id"), "P0 defect repair_id")
        require(repair_id not in repair_ids, "P0 defect repair IDs must be distinct")
        repair_ids.add(repair_id)
        findings = repair.get("finding_ids")
        require(isinstance(findings, list) and findings and len(set(findings)) == len(findings), "P0 defect repair must name distinct finding IDs")
        require(all(isinstance(item, str) and item.strip() for item in findings), "P0 defect repair finding IDs must be non-empty text")
        require(repair.get("repair_scope") == "local", "P0 shared correctness repair must remain local")
        before = repair.get("before_body_sha256")
        after = repair.get("after_body_sha256")
        require(is_sha256(before) and is_sha256(after) and before != after, "P0 defect repair must bind distinct before/after body hashes")
        require(before == previous_after, "P0 defect repair hashes must form one ordered chain")
        require(version_hashes[index] == after, "P0 defect repair output differs from its immutable version artifact")
        previous_after = str(after)
        nonempty_text(repair.get("evaluator_run_id"), "P0 defect repair evaluator_run_id")
    require(previous_after == body_sha256, "P0 final single draft must equal the end of its recorded creative/repair chain")
    require(version_hashes[-1] == body_sha256, "P0 final body differs from its last immutable version artifact")
    normalized = copy.deepcopy(value)
    normalized["version_body_sha256s"] = version_hashes
    return normalized


def close_treatment_run(
    project: Path,
    run_id: str,
    input_path: Path,
    pass_a_body: Path | None = None,
    pass_b_body: Path | None = None,
    single_body: Path | None = None,
    single_original_body: Path | None = None,
    single_repair_bodies: list[Path] | None = None,
) -> dict[str, Any]:
    project = project.resolve()
    run = load_treatment_run(project, run_id)
    require(run["close"] is None, "treatment run is already closed")
    opened = run["open"]
    require(head_record(project)["generation_id"] == opened["base_generation"], "treatment run start boundary is stale")
    require(sha_file(outline_file(project, opened["chapter"])) == opened["outline_sha256"], "treatment run outline changed after the start boundary")
    document = read_json(input_path, "treatment run close")
    require(document.get("schema") == TREATMENT_RUN_SCHEMA and document.get("run_id") == opened["run_id"], "treatment run close identity mismatch")
    require(document.get("treatment") == opened["treatment"], "treatment run close treatment mismatch")
    if opened["treatment"] == "P0":
        require(single_body is not None and single_original_body is not None and pass_a_body is None and pass_b_body is None, "P0 close requires --single-body and --single-original-body only")
        require(chapter_number(single_body) == opened["chapter"], "P0 single draft must identify the treatment chapter")
        repair_bodies = single_repair_bodies or []
        version_bodies = [single_original_body, *repair_bodies]
        require(all(chapter_number(path) == opened["chapter"] for path in version_bodies), "P0 version bodies must identify the treatment chapter")
        version_hashes = [sha_file(path) for path in version_bodies]
        single_hash = sha_file(single_body)
        max_visible_chars = opened["budget"]["max_visible_chars"]
        require(all(len(re.sub(r"\s+", "", path.read_text(encoding="utf-8"))) <= max_visible_chars for path in [*version_bodies, single_body]), "P0 treatment body exceeds the frozen visible-character budget")
        single = _validate_p0_single_draft(document.get("single_draft"), single_hash, opened["budget"], version_hashes)
        root = treatment_run_root(project, opened["run_id"])
        artifacts = root / "artifacts"
        artifacts.mkdir(parents=True, exist_ok=False)
        version_artifacts = ["artifacts/single-original.md"] + [
            f"artifacts/single-repair-{index:03d}.md" for index in range(1, len(version_bodies))
        ]
        for source, relative in zip(version_bodies, version_artifacts):
            shutil.copy2(source, root / relative)
        shutil.copy2(single_body, artifacts / "single-draft.md")
        closed = {
            "schema": TREATMENT_RUN_SCHEMA,
            "run_id": opened["run_id"],
            "treatment": "P0",
            "start_boundary_sha256": opened["start_boundary_sha256"],
            "single_draft": single,
            "selected_label": "single_draft",
            "selected_body_sha256": single_hash,
            "artifacts": {"single_draft": "artifacts/single-draft.md", "versions": version_artifacts},
            "mode": "SHADOW",
            "non_enforced": True,
            "received_at": now(),
        }
        closed["close_boundary_sha256"] = sha_json(closed)
        atomic_json(root / "close.json", closed)
        return {
            "schema": SCHEMA,
            "status": "treatment_run_closed",
            "run_id": opened["run_id"],
            "treatment": "P0",
            "selected_label": "single_draft",
            "selected_body_sha256": single_hash,
            "close_boundary_sha256": closed["close_boundary_sha256"],
            "mode": "SHADOW",
            "non_enforced": True,
        }

    require(pass_a_body is not None and pass_b_body is not None and single_body is None and single_original_body is None and not single_repair_bodies, "P1 close requires only --pass-a-body and --pass-b-body")
    require(chapter_number(pass_a_body) == opened["chapter"] and chapter_number(pass_b_body) == opened["chapter"], "treatment bodies must identify the treatment chapter")
    a_hash = sha_file(pass_a_body)
    b_hash = sha_file(pass_b_body)
    max_visible_chars = opened["budget"]["max_visible_chars"]
    require(all(len(re.sub(r"\s+", "", path.read_text(encoding="utf-8"))) <= max_visible_chars for path in (pass_a_body, pass_b_body)), "P1 treatment body exceeds the frozen visible-character budget")
    pass_a, a_eligible, a_writer, a_evaluator = _validate_treatment_pass("A", document.get("pass_a"), a_hash)
    pass_b, b_eligible, b_writer, b_evaluator = _validate_treatment_pass("B", document.get("pass_b"), b_hash)
    require(a_eligible, "plain_direct Pass A does not meet the publishable prose floor")
    require(a_writer != b_writer, "Pass A and Pass B writers must use isolated runs")
    require(len({a_writer, b_writer, a_evaluator, b_evaluator}) == 4, "Pass writers and evaluators must use mutually isolated runs")
    require(pass_b.get("source_pass_a_sha256") == a_hash, "Pass B must bind the frozen Pass A body")
    invariants = pass_b.get("invariants")
    invariant_keys = {"causal_beats_unchanged", "facts_unchanged", "event_order_unchanged", "pov_unchanged", "reader_oracle_unchanged"}
    require(isinstance(invariants, dict) and set(invariants) == invariant_keys, "Pass B invariant set is invalid")
    b_eligible = b_eligible and all(invariants[key] is True for key in invariant_keys)
    selection = document.get("selection")
    require(isinstance(selection, dict), "treatment run requires a blind selection")
    require(selection.get("labels_hidden") is True and selection.get("order_randomized") is True, "treatment selection must hide labels and randomize order")
    winner = selection.get("winner")
    require(winner in {"A", "B"}, "treatment selection winner must be A or B")
    require(winner != "B" or b_eligible, "voice_restore Pass B cannot win after comprehension or invariant regression")
    selector_run_id = nonempty_text(selection.get("selector_run_id"), "treatment selector_run_id")
    require(selector_run_id not in {a_writer, b_writer, a_evaluator, b_evaluator}, "treatment selector must be isolated from pass writers and evaluators")
    nonempty_text(selection.get("randomization_nonce"), "treatment randomization_nonce")
    nonempty_text(selection.get("rationale"), "treatment selection rationale")
    selector_input = {
        "items": [{"label": "A", "body_sha256": a_hash}, {"label": "B", "body_sha256": b_hash}],
        "pass_a_checks_sha256": sha_json(pass_a),
        "pass_b_checks_sha256": sha_json(pass_b),
    }
    require(selection.get("input_fingerprint") == sha_json(selector_input), "treatment selector input fingerprint mismatch")
    selected_hash = a_hash if winner == "A" else b_hash
    root = treatment_run_root(project, opened["run_id"])
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=False)
    shutil.copy2(pass_a_body, artifacts / "pass-a.md")
    shutil.copy2(pass_b_body, artifacts / "pass-b.md")
    closed = {
        "schema": TREATMENT_RUN_SCHEMA,
        "run_id": opened["run_id"],
        "treatment": "P1",
        "start_boundary_sha256": opened["start_boundary_sha256"],
        "pass_a": pass_a,
        "pass_b": pass_b,
        "pass_a_eligible": a_eligible,
        "pass_b_eligible": b_eligible,
        "selection": copy.deepcopy(selection),
        "selected_label": winner,
        "selected_body_sha256": selected_hash,
        "artifacts": {"pass_a": "artifacts/pass-a.md", "pass_b": "artifacts/pass-b.md"},
        "mode": "SHADOW",
        "non_enforced": True,
        "received_at": now(),
    }
    closed["close_boundary_sha256"] = sha_json(closed)
    atomic_json(root / "close.json", closed)
    return {"schema": SCHEMA, "status": "treatment_run_closed", "run_id": opened["run_id"], "treatment": "P1", "selected_label": winner, "selected_body_sha256": selected_hash, "close_boundary_sha256": closed["close_boundary_sha256"], "mode": "SHADOW", "non_enforced": True}


def nonempty_text(value: object, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label} must be non-empty text")
    return value.strip()


def reader_input_fingerprint(base: dict[str, Any], pending: dict[str, Any]) -> str:
    chapter = pending["chapter"]
    prefix = [
        {"chapter": number, "revision": base["chapters"][str(number)]["revision"]}
        for number in range(1, chapter)
        if str(number) in base.get("chapters", {})
    ]
    return sha_json({"accepted_prefix": prefix, "candidate_chapter": chapter, "candidate_revision": pending["revision"]})


def reader_revision_sequence(base: dict[str, Any], pending: dict[str, Any]) -> list[str]:
    chapter = pending["chapter"]
    require(all(str(number) in base.get("chapters", {}) for number in range(1, chapter)), "reader input requires a contiguous accepted chapter prefix")
    return [base["chapters"][str(number)]["revision"] for number in range(1, chapter)] + [pending["revision"]]


def reader_batch_hashes(revisions: list[str], size: int = 5) -> list[str]:
    return [sha_json(revisions[index:index + size]) for index in range(0, len(revisions), size)]


def validate_reader_measurements(row: dict[str, Any], *, candidate_visible_chars: int | None = None) -> dict[str, Any]:
    reader_schema = row.get("reader_schema")
    require(reader_schema in {READER_SCHEMA_V2, READER_SCHEMA_V3}, "reader_schema is unsupported")
    persona_id = safe_component(row.get("persona_id"), "persona_id")
    profile = row.get("persona_profile")
    require(isinstance(profile, dict), f"reader {persona_id} persona_profile must be an object")
    require(profile.get("genre_familiarity") in {"low", "medium", "high"}, "persona genre_familiarity is invalid")
    require(profile.get("reading_history") in {"fresh", "sequential", "full_prefix"}, "persona reading_history is invalid")
    require(row.get("persona_profile_sha256") == sha_json(profile), "persona profile hash mismatch")
    require(row.get("evidence_type") in {"llm_proxy", "human"}, "reader evidence_type is invalid")
    measurements = row.get("measurements")
    require(isinstance(measurements, dict), "reader v2 measurements must be an object")

    friction = measurements.get("first_friction")
    require(isinstance(friction, dict) and isinstance(friction.get("present"), bool), "first_friction measurement is invalid")
    if friction["present"]:
        safe_component(friction.get("scene_id"), "first_friction.scene_id")
        integer(friction.get("scene_index"), "first_friction.scene_index", minimum=1)
        offset = integer(friction.get("start_offset"), "first_friction.start_offset", minimum=0)
        ratio = number(friction.get("visible_ratio"), "first_friction.visible_ratio", minimum=0, maximum=1)
        require(friction.get("kind") in FRICTION_KINDS, "first_friction.kind is invalid")
        integer(friction.get("severity"), "first_friction.severity", minimum=1, maximum=4)
        require(isinstance(friction.get("recovered"), bool), "first_friction.recovered must be boolean")
        require(isinstance(friction.get("quit_intent"), bool), "first_friction.quit_intent must be boolean")
        nonempty_text(friction.get("evidence_anchor"), "first_friction.evidence_anchor")
        if candidate_visible_chars:
            require(offset <= candidate_visible_chars, "first_friction offset exceeds the immutable candidate body")
            expected_ratio = offset / candidate_visible_chars
            require(abs(ratio - expected_ratio) <= 0.02, "first_friction visible_ratio does not match its body offset")
    else:
        require(friction.get("severity") == 0 and friction.get("quit_intent") is False, "absent friction must have severity 0 and no quit intent")

    read_on = measurements.get("strongest_read_on")
    require(isinstance(read_on, dict), "strongest_read_on measurement must be an object")
    safe_component(read_on.get("scene_id"), "strongest_read_on.scene_id")
    integer(read_on.get("scene_index"), "strongest_read_on.scene_index", minimum=1)
    start = integer(read_on.get("start_offset"), "strongest_read_on.start_offset", minimum=0)
    end = integer(read_on.get("end_offset"), "strongest_read_on.end_offset", minimum=start)
    safe_component(read_on.get("function"), "strongest_read_on.function")
    integer(read_on.get("intensity"), "strongest_read_on.intensity", minimum=1, maximum=5)
    number(read_on.get("confidence"), "strongest_read_on.confidence", minimum=0, maximum=1)
    nonempty_text(read_on.get("evidence_anchor"), "strongest_read_on.evidence_anchor")
    if candidate_visible_chars:
        require(end <= candidate_visible_chars, "strongest_read_on range exceeds the immutable candidate body")

    expectation = measurements.get("end_expectation")
    require(isinstance(expectation, dict), "end_expectation measurement must be an object")
    for key in ("expectation_ids", "hypothesis_ids"):
        require(isinstance(expectation.get(key), list), f"end_expectation.{key} must be a list")
        require(all(isinstance(value, str) and value.strip() for value in expectation[key]), f"end_expectation.{key} values must be non-empty strings")
    require(expectation["expectation_ids"], "end_expectation must identify at least one continuation function")
    number(expectation.get("confidence"), "end_expectation.confidence", minimum=0, maximum=1)
    nonempty_text(expectation.get("free_text"), "end_expectation.free_text")

    emotion = measurements.get("target_emotion")
    require(isinstance(emotion, dict), "target_emotion measurement must be an object")
    nonempty_text(emotion.get("target_id"), "target_emotion.target_id")
    nonempty_text(emotion.get("observed_emotion"), "target_emotion.observed_emotion")
    integer(emotion.get("intensity"), "target_emotion.intensity", minimum=0, maximum=5)
    number(emotion.get("confidence"), "target_emotion.confidence", minimum=0, maximum=1)
    require(isinstance(emotion.get("received"), bool), "target_emotion.received must be boolean")

    fatigue = measurements.get("cumulative_fatigue")
    require(isinstance(fatigue, dict), "cumulative_fatigue measurement must be an object")
    integer(fatigue.get("level"), "cumulative_fatigue.level", minimum=0, maximum=4)
    integer(fatigue.get("delta"), "cumulative_fatigue.delta", minimum=-4, maximum=4)
    nonempty_text(fatigue.get("reason"), "cumulative_fatigue.reason")
    require(isinstance(measurements.get("continued_by_choice"), bool), "continued_by_choice must be boolean")
    require(isinstance(measurements.get("continued_for_study"), bool), "continued_for_study must be boolean")
    if reader_schema == READER_SCHEMA_V3:
        for key in ("cumulative_confusion", "mystery_fatigue"):
            state = measurements.get(key)
            require(isinstance(state, dict), f"{key} must be an object")
            integer(state.get("level"), f"{key}.level", minimum=0, maximum=4)
            integer(state.get("delta"), f"{key}.delta", minimum=-4, maximum=4)
            nonempty_text(state.get("reason"), f"{key}.reason")
        first_quit = measurements.get("first_quit_chapter")
        if first_quit is not None:
            integer(first_quit, "first_quit_chapter", minimum=1)
            require(measurements["continued_by_choice"] is False, "a reader with first_quit_chapter cannot count as natural continuation")
        if measurements["continued_for_study"]:
            require(first_quit is not None and measurements["continued_by_choice"] is False, "study continuation requires a recorded natural quit")
        if first_quit is None:
            require(measurements["continued_for_study"] is False, "study continuation cannot precede first_quit_chapter")
    return copy.deepcopy(measurements)


def validate_reader_measurement_transition(previous: dict[str, Any], current: dict[str, Any], chapter: int) -> None:
    previous_quit = previous.get("first_quit_chapter")
    current_quit = current.get("first_quit_chapter")
    require(current_quit is None or current_quit <= chapter, "first_quit_chapter cannot point beyond the reviewed chapter")
    if previous_quit is not None:
        require(current_quit == previous_quit, "first_quit_chapter is immutable once recorded")
    elif current_quit is not None:
        require(current_quit == chapter, "a sequential reader may first quit only at the current chapter")
    for key in ("cumulative_fatigue", "cumulative_confusion", "mystery_fatigue"):
        before = previous.get(key)
        after = current.get(key)
        if isinstance(before, dict) and isinstance(after, dict):
            require(after["level"] - before["level"] == after["delta"], f"{key}.delta does not match its accepted prior state")


def accepted_reader_state(project: Path, reader_id: str, chapter: int, expected_hash: str) -> dict[str, Any]:
    matches = []
    for path in (quality_root(project) / "readers" / reader_id).glob(f"chapter-{chapter:06d}-*.json"):
        state = read_json(path, "accepted prior reader state")
        if state.get("state_hash") == expected_hash:
            matches.append(state)
    require(len(matches) == 1, f"accepted prior reader state {reader_id}/{chapter} is absent or ambiguous")
    return matches[0]


def validate_reader_state(
    row: object,
    chapter: int,
    previous: str | None,
    *,
    candidate_revision: str,
    input_fingerprint: str,
    revision_sequence: list[str],
    candidate_visible_chars: int | None = None,
) -> tuple[dict[str, Any], str]:
    require(isinstance(row, dict), "reader cohort rows must be objects")
    required = {
        "reader_id", "cohort_type", "source_scope", "previous_hash", "remembered", "forgotten",
        "believes", "guesses", "emotion", "expectation", "first_friction", "strongest_read_on",
        "end_expectation", "target_emotion_received", "cumulative_fatigue", "independent",
        "run_id", "retention_verdict", "retention_evidence", "input_fingerprint",
    }
    require(required <= set(row), f"reader state missing: {', '.join(sorted(required - set(row)))}")
    reader_id = safe_component(row["reader_id"], "reader_id")
    nonempty_text(row["run_id"], f"reader {reader_id} run_id")
    require(row["independent"] is True, f"reader {reader_id} must be independently sampled")
    require(row["cohort_type"] in {"sequential", "fresh_replay"}, "invalid reader cohort type")
    expected_scope = {
        "accepted_prose_through": chapter - 1,
        "candidate_chapter": chapter,
        "candidate_revision": candidate_revision,
        "oracle_visible": False,
    }
    require(row["source_scope"] == expected_scope, "reader source must be accepted prefix plus the immutable current candidate, without oracle data")
    require(row["input_fingerprint"] == input_fingerprint, "reader input fingerprint does not match accepted prefix and candidate revision")
    require(row["previous_hash"] == previous, f"reader {reader_id} previous hash does not match chapter {chapter - 1}")
    if row["cohort_type"] == "fresh_replay":
        require(row.get("replayed_from_chapter") == 1, "fresh reader must replay from chapter 1")
        require(row.get("replayed_through_chapter") == chapter, "fresh reader must replay through the reviewed chapter")
        require(row.get("replayed_revision_hashes") == revision_sequence, "fresh replay must bind every accepted-prefix and candidate revision hash")
        require(row.get("batch_hashes") == reader_batch_hashes(revision_sequence), "fresh replay batch hashes do not match the reviewed revisions")
    for key in ("remembered", "forgotten", "believes", "guesses"):
        require(isinstance(row[key], list), f"reader state {key} must be a list")
    for key in ("emotion", "expectation", "first_friction", "strongest_read_on", "end_expectation", "cumulative_fatigue"):
        nonempty_text(row[key], f"reader state {key}")
    require(row["retention_verdict"] in {"pass", "review", "block"}, f"reader {reader_id} retention verdict is invalid")
    nonempty_text(row["retention_evidence"], f"reader {reader_id} retention evidence")
    require(isinstance(row.get("retention_issue_ids"), list), f"reader {reader_id} retention issue IDs must be a list")
    require(all(isinstance(value, str) and value.strip() for value in row["retention_issue_ids"]), f"reader {reader_id} retention issue IDs must be non-empty strings")
    require(isinstance(row["target_emotion_received"], bool), "target_emotion_received must be boolean")
    if row.get("reader_schema") is not None:
        validate_reader_measurements(row, candidate_visible_chars=candidate_visible_chars)
    normalized = copy.deepcopy(row)
    normalized["chapter"] = chapter
    normalized.pop("state_hash", None)
    state_hash = sha_json(normalized)
    normalized["state_hash"] = state_hash
    return normalized, state_hash


def derive_strength_gate(
    pending: dict[str, Any],
    policy: dict[str, Any],
    cohort: list[dict[str, Any]],
) -> dict[str, Any]:
    mode = policy["strength_mode"]
    p1 = pending.get("outline_contract", {}).get("p1")
    expected_reader_schema = policy["reader_measurement_schema"]
    if not isinstance(p1, dict) or not cohort or any(row.get("reader_schema") != expected_reader_schema for row in cohort):
        return {
            "mode": mode,
            "status": "INSUFFICIENT_EVIDENCE",
            "policy_sha256": pending.get("quality_policy_sha256"),
            "reason_codes": ["reader-schema-or-outline-contract-missing"],
            "persona_results": [],
        }

    required = policy.get("required_personas", [])
    if not required:
        counts: dict[tuple[str, str], int] = {}
        for row in cohort:
            key = (row["persona_id"], row["persona_profile_sha256"])
            counts[key] = counts.get(key, 0) + 1
        required = [
            {
                "persona_id": persona_id,
                "persona_profile": next(row["persona_profile"] for row in cohort if row["persona_id"] == persona_id and row["persona_profile_sha256"] == profile_sha256),
                "persona_profile_sha256": profile_sha256,
                "minimum_independent": 2,
                "evidence_types": ["llm_proxy", "human"],
            }
            for (persona_id, profile_sha256), count in counts.items() if count >= 2
        ]
    if not required:
        return {
            "mode": mode,
            "status": "INSUFFICIENT_EVIDENCE",
            "policy_sha256": pending.get("quality_policy_sha256"),
            "reason_codes": ["no-decision-persona-has-two-independent-readers"],
            "persona_results": [],
        }

    thresholds = policy["thresholds"]
    required_deliveries = set(p1["required_deliveries"])
    allowed_expectations = set(p1["allowed_expectation_ids"])
    allowed_hypotheses = set(p1["allowed_hypothesis_ids"])
    scene_catalog = {row["scene_id"]: row["scene_index"] for row in p1["scene_catalog"]}
    invalid_scene_readers = []
    for row in cohort:
        read_on = row["measurements"]["strongest_read_on"]
        friction = row["measurements"]["first_friction"]
        read_on_valid = scene_catalog.get(read_on["scene_id"]) == read_on["scene_index"]
        friction_valid = (
            not friction["present"]
            or scene_catalog.get(friction["scene_id"]) == friction["scene_index"]
        )
        if not (read_on_valid and friction_valid):
            invalid_scene_readers.append(row.get("reader_id"))
    if invalid_scene_readers:
        return {
            "mode": mode,
            "status": "INSUFFICIENT_EVIDENCE",
            "policy_sha256": pending.get("quality_policy_sha256"),
            "chapter_function": p1["chapter_function"],
            "reason_codes": ["reader-scene-reference-not-in-outline-catalog"],
            "persona_results": [],
        }
    function_rule = policy["function_rules"].get(p1["chapter_function"]) or policy["function_rules"].get("*")
    if not isinstance(function_rule, dict):
        return {
            "mode": mode,
            "status": "INSUFFICIENT_EVIDENCE",
            "policy_sha256": pending.get("quality_policy_sha256"),
            "chapter_function": p1["chapter_function"],
            "reason_codes": [f"chapter-function-not-calibrated:{p1['chapter_function']}"],
            "persona_results": [],
        }
    allowed_deliveries = set(function_rule["allowed_deliveries"])
    if "*" not in allowed_deliveries and not required_deliveries <= allowed_deliveries:
        return {
            "mode": mode,
            "status": "INSUFFICIENT_EVIDENCE",
            "policy_sha256": pending.get("quality_policy_sha256"),
            "chapter_function": p1["chapter_function"],
            "reason_codes": [f"chapter-function-delivery-outside-calibration:{p1['chapter_function']}"],
            "persona_results": [],
        }
    persona_results: list[dict[str, Any]] = []
    insufficient = False
    flat = False
    reason_codes: set[str] = set()
    for requirement in required:
        rows = [
            row for row in cohort
            if row.get("persona_id") == requirement["persona_id"]
            and row.get("persona_profile_sha256") == requirement["persona_profile_sha256"]
            and row.get("evidence_type") in requirement.get("evidence_types", ["llm_proxy", "human"])
        ]
        minimum = int(requirement["minimum_independent"])
        if len(rows) < minimum:
            insufficient = True
            reason_codes.add(f"insufficient-persona:{requirement['persona_id']}")
            persona_results.append({"persona_id": requirement["persona_id"], "readers": len(rows), "status": "INSUFFICIENT_EVIDENCE"})
            continue
        majority = len(rows) // 2 + 1
        severe_early = 0
        delivery_scenes: list[int] = []
        emotion_hits = 0
        expectation_hits = 0
        expectation_votes: dict[str, int] = {}
        for row in rows:
            measurements = row["measurements"]
            friction = measurements["first_friction"]
            if (
                friction["present"]
                and friction["visible_ratio"] <= thresholds["early_friction_ratio"]
                and friction["severity"] >= thresholds["severe_friction"]
                and friction["recovered"] is False
                and friction["quit_intent"] is True
            ):
                severe_early += 1
            read_on = measurements["strongest_read_on"]
            if (
                read_on["function"] in required_deliveries
                and read_on["intensity"] >= thresholds["minimum_read_on_intensity"]
                and read_on["confidence"] >= thresholds["minimum_confidence"]
            ):
                delivery_scenes.append(int(read_on["scene_index"]))
            emotion = measurements["target_emotion"]
            if (
                emotion["target_id"] == p1["target_emotion_id"]
                and emotion["received"] is True
                and emotion["intensity"] >= thresholds["minimum_emotion_intensity"]
                and emotion["confidence"] >= thresholds["minimum_confidence"]
            ):
                emotion_hits += 1
            expectation = measurements["end_expectation"]
            hypotheses = set(expectation["hypothesis_ids"])
            recognized_expectations = set(expectation["expectation_ids"]) & allowed_expectations
            if (
                bool(recognized_expectations)
                and (not hypotheses or hypotheses <= allowed_hypotheses)
                and expectation["confidence"] >= thresholds["minimum_confidence"]
            ):
                expectation_hits += 1
                for expectation_id in recognized_expectations:
                    expectation_votes[expectation_id] = expectation_votes.get(expectation_id, 0) + 1
        delivery_scenes.sort()
        delivery_consensus = 0
        left = 0
        for right, scene_index in enumerate(delivery_scenes):
            while scene_index - delivery_scenes[left] > 1:
                left += 1
            delivery_consensus = max(delivery_consensus, right - left + 1)
        expectation_consensus = max(expectation_votes.values(), default=0)
        failures = []
        if severe_early >= thresholds["corroborated_quit_readers"]:
            failures.append("corroborated-severe-unrecovered-early-friction")
        if function_rule["require_delivery_consensus"] and delivery_consensus < majority:
            failures.append("planned-delivery-lacks-shared-region")
        if function_rule["require_emotion_majority"] and emotion_hits < majority:
            failures.append("target-emotion-not-received")
        if function_rule["require_expectation_consensus"] and expectation_consensus < majority:
            failures.append("continuation-function-lacks-consensus")
        if failures:
            flat = True
            reason_codes.update(f"{requirement['persona_id']}:{item}" for item in failures)
        persona_results.append({
            "persona_id": requirement["persona_id"],
            "readers": len(rows),
            "minimum_independent": minimum,
            "persona_profile_sha256": requirement["persona_profile_sha256"],
            "severe_early": severe_early,
            "delivery_hits": len(delivery_scenes),
            "delivery_consensus": delivery_consensus,
            "emotion_hits": emotion_hits,
            "expectation_hits": expectation_hits,
            "expectation_consensus": expectation_consensus,
            "status": "FLAT" if failures else "PASS",
        })
    status = "INSUFFICIENT_EVIDENCE" if insufficient else "FLAT" if flat else "PASS"
    return {
        "mode": mode,
        "status": status,
        "policy_sha256": pending.get("quality_policy_sha256"),
        "chapter_function": p1["chapter_function"],
        "reason_codes": sorted(reason_codes),
        "persona_results": persona_results,
    }


def require_bound_text_artifact(item: dict[str, Any], *, text_key: str, hash_key: str, label: str) -> str:
    text = nonempty_text(item.get(text_key), f"{label} {text_key}")
    digest = item.get(hash_key)
    require(is_sha256(digest) and digest == sha_bytes(text.encode("utf-8")), f"{label} hash is not bound to its text artifact")
    return digest


def frozen_benchmark_fixture() -> tuple[dict[str, Any], str]:
    path = Path(__file__).with_name("positive-benchmark-fixtures.json")
    document = read_json(path, "frozen positive benchmark fixture")
    require(document.get("schema") == "story-positive-benchmark-fixtures/v1", "positive benchmark fixture schema mismatch")
    nonempty_text(document.get("version"), "positive benchmark fixture version")
    nonempty_text(document.get("evaluator_protocol"), "positive benchmark evaluator protocol")
    sets = document.get("sets")
    require(isinstance(sets, dict), "positive benchmark fixture sets must be an object")
    for key in ("development", "held_out", "controls", "mutants"):
        require(isinstance(sets.get(key), list) and sets[key], f"frozen positive benchmark requires {key}")
        for row in sets[key]:
            require(isinstance(row, dict), f"frozen positive benchmark {key} rows must be objects")
            require_bound_text_artifact(
                row, text_key="artifact_text", hash_key="artifact_sha256", label=f"frozen positive benchmark {key}"
            )
            require(row.get("expected") in {"clean", "defect"}, f"frozen positive benchmark {key} oracle is invalid")
    return document, sha_file(path)


def voice_bearing_lines(body: str) -> list[str]:
    pairs = (("「", "」"), ("『", "』"), ("“", "”"), ('"', '"'))
    return [
        line.strip()
        for line in body.splitlines()
        if any(opening in line and closing in line[line.find(opening) + len(opening):] for opening, closing in pairs)
    ]


def validate_review_packet(
    packet: dict[str, Any],
    pending: dict[str, Any],
    base: dict[str, Any],
    *,
    tracking_events: dict[str, dict[str, Any]] | None = None,
    candidate_body: str,
    project: Path | None = None,
    reader_state_overrides: dict[str, dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], bool]:
    require(packet.get("schema") == PACKET_SCHEMA, f"review packet schema must be {PACKET_SCHEMA}")
    chapter = pending["chapter"]
    revision = pending["revision"]
    require(packet.get("chapter") == chapter, "review packet chapter mismatch")
    require(packet.get("revision") == revision, "review packet revision mismatch")
    policy = validate_policy(copy.deepcopy(pending.get("quality_policy") or default_policy()))
    policy_sha256 = pending.get("quality_policy_sha256") or sha_json(policy)
    require(sha_json(policy) == policy_sha256, "pending quality policy hash mismatch")
    pending["quality_policy"] = policy
    pending["quality_policy_sha256"] = policy_sha256

    roles = packet.get("roles")
    require(isinstance(roles, dict), "roles must be an object")
    role_names = [nonempty_text(roles.get(key), f"roles.{key}") for key in ("defect_evaluator", "holistic_selector", "final_validator")]
    require(len(set(role_names)) == 3, "defect evaluator, holistic selector, and final validator must be isolated")
    repairer = roles.get("repairer")
    if pending["kind"] == "revision":
        nonempty_text(repairer, "roles.repairer")
        require(repairer not in set(role_names), "repairer must be isolated from defect evaluator, selector, and final validator")
    execution_run_ids = set(role_names)
    if repairer:
        execution_run_ids.add(repairer)
    if pending.get("revision_intent") == "strength_reopen":
        # Stage binds the case; callers that validate a persisted pending inject
        # the reserved run IDs so generation, selection, and final review cannot
        # collapse into one execution identity.
        reserved = pending.get("reopen_reserved_run_ids", [])
        require(isinstance(reserved, list) and reserved, "strength reopen pending lacks reserved generation/selection run IDs")
        require(not (set(reserved) & execution_run_ids), "reopen writer/selector/evaluator runs must be isolated from final review roles")
        execution_run_ids.update(reserved)

    gate = packet.get("correctness_gate")
    require(isinstance(gate, dict), "correctness_gate must be an object")
    require(set(gate) == CORRECTNESS_GATES, "correctness_gate must contain the four derived gate keys")

    perspectives = packet.get("perspectives")
    require(isinstance(perspectives, dict) and PERSPECTIVES <= set(perspectives), "all six review perspectives are required")
    all_findings: list[dict[str, Any]] = []
    perspective_run_ids: set[str] = set()
    expected_input_fingerprint = reader_input_fingerprint(base, pending)
    all_perspectives_pass = True
    for name in sorted(PERSPECTIVES):
        view = perspectives[name]
        require(isinstance(view, dict) and view.get("verdict") in {"PASS", "FAIL"}, f"invalid {name} verdict")
        require(isinstance(view.get("findings"), list), f"{name}.findings must be a list")
        execution = view.get("execution")
        require(isinstance(execution, dict), f"{name} requires execution evidence")
        run_id = nonempty_text(execution.get("run_id"), f"{name} execution run_id")
        require(run_id not in execution_run_ids, "all evaluator, repairer, perspective, reader, judge, and validator runs must be globally distinct")
        perspective_run_ids.add(run_id)
        execution_run_ids.add(run_id)
        require(execution.get("candidate_revision") == revision, f"{name} execution is not bound to the candidate revision")
        require(execution.get("input_fingerprint") == expected_input_fingerprint, f"{name} execution input fingerprint mismatch")
        require(isinstance(execution.get("reviewed_units"), list) and execution["reviewed_units"], f"{name} must name reviewed units")
        nonempty_text(execution.get("evidence_summary"), f"{name} evidence summary")
        if view["verdict"] != "PASS":
            all_perspectives_pass = False
        all_findings.extend(view["findings"])
    ids: set[str] = set()
    for finding in all_findings:
        require(isinstance(finding, dict), "findings must be objects")
        identifier = nonempty_text(finding.get("id"), "finding.id")
        require(identifier not in ids, f"duplicate finding id: {identifier}")
        ids.add(identifier)
        severity = finding.get("severity")
        disposition = finding.get("disposition")
        require(severity in SEVERITIES, f"invalid severity for {identifier}")
        require(disposition in DISPOSITIONS, f"invalid disposition for {identifier}")
        nonempty_text(finding.get("evidence"), f"finding {identifier} evidence")
        nonempty_text(finding.get("evidence_anchor"), f"finding {identifier} evidence_anchor")
        gate_impacts = finding.get("gate_impacts")
        require(isinstance(gate_impacts, list) and set(gate_impacts) <= CORRECTNESS_GATES, f"finding {identifier} gate_impacts are invalid")
        require(len(set(gate_impacts)) == len(gate_impacts), f"finding {identifier} gate_impacts must be distinct")
        if severity in {"S1", "S2"}:
            require(disposition in {"FIXED_VERIFIED", "FALSE_POSITIVE"}, f"{severity} finding {identifier} is unresolved")
        if disposition == "PRESERVED_WITH_FUNCTION":
            nonempty_text(finding.get("preserved_function"), f"finding {identifier} preserved_function")
            require(finding.get("blind_ab_non_inferior") is True, f"preserved finding {identifier} needs non-inferior blind A/B")
        if disposition == "FALSE_POSITIVE":
            nonempty_text(finding.get("rationale"), f"finding {identifier} false-positive rationale")
        if disposition == "OVERRIDDEN":
            nonempty_text(finding.get("author_approval"), f"finding {identifier} author approval")

    perspective_gate_sources = {
        "causality": ("story-logic",),
        "facts": ("continuity",),
        "present_action": ("reader-comprehension",),
        "mystery_legitimacy": ("reader-comprehension", "story-logic"),
    }
    active_critical_impacts = {
        impact
        for finding in all_findings
        if finding["severity"] in {"S1", "S2"}
        and finding["disposition"] not in {"FIXED_VERIFIED", "FALSE_POSITIVE"}
        for impact in finding["gate_impacts"]
    }
    derived_gate = {
        key: "PASS"
        if all(perspectives[name]["verdict"] == "PASS" for name in sources) and key not in active_critical_impacts
        else "FAIL"
        for key, sources in perspective_gate_sources.items()
    }
    # The caller may include the display field, but it is never trusted: the
    # persisted packet always carries the value recomputed from raw review data.
    packet["correctness_gate"] = derived_gate

    if (
        pending["kind"] == "revision"
        and not pending.get("rollback_reason")
        and pending.get("revision_intent", "defect_repair") == "defect_repair"
    ):
        target_findings = set(pending.get("finding_ids", []))
        require(target_findings, "revision pending generation must bind its target finding IDs")
        finding_dispositions = {finding["id"]: finding["disposition"] for finding in all_findings}
        require(target_findings <= set(finding_dispositions), "revision review must account for every staged target finding")
        unresolved_targets = sorted(
            finding_id for finding_id in target_findings
            if finding_dispositions[finding_id] != "FIXED_VERIFIED"
        )
        require(
            not unresolved_targets,
            f"revision target findings must be independently FIXED_VERIFIED: {unresolved_targets}",
        )

    repair = packet.get("repair")
    require(isinstance(repair, dict), "repair must be an object")
    require(repair.get("attempt") in {0, 1, 2, 3}, "repair.attempt must be 0-3")
    repeated = repair.get("repeated_finding_ids", [])
    require(isinstance(repeated, list), "repeated_finding_ids must be a list")
    if repeated:
        nonempty_text(repair.get("rediagnosis"), "repeated findings require rediagnosis")

    blind = packet.get("blind_ab")
    require(isinstance(blind, dict), "blind_ab must be an object")
    eligible = all_perspectives_pass and all(value == "PASS" for value in derived_gate.values())
    if pending["kind"] == "revision":
        require(blind.get("labels_hidden") is True and blind.get("order_randomized") is True, "revision comparison must be blinded and order-randomized")
        require(blind.get("previous_revision") == pending["parent_revision"], "blind A/B previous revision mismatch")
        require(blind.get("candidate_revision") == revision, "blind A/B candidate revision mismatch")
        require(blind.get("winner") in {"candidate", "previous", "tie"}, "invalid blind A/B winner")
        nonempty_text(blind.get("rationale"), "blind A/B rationale")
        package = blind.get("package")
        require(isinstance(package, dict), "revision comparison requires a verifiable blind package")
        items = package.get("items")
        require(isinstance(items, list) and len(items) == 2, "blind package requires exactly two items")
        labels = [nonempty_text(item.get("label") if isinstance(item, dict) else None, "blind item label") for item in items]
        require(len(set(labels)) == 2, "blind item labels must be distinct")
        body_hashes = [item.get("body_sha256") for item in items]
        require(all(is_sha256(value) for value in body_hashes), "blind package body hashes must be SHA-256")
        require(set(body_hashes) == {pending["parent_revision"], revision}, "blind package must contain the previous and candidate bodies")
        criteria = package.get("criteria")
        require(isinstance(criteria, list) and criteria, "blind package requires comparison criteria")
        require(package.get("selector_run_id") == roles["holistic_selector"], "blind selector run identity mismatch")
        require(package.get("selector_input_sha256") == sha_json({"items": items, "criteria": criteria}), "blind selector input hash mismatch")
        nonempty_text(package.get("randomization_nonce"), "blind package randomization nonce")
        require(package.get("origin_key_revealed_after_selection") is True, "blind origin key may be revealed only after selection")
        winner_label = package.get("winner_label")
        if blind["winner"] == "tie":
            require(winner_label is None, "tie cannot name a winning blind label")
        else:
            expected_hash = revision if blind["winner"] == "candidate" else pending["parent_revision"]
            require(any(item["label"] == winner_label and item["body_sha256"] == expected_hash for item in items), "blind winner label does not match the recorded winner")
        eligible = eligible and blind["winner"] == "candidate"
    else:
        require(blind.get("winner") in {"candidate", "not_applicable"}, "initial draft must be selected or explicitly not applicable")

    selection = packet.get("selection_protocol")
    require(isinstance(selection, dict), "selection_protocol must be an object")
    dimensions = selection.get("improvement_dimensions")
    require(isinstance(dimensions, dict), "improvement_dimensions must be an object")
    for key in ("retention", "emotion_delivery", "voice", "memory_points", "genre_contract"):
        require(dimensions.get(key) in {"better", "equal", "worse", "not_applicable"}, f"invalid improvement dimension {key}")
    if any(value == "worse" for value in dimensions.values()):
        eligible = False
    benchmark = selection.get("positive_benchmark")
    require(isinstance(benchmark, dict) and benchmark.get("structural_function_only") is True, "positive benchmark may compare structural function/effect only")
    frozen_fixture, frozen_fixture_sha256 = frozen_benchmark_fixture()
    require(benchmark.get("fixture_version") == frozen_fixture["version"], "positive benchmark fixture version mismatch")
    require(benchmark.get("fixture_sha256") == frozen_fixture_sha256, "positive benchmark is not bound to the frozen fixture")
    benchmark_sets: dict[str, list[dict[str, Any]]] = {}
    benchmark_hashes: set[str] = set()
    for key in ("development", "held_out", "controls", "mutants"):
        require(isinstance(benchmark.get(key), list) and benchmark[key], f"positive benchmark requires {key} set")
        benchmark_sets[key] = benchmark[key]
        frozen_rows = frozen_fixture["sets"][key]
        require(len(benchmark[key]) == len(frozen_rows), f"positive benchmark {key} does not match the frozen fixture")
        for item, frozen in zip(benchmark[key], frozen_rows):
            require(isinstance(item, dict), f"positive benchmark {key} rows must be objects")
            require(item.get("id") == frozen["id"], f"positive benchmark {key} fixture ID mismatch")
            artifact = require_bound_text_artifact(
                item, text_key="artifact_text", hash_key="artifact_sha256", label=f"positive benchmark {key}"
            )
            require(
                item.get("artifact_text") == frozen["artifact_text"] and artifact == frozen["artifact_sha256"],
                f"positive benchmark {key} artifact differs from the frozen fixture",
            )
            require("expected" not in item, f"positive benchmark {key} packet must not expose the frozen oracle")
            require(artifact not in benchmark_hashes, "positive benchmark sets must be mutually exclusive")
            benchmark_hashes.add(artifact)
            evaluation = item.get("evaluation")
            require(isinstance(evaluation, dict), f"positive benchmark {key} requires execution evidence")
            run_id = nonempty_text(evaluation.get("run_id"), f"positive benchmark {key} evaluator run_id")
            require(run_id not in execution_run_ids, "benchmark evaluators require globally isolated execution runs")
            execution_run_ids.add(run_id)
            require(
                evaluation.get("input_fingerprint") == sha_json({
                    "artifact_sha256": artifact,
                    "fixture_version": frozen_fixture["version"],
                    "evaluator_protocol": frozen_fixture["evaluator_protocol"],
                }),
                f"positive benchmark {key} evaluator input mismatch",
            )
            require(evaluation.get("observed") == frozen["expected"], f"positive benchmark {key} did not produce its frozen oracle result")
            require(isinstance(evaluation.get("finding_ids"), list), f"positive benchmark {key} requires finding IDs")
            nonempty_text(evaluation.get("evidence_summary"), f"positive benchmark {key} evidence summary")
    require(benchmark.get("dataset_sha256") == sha_json(benchmark_sets), "positive benchmark execution dataset hash mismatch")
    dialogue = selection.get("dialogue_test")
    require(isinstance(dialogue, dict), "dialogue_test must be an object")
    detected_voice_lines = voice_bearing_lines(candidate_body)
    if dialogue.get("applicable") is False:
        nonempty_text(dialogue.get("reason"), "dialogue test exemption reason")
        require(dialogue.get("voice_bearing_line_count") == 0, "dialogue test exemption requires zero voice-bearing lines")
        require(not detected_voice_lines, "dialogue test cannot be exempted while the candidate contains voice-bearing lines")
        nonempty_text(dialogue.get("evidence"), "dialogue test exemption evidence")
    else:
        require(dialogue.get("scope") == "voice-bearing-only", "dialogue test covers voice-bearing lines only")
        require(dialogue.get("blinded") is True, "dialogue voice test must be blinded")
        require(dialogue.get("voice_card_provided") is True, "dialogue voice test requires a voice card")
        require(dialogue.get("prior_context_provided") is True, "dialogue voice test requires prior context")
        require(dialogue.get("global_accuracy_threshold") is False, "dialogue test cannot impose a global accuracy threshold")
        require(dialogue.get("speaker_swap_diagnostic") is True, "dialogue test requires speaker-swap diagnostic")
        require(dialogue.get("catchphrase_fix") is False, "dialogue voice cannot be repaired with catchphrases")
        require(dialogue.get("voice_bearing_line_count") == len(detected_voice_lines), "dialogue test voice-bearing line count mismatch")
        samples = dialogue.get("samples")
        require(isinstance(samples, list) and samples, "dialogue voice test requires sampled lines")
        sampled_lines: set[str] = set()
        for sample in samples:
            require(isinstance(sample, dict), "dialogue samples must be objects")
            line_digest = require_bound_text_artifact(
                sample, text_key="line_text", hash_key="line_sha256", label="dialogue sample"
            )
            require(sample["line_text"] in detected_voice_lines, "dialogue sample must equal a detected voice-bearing line")
            require(sample["line_text"] not in sampled_lines, "dialogue samples must be distinct voice-bearing lines")
            sampled_lines.add(sample["line_text"])
            for key in ("expected_speaker", "predicted_speaker", "swapped_predicted_speaker"):
                nonempty_text(sample.get(key), f"dialogue sample {key}")
            require(isinstance(sample.get("speaker_swap_changed"), bool), "dialogue sample requires a speaker-swap diagnostic result")
            require(is_sha256(line_digest), "dialogue sample hash must be SHA-256")
        dialogue_run_id = nonempty_text(dialogue.get("run_id"), "dialogue test run_id")
        require(dialogue_run_id not in execution_run_ids, "dialogue test requires an isolated execution run")
        execution_run_ids.add(dialogue_run_id)
        require(dialogue.get("input_fingerprint") == sha_json(samples), "dialogue test input fingerprint mismatch")
    variants = selection.get("variants")
    require(isinstance(variants, dict), "selection variants must be an object")
    variants_required = variants.get("premarked_key_chapter") is True or (
        pending.get("repair_scope") in {"structural", "full"}
        and pending.get("revision_intent", "defect_repair") == "defect_repair"
    )
    if variants_required:
        baseline_versions = variants.get("baseline_versions")
        candidate_versions = variants.get("candidate_versions")
        require(isinstance(baseline_versions, list) and isinstance(candidate_versions, list), "key chapter variants require both version artifact sets")
        require(len(baseline_versions) >= 2 and len(baseline_versions) == len(candidate_versions), "key chapter requires equal non-zero version counts")
        require(variants.get("baseline_count") == len(baseline_versions) and variants.get("candidate_count") == len(candidate_versions), "key chapter version counts do not match artifacts")
        baseline_hashes = [
            require_bound_text_artifact(item, text_key="body", hash_key="body_sha256", label="key chapter baseline")
            for item in baseline_versions if isinstance(item, dict)
        ]
        candidate_hashes = [
            require_bound_text_artifact(item, text_key="body", hash_key="body_sha256", label="key chapter candidate")
            for item in candidate_versions if isinstance(item, dict)
        ]
        require(len(baseline_hashes) == len(baseline_versions) and len(candidate_hashes) == len(candidate_versions), "key chapter versions must be artifact objects")
        require(len(set(baseline_hashes)) == len(baseline_hashes) and len(set(candidate_hashes)) == len(candidate_hashes), "key chapter versions must be distinct within each arm")
        require(set(baseline_hashes).isdisjoint(candidate_hashes), "key chapter baseline and candidate versions must be distinct")
        require(revision in candidate_hashes, "key chapter candidate artifacts must include the staged immutable candidate")
        if pending.get("kind") == "revision":
            require(pending.get("parent_revision") in baseline_hashes, "key chapter baseline artifacts must include the accepted parent revision")

    reader = packet.get("reader_evidence")
    require(isinstance(reader, dict), "reader_evidence must be an object")
    cohort = reader.get("cohort")
    require(isinstance(cohort, list) and len(cohort) >= 2, "reader-retention requires at least two independent readers")
    chains = copy.deepcopy(base.get("reader_chains", {}))
    normalized_cohort = []
    reader_ids: set[str] = set()
    reader_run_ids: set[str] = set()
    input_fingerprint = reader_input_fingerprint(base, pending)
    revision_sequence = reader_revision_sequence(base, pending)
    for row in cohort:
        reader_id = safe_component(row.get("reader_id") if isinstance(row, dict) else None, "reader_id")
        require(reader_id not in reader_ids, "reader cohort IDs must be distinct")
        reader_ids.add(reader_id)
        run_id = nonempty_text(row.get("run_id"), f"reader {reader_id} run_id")
        require(run_id not in execution_run_ids, "all evaluator, repairer, perspective, reader, judge, and validator runs must be globally distinct")
        reader_run_ids.add(run_id)
        execution_run_ids.add(run_id)
        previous = chains.get(reader_id, {}).get(str(chapter - 1)) if chapter > 1 else None
        if chapter > 1 and row.get("cohort_type") == "sequential":
            chain = chains.get(reader_id, {})
            require(set(chain) >= {str(number) for number in range(1, chapter)}, f"sequential reader {reader_id} must have an unbroken chapter 1..{chapter - 1} chain")
            require(previous is not None, f"new reader {reader_id} must start with a fresh replay")
        normalized, state_hash = validate_reader_state(
            row,
            chapter,
            previous,
            candidate_revision=revision,
            input_fingerprint=input_fingerprint,
            revision_sequence=revision_sequence,
            candidate_visible_chars=len(re.sub(r"\s+", "", candidate_body)),
        )
        if previous is not None and normalized.get("reader_schema") == READER_SCHEMA_V3:
            prior_state = (reader_state_overrides or {}).get(previous)
            if prior_state is None:
                require(project is not None, "reader v3 transition validation requires the quality project")
                prior_state = accepted_reader_state(project, reader_id, chapter - 1, previous)
            require(prior_state.get("reader_schema") == READER_SCHEMA_V3, "reader v3 cannot continue from a different cumulative schema")
            validate_reader_measurement_transition(prior_state["measurements"], normalized["measurements"], chapter)
        chains.setdefault(reader_id, {})[str(chapter)] = state_hash
        normalized_cohort.append(normalized)
    if chapter % 15 == 0:
        require(any(row["cohort_type"] == "fresh_replay" for row in normalized_cohort), "every 15 chapters requires at least one fresh reader replay from chapter 1")
    reader["cohort"] = normalized_cohort
    decision = reader.get("retention_decision")
    require(decision in {"pass", "review", "block"}, "invalid retention decision")
    blocking_support: dict[str, set[str]] = {}
    for row in normalized_cohort:
        if row["retention_verdict"] != "block":
            continue
        for issue_id in row["retention_issue_ids"]:
            blocking_support.setdefault(issue_id, set()).add(row["reader_id"])
    corroborated_issues = {issue_id: ids for issue_id, ids in blocking_support.items() if len(ids) >= 2}
    nonpass_readers = {row["reader_id"] for row in normalized_cohort if row["retention_verdict"] != "pass"}
    derived_decision = "block" if corroborated_issues else "review" if len(nonpass_readers) >= 2 else "pass"
    require(decision == derived_decision, "retention decision must be derived from the cohort verdicts")
    if decision == "block":
        corroborated = reader.get("corroborated_reader_ids")
        require(isinstance(corroborated, list) and len(set(corroborated)) >= 2, "one subjective reader cannot veto a chapter")
        require(set(corroborated) <= reader_ids, "retention block cites readers outside the reviewed cohort")
        blocking_ids = {row["reader_id"] for row in normalized_cohort if row["retention_verdict"] == "block"}
        require(set(corroborated) <= blocking_ids, "retention block requires the cited cohort readers to independently report block")
        cited_rows = [row for row in normalized_cohort if row["reader_id"] in set(corroborated)]
        shared_issues = set(cited_rows[0]["retention_issue_ids"])
        for row in cited_rows[1:]:
            shared_issues &= set(row["retention_issue_ids"])
        require(shared_issues, "retention block requires independently corroborated issue or fatigue IDs")
        require(shared_issues <= set(corroborated_issues), "retention block cites an issue without independent corroboration")
        nonempty_text(reader.get("corroborating_evidence"), "retention block evidence")
    if decision != "pass":
        eligible = False
    judge = reader.get("judge")
    require(isinstance(judge, dict), "reader evidence requires an independent judge")
    judge_id = nonempty_text(judge.get("judge_id"), "reader judge ID")
    judge_run_id = nonempty_text(judge.get("run_id"), "reader judge run_id")
    require(judge_id not in reader_ids, "reader judge cannot be a cohort reader")
    require(judge_run_id not in execution_run_ids, "all evaluator, repairer, perspective, reader, judge, and validator runs must be globally distinct")
    execution_run_ids.add(judge_run_id)
    judge_input = {
        "outline_sha256": pending["outline_sha256"],
        "reader_state_hashes": [row["state_hash"] for row in normalized_cohort],
    }
    require(judge.get("input_fingerprint") == sha_json(judge_input), "reader judge input is not bound to the outline oracle and reader outputs")
    require(judge.get("oracle_visible_to_readers") is False, "reader oracle must remain hidden from reader runs")
    for key in ("must_know", "may_believe", "must_not_know", "open_ids"):
        require(isinstance(judge.get(key), list), f"reader judge {key} must be a list")
    require(judge.get("status") in {"PASS", "FAIL"}, "reader judge status must be PASS/FAIL")
    require(judge.get("status") == "PASS", "reader oracle comparison did not pass")
    packet["reader_evidence"] = reader
    p0_eligible_before_strength = eligible
    packet["gate_breakdown"] = {"p0_eligible_before_strength": p0_eligible_before_strength}

    outline = packet.get("outline_contract")
    require(isinstance(outline, dict), "outline_contract must be an object")
    for key in ("ending_beat_id", "expectation_id"):
        nonempty_text(outline.get(key), f"outline_contract.{key}")
    require(outline.get("ending_beat_type") in ENDING_TYPES, "invalid ending beat type")
    require(outline.get("expectation_type") in ENDING_TYPES, "invalid expectation type")
    require(outline == pending.get("outline_contract"), "review outline contract does not match the staged fine outline")

    derived_strength = derive_strength_gate(pending, policy, normalized_cohort)
    supplied_strength = packet.get("strength_gate")
    if supplied_strength is None:
        require(policy["strength_mode"] == "SHADOW", "ENFORCE policy requires an explicit derived strength_gate")
        packet["strength_gate"] = derived_strength
    else:
        require(isinstance(supplied_strength, dict), "strength_gate must be an object")
        require(supplied_strength.get("derived") is True, "strength_gate must be recorded as a derived result")
        for key in ("mode", "status", "policy_sha256", "chapter_function", "reason_codes", "persona_results"):
            require(supplied_strength.get(key) == derived_strength.get(key), f"strength_gate {key} does not match reader evidence")
        packet["strength_gate"] = {**derived_strength, "derived": True}
    packet["strength_gate"].setdefault("derived", True)
    if policy["strength_mode"] == "ENFORCE" and packet["strength_gate"]["status"] != "PASS":
        eligible = False

    extraction = packet.get("posthoc_extraction")
    require(isinstance(extraction, dict) and extraction.get("complete") is True, "writer-isolated post-hoc extraction must be complete")
    require(isinstance(extraction.get("observations"), list) and extraction["observations"], "cold observations must contain evidence from the completed chapter")
    for observation in extraction["observations"]:
        require(isinstance(observation, dict), "cold observations must be objects")
        nonempty_text(observation.get("evidence"), "cold observation evidence")
    events = extraction.get("authoritative_events")
    require(isinstance(events, list), "authoritative_events must be a list")
    prior_index = {
        key: value
        for key, value in base.get("event_index", {}).items()
        if pending.get("kind") != "revision" or int(value.get("chapter", 0)) < chapter
    }
    event_ids: set[str] = set()
    extracted_tracking_ids: set[str] = set()
    for event in events:
        require(isinstance(event, dict), "authoritative events must be objects")
        event_id = nonempty_text(event.get("id"), "event.id")
        require(event_id not in event_ids, f"duplicate authoritative event ID {event_id}")
        require(event_id not in prior_index, f"authoritative event ID already exists in accepted history: {event_id}")
        event_ids.add(event_id)
        require(event.get("kind") in EVENT_KINDS, f"invalid event kind for {event_id}")
        require(event.get("confidence") in {"explicit", "strongly_implied"}, f"invalid event confidence for {event_id}")
        require(event.get("occurrence_state") == "occurred", f"future plans cannot enter occurred event ledger: {event_id}")
        nonempty_text(event.get("evidence"), f"event {event_id} evidence")
        tracking_event_id = nonempty_text(event.get("tracking_event_id"), f"event {event_id} tracking_event_id")
        require(tracking_event_id not in extracted_tracking_ids, f"tracking event {tracking_event_id} is extracted more than once")
        extracted_tracking_ids.add(tracking_event_id)
        tracking_fingerprint = nonempty_text(
            event.get("tracking_event_fingerprint"), f"event {event_id} tracking_event_fingerprint"
        )
        require(is_sha256(tracking_fingerprint), f"event {event_id} tracking fingerprint must be SHA-256")
        binding = None
        if tracking_events is not None:
            binding = tracking_events.get(tracking_event_id)
            require(binding is not None, f"event {event_id} is not reconciled to the accepted tracking transaction")
            require(binding.get("chapter") == chapter, f"event {event_id} is bound to a tracking fact from another chapter")
            require(
                binding.get("fingerprint") == tracking_fingerprint,
                f"event {event_id} contradicts the bound tracking fact",
            )
        require(isinstance(event.get("data"), dict), f"event {event_id} data must be an object")
        if event["kind"] == "relation":
            for key in ("subject", "object", "relation", "before", "after", "trigger"):
                nonempty_text(event["data"].get(key), f"relation event {event_id} data.{key}")
            matching = [
                value for value in prior_index.values()
                if value.get("kind") == "relation"
                and all(value.get("data", {}).get(key) == event["data"].get(key) for key in ("subject", "object", "relation"))
            ]
            if matching:
                latest = max(matching, key=lambda value: int(value["chapter"]))
                require(event["data"]["before"] == latest["data"]["after"], f"relation event {event_id} breaks the accepted before/after chain")
        if event["kind"] == "arc":
            for key in ("character", "dimension", "before", "after", "trigger"):
                nonempty_text(event["data"].get(key), f"arc event {event_id} data.{key}")
            matching = [
                value for value in prior_index.values()
                if value.get("kind") == "arc"
                and all(value.get("data", {}).get(key) == event["data"].get(key) for key in ("character", "dimension"))
            ]
            if matching:
                latest = max(matching, key=lambda value: int(value["chapter"]))
                require(event["data"]["before"] == latest["data"]["after"], f"arc event {event_id} breaks the accepted before/after chain")
        if event["kind"] == "knowledge":
            data = event["data"]
            for key in ("character", "fact_id", "state", "source"):
                nonempty_text(data.get(key), f"knowledge event {event_id} data.{key}")
            require(data["state"] in KNOWLEDGE_STATES, f"knowledge event {event_id} state is invalid")
            source_chapter = integer(data.get("source_chapter"), f"knowledge event {event_id} source_chapter", minimum=1, maximum=chapter)
            occurrence_order = integer(data.get("occurrence_order"), f"knowledge event {event_id} occurrence_order", minimum=1)
            if source_chapter == chapter:
                source_order = integer(data.get("source_order"), f"knowledge event {event_id} source_order", minimum=1)
                require(source_order <= occurrence_order, f"knowledge event {event_id} source occurs after the knowledge state")
            if isinstance(binding, dict) and isinstance(binding.get("event"), dict):
                tracked = binding["event"]
                require(tracked.get("kind") == "knowledge" and tracked.get("occurrence_order") == occurrence_order, f"knowledge event {event_id} does not match tracking order/kind")
                require(tracked.get("knowledge") == {key: data.get(key) for key in ("character", "fact_id", "state", "source", "source_chapter", "source_order")}, f"knowledge event {event_id} contradicts tracking knowledge state")
        if event["kind"] == "open_question":
            data = event["data"]
            nonempty_text(data.get("open_id"), f"open question {event_id} data.open_id")
            require(data.get("state") in {"open", "payoff", "paused", "superseded"}, f"open question {event_id} state is invalid")
            planned = data.get("planned_payoff_chapter")
            require(planned is None or (isinstance(planned, int) and planned >= chapter), f"open question {event_id} planned payoff chapter is invalid")

    prerequisites = extraction.get("knowledge_prerequisites", [])
    require(isinstance(prerequisites, list), "knowledge_prerequisites must be a list")
    current_knowledge = {event["id"]: event for event in events if event.get("kind") == "knowledge"}
    for index, premise in enumerate(prerequisites):
        require(isinstance(premise, dict), "knowledge prerequisite rows must be objects")
        nonempty_text(premise.get("action_id"), f"knowledge_prerequisites[{index}].action_id")
        character = nonempty_text(premise.get("character"), f"knowledge_prerequisites[{index}].character")
        fact_id = nonempty_text(premise.get("fact_id"), f"knowledge_prerequisites[{index}].fact_id")
        action_order = integer(premise.get("action_occurrence_order"), f"knowledge_prerequisites[{index}].action_occurrence_order", minimum=1)
        source_event_id = nonempty_text(premise.get("source_event_id"), f"knowledge_prerequisites[{index}].source_event_id")
        source = current_knowledge.get(source_event_id) or prior_index.get(source_event_id)
        require(isinstance(source, dict) and source.get("kind") == "knowledge", f"action premise {fact_id} has no traceable knowledge event")
        source_data = source.get("data", {})
        require(source_data.get("character") == character and source_data.get("fact_id") == fact_id, f"action premise {fact_id} is bound to the wrong character/fact")
        source_chapter = int(source.get("chapter", chapter))
        require(source_chapter < chapter or int(source_data.get("occurrence_order", 0)) < action_order, f"action premise {fact_id} is learned after the action that uses it")

    if tracking_events is not None:
        require(
            extracted_tracking_ids == set(tracking_events),
            "authoritative event extraction must cover every same-chapter tracking fact exactly once",
        )

    validator = packet.get("final_validation")
    require(isinstance(validator, dict) and validator.get("status") == "PASS", "final validator must PASS")
    require(validator.get("validator") == roles["final_validator"], "final validator identity mismatch")
    execution = validator.get("execution")
    require(isinstance(execution, dict), "final validator requires execution evidence")
    require(execution.get("run_id") == roles["final_validator"], "final validator run identity mismatch")
    require(execution.get("candidate_revision") == revision, "final validator is not bound to the candidate revision")
    require(execution.get("input_fingerprint") == expected_input_fingerprint, "final validator input fingerprint mismatch")
    require(isinstance(execution.get("reviewed_units"), list) and execution["reviewed_units"], "final validator must name reviewed units")
    nonempty_text(execution.get("evidence_summary"), "final validator evidence summary")
    return packet, eligible


def apply_event_index(manifest: dict[str, Any], packet: dict[str, Any], *, replace_from: int | None = None) -> None:
    index = manifest.setdefault("event_index", {})
    if replace_from is not None:
        for event_id in [key for key, value in index.items() if int(value.get("chapter", 0)) >= replace_from]:
            del index[event_id]
    chapter = packet["chapter"]
    for event in packet["posthoc_extraction"]["authoritative_events"]:
        index[event["id"]] = {"chapter": chapter, "revision": packet["revision"], **copy.deepcopy(event)}


def pending_tracking_bindings(
    project: Path,
    pending_dir: Path,
    pending: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    transaction_path = pending_dir / "tracking-transaction.json"
    require(
        sha_file(transaction_path) == pending.get("tracking_transaction_sha256"),
        "tracking transaction changed after staging",
    )
    transaction = read_json(transaction_path, "tracking transaction")
    require(transaction.get("wordcount") is None, "staged tracking transaction must omit derived wordcount evidence")
    tracking_module = load_tracking_module()
    snapshot_state = tracking_module.normalize_state(read_json(
        generation_dir(project, pending["base_generation"]) / "tracking/_tracking-state.json",
        "accepted tracking snapshot",
    ))
    normalized_transaction = tracking_module.normalize_transaction(project, snapshot_state, transaction)
    for event in normalized_transaction["delta"]["timeline_events"]:
        previous = snapshot_state.get("timeline", {}).get(event.get("id"))
        if event.get("action", "upsert") != "delete" and isinstance(previous, dict):
            require(
                previous.get("first_recorded_chapter") == pending["chapter"],
                f"tracking event {event['id']} belongs to another chapter; record a new global event ID",
            )
    return normalized_transaction, tracking_event_bindings(
        normalized_transaction["delta"]["timeline_events"], pending["chapter"]
    )


def certify(project: Path, pending_id: str, packet_path: Path) -> dict[str, Any]:
    project = project.resolve()
    root = quality_root(project)
    pending_id = safe_component(pending_id, "pending_id")
    pending_dir = root / "pending" / pending_id
    pending = read_json(pending_dir / "pending.json", "pending generation")
    require(head_record(project)["generation_id"] == pending["base_generation"], "pending generation is based on stale HEAD")
    base = manifest_for(project, pending["base_generation"])
    require_fresh(base, "certify a chapter")
    require(check(project)["status"] == "pass", "accepted projections differ from HEAD; run rebuild before certification")
    packet = read_json(packet_path, "review packet")
    _, tracking_events = pending_tracking_bindings(project, pending_dir, pending)
    candidate_path, _ = revision_paths(root, pending["chapter"], pending["revision"])
    require(sha_file(candidate_path) == pending["revision"], "staged candidate revision body hash mismatch")
    normalized, eligible = validate_review_packet(
        packet,
        pending,
        base,
        tracking_events=tracking_events,
        candidate_body=candidate_path.read_text(encoding="utf-8"),
        project=project,
    )
    packet_sha256 = sha_json(normalized)
    strength = normalized["strength_gate"]
    p0_eligible = normalized.get("gate_breakdown", {}).get("p0_eligible_before_strength") is True
    if not p0_eligible:
        selection_status = "FIX_FAILED" if pending["kind"] == "revision" else "REJECTED"
    elif strength["mode"] == "ENFORCE" and strength["status"] == "FLAT":
        selection_status = "REOPEN_REQUIRED"
    elif strength["mode"] == "ENFORCE" and strength["status"] == "INSUFFICIENT_EVIDENCE":
        selection_status = "EVIDENCE_REQUIRED"
    elif eligible:
        selection_status = "ACCEPT_CANDIDATE"
    else:
        selection_status = "FIX_FAILED" if pending["kind"] == "revision" else "REJECTED"
    certificate = {
        "schema": SCHEMA,
        "pending_sha256": sha_json(pending),
        "eligible": eligible,
        "selection_status": selection_status,
        "strength_mode": strength["mode"],
        "strength_status": strength["status"],
        "p0_eligible_before_strength": p0_eligible,
        "packet_sha256": packet_sha256,
        "packet": normalized,
        "certified_at": now(),
    }
    path = pending_dir / "certificate.json"
    if path.exists():
        existing = read_json(path, "certificate")
        require(
            existing.get("packet_sha256") == packet_sha256
            and existing.get("pending_sha256") == sha_json(pending)
            and existing.get("eligible") == eligible
            and existing.get("selection_status") == selection_status,
            "certificate is immutable; stage a new pending generation",
        )
        certificate = existing
    else:
        atomic_json(path, certificate)
    return {
        "schema": SCHEMA,
        "status": "certified",
        "pending_id": pending_id,
        "eligible": eligible,
        "selection_status": selection_status,
        "strength_mode": strength["mode"],
        "strength_status": strength["status"],
    }


def load_storyctl() -> Any:
    path = Path(__file__).with_name("storyctl.py")
    spec = importlib.util.spec_from_file_location("story_quality_storyctl", path)
    require(spec is not None and spec.loader is not None, "unable to load storyctl.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_tracking_module() -> Any:
    path = Path(__file__).with_name("tracking_commit.py")
    spec = importlib.util.spec_from_file_location("story_quality_tracking", path)
    require(spec is not None and spec.loader is not None, "unable to load tracking_commit.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def tracking_accept(project: Path, base_generation: str, pending_dir: Path, pending: dict[str, Any]) -> tuple[dict[str, Any], Path, tempfile.TemporaryDirectory[str]]:
    holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(prefix="story-quality-accept-")
    sandbox = Path(holder.name)
    (sandbox / "正文").mkdir()
    (sandbox / "大纲").mkdir()
    source_outline = outline_file(project, pending["chapter"])
    require(sha_file(source_outline) == pending["outline_sha256"], "fine outline changed after staging")
    shutil.copy2(source_outline, sandbox / "大纲" / source_outline.name)
    revision_body, _ = revision_paths(quality_root(project), pending["chapter"], pending["revision"])
    shutil.copy2(revision_body, sandbox / "正文" / pending["filename"])
    shutil.copytree(generation_dir(project, base_generation) / "tracking", sandbox / "追踪")
    transaction = pending_dir / "tracking-transaction.json"
    require(sha_file(transaction) == pending["tracking_transaction_sha256"], "tracking transaction changed after staging")
    storyctl = load_storyctl()
    try:
        result = storyctl.chapter_commit(
            sandbox,
            pending["chapter"],
            transaction,
            accept_current_length=pending["length_resolution"] == "accepted_current_length",
        )
    except Exception as exc:
        holder.cleanup()
        raise QualityError(f"deterministic chapter/tracking validation failed: {exc}") from exc
    return result, sandbox / "追踪", holder


def copy_certificate_artifacts(project: Path, manifest: dict[str, Any], certificate: dict[str, Any]) -> None:
    root = quality_root(project)
    packet = certificate["packet"]
    chapter = packet["chapter"]
    revision = packet["revision"]
    certificate_key = certificate["packet_sha256"]
    review_path = root / "reviews" / f"chapter-{chapter:06d}" / f"{revision}-{certificate_key[:12]}.json"
    event_path = root / "events" / f"chapter-{chapter:06d}" / f"{revision}-{certificate_key[:12]}.json"
    if not review_path.exists():
        atomic_json(review_path, certificate)
    if not event_path.exists():
        atomic_json(event_path, packet["posthoc_extraction"])
    for state in packet["reader_evidence"]["cohort"]:
        reader_path = root / "readers" / state["reader_id"] / f"chapter-{chapter:06d}-{revision[:12]}-{certificate_key[:12]}.json"
        if not reader_path.exists():
            atomic_json(reader_path, state)


def recovery_target(project: Path, generation_id: str, area: str, relative: Path) -> Path:
    base = quality_root(project) / "recovered-projections" / generation_id / area / relative
    if not base.exists():
        return base
    return base.with_name(f"{base.name}.{sha_file(base)[:12]}")


def move_recoverable(project: Path, source: Path, generation_id: str, area: str, relative: Path) -> None:
    target = recovery_target(project, generation_id, area, relative)
    require_safe_projection_target(quality_root(project), target, "recovery target")
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, target)


def materialize_manifest(project: Path, manifest: dict[str, Any]) -> None:
    project = project.resolve()
    require_projection_roots_safe(project)
    root = quality_root(project)
    generation_id = manifest["generation_id"]
    generation = generation_dir(project, generation_id)
    desired_paths: set[Path] = set()
    for key, entry in manifest["chapters"].items():
        chapter = int(key)
        body, _ = revision_paths(root, chapter, entry["revision"])
        target = project / "正文" / entry["filename"]
        require_safe_projection_target(project, target, "正文 projection target")
        desired_paths.add(target.absolute())
        atomic_bytes(target, body.read_bytes())
    for path in chapter_files(project):
        require_safe_projection_target(project, path, "正文 projection file")
        if path.absolute() not in desired_paths:
            move_recoverable(project, path, generation_id, "正文", Path(path.name))

    snapshot = generation / "tracking"
    snapshot_files = {
        path.relative_to(snapshot)
        for path in snapshot.rglob("*")
        if path.is_file() and path.relative_to(snapshot) not in TRACKING_RUNTIME_FILES
    }
    live_tracking = project / "追踪"
    tracking = load_tracking_module()
    with tracking.project_write_lock(project):
        for relative in sorted(snapshot_files):
            target = live_tracking / relative
            require_safe_projection_target(project, target, "追踪 projection target")
            atomic_bytes(target, (snapshot / relative).read_bytes())
        for path in sorted((item for item in live_tracking.rglob("*") if item.is_file()), reverse=True):
            require_safe_projection_target(project, path, "追踪 projection file")
            relative = path.relative_to(live_tracking)
            if relative in TRACKING_RUNTIME_FILES or relative in snapshot_files:
                continue
            move_recoverable(project, path, generation_id, "追踪", relative)

    quality = generation / "quality"
    for area in ("reviews", "events", "readers"):
        source_root = quality / area
        if not source_root.is_dir():
            continue
        for source in (path for path in source_root.rglob("*") if path.is_file()):
            relative = source.relative_to(source_root)
            target = root / area / relative
            require_safe_projection_target(root, target, f"quality {area} projection target")
            if not target.exists():
                atomic_bytes(target, source.read_bytes())
    atomic_json(root / "PROJECTION.json", {"generation_id": generation_id, "materialized_at": now()})


def materialize(project: Path, old: dict[str, Any], new: dict[str, Any]) -> None:
    del old
    materialize_manifest(project, new)


def rebuild(project: Path) -> dict[str, Any]:
    project = project.resolve()
    head = head_record(project)
    manifest = manifest_for(project, head["generation_id"])
    generation = generation_dir(project, head["generation_id"])
    require(tree_hash(generation / "tracking") == manifest["tracking_tree_sha256"], "accepted tracking snapshot hash mismatch")
    require(tree_hash(generation / "quality") == manifest["quality_tree_sha256"], "accepted quality artifact hash mismatch")
    materialize_manifest(project, manifest)
    return {"schema": SCHEMA, "status": "rebuilt", "generation_id": head["generation_id"], "chapters": len(manifest["chapters"])}


def accept(project: Path, pending_id: str) -> dict[str, Any]:
    project = project.resolve()
    root = quality_root(project)
    pending_id = safe_component(pending_id, "pending_id")
    pending_dir = root / "pending" / pending_id
    pending = read_json(pending_dir / "pending.json", "pending generation")
    require(pending.get("simulation_only") is not True, "SHADOW simulation candidates cannot advance the accepted HEAD")
    certificate = read_json(pending_dir / "certificate.json", "review certificate")
    head = head_record(project)
    require(head["generation_id"] == pending["base_generation"], "pending generation is based on stale HEAD")
    base = manifest_for(project, head["generation_id"])
    require_fresh(base, "accept a chapter")
    require(check(project)["status"] == "pass", "accepted projections differ from HEAD; run rebuild before accept")
    require(certificate.get("schema") == SCHEMA, "review certificate schema mismatch")
    require(certificate.get("pending_sha256") == sha_json(pending), "pending generation changed after certification")
    packet = certificate.get("packet")
    require(isinstance(packet, dict), "review certificate packet must be an object")
    require(certificate.get("packet_sha256") == sha_json(packet), "review certificate packet hash mismatch")
    _, tracking_events = pending_tracking_bindings(project, pending_dir, pending)
    candidate_path, _ = revision_paths(root, pending["chapter"], pending["revision"])
    require(sha_file(candidate_path) == pending["revision"], "staged candidate revision body hash mismatch")
    if pending.get("treatment_run_id") is not None:
        treatment_run = load_treatment_run(project, pending["treatment_run_id"], require_closed=True)
        opened = treatment_run["open"]
        closed = treatment_run["close"]
        assert isinstance(closed, dict)
        require(opened["treatment"] == pending.get("treatment"), "pending treatment differs from its immutable run")
        require(opened["start_boundary_sha256"] == pending.get("treatment_start_boundary_sha256"), "pending treatment start boundary mismatch")
        require(closed["close_boundary_sha256"] == pending.get("treatment_close_boundary_sha256"), "pending treatment close boundary mismatch")
        require(opened["chapter"] == pending["chapter"] and opened["base_generation"] == pending["base_generation"], "pending treatment run scope mismatch")
        require(opened["outline_sha256"] == pending["outline_sha256"], "pending treatment outline mismatch")
        require(closed["selected_body_sha256"] == pending["revision"], "pending revision is not the closed treatment winner")
    revalidated, eligible = validate_review_packet(
        copy.deepcopy(packet),
        pending,
        base,
        tracking_events=tracking_events,
        candidate_body=candidate_path.read_text(encoding="utf-8"),
        project=project,
    )
    require(sha_json(revalidated) == certificate["packet_sha256"], "review certificate changed after certification")
    require(certificate.get("eligible") is eligible, "review certificate eligibility does not match its packet")
    require(eligible is True, "blind selection kept the previous version; candidate cannot be accepted")
    gid = generation_id(f"accept:{pending_id}:{certificate['packet_sha256']}")
    derived_index_updates = (
        prepare_derived_index_invalidations(project, pending["chapter"], gid)
        if pending["kind"] == "revision" else []
    )
    result, tracking_source, holder = tracking_accept(project, head["generation_id"], pending_dir, pending)
    try:
        manifest = copy.deepcopy(base)
        manifest.update({
            "generation_id": gid,
            "previous_generation": head["generation_id"],
            "created_at": now(),
            "reason": pending.get("revision_intent") or pending["kind"],
            "status": "accepted",
        })
        _, revision_metadata = revision_paths(root, pending["chapter"], pending["revision"])
        require(sha_file(revision_metadata) == pending["revision_metadata_sha256"], "revision metadata changed after staging")
        chapter_record = {
            "revision": pending["revision"],
            "filename": pending["filename"],
            "metadata_sha256": pending["revision_metadata_sha256"],
        }
        if pending.get("treatment_run_id") is not None:
            chapter_record["treatment_provenance"] = {
                "treatment": pending["treatment"],
                "run_id": pending["treatment_run_id"],
                "start_boundary_sha256": pending["treatment_start_boundary_sha256"],
                "close_boundary_sha256": pending["treatment_close_boundary_sha256"],
            }
        manifest["chapters"][str(pending["chapter"])] = chapter_record
        last_chapter = max((int(key) for key in manifest["chapters"]), default=0)
        invalidation = None
        if pending["kind"] == "revision":
            invalidation = {
                "from_chapter": pending["chapter"],
                "through_chapter": last_chapter,
                "artifacts": ["reader_chain", "quality_certificates", "facts", "knowledge", "relations", "arcs", "cumulative_certificates", "checkpoints", "suspense_debt", "structural_benchmarks"],
                "note": "revalidation does not authorize downstream prose rewriting",
            }
            for key, value in manifest["quality_certificates"].items():
                if int(key) >= pending["chapter"]:
                    value["status"] = "stale"
            stale_from = pending["chapter"] + 1 if last_chapter > pending["chapter"] else None
            manifest["stale"] = {"reader_from": stale_from, "quality_from": stale_from, "semantic_replay_from": stale_from}
            apply_event_index(manifest, certificate["packet"], replace_from=pending["chapter"])
        else:
            manifest["stale"] = {"reader_from": None, "quality_from": None, "semantic_replay_from": None}
            apply_event_index(manifest, certificate["packet"])
        manifest["invalidation"] = invalidation
        manifest["quality_certificates"][str(pending["chapter"])] = {
            "revision": pending["revision"],
            "packet_sha256": certificate["packet_sha256"],
            "status": "fresh",
            "strength_status": certificate.get("strength_status"),
            "quality_policy_sha256": pending.get("quality_policy_sha256"),
        }
        for state in certificate["packet"]["reader_evidence"]["cohort"]:
            manifest.setdefault("reader_chains", {}).setdefault(state["reader_id"], {})[str(pending["chapter"])] = state["state_hash"]
        create_generation(
            project,
            manifest,
            tracking_source,
            quality_source=generation_dir(project, head["generation_id"]) / "quality",
            certificates=[certificate],
        )
        copy_certificate_artifacts(project, manifest, certificate)
        apply_prepared_derived_index_invalidations(derived_index_updates)
        switch_head(project, manifest)
        materialize(project, base, manifest)
    finally:
        holder.cleanup()
    return {
        "schema": SCHEMA,
        "status": "accepted" if manifest["stale"]["reader_from"] is None else "accepted_replay_required",
        "generation_id": gid,
        "chapter": pending["chapter"],
        "revision": pending["revision"],
        "tracking_state_revision": result["state_revision"],
        "stale": manifest["stale"],
    }


def replay(project: Path, input_path: Path) -> dict[str, Any]:
    """Revalidate a stale downstream range without rewriting accepted prose."""
    project = project.resolve()
    document = read_json(input_path, "replay packet")
    require(document.get("schema") == REPLAY_SCHEMA, f"replay schema must be {REPLAY_SCHEMA}")
    head = head_record(project)
    base = manifest_for(project)
    require(check(project)["status"] == "replay_required", "accepted projections differ from HEAD; run rebuild before replay")
    start = base["stale"].get("reader_from")
    require(isinstance(start, int), "accepted HEAD has no stale replay range")
    last = max((int(key) for key in base["chapters"]), default=0)
    packets = document.get("packets")
    require(isinstance(packets, list), "replay packets must be a list")
    require([row.get("chapter") for row in packets if isinstance(row, dict)] == list(range(start, last + 1)), f"replay must cover every chapter {start}..{last} in order")
    working = copy.deepcopy(base)
    tracking_holder: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory(prefix="story-quality-replay-")
    tracking_project = Path(tracking_holder.name)
    tracking_source = tracking_project / "追踪"
    shutil.copytree(generation_dir(project, head["generation_id"]) / "tracking", tracking_source)
    tracking_transactions = document.get("tracking_transactions", [])
    require(isinstance(tracking_transactions, list), "replay tracking_transactions must be a list")
    tracking_module = load_tracking_module()
    transactions_by_chapter: dict[int, dict[str, Any]] = {}
    for transaction in tracking_transactions:
        require(isinstance(transaction, dict), "replay tracking transactions must be objects")
        require(transaction.get("mode") == "revision", "replay may reconcile tracking only with revision transactions")
        require(transaction.get("chapter") in range(start, last + 1), "replay tracking transaction chapter is outside the stale range")
        chapter = int(transaction["chapter"])
        require(chapter not in transactions_by_chapter, f"replay has multiple tracking transactions for chapter {chapter}")
        transactions_by_chapter[chapter] = transaction
    certificates: list[dict[str, Any]] = []
    reader_state_overrides: dict[str, dict[str, Any]] = {}
    for packet in packets:
        chapter = packet["chapter"]
        transaction = transactions_by_chapter.get(chapter)
        if transaction is not None:
            state_before = tracking_module.load_state(tracking_project)
            normalized_transaction = tracking_module.normalize_transaction(tracking_project, state_before, transaction)
            for event in normalized_transaction["delta"]["timeline_events"]:
                previous = state_before.get("timeline", {}).get(event.get("id"))
                if event.get("action", "upsert") != "delete" and isinstance(previous, dict):
                    require(
                        previous.get("first_recorded_chapter") == chapter,
                        f"tracking event {event['id']} belongs to another chapter; record a new global event ID",
                    )
            tracking_module.apply_transaction(tracking_project, transaction)
        tracking_state = tracking_module.load_state(tracking_project)
        timeline = tracking_state.get("timeline", {})
        future_mutations = [
            event_id
            for event_id, event in timeline.items()
            if isinstance(event_id, str)
            and isinstance(event, dict)
            and event.get("first_recorded_chapter") == chapter
            and event.get("updated_chapter") != chapter
        ] if isinstance(timeline, dict) else []
        require(
            not future_mutations,
            f"replay chapter {chapter} contains facts mutated by a later chapter; replace them with new global event IDs: {future_mutations}",
        )
        tracking_events = {
            event_id: {
                "chapter": chapter,
                "fingerprint": tracking_event_fingerprint(event),
                "event": copy.deepcopy(event),
            }
            for event_id, event in timeline.items()
            if isinstance(event_id, str)
            and isinstance(event, dict)
            and event.get("first_recorded_chapter") == chapter
        } if isinstance(timeline, dict) else {}
        entry = working["chapters"][str(chapter)]
        outline = outline_file(project, chapter)
        prior_certificate = working.get("quality_certificates", {}).get(str(chapter), {})
        prior_policy_sha256 = prior_certificate.get("quality_policy_sha256") if isinstance(prior_certificate, dict) else None
        if is_sha256(prior_policy_sha256):
            policy, policy_sha256 = policy_by_hash(project, prior_policy_sha256)
        else:
            policy, policy_sha256 = persist_policy_version(
                project,
                default_policy(generation=working.get("generation_id")),
            )
        pseudo = {
            "chapter": chapter,
            "revision": entry["revision"],
            "parent_revision": None,
            "kind": "replay",
            "outline_sha256": sha_file(outline),
            "outline_contract": outline_contract(outline),
            "quality_policy": policy,
            "quality_policy_sha256": policy_sha256,
        }
        normalized, eligible = validate_review_packet(
            copy.deepcopy(packet),
            pseudo,
            working,
            tracking_events=tracking_events,
            candidate_body=revision_paths(quality_root(project), chapter, entry["revision"])[0].read_text(encoding="utf-8"),
            project=project,
            reader_state_overrides=reader_state_overrides,
        )
        require(eligible, f"replay chapter {chapter} did not pass holistic/retention selection")
        for state in normalized["reader_evidence"]["cohort"]:
            reader_state_overrides[state["state_hash"]] = state
        certificate = {
            "schema": SCHEMA,
            "eligible": True,
            "selection_status": "ACCEPT_CANDIDATE",
            "strength_mode": normalized["strength_gate"]["mode"],
            "strength_status": normalized["strength_gate"]["status"],
            "packet_sha256": sha_json(normalized),
            "packet": normalized,
            "certified_at": now(),
        }
        certificates.append(certificate)
        apply_event_index(working, normalized)
        working["quality_certificates"][str(chapter)] = {
            "revision": entry["revision"],
            "packet_sha256": certificate["packet_sha256"],
            "status": "fresh",
            "strength_status": certificate.get("strength_status"),
            "quality_policy_sha256": policy_sha256,
        }
        for state in normalized["reader_evidence"]["cohort"]:
            working.setdefault("reader_chains", {}).setdefault(state["reader_id"], {})[str(chapter)] = state["state_hash"]
    gid = generation_id(f"replay:{head['generation_id']}:{sha_file(input_path)}")
    working.update({
        "generation_id": gid,
        "previous_generation": head["generation_id"],
        "created_at": now(),
        "reason": "sequential_replay",
        "status": "accepted",
        "stale": {"reader_from": None, "quality_from": None, "semantic_replay_from": None},
        "legacy_audit_required": False,
        "replay_completed": {"from_chapter": start, "through_chapter": last, "completed_at": now()},
    })
    create_generation(
        project,
        working,
        tracking_source,
        quality_source=generation_dir(project, head["generation_id"]) / "quality",
        certificates=certificates,
    )
    for certificate in certificates:
        copy_certificate_artifacts(project, working, certificate)
    switch_head(project, working)
    materialize(project, base, working)
    tracking_holder.cleanup()
    return {"schema": SCHEMA, "status": "replayed", "generation_id": gid, "from_chapter": start, "through_chapter": last}


def check(project: Path) -> dict[str, Any]:
    project = project.resolve()
    require_projection_roots_safe(project)
    root = quality_root(project)
    head = head_record(project)
    manifest = manifest_for(project, head["generation_id"])
    generation = generation_dir(project, head["generation_id"])
    require(tree_hash(generation / "tracking") == manifest["tracking_tree_sha256"], "accepted tracking snapshot hash mismatch")
    require(tree_hash(generation / "quality") == manifest["quality_tree_sha256"], "accepted quality artifact hash mismatch")
    projection = read_json(root / "PROJECTION.json", "projection marker")
    require(projection.get("generation_id") == head["generation_id"], "projections are not materialized from accepted HEAD")
    for key, entry in manifest["chapters"].items():
        chapter = int(key)
        body, metadata = revision_paths(root, chapter, entry["revision"])
        require(body.is_file() and metadata.is_file(), f"missing immutable revision for chapter {chapter}")
        require(sha_file(body) == entry["revision"], f"immutable revision hash mismatch for chapter {chapter}")
        require(sha_file(metadata) == entry.get("metadata_sha256"), f"immutable revision metadata hash mismatch for chapter {chapter}")
        revision_metadata = read_json(metadata, f"revision metadata for chapter {chapter}")
        require(revision_metadata.get("chapter") == chapter and revision_metadata.get("revision") == entry["revision"], f"revision metadata identity mismatch for chapter {chapter}")
        official = chapter_files(project, chapter)
        require(len(official) == 1, f"chapter {chapter} must have exactly one accepted body projection")
        require(official[0].name == entry["filename"] and sha_file(official[0]) == entry["revision"], f"chapter {chapter} projection differs from HEAD")
    projected_chapters = {chapter_number(path) for path in chapter_files(project)}
    accepted_chapters = {int(key) for key in manifest["chapters"]}
    require(projected_chapters == accepted_chapters, "正文 projection contains an unaccepted or missing chapter")
    snapshot = generation / "tracking"
    expected_tracking = {
        path.relative_to(snapshot)
        for path in snapshot.rglob("*")
        if path.is_file() and path.relative_to(snapshot) not in TRACKING_RUNTIME_FILES
    }
    for source in (
        path
        for path in snapshot.rglob("*")
        if path.is_file() and path.relative_to(snapshot) not in TRACKING_RUNTIME_FILES
    ):
        relative = source.relative_to(snapshot)
        target = project / "追踪" / relative
        require_safe_projection_target(project, target, "追踪 projection target")
        require(target.is_file() and sha_file(target) == sha_file(source), f"tracking projection differs from HEAD: {relative}")
    live_tracking = {
        path.relative_to(project / "追踪")
        for path in (project / "追踪").rglob("*")
        if path.is_file() and path.relative_to(project / "追踪") not in TRACKING_RUNTIME_FILES
    }
    require(live_tracking == expected_tracking, "追踪 projection contains an extra or missing file")
    stale = manifest["stale"]
    stale_from = min((value for value in stale.values() if isinstance(value, int)), default=None)
    for chapter in accepted_chapters:
        certificate = manifest.get("quality_certificates", {}).get(str(chapter))
        if stale_from is not None and chapter >= stale_from:
            continue
        require(isinstance(certificate, dict) and certificate.get("status") == "fresh", f"accepted chapter {chapter} lacks a fresh quality certificate")
    active_policy(project)
    status = "pass" if not any(value is not None for value in stale.values()) else "replay_required"
    return {"schema": SCHEMA, "status": status, "generation_id": head["generation_id"], "chapters": len(manifest["chapters"]), "stale": stale}


def hot_context(project: Path, dependencies_path: Path) -> dict[str, Any]:
    dependencies = read_json(dependencies_path, "outline dependencies")
    event_ids = set(dependencies.get("event_ids", []))
    characters = set(dependencies.get("characters", []))
    kinds = set(dependencies.get("kinds", EVENT_KINDS))
    require(kinds <= EVENT_KINDS, "outline dependencies contain unknown event kinds")
    manifest = manifest_for(project)
    require_fresh(manifest, "build hot context")
    require(check(project)["status"] == "pass", "accepted projections differ from HEAD; run rebuild before building hot context")
    selected = []
    for key, entry in sorted(manifest["chapters"].items(), key=lambda item: int(item[0])):
        certificate = manifest.get("quality_certificates", {}).get(key)
        if not certificate or certificate.get("status") != "fresh":
            continue
        path = generation_dir(project, manifest["generation_id"]) / "quality/events" / f"chapter-{int(key):06d}" / f"{entry['revision']}-{certificate['packet_sha256'][:12]}.json"
        if not path.is_file():
            continue
        extraction = read_json(path, "event extraction")
        for event in extraction.get("authoritative_events", []):
            data = event.get("data", {})
            names = {str(data.get("subject", "")), str(data.get("object", "")), str(data.get("character", ""))}
            if event["kind"] in kinds and (event["id"] in event_ids or characters & names):
                selected.append({**event, "chapter": int(key), "revision": entry["revision"]})
    require(len(selected) <= 128, "hot context exceeds the 128-event bound; narrow outline dependencies")
    result = {"schema": SCHEMA, "status": "pass", "bounded": True, "events": selected}
    require(len(payload(result).encode("utf-8")) <= 65536, "hot context exceeds the 64 KiB bound; narrow outline dependencies")
    return result


def graph(project: Path) -> dict[str, Any]:
    manifest = manifest_for(project)
    require_fresh(manifest, "build relationship/arc graph")
    require(check(project)["status"] == "pass", "accepted projections differ from HEAD; run rebuild before building graph")
    nodes: set[str] = set()
    edges: list[dict[str, Any]] = []
    arcs: list[dict[str, Any]] = []
    for key, entry in sorted(manifest["chapters"].items(), key=lambda item: int(item[0])):
        certificate = manifest.get("quality_certificates", {}).get(key)
        if not certificate:
            continue
        path = generation_dir(project, manifest["generation_id"]) / "quality/events" / f"chapter-{int(key):06d}" / f"{entry['revision']}-{certificate['packet_sha256'][:12]}.json"
        if not path.is_file():
            continue
        for event in read_json(path, "event extraction").get("authoritative_events", []):
            data = event.get("data", {})
            if event.get("kind") == "relation" and data.get("subject") and data.get("object"):
                nodes.update((str(data["subject"]), str(data["object"])))
                edges.append({"chapter": int(key), "event_id": event["id"], **data})
            elif event.get("kind") == "arc" and data.get("character"):
                nodes.add(str(data["character"]))
                arcs.append({"chapter": int(key), "event_id": event["id"], **data})
    return {"schema": SCHEMA, "status": "pass", "nodes": sorted(nodes), "relations": edges, "character_arcs": arcs}


def checkpoint_due(chapter: int) -> bool:
    return chapter in {3, 5} or (chapter >= 10 and chapter % 5 == 0)


def derive_suspense_debt(manifest: dict[str, Any], through_chapter: int) -> list[dict[str, Any]]:
    ledger: dict[str, dict[str, Any]] = {}
    rows = sorted(manifest.get("event_index", {}).values(), key=lambda row: (int(row.get("chapter", 0)), str(row.get("id", ""))))
    for event in rows:
        if event.get("kind") != "open_question" or int(event.get("chapter", 0)) > through_chapter:
            continue
        data = event.get("data", {})
        open_id = data.get("open_id")
        if not isinstance(open_id, str) or not open_id:
            continue
        previous = ledger.get(open_id)
        opened_chapter = int(previous["opened_chapter"]) if previous else int(event["chapter"])
        ledger[open_id] = {
            "open_id": open_id,
            "state": data.get("state"),
            "opened_chapter": opened_chapter,
            "last_event_chapter": int(event["chapter"]),
            "planned_payoff_chapter": data.get("planned_payoff_chapter"),
            "age": through_chapter - opened_chapter,
            "event_id": event.get("id"),
        }
    return [ledger[key] for key in sorted(ledger)]


def derive_reader_cumulative_state(project: Path, manifest: dict[str, Any], through_chapter: int) -> list[dict[str, Any]]:
    rows = []
    root = quality_root(project)
    for reader_id, chain in sorted(manifest.get("reader_chains", {}).items()):
        if not isinstance(chain, dict) or str(through_chapter) not in chain:
            continue
        expected_hash = chain[str(through_chapter)]
        matches = []
        for path in (root / "readers" / reader_id).glob(f"chapter-{through_chapter:06d}-*.json"):
            state = read_json(path, "accepted reader cumulative state")
            if state.get("state_hash") == expected_hash:
                matches.append(state)
        require(len(matches) == 1, f"accepted reader state {reader_id}/{through_chapter} is absent or ambiguous")
        state = matches[0]
        if state.get("reader_schema") != READER_SCHEMA_V3:
            continue
        measurements = validate_reader_measurements(state)
        rows.append({
            "reader_id": reader_id,
            "reader_state_hash": expected_hash,
            "first_quit_chapter": measurements["first_quit_chapter"],
            "continued_by_choice": measurements["continued_by_choice"],
            "continued_for_study": measurements["continued_for_study"],
            "cumulative_confusion": copy.deepcopy(measurements["cumulative_confusion"]),
            "mystery_fatigue": copy.deepcopy(measurements["mystery_fatigue"]),
            "cumulative_fatigue": copy.deepcopy(measurements["cumulative_fatigue"]),
        })
    return rows


def validate_checkpoint_attachments(attachments: dict[str, Any]) -> None:
    strength = attachments.get("strength_summary", {})
    require(isinstance(strength, dict), "checkpoint strength_summary must be an object")
    for key in STRENGTH_STATUSES:
        integer(strength.get(key, 0), f"checkpoint strength count {key}", minimum=0)

    for row in attachments.get("character_core_tests", []):
        require(isinstance(row, dict), "character core tests must be objects")
        nonempty_text(row.get("character"), "character core character")
        require(isinstance(row.get("hypothetical_situation"), str) and row["hypothetical_situation"].strip(), "character core test requires a hypothetical situation")
        require(isinstance(row.get("reader_choices"), list) and row["reader_choices"], "character core test requires reader choices")
        require(isinstance(row.get("rationale_chains"), list) and row["rationale_chains"], "character core test requires rationale chains")
        require(row.get("bounded_surprise_allowed") is True, "character core test must allow coherent surprise")
        require(row.get("predictability_maximization") is False, "character core test cannot maximize predictability")

    for row in attachments.get("memory_recall", []):
        require(isinstance(row, dict), "memory recall rows must be objects")
        for key in ("free_recall", "prompted_recall", "recent_two_chapter_items"):
            require(isinstance(row.get(key), list), f"memory recall {key} must be a list")
        require(row.get("exact_quote_required") is False, "memory recall cannot require exact quotations")

    emotion = attachments.get("emotion_curve", {})
    require(isinstance(emotion, dict), "checkpoint emotion_curve must be an object")
    for key in ("planned", "observed"):
        curve = emotion.get(key, [])
        require(isinstance(curve, list), f"emotion curve {key} must be a list")
        for point in curve:
            require(isinstance(point, dict), "emotion curve points must be objects")
            integer(point.get("scene_index"), "emotion curve scene_index", minimum=1)
            number(point.get("intensity"), "emotion curve intensity", minimum=0, maximum=5)
    require(emotion.get("mechanical_match_required") is False, "observed emotion may outperform rather than mechanically copy the plan")


def record_checkpoint(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    document = read_json(input_path, "cumulative checkpoint")
    require(document.get("schema") == CHECKPOINT_SCHEMA, f"checkpoint schema must be {CHECKPOINT_SCHEMA}")
    chapter = integer(document.get("chapter"), "checkpoint chapter", minimum=1)
    require(checkpoint_due(chapter), "checkpoint chapter must be 3, 5, or a later multiple of 5")
    manifest = manifest_for(project)
    require_fresh(manifest, "record a cumulative checkpoint")
    require(document.get("generation_id") == manifest["generation_id"], "checkpoint generation mismatch")
    require(str(chapter) in manifest.get("chapters", {}), "checkpoint chapter is not accepted")
    revisions = [manifest["chapters"][str(number)]["revision"] for number in range(1, chapter + 1)]
    require(document.get("revision_sequence_sha256") == sha_json(revisions), "checkpoint revision sequence mismatch")
    reader_hashes = document.get("reader_state_hashes")
    require(isinstance(reader_hashes, list) and all(is_sha256(value) for value in reader_hashes), "checkpoint reader state hashes must be SHA-256 values")
    known_reader_hashes = {
        chain[str(chapter)]
        for chain in manifest.get("reader_chains", {}).values()
        if isinstance(chain, dict) and str(chapter) in chain
    }
    require(reader_hashes and set(reader_hashes) <= known_reader_hashes, "checkpoint reader hashes are not bound to the accepted reader chains")
    run_ids = document.get("run_ids")
    require(isinstance(run_ids, list) and run_ids, "checkpoint requires independent run IDs")
    require(len(set(run_ids)) == len(run_ids) and all(isinstance(value, str) and value.strip() for value in run_ids), "checkpoint run IDs must be unique non-empty strings")
    require(document.get("advisory_only") is True and document.get("correctness_impact") is False, "cumulative checkpoint must remain advisory")
    attachments = document.get("attachments")
    require(isinstance(attachments, dict), "checkpoint attachments must be an object")
    validate_checkpoint_attachments(attachments)
    require(attachments.get("suspense_debt") == derive_suspense_debt(manifest, chapter), "checkpoint suspense debt must be derived from accepted open-question events")
    require(attachments.get("reader_cumulative_state") == derive_reader_cumulative_state(project, manifest, chapter), "checkpoint cumulative reader state must be derived from accepted reader chains")
    alerts = document.get("quality_alerts")
    require(isinstance(alerts, list), "checkpoint quality_alerts must be a list")
    for alert in alerts:
        require(isinstance(alert, dict), "quality alerts must be objects")
        require(alert.get("diagnosis") in {"prose_delivery", "chapter_design", "multi_chapter_structure", "core_contract"}, "quality alert diagnosis is invalid")
        nonempty_text(alert.get("evidence"), "quality alert evidence")
        require(alert.get("action") in {"reopen_recommendation", "outline_review_recommendation", "observe"}, "quality alert action is invalid")
    require(document.get("attention_required") is bool(alerts), "checkpoint attention_required must be derived from alerts")
    digest = sha_json(document)
    root = quality_root(project)
    target = root / "checkpoints" / manifest["generation_id"] / f"chapter-{chapter:06d}-{digest[:12]}.json"
    atomic_json(target, document)
    index_path = root / "CHECKPOINT_INDEX.json"
    index = read_json(index_path, "checkpoint index") if index_path.exists() else {"schema": CHECKPOINT_SCHEMA, "entries": []}
    entry = {"generation_id": manifest["generation_id"], "chapter": chapter, "checkpoint_sha256": digest, "status": "fresh", "path": target.relative_to(root).as_posix()}
    index["entries"] = [row for row in index["entries"] if not (row.get("generation_id") == manifest["generation_id"] and row.get("chapter") == chapter)] + [entry]
    atomic_json(index_path, index)
    return {"schema": SCHEMA, **entry, "status": "checkpoint_recorded", "attention_required": bool(alerts)}


def prepare_derived_index_invalidations(project: Path, from_chapter: int, new_generation: str) -> list[tuple[Path, dict[str, Any]]]:
    root = quality_root(project)
    prepared = []
    for name in ("CHECKPOINT_INDEX.json", "STRUCTURAL_BENCHMARK_INDEX.json"):
        path = root / name
        if not path.exists():
            continue
        index = read_json(path, "derived quality index")
        require(isinstance(index.get("entries"), list), "derived quality index entries must be a list")
        changed = False
        for row in index["entries"]:
            require(isinstance(row, dict), "derived quality index entries must be objects")
            if int(row.get("chapter", 0)) >= from_chapter and row.get("status") == "fresh":
                row.update({"status": "stale", "invalidated_by_generation": new_generation, "invalidated_from_chapter": from_chapter})
                changed = True
        if changed:
            prepared.append((path, index))
    return prepared


def apply_prepared_derived_index_invalidations(prepared: list[tuple[Path, dict[str, Any]]]) -> None:
    for path, index in prepared:
        atomic_json(path, index)


def reopen_case_root(project: Path, case_id: str) -> Path:
    return quality_root(project) / "reopen-cases" / safe_component(case_id, "reopen_case_id")


def write_reopen_case(project: Path, case: dict[str, Any]) -> str:
    root = reopen_case_root(project, case["case_id"])
    snapshot = copy.deepcopy(case)
    snapshot["updated_at"] = now()
    digest = sha_json(snapshot)
    target = root / "history" / f"{digest}.json"
    if not target.exists():
        atomic_json(target, snapshot)
    atomic_json(root / "CASE.json", {"schema": REOPEN_SCHEMA, "case_sha256": digest, "path": target.relative_to(root).as_posix()})
    return digest


def load_reopen_case(project: Path, case_id: str) -> dict[str, Any]:
    root = reopen_case_root(project, case_id)
    pointer = read_json(root / "CASE.json", "reopen case pointer")
    digest = pointer.get("case_sha256")
    require(is_sha256(digest), "reopen case pointer hash is invalid")
    case = read_json(root / str(pointer.get("path")), "reopen case snapshot")
    require(sha_json(case) == digest, "reopen case snapshot hash mismatch")
    return case


def open_reopen_case(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    document = read_json(input_path, "reopen request")
    require(document.get("schema") == REOPEN_SCHEMA, f"reopen request schema must be {REOPEN_SCHEMA}")
    pending_id = safe_component(document.get("pending_id"), "pending_id")
    pending_dir = quality_root(project) / "pending" / pending_id
    pending = read_json(pending_dir / "pending.json", "flat pending generation")
    certificate_path = pending_dir / "certificate.json"
    certificate = read_json(certificate_path, "flat strength certificate")
    require(certificate.get("p0_eligible_before_strength") is True and certificate.get("strength_status") == "FLAT", "reopen requires a P0-eligible certificate with FLAT strength")
    simulation_only = certificate.get("strength_mode") == "SHADOW"
    if simulation_only:
        require(document.get("simulation_only") is True, "SHADOW reopen must be explicitly simulation-only")
    else:
        require(certificate.get("selection_status") == "REOPEN_REQUIRED" and document.get("simulation_only") is False, "production reopen requires ENFORCE REOPEN_REQUIRED evidence")
    require(pending.get("base_generation") == head_record(project)["generation_id"], "flat pending generation is based on stale HEAD")
    level = document.get("level")
    require(level in {"L1", "L2", "L3"}, "reopen level must be L1/L2/L3")
    regions = document.get("localized_regions", [])
    require(isinstance(regions, list) and all(isinstance(value, str) and value.strip() for value in regions), "reopen localized_regions must be strings")
    if level == "L1":
        require(regions, "L1 reopen requires localized strength evidence")
    authorization = document.get("author_authorization")
    if level in {"L2", "L3"}:
        nonempty_text(authorization, f"{level} author authorization")
        search_scope = document.get("search_scope")
        require(isinstance(search_scope, dict) and search_scope, f"{level} requires a bounded search_scope")
    reason_codes = document.get("reason_codes")
    require(isinstance(reason_codes, list) and reason_codes == certificate["packet"]["strength_gate"]["reason_codes"], "reopen reason codes must equal the flat certificate")
    certificate_sha256 = sha_file(certificate_path)
    parent_case_id = document.get("parent_reopen_case_id")
    parent_case = None
    if level == "L3":
        parent_case_id = safe_component(parent_case_id, "L3 parent_reopen_case_id")
        parent_case = load_reopen_case(project, parent_case_id)
        require(parent_case.get("level") == "L2" and parent_case.get("state") == "L3_PROPOSAL_REQUIRED", "L3 requires an all-flat L2 parent case")
    elif parent_case_id is not None:
        parent_case_id = safe_component(parent_case_id, "parent_reopen_case_id")
        parent_case = load_reopen_case(project, parent_case_id)
        require(level == "L2" and parent_case.get("level") == "L1" and parent_case.get("state") == "L2_PROPOSAL_REQUIRED", "only all-flat L1 may parent an L2 case")
    if parent_case is not None:
        require(parent_case.get("base_generation") == pending["base_generation"] and parent_case.get("chapter") == pending["chapter"], "reopen escalation parent lineage mismatch")
        require(parent_case.get("strength_certificate_sha256") == certificate_sha256, "reopen escalation must retain the same flat certificate")
        require(parent_case.get("simulation_only") is simulation_only, "reopen escalation cannot cross SHADOW/production scope")
    lineage_suffix = f"-{sha_bytes(str(parent_case_id).encode())[:8]}" if parent_case_id else ""
    case_id = f"reopen-{pending['chapter']:06d}-{certificate_sha256[:12]}-{level.lower()}{lineage_suffix}"
    case = {
        "schema": REOPEN_SCHEMA,
        "case_id": case_id,
        "base_generation": pending["base_generation"],
        "chapter": pending["chapter"],
        "parent_revision": pending.get("parent_revision"),
        "flat_revision": pending["revision"],
        "outline_sha256": pending["outline_sha256"],
        "strength_certificate_sha256": certificate_sha256,
        "strength_mode": certificate.get("strength_mode"),
        "simulation_only": simulation_only,
        "level": level,
        "parent_reopen_case_id": parent_case_id,
        "outline_contract": copy.deepcopy(pending.get("outline_contract")),
        "quality_policy": copy.deepcopy(pending.get("quality_policy")),
        "quality_policy_sha256": pending.get("quality_policy_sha256"),
        "localized_regions": regions,
        "author_authorization": authorization,
        "search_scope": document.get("search_scope"),
        "reason_codes": reason_codes,
        "arms": [],
        "state": "OPEN",
        "created_at": now(),
    }
    root = reopen_case_root(project, case_id)
    require(not (root / "CASE.json").exists(), "reopen case already exists")
    digest = write_reopen_case(project, case)
    if parent_case is not None:
        parent_case["state"] = f"ESCALATED_TO_{level}"
        parent_case["child_reopen_case_id"] = case_id
        write_reopen_case(project, parent_case)
    return {"schema": SCHEMA, "status": "reopen_opened", "case_id": case_id, "case_sha256": digest, "level": level}


def record_reopen_arm(project: Path, case_id: str, input_path: Path, body_path: Path, outline_path: Path | None) -> dict[str, Any]:
    project = project.resolve()
    case = load_reopen_case(project, case_id)
    require(case.get("state") == "OPEN", "reopen case no longer accepts arms")
    document = read_json(input_path, "reopen arm metadata")
    require(document.get("schema") == REOPEN_SCHEMA, f"reopen arm schema must be {REOPEN_SCHEMA}")
    arm_id = safe_component(document.get("arm_id"), "reopen arm_id")
    require(all(row.get("arm_id") != arm_id for row in case["arms"]), "reopen arm ID already exists")
    writer_run_id = nonempty_text(document.get("writer_run_id"), "reopen writer_run_id")
    used_runs = {
        run_id
        for row in case["arms"]
        for run_id in [row.get("writer_run_id"), row.get("evaluator_run_id"), *row.get("reader_run_ids", [])]
        if isinstance(run_id, str)
    }
    require(writer_run_id not in used_runs, "reopen writer runs must be globally isolated within the case")
    integer(document.get("generation_budget"), "reopen generation_budget", minimum=1)
    nonempty_text(document.get("stop_rule"), "reopen stop_rule")
    require(body_path.is_file(), "reopen arm body is missing")
    body_digest = sha_file(body_path)
    require(document.get("body_sha256") == body_digest, "reopen arm body hash mismatch")
    outline_digest = None
    arm_outline_contract = copy.deepcopy(case["outline_contract"])
    if case["level"] == "L3":
        require(outline_path is not None and outline_path.is_file(), "L3 reopen arm requires an outline variant")
        outline_digest = sha_file(outline_path)
        require(document.get("outline_sha256") == outline_digest, "L3 outline variant hash mismatch")
        arm_outline_contract = outline_contract(outline_path)
    else:
        require(outline_path is None and document.get("outline_sha256") in {None, case["outline_sha256"]}, "L1/L2 must keep the accepted fine outline")
    require(body_digest not in {row.get("body_sha256") for row in case["arms"]}, "reopen body arms must be distinct")
    if outline_digest:
        require(outline_digest not in {row.get("outline_sha256") for row in case["arms"]}, "L3 outline variants must be distinct")
    evaluation = document.get("evaluation")
    require(isinstance(evaluation, dict), "reopen arm requires a strength evaluation")
    evaluator_run_id = nonempty_text(evaluation.get("evaluator_run_id"), "reopen arm evaluator_run_id")
    require(evaluator_run_id not in used_runs | {writer_run_id}, "reopen evaluator must be isolated from every writer/evaluator/reader run")
    cohort = evaluation.get("reader_evidence")
    require(isinstance(cohort, list) and len(cohort) >= 2, "reopen arm evaluation requires at least two reader evidence rows")
    reader_run_ids: list[str] = []
    reader_ids: set[str] = set()
    normalized_cohort = []
    visible_chars = len(re.sub(r"\s+", "", body_path.read_text(encoding="utf-8")))
    for row in cohort:
        require(isinstance(row, dict), "reopen reader evidence rows must be objects")
        reader_id = safe_component(row.get("reader_id"), "reopen reader_id")
        require(reader_id not in reader_ids, "reopen reader IDs must be distinct")
        reader_ids.add(reader_id)
        run_id = nonempty_text(row.get("run_id"), f"reopen reader {reader_id} run_id")
        require(run_id not in used_runs | {writer_run_id, evaluator_run_id} | set(reader_run_ids), "reopen reader runs must be globally isolated")
        reader_run_ids.append(run_id)
        normalized_row = copy.deepcopy(row)
        validate_reader_measurements(normalized_row, candidate_visible_chars=visible_chars)
        normalized_cohort.append(normalized_row)
    policy = validate_policy(copy.deepcopy(case["quality_policy"]))
    pseudo_pending = {
        "chapter": case["chapter"],
        "revision": body_digest,
        "outline_contract": arm_outline_contract,
        "quality_policy_sha256": case["quality_policy_sha256"],
    }
    derived_strength = derive_strength_gate(pseudo_pending, policy, normalized_cohort)
    supplied_strength = evaluation.get("strength_gate")
    require(isinstance(supplied_strength, dict) and supplied_strength == {**derived_strength, "derived": True}, "reopen arm strength result is not derived from its reader evidence")
    evidence_hashes = [sha_json(row) for row in normalized_cohort]
    evaluation_input = {
        "body_sha256": body_digest,
        "outline_sha256": outline_digest or case["outline_sha256"],
        "policy_sha256": case["quality_policy_sha256"],
        "reader_evidence_sha256s": evidence_hashes,
    }
    require(evaluation.get("input_fingerprint") == sha_json(evaluation_input), "reopen arm evaluation input fingerprint mismatch")
    artifacts = reopen_case_root(project, case_id) / "artifacts"
    body_target = artifacts / "bodies" / f"{body_digest}.md"
    if not body_target.exists():
        atomic_bytes(body_target, body_path.read_bytes())
    if outline_digest and outline_path is not None:
        outline_target = quality_root(project) / "outline-variants" / f"{outline_digest}.md"
        if not outline_target.exists():
            atomic_bytes(outline_target, outline_path.read_bytes())
    reader_artifacts = []
    for row, digest in zip(normalized_cohort, evidence_hashes):
        reader_target = artifacts / "readers" / f"{digest}.json"
        if not reader_target.exists():
            atomic_json(reader_target, row)
        reader_artifacts.append({"sha256": digest, "path": reader_target.relative_to(reopen_case_root(project, case_id)).as_posix()})
    strength_artifact = {**derived_strength, "derived": True}
    strength_target = artifacts / "strength-gates" / f"{sha_json(strength_artifact)}.json"
    if not strength_target.exists():
        atomic_json(strength_target, strength_artifact)
    arm = {
        "arm_id": arm_id,
        "writer_run_id": writer_run_id,
        "evaluator_run_id": evaluator_run_id,
        "reader_run_ids": reader_run_ids,
        "reader_evidence_sha256s": evidence_hashes,
        "reader_evidence_artifacts": reader_artifacts,
        "evaluation_input_sha256": evaluation["input_fingerprint"],
        "strength_status": derived_strength["status"],
        "strength_gate_sha256": sha_json(strength_artifact),
        "strength_gate_artifact_path": strength_target.relative_to(reopen_case_root(project, case_id)).as_posix(),
        "generation_budget": document["generation_budget"],
        "stop_rule": document["stop_rule"],
        "body_sha256": body_digest,
        "body_artifact_path": body_target.relative_to(reopen_case_root(project, case_id)).as_posix(),
        "outline_sha256": outline_digest or case["outline_sha256"],
        "outline_contract": arm_outline_contract,
        "recorded_at": now(),
    }
    case["arms"].append(arm)
    digest = write_reopen_case(project, case)
    return {"schema": SCHEMA, "status": "reopen_arm_recorded", "case_id": case_id, "case_sha256": digest, **arm}


def revalidate_reopen_arm(project: Path, case: dict[str, Any], arm: dict[str, Any]) -> None:
    root = reopen_case_root(project, case["case_id"])
    body_path = root / str(arm.get("body_artifact_path"))
    require_safe_projection_target(root, body_path, "reopen body artifact")
    require(body_path.is_file() and sha_file(body_path) == arm.get("body_sha256"), "reopen arm immutable body artifact is missing or changed")
    reader_artifacts = arm.get("reader_evidence_artifacts")
    require(isinstance(reader_artifacts, list) and reader_artifacts, "reopen arm lacks retrievable reader artifacts")
    cohort = []
    for reference in reader_artifacts:
        require(isinstance(reference, dict) and is_sha256(reference.get("sha256")), "reopen reader artifact reference is invalid")
        path = root / str(reference.get("path"))
        require_safe_projection_target(root, path, "reopen reader artifact")
        row = read_json(path, "reopen immutable reader evidence")
        require(sha_json(row) == reference["sha256"], "reopen immutable reader evidence hash mismatch")
        validate_reader_measurements(row, candidate_visible_chars=len(re.sub(r"\s+", "", body_path.read_text(encoding="utf-8"))))
        cohort.append(row)
    require([sha_json(row) for row in cohort] == arm.get("reader_evidence_sha256s"), "reopen reader evidence order/hash mismatch")
    policy = validate_policy(copy.deepcopy(case["quality_policy"]))
    pseudo_pending = {
        "chapter": case["chapter"],
        "revision": arm["body_sha256"],
        "outline_contract": arm["outline_contract"],
        "quality_policy_sha256": case["quality_policy_sha256"],
    }
    derived = {**derive_strength_gate(pseudo_pending, policy, cohort), "derived": True}
    strength_path = root / str(arm.get("strength_gate_artifact_path"))
    require_safe_projection_target(root, strength_path, "reopen strength artifact")
    stored_strength = read_json(strength_path, "reopen immutable strength gate")
    require(stored_strength == derived and sha_json(stored_strength) == arm.get("strength_gate_sha256"), "reopen arm strength gate cannot be reproduced from stored readers")
    require(stored_strength["status"] == arm.get("strength_status"), "reopen arm stored strength status mismatch")


def resolve_reopen_case(project: Path, case_id: str, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    case = load_reopen_case(project, case_id)
    require(case.get("state") == "OPEN", "reopen case is not open")
    arms = case.get("arms", [])
    for arm in arms:
        revalidate_reopen_arm(project, case, arm)
    minimum, maximum = (1, 1) if case["level"] == "L1" else (2, 3)
    require(minimum <= len(arms) <= maximum, f"{case['level']} reopen requires {minimum}-{maximum} arms")
    if len(arms) > 1:
        budgets = {(row["generation_budget"], row["stop_rule"]) for row in arms}
        require(len(budgets) == 1, "reopen arms require equal preregistered budget and stop rules")
    decision = read_json(input_path, "reopen selection")
    require(decision.get("schema") == REOPEN_SCHEMA, f"reopen selection schema must be {REOPEN_SCHEMA}")
    require(decision.get("blinded") is True and decision.get("order_randomized") is True, "reopen selection must be blinded and order-randomized")
    arm_ids = [row["arm_id"] for row in arms]
    require(isinstance(decision.get("arm_order"), list) and len(decision["arm_order"]) == len(arm_ids) and len(set(decision["arm_order"])) == len(arm_ids) and set(decision["arm_order"]) == set(arm_ids), "reopen selection must include every arm exactly once")
    selector_run_id = nonempty_text(decision.get("selector_run_id"), "reopen selector_run_id")
    reserved_runs = {
        run_id
        for row in arms
        for run_id in [row["writer_run_id"], row["evaluator_run_id"], *row["reader_run_ids"]]
    }
    require(selector_run_id not in reserved_runs, "reopen selector must be isolated from all writers/evaluators/readers")
    nonempty_text(decision.get("randomization_nonce"), "reopen randomization_nonce")
    criteria = decision.get("selection_criteria")
    require(isinstance(criteria, list) and criteria, "reopen selection requires criteria")
    selector_input = {"arms": [{"arm_id": row["arm_id"], "body_sha256": row["body_sha256"], "outline_sha256": row["outline_sha256"], "strength_status": row["strength_status"], "strength_gate_sha256": row["strength_gate_sha256"]} for row in arms], "arm_order": decision["arm_order"], "criteria": criteria}
    require(decision.get("selector_input_sha256") == sha_json(selector_input), "reopen selector input hash mismatch")
    outcome = decision.get("outcome")
    require(outcome in {"selected", "all_flat"}, "reopen outcome is invalid")
    winner = decision.get("winner_arm_id")
    final_validation = decision.get("held_out_final_validation")
    require(isinstance(final_validation, dict), "reopen selection requires held-out final validation")
    validation_run_id = nonempty_text(final_validation.get("run_id"), "reopen held-out validation run_id")
    require(validation_run_id not in reserved_runs | {selector_run_id}, "reopen held-out validator must be isolated from generation, evaluation, and selection")
    evidence_bundle = evidence_by_hash(project, final_validation.get("evidence_bundle_sha256"))
    if case.get("simulation_only"):
        require(evidence_bundle["source_kind"] == "synthetic_fixture" and evidence_bundle["synthetic"] is True, "SHADOW simulation must use explicitly synthetic held-out evidence")
    else:
        require(evidence_bundle["kind"] == "human_reader_import" and evidence_bundle["source_kind"] == "human_blind_import" and evidence_bundle["synthetic"] is False, "production reopen requires recorded non-synthetic human validation")
        require(case_id in evidence_bundle["artifact"]["story_package_ids"], "production reopen human evidence is not bound to this case")
        require(evidence_bundle["artifact"]["reader_count"] >= 2, "production reopen requires at least two held-out readers")
    heldout_votes: list[str | None] = []
    for reader in evidence_bundle["artifact"]["readers"]:
        raw = reader["raw_observations"]
        require(raw.get("case_id") == case_id and raw.get("blinded") is True, "reopen held-out reader is not blindly bound to this case")
        raw_order = raw.get("arm_order")
        require(isinstance(raw_order, list) and len(raw_order) == len(arm_ids) and len(set(raw_order)) == len(arm_ids) and set(raw_order) == set(arm_ids), "reopen held-out reader must observe every arm exactly once")
        observations = raw.get("arm_observations")
        require(isinstance(observations, list) and [row.get("arm_id") for row in observations if isinstance(row, dict)] == raw_order, "reopen held-out observations must follow the blind arm order")
        expected_by_id = {row["arm_id"]: row for row in arms}
        for observation in observations:
            expected = expected_by_id[observation["arm_id"]]
            require(
                observation == {
                    "arm_id": expected["arm_id"],
                    "body_sha256": expected["body_sha256"],
                    "outline_sha256": expected["outline_sha256"],
                    "strength_status": expected["strength_status"],
                },
                "reopen held-out observation differs from its immutable arm",
            )
        require(raw.get("outcome") == outcome, "reopen held-out reader outcome differs from the selection")
        heldout_votes.append(raw.get("winner_arm_id"))
    majority = len(heldout_votes) // 2 + 1
    if outcome == "selected":
        require(sum(value == winner for value in heldout_votes) >= majority, "reopen winner lacks a held-out reader majority")
    else:
        require(all(value is None for value in heldout_votes), "all-flat held-out readers cannot name a winner")
    validation_input = {
        "selector_input_sha256": decision["selector_input_sha256"],
        "outcome": outcome,
        "winner_arm_id": winner,
        "evidence_bundle_sha256": final_validation["evidence_bundle_sha256"],
    }
    require(final_validation.get("input_fingerprint") == sha_json(validation_input), "reopen held-out validation fingerprint mismatch")
    require(final_validation.get("status") == "PASS", "reopen held-out final validation did not PASS")
    if outcome == "selected":
        require(winner in arm_ids, "selected reopen arm is invalid")
        selected = next(row for row in arms if row["arm_id"] == winner)
        require(selected["strength_status"] == "PASS", "selected reopen arm must PASS the calibrated strength gate")
        case.update({"state": "SELECTED", "selected_arm_id": winner})
    else:
        require(winner is None, "all-flat reopen cannot name a winner")
        require(all(row["strength_status"] == "FLAT" for row in arms), "all-flat outcome requires every arm to be independently FLAT")
        next_state = {"L1": "L2_PROPOSAL_REQUIRED", "L2": "L3_PROPOSAL_REQUIRED", "L3": "DESIGN_REVISION_REQUIRED"}[case["level"]]
        case.update({"state": next_state, "selected_arm_id": None})
    case["selection"] = copy.deepcopy(decision)
    case["reserved_run_ids"] = sorted(reserved_runs | {selector_run_id, validation_run_id})
    digest = write_reopen_case(project, case)
    return {"schema": SCHEMA, "status": "reopen_resolved", "case_id": case_id, "case_sha256": digest, "state": case["state"], "selected_arm_id": case.get("selected_arm_id")}


def record_outline_revision(project: Path, old: Path, new: Path, input_path: Path) -> dict[str, Any]:
    decision = read_json(input_path, "outline revision decision")
    require(decision.get("diagnosis") in {"prose_delivery", "chapter_design", "multi_chapter_structure", "core_contract"}, "invalid outline failure diagnosis")
    earliest = decision.get("earliest_divergent_chapter")
    require(isinstance(earliest, int) and earliest >= 1, "earliest divergent chapter is required")
    nonempty_text(decision.get("author_approval"), "outline revision author approval")
    require(decision.get("retrospective_relabel") is False, "old prose cannot be relabeled PASS by rewriting goals")
    root = quality_root(project) / "outline-revisions"
    old_hash, new_hash = sha_file(old), sha_file(new)
    require(old_hash != new_hash, "outline revision must contain a real plan change")
    reopen_case_id = decision.get("reopen_case_id")
    reopen_case = None
    if reopen_case_id is not None:
        reopen_case = load_reopen_case(project, safe_component(reopen_case_id, "reopen_case_id"))
        require(reopen_case.get("level") == "L3" and reopen_case.get("state") == "SELECTED", "outline revision must bind a selected L3 reopen case")
        selected = next((row for row in reopen_case.get("arms", []) if row.get("arm_id") == reopen_case.get("selected_arm_id")), None)
        require(isinstance(selected, dict) and selected.get("outline_sha256") == new_hash, "outline revision new plan is not the selected L3 variant")
        require(old_hash == reopen_case.get("outline_sha256"), "outline revision old plan is not the L3 case parent outline")
        require(earliest == reopen_case.get("chapter"), "L3 outline revision must bind its case chapter as the earliest divergence")
        require(decision.get("author_approval") == reopen_case.get("author_authorization"), "outline revision author approval differs from the L3 authorization")
    for source, digest in ((old, old_hash), (new, new_hash)):
        target = root / "plans" / f"{digest}.md"
        if not target.exists():
            atomic_bytes(target, source.read_bytes())
    record = {"schema": SCHEMA, "old_plan": old_hash, "new_plan": new_hash, **decision, "recorded_at": now()}
    record_hash = sha_json(record)
    atomic_json(root / "decisions" / f"{record_hash}.json", record)
    if reopen_case is not None:
        reopen_case["state"] = "OUTLINE_REVISION_RECORDED"
        reopen_case["outline_revision_decision"] = record_hash
        write_reopen_case(project, reopen_case)
    return {"schema": SCHEMA, "status": "recorded", "decision": record_hash, "rebuild_from_chapter": earliest}


def record_outline_search(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    document = read_json(input_path, "outline search")
    require(document.get("schema") == OUTLINE_SEARCH_SCHEMA, f"outline search schema must be {OUTLINE_SEARCH_SCHEMA}")
    require(document.get("instrument_only") is True, "outline search is instrument-only until CASE/outline/final-prose provenance is implemented")
    require(document.get("proxy_only") is True and document.get("final_prose_validation_required") is True, "outline proxy may shortlist only")
    variants = document.get("variants")
    require(isinstance(variants, list) and 2 <= len(variants) <= 3, "outline search requires 2-3 variants")
    ids: set[str] = set()
    hashes: set[str] = set()
    root = quality_root(project)
    for row in variants:
        require(isinstance(row, dict), "outline variants must be objects")
        variant_id = safe_component(row.get("variant_id"), "outline variant_id")
        require(variant_id not in ids, "outline variant IDs must be distinct")
        ids.add(variant_id)
        text_value = nonempty_text(row.get("outline_text"), "outline variant text")
        digest = sha_bytes(text_value.encode("utf-8"))
        require(row.get("outline_sha256") == digest and digest not in hashes, "outline variants must be distinct hash-bound artifacts")
        hashes.add(digest)
        sequence = row.get("sequence")
        require(isinstance(sequence, list) and sequence, "outline variant requires a structural sequence")
        for unit in sequence:
            require(isinstance(unit, dict), "outline sequence units must be objects")
            for key in ("ending_beat_id", "expectation_id", "must_know", "must_not_know"):
                require(key in unit, f"outline sequence unit lacks {key}")
        evaluation = row.get("proxy_evaluation")
        require(isinstance(evaluation, dict), "outline variant requires proxy evaluation")
        nonempty_text(evaluation.get("run_id"), "outline proxy run_id")
        require(evaluation.get("held_out_from_generation") is True, "outline proxy evaluator must be held out from generation")
        for key in ("expectation_chain_breaks", "same_type_streak", "open_density_curve", "emotion_curve"):
            require(key in evaluation, f"outline proxy evaluation lacks {key}")
        target = root / "outline-variants" / f"{digest}.md"
        if not target.exists():
            atomic_text(target, text_value)
    selected = document.get("selected_variant_id")
    require(selected in ids, "outline search selected variant is invalid")
    nonempty_text(document.get("selector_run_id"), "outline selector_run_id")
    require(document.get("search_input_sha256") == sha_json([{"variant_id": row["variant_id"], "outline_sha256": row["outline_sha256"], "sequence": row["sequence"]} for row in variants]), "outline search input hash mismatch")
    digest = sha_json(document)
    atomic_json(root / "outline-searches" / f"{digest}.json", document)
    return {"schema": SCHEMA, "status": "outline_search_recorded", "search_sha256": digest, "selected_variant_id": selected, "instrument_only": True, "blocking": False}


def record_structural_benchmark(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    document = read_json(input_path, "structural benchmark")
    require(document.get("schema") == STRUCTURAL_BENCHMARK_SCHEMA, f"structural benchmark schema must be {STRUCTURAL_BENCHMARK_SCHEMA}")
    require(document.get("diagnostic_only") is True and document.get("blocking") is False, "structural benchmark must be diagnostic-only")
    prohibited = document.get("prohibited_comparisons")
    require(prohibited == {"sentences": False, "plot_beats": False, "proper_nouns": False}, "structural benchmark must prohibit sentence/plot/proper-noun comparison")
    chapter = integer(document.get("chapter"), "structural benchmark chapter", minimum=1)
    manifest = manifest_for(project)
    require(document.get("generation_id") == manifest["generation_id"] and str(chapter) in manifest["chapters"], "structural benchmark must bind the accepted generation/chapter")
    number(document.get("volume_position_ratio"), "volume_position_ratio", minimum=0, maximum=1)
    dimensions = document.get("dimensions")
    required = {"event_density", "information_release", "ending_type_distribution", "emotion_intensity", "dialogue_narration_ratio"}
    require(isinstance(dimensions, dict) and required <= set(dimensions), "structural benchmark lacks transferable dimensions")
    for key in required:
        row = dimensions[key]
        require(isinstance(row, dict), f"structural benchmark {key} must be an object")
        number(row.get("candidate"), f"{key}.candidate")
        number(row.get("reference"), f"{key}.reference")
        number(row.get("relative_difference"), f"{key}.relative_difference")
        number(row.get("confidence"), f"{key}.confidence", minimum=0, maximum=1)
    require(document.get("normalized_by_genre_and_position") is True, "structural benchmark must normalize by genre and structural position")
    digest = sha_json(document)
    root = quality_root(project)
    target = root / "structural-benchmarks" / manifest["generation_id"] / f"chapter-{chapter:06d}-{digest[:12]}.json"
    atomic_json(target, document)
    index_path = root / "STRUCTURAL_BENCHMARK_INDEX.json"
    index = read_json(index_path, "structural benchmark index") if index_path.exists() else {"schema": STRUCTURAL_BENCHMARK_SCHEMA, "entries": []}
    index["entries"].append({"generation_id": manifest["generation_id"], "chapter": chapter, "benchmark_sha256": digest, "status": "fresh", "blocking": False})
    atomic_json(index_path, index)
    return {"schema": SCHEMA, "status": "structural_benchmark_recorded", "benchmark_sha256": digest, "blocking": False}


def record_golden_three_plan(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    document = read_json(input_path, "golden-three plan")
    require(document.get("schema") == GOLDEN_THREE_SCHEMA, f"golden-three schema must be {GOLDEN_THREE_SCHEMA}")
    require(document.get("plan_only") is True, "golden-three is plan-only until treatment and held-out execution provenance is implemented")
    require(document.get("chapters") == [1, 2, 3], "golden-three plan must cover chapters 1-3")
    require(document.get("budget_preregistered") is True and document.get("fixed_six_arm_rule") is False, "golden-three arm count must be evidence-driven and preregistered, not fixed at six")
    calibration_id = safe_component(document.get("calibration_id"), "golden-three calibration_id")
    calibration_path = quality_root(project) / "calibration" / f"{calibration_id}.json"
    calibration = validate_calibration_document(read_json(calibration_path, "golden-three calibration"), project)
    require(sha_json(calibration) == document.get("calibration_sha256"), "golden-three calibration hash mismatch")
    require(calibration.get("purpose") == "development_thresholds", "golden-three plan must be decided and frozen from development data before held-out validation")
    arm_plans = document.get("arm_plans")
    require(isinstance(arm_plans, list) and [row.get("chapter") for row in arm_plans if isinstance(row, dict)] == [1, 2, 3], "golden-three requires one arm plan per opening chapter")
    for row in arm_plans:
        integer(row.get("outline_variants"), "golden-three outline_variants", minimum=2, maximum=3)
        integer(row.get("prose_variants_per_outline"), "golden-three prose_variants_per_outline", minimum=1, maximum=3)
        nonempty_text(row.get("stop_rule"), "golden-three stop_rule")
        require(row.get("selector_blinded") is True and row.get("held_out_final_readers") is True, "golden-three selection and final readers must be isolated")
    derived_budget = calibration.get("golden_three_budget")
    require(
        [{key: row[key] for key in ("chapter", "outline_variants", "prose_variants_per_outline", "stop_rule")} for row in arm_plans] == derived_budget,
        "golden-three arm plans do not match the calibrated budget",
    )
    prereg = document.get("preregistration")
    require(isinstance(prereg, dict) and document.get("preregistration_sha256") == sha_json(prereg), "golden-three preregistration hash mismatch")
    require(prereg.get("arm_plans") == arm_plans, "golden-three preregistration must freeze the complete arm plans")
    digest = sha_json(document)
    atomic_json(quality_root(project) / "golden-three-plans" / f"{digest}.json", document)
    return {"schema": SCHEMA, "status": "golden_three_plan_recorded", "plan_sha256": digest, "plan_only": True, "execution_ready": False}


def validate_between_subject_power_plan(
    document: dict[str, Any],
    *,
    sample_size: int,
    effect_key: str,
    maximum_effect: float,
) -> None:
    plan = document.get("power_analysis")
    require(isinstance(plan, dict), "powered between-subject study requires a preregistered power_analysis")
    require(plan.get("method") == "two-sample-normal-approximation-v1", "between-subject power method is unsupported")
    alpha = number(plan.get("two_sided_alpha"), "power_analysis.two_sided_alpha", minimum=0.001, maximum=0.1)
    target_power = number(plan.get("target_power"), "power_analysis.target_power", minimum=0.8, maximum=0.99)
    assumed_sd = number(plan.get("assumed_standard_deviation"), "power_analysis.assumed_standard_deviation", minimum=0.01)
    minimum_effect = number(plan.get(effect_key), f"power_analysis.{effect_key}", minimum=0.01, maximum=maximum_effect)
    require(all(math.isfinite(value) for value in (alpha, target_power, assumed_sd, minimum_effect)), "between-subject power assumptions must be finite")
    planned_per_arm = integer(plan.get("planned_per_arm"), "power_analysis.planned_per_arm", minimum=2)
    require(sample_size == planned_per_arm * 2, "powered sample size must equal two preregistered arm sizes")
    z_alpha = NormalDist().inv_cdf(1 - alpha / 2)
    z_power = NormalDist().inv_cdf(target_power)
    required_per_arm = math.ceil(2 * ((z_alpha + z_power) * assumed_sd / minimum_effect) ** 2)
    require(planned_per_arm >= required_per_arm, "powered sample size is below its own preregistered power assumptions")


def require_exact_unique_list(value: object, expected: frozenset[str], label: str) -> list[str]:
    require(
        isinstance(value, list)
        and all(isinstance(item, str) for item in value)
        and len(value) == len(expected)
        and len(value) == len(set(value))
        and set(value) == expected,
        f"{label} must contain each closed-vocabulary value exactly once",
    )
    return value


def validate_between_subject_preregistration(document: dict[str, Any]) -> dict[str, Any]:
    schema = document.get("schema")
    expected_kind = {
        REVISION_APPEAL_PREREG_SCHEMA: "revision_appeal",
        AUTHOR_VOICE_EFFECT_PREREG_SCHEMA: "author_voice_effect",
    }.get(schema)
    require(expected_kind is not None, "between-subject preregistration schema is unsupported")
    safe_component(document.get("preregistration_id"), "between-subject preregistration_id")
    safe_component(document.get("study_id"), "between-subject study_id")
    require(document.get("study_kind") == expected_kind, "between-subject preregistration study_kind does not match its schema")
    parse_utc_timestamp(document.get("registered_at"), "between-subject preregistration registered_at")
    require(document.get("synthetic") is False, "between-subject human study preregistration cannot be synthetic")
    stage = document.get("stage")
    require(stage in {"pilot", "powered"}, "between-subject study stage must be pilot/powered")
    require(document.get("assignment") == "between_subject", "between-subject study cannot assign one reader to both arms")
    span = document.get("chapter_span")
    require(isinstance(span, dict) and set(span) == {"start", "end"}, "between-subject study requires an exact chapter_span")
    start = integer(span.get("start"), "chapter_span.start", minimum=1)
    end = integer(span.get("end"), "chapter_span.end", minimum=start)
    require(end - start == 14, "between-subject study must preregister exactly 15 consecutive chapters")
    labels = document.get("arm_labels")
    require(isinstance(labels, list) and len(labels) == 2, "between-subject study requires two blind arm labels")
    normalized_labels = [safe_component(label, "between-subject arm label") for label in labels]
    require(len(set(normalized_labels)) == 2, "between-subject arm labels must be distinct")
    sample = document.get("sample_size_rule")
    require(isinstance(sample, dict), "between-subject preregistration requires sample_size_rule")
    planned = integer(sample.get("planned"), "preregistered reader count", minimum=2)
    require(planned % 2 == 0, "between-subject study requires equal preregistered arm sizes")
    require(sample.get("unit") == "reader" and sample.get("exact_completed_required") is True, "between-subject study requires exact reader completion")
    expansion = document.get("expansion_rule")
    require(isinstance(expansion, dict) and expansion.get("allowed") is False, "between-subject study cannot expand its sample after registration")
    for key in ("inclusion_rules", "exclusion_rules"):
        rows = document.get(key)
        require(isinstance(rows, list) and rows, f"between-subject preregistration {key} must contain named rules")
        rule_ids = []
        for row in rows:
            require(isinstance(row, dict), f"between-subject preregistration {key} entries must be objects")
            rule_ids.append(safe_component(row.get("rule_id"), f"{key} rule_id"))
            nonempty_text(row.get("criterion"), f"{key} criterion")
        require(len(rule_ids) == len(set(rule_ids)), f"between-subject preregistration {key} rule IDs must be unique")
    for key in ("allocation_algorithm", "random_seed_commitment", "stop_rule"):
        nonempty_text(document.get(key), f"between-subject preregistration {key}")
    require(document.get("secondary_cannot_replace_primary") is True, "secondary endpoints cannot replace the preregistered primary endpoint")

    if expected_kind == "revision_appeal":
        require(document.get("primary_endpoint") == "first_quit_chapter", "revision appeal primary_endpoint must remain first_quit_chapter")
        require_exact_unique_list(document.get("secondary_endpoints"), REVISION_SECONDARY_ENDPOINTS, "revision appeal secondary_endpoints")
        revised = document.get("revised_chapters")
        require(isinstance(revised, list) and revised, "revision appeal must preregister revised_chapters")
        for chapter in revised:
            integer(chapter, "revision appeal revised_chapter", minimum=start, maximum=end)
        require(revised == sorted(set(revised)), "revision appeal revised_chapters must be sorted and unique")
        effect_key = "minimum_detectable_chapter_gain"
        maximum_effect = 15
    else:
        require(document.get("primary_endpoint") == "target_reader_preference", "author voice primary_endpoint must remain target_reader_preference")
        require_exact_unique_list(document.get("secondary_endpoints"), VOICE_SECONDARY_ENDPOINTS, "author voice secondary_endpoints")
        require(document.get("guardrail_rule") == "no-higher-comprehension-or-continuity-regression-rate", "author voice study must protect comprehension and continuity")
        profile_sha256 = document.get("voice_profile_sha256")
        require(is_sha256(profile_sha256), "author voice study requires a frozen voice_profile_sha256")
        require_exact_unique_list(document.get("frozen_condition_keys"), VOICE_FROZEN_CONDITION_KEYS, "author voice frozen_condition_keys")
        effect_key = "minimum_detectable_preference_gain"
        maximum_effect = 4

    decision = document.get("decision_rule")
    require(isinstance(decision, dict), "between-subject preregistration requires decision_rule")
    if stage == "pilot":
        require(document.get("power_analysis") is None, "pilot cannot carry a powered-study claim")
        require(decision == {"algorithm": "underpowered-pilot-no-winner-v1"}, "pilot decision rule must prohibit a winner")
    else:
        expected_algorithm = "restricted-mean-first-quit-chapter-v1" if expected_kind == "revision_appeal" else "mean-target-reader-preference-v1"
        require(set(decision) == {"algorithm", "tie_rule", effect_key}, "powered between-subject decision rule has missing or unsupported fields")
        require(decision.get("algorithm") == expected_algorithm, "powered between-subject decision algorithm is unsupported")
        require(decision.get("tie_rule") == "NO_WINNER", "powered between-subject ties must not select a winner")
        minimum_effect = number(decision.get(effect_key), f"decision_rule.{effect_key}", minimum=0.01, maximum=maximum_effect)
        validate_between_subject_power_plan(document, sample_size=planned, effect_key=effect_key, maximum_effect=maximum_effect)
        require(document["power_analysis"][effect_key] == minimum_effect, "power assumptions and decision rule use different minimum effects")
    return copy.deepcopy(document)


def validate_experiment_preregistration(document: dict[str, Any]) -> dict[str, Any]:
    if document.get("schema") in {REVISION_APPEAL_PREREG_SCHEMA, AUTHOR_VOICE_EFFECT_PREREG_SCHEMA}:
        return validate_between_subject_preregistration(document)
    require(document.get("schema") == EXPERIMENT_PREREG_SCHEMA, f"experiment preregistration schema must be {EXPERIMENT_PREREG_SCHEMA}")
    safe_component(document.get("preregistration_id"), "experiment preregistration_id")
    scope = document.get("scope")
    require(scope in {"story", "system"}, "experiment preregistration scope must be story/system")
    parse_utc_timestamp(document.get("registered_at"), "experiment preregistration registered_at")
    source_kind = document.get("source_kind")
    require(source_kind in {"held_out_original", "synthetic_fixture"}, "experiment preregistration source_kind is invalid")
    require(document.get("synthetic") is (source_kind == "synthetic_fixture"), "synthetic experiment preregistration must be explicit")
    if scope == "story":
        require(document.get("stage") in {"pilot", "formal"}, "story preregistration stage is invalid")
        safe_component(document.get("story_package_id"), "preregistered story_package_id")
        require(is_sha256(document.get("story_package_evidence_sha256")), "story preregistration requires story package evidence SHA-256")
        sample = document.get("sample_size_rule")
        require(isinstance(sample, dict), "story preregistration requires sample_size_rule")
        integer(sample.get("planned"), "preregistered reader count", minimum=2)
        require(sample.get("unit") == "reader" and sample.get("exact_completed_required") is True, "story preregistration requires exact reader completion")
        expansion = document.get("expansion_rule")
        require(isinstance(expansion, dict) and expansion.get("allowed") is False, "v2 production validator currently requires no post-registration sample expansion")
        for key in ("inclusion_rules", "exclusion_rules"):
            rows = document.get(key)
            require(isinstance(rows, list) and rows and all(isinstance(row, dict) and safe_component(row.get("rule_id"), f"{key} rule_id") and isinstance(row.get("criterion"), str) and row["criterion"].strip() for row in rows), f"story preregistration {key} must contain named rules")
        for key in ("allocation_algorithm", "random_seed_commitment", "order_balance_rule", "stop_rule", "primary_endpoint", "primary_analysis", "sequence_contamination_plan"):
            nonempty_text(document.get(key), f"story preregistration {key}")
        require(document.get("arm_treatments") == ["P0", "P1"], "story preregistration must freeze the P0/P1 treatments")
        variant_budget = document.get("variant_budget")
        require(isinstance(variant_budget, dict) and set(variant_budget) == {"P0", "P1"}, "story preregistration requires P0/P1 variant budgets")
        for treatment, budget in variant_budget.items():
            integer(budget, f"{treatment} variant budget", minimum=1)
        integer(document.get("shared_max_visible_chars"), "preregistered shared_max_visible_chars", minimum=500)
        if document["stage"] == "formal":
            require(source_kind == "held_out_original" and document["synthetic"] is False, "formal preregistration cannot use synthetic/reference evidence")
            require(sample["planned"] >= 4, "formal preregistration requires at least four held-out readers")
    else:
        package_ids = document.get("story_package_ids")
        require(isinstance(package_ids, list) and len(package_ids) >= 3 and len(set(package_ids)) == len(package_ids), "system preregistration requires at least three exact story packages")
        prereg_hashes = document.get("story_preregistration_sha256s")
        require(isinstance(prereg_hashes, list) and len(prereg_hashes) == len(package_ids) and len(set(prereg_hashes)) == len(prereg_hashes) and all(is_sha256(value) for value in prereg_hashes), "system preregistration must freeze one preregistration per story package")
        wins = integer(document.get("minimum_candidate_wins"), "system minimum_candidate_wins", minimum=2, maximum=len(package_ids))
        del wins
        require(document.get("ties_count_as_nonwins") is True and document.get("exact_package_set") is True, "system preregistration must freeze package count and tie handling")
        require(source_kind == "held_out_original" and document["synthetic"] is False, "system conclusion cannot use synthetic packages")
    return copy.deepcopy(document)


def record_experiment_preregistration(project: Path, input_path: Path) -> dict[str, Any]:
    project = project.resolve()
    require(check(project)["status"] in {"pass", "replay_required"}, "quality project must be internally consistent")
    document = validate_experiment_preregistration(read_json(input_path, "experiment preregistration"))
    if document.get("schema") == EXPERIMENT_PREREG_SCHEMA and document["scope"] == "story":
        evidence = evidence_by_hash(project, document["story_package_evidence_sha256"])
        require(evidence["kind"] == "story_package" and evidence["artifact"]["story_package_id"] == document["story_package_id"], "experiment preregistration does not match its story package artifact")
        require(evidence["source_kind"] == document["source_kind"] and evidence["synthetic"] is document["synthetic"], "experiment preregistration source differs from story package evidence")
    digest = sha_json(document)
    target = quality_root(project) / "experiment-preregistrations" / f"{digest}.json"
    if target.exists():
        record = experiment_preregistration_record_by_hash(project, digest)
        require(record["preregistration"] == document, "experiment preregistration hash collision")
    else:
        record = {
            "schema": EXPERIMENT_PREREG_RECORD_SCHEMA,
            "preregistration_sha256": digest,
            "recorded_by_lifecycle_at": now(),
            "preregistration": document,
        }
        atomic_json(target, record)
    return {
        "schema": SCHEMA,
        "status": "experiment_preregistration_recorded",
        "preregistration_sha256": digest,
        "recorded_by_lifecycle_at": record["recorded_by_lifecycle_at"],
        "scope": document.get("scope", document.get("study_kind")),
        "synthetic": document["synthetic"],
    }


def experiment_preregistration_record_by_hash(project: Path, digest: object) -> dict[str, Any]:
    require(is_sha256(digest), "experiment preregistration SHA-256 is invalid")
    path = quality_root(project) / "experiment-preregistrations" / f"{digest}.json"
    record = read_json(path, "recorded experiment preregistration")
    require(record.get("schema") == EXPERIMENT_PREREG_RECORD_SCHEMA, "experiment preregistration record schema mismatch")
    require(record.get("preregistration_sha256") == digest, "experiment preregistration record pointer mismatch")
    parse_utc_timestamp(record.get("recorded_by_lifecycle_at"), "preregistration lifecycle receipt")
    require(isinstance(record.get("preregistration"), dict), "experiment preregistration record lacks its document")
    document = validate_experiment_preregistration(record["preregistration"])
    require(sha_json(document) == digest, "recorded experiment preregistration hash mismatch")
    return {**record, "preregistration": document}


def experiment_preregistration_by_hash(project: Path, digest: object) -> dict[str, Any]:
    return experiment_preregistration_record_by_hash(project, digest)["preregistration"]


def validate_experiment_v1(path: Path) -> dict[str, Any]:
    experiment = read_json(path, "longitudinal experiment")
    require(experiment.get("schema") == EXPERIMENT_SCHEMA, f"experiment schema must be {EXPERIMENT_SCHEMA}")
    require(experiment.get("chapters") == 15, "longitudinal experiment must cover exactly 15 sequential chapters")
    require(experiment.get("blind") is True and experiment.get("order_randomized") is True, "experiment must be blind and order-randomized")
    arms = experiment.get("arms")
    require(isinstance(arms, list) and len(arms) == 2, "experiment requires baseline and candidate arms")
    arm_labels: set[str] = set()
    all_hashes: set[str] = set()
    arm_hashes: dict[str, str] = {}
    for arm in arms:
        require(isinstance(arm, dict) and len(arm.get("chapter_artifacts", [])) == 15, "each arm requires 15 chapter body artifacts")
        label = nonempty_text(arm.get("label"), "experiment arm label")
        require(label not in arm_labels, "experiment arm labels must be distinct")
        arm_labels.add(label)
        artifacts = arm["chapter_artifacts"]
        require(
            [row.get("chapter") for row in artifacts if isinstance(row, dict)] == list(range(1, 16)),
            "experiment arm artifacts must cover chapters 1-15 in order",
        )
        hashes = [
            require_bound_text_artifact(row, text_key="body", hash_key="revision", label=f"experiment arm {label}")
            for row in artifacts if isinstance(row, dict)
        ]
        require(len(hashes) == 15 and len(set(hashes)) == 15, "each arm must contain 15 distinct sequential chapter artifacts")
        require(all_hashes.isdisjoint(hashes), "baseline and candidate arms must contain distinct artifacts")
        all_hashes.update(hashes)
        arm_digest = sha_json([{"chapter": row["chapter"], "revision": row["revision"]} for row in artifacts])
        require(arm.get("arm_sha256") == arm_digest, f"experiment arm {label} hash mismatch")
        arm_hashes[label] = arm_digest
    readers = experiment.get("human_cumulative_readers")
    require(isinstance(readers, list) and len(readers) >= 2, "final proof requires at least two human cumulative blind readers")
    reader_ids: set[str] = set()
    blind_codes: set[str] = set()
    allocation = []
    bound_reader_results: list[dict[str, Any]] = []
    for row in readers:
        require(isinstance(row, dict) and row.get("read_from_chapter") == 1 and row.get("read_through_chapter") == 15, "human readers must cumulatively read chapters 1-15")
        reader_id = nonempty_text(row.get("reader_id"), "human reader ID")
        blind_code = nonempty_text(row.get("blind_code"), "human reader blind code")
        require(reader_id not in reader_ids and blind_code not in blind_codes, "human reader IDs and blind codes must be unique")
        reader_ids.add(reader_id)
        blind_codes.add(blind_code)
        arm_order = row.get("arm_order")
        require(isinstance(arm_order, list) and len(arm_order) == 2 and set(arm_order) == arm_labels, "each human reader must blindly read both experiment arms")
        require(row.get("order_randomized") is True, "each human reader arm order must be randomized")
        randomization_nonce = nonempty_text(row.get("randomization_nonce"), "human reader randomization nonce")
        observations_by_arm = row.get("arm_observations")
        require(isinstance(observations_by_arm, dict) and set(observations_by_arm) == arm_labels, "human readers require observations for both blind arms")
        for arm_label in arm_order:
            observations = observations_by_arm[arm_label]
            require(isinstance(observations, list) and [item.get("chapter") for item in observations if isinstance(item, dict)] == list(range(1, 16)), f"human reader arm {arm_label} requires ordered observations for every chapter 1-15")
            for observation in observations:
                require(isinstance(observation, dict), "human observations must be objects")
                for key in ("first_friction", "strongest_read_on", "end_expectation", "cumulative_fatigue"):
                    nonempty_text(observation.get(key), f"human observation {key}")
                require(isinstance(observation.get("target_emotion_received"), bool), "human observation target emotion must be boolean")
                require(isinstance(observation.get("continued"), bool), "human observation continued must be boolean")
        require(row.get("final_preference") in arm_labels | {"tie"}, "human reader final preference is invalid")
        nonempty_text(row.get("final_reason"), "human reader final reason")
        allocation.append({
            "reader_id": reader_id,
            "blind_code": blind_code,
            "arm_order": arm_order,
            "randomization_nonce": randomization_nonce,
        })
        bound_reader_results.append({
            "reader_id": reader_id,
            "blind_code": blind_code,
            "arm_order": arm_order,
            "randomization_nonce": randomization_nonce,
            "arm_observations": observations_by_arm,
            "final_preference": row["final_preference"],
            "final_reason": row["final_reason"],
        })
    require(experiment.get("allocation_sha256") == sha_json(allocation), "human blind allocation hash mismatch")
    sample_plan = experiment.get("sample_size_plan")
    require(isinstance(sample_plan, dict), "experiment requires an explicit sample-size plan")
    require(sample_plan.get("method") in {"pilot_variance", "exact_minimum_with_underpowered_warning"}, "sample-size method is invalid")
    require(sample_plan.get("planned") == len(readers) and sample_plan.get("completed") == len(readers), "sample-size plan must match completed readers")
    nonempty_text(sample_plan.get("rationale"), "sample-size rationale")
    if len(readers) == 2:
        require(sample_plan.get("underpowered_warning") is True, "two-reader pilot must report that it is underpowered")
    require(experiment.get("llm_retention_role") == "proxy_only", "LLM retention is proxy evidence, not final proof")
    require(experiment.get("cost_limited") is False, "quality experiment cannot reduce coverage for cost")
    mapping = experiment.get("blind_mapping")
    require(isinstance(mapping, dict) and mapping.get("revealed_after_observations") is True, "blind arm origins may be revealed only after all observations")
    require(mapping.get("baseline_label") in arm_labels and mapping.get("candidate_label") in arm_labels, "blind mapping must name both experiment arms")
    require(mapping["baseline_label"] != mapping["candidate_label"], "baseline and candidate must map to distinct blind arms")
    outcome = experiment.get("outcome")
    require(isinstance(outcome, dict), "experiment requires an outcome decision")
    require(outcome.get("winner") in {"candidate", "baseline", "tie"}, "experiment outcome winner is invalid")
    nonempty_text(outcome.get("judge_run_id"), "experiment outcome judge_run_id")
    nonempty_text(outcome.get("rationale"), "experiment outcome rationale")
    candidate_label = mapping["candidate_label"]
    baseline_label = mapping["baseline_label"]
    candidate_votes = sum(row["final_preference"] == candidate_label for row in readers)
    baseline_votes = sum(row["final_preference"] == baseline_label for row in readers)
    derived_winner = "candidate" if candidate_votes > baseline_votes else "baseline" if baseline_votes > candidate_votes else "tie"
    outcome_input = {
        "arm_hashes": arm_hashes,
        "reader_result_sha256s": [sha_json(row) for row in bound_reader_results],
        "blind_mapping": mapping,
        "decision_rule": "strict-human-preference-majority-v1",
    }
    require(outcome.get("input_fingerprint") == sha_json(outcome_input), "experiment outcome is not bound to artifacts, readers, and revealed mapping")
    require(outcome.get("winner") == derived_winner, "experiment outcome winner is not derived from the human reader preferences")
    return {
        "schema": SCHEMA,
        "status": "historical_shadow_only",
        "winner": derived_winner,
        "product_release_pass": False,
        "release_gate_status": "BLOCKED_LEGACY_SCHEMA",
        "human_readers": len(readers),
        "chapters": 15,
    }


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    require(total > 0, "preference interval requires readers")
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * ((p * (1 - p) / total + z * z / (4 * total * total)) ** 0.5) / denominator
    return round(max(0.0, center - margin), 6), round(min(1.0, center + margin), 6)


def validate_experiment_v2_document(experiment: dict[str, Any], project: Path | None = None) -> dict[str, Any]:
    require(experiment.get("schema") == EXPERIMENT_SCHEMA_V2, f"experiment schema must be {EXPERIMENT_SCHEMA_V2}")
    require(experiment.get("chapters") == 15, "P1 experiment must cover exactly 15 chapters")
    require(experiment.get("stage") in {"pilot", "formal"}, "experiment stage must be pilot/formal")
    require(project is not None, "P1 experiment v2 must resolve a preregistration from its quality project")
    project = project.resolve()
    preregistration = experiment.get("preregistration")
    require(isinstance(preregistration, dict) and preregistration.get("scope") == "story", "experiment requires a story preregistration")
    preregistration_sha256 = experiment.get("preregistration_sha256")
    preregistration_record = experiment_preregistration_record_by_hash(project, preregistration_sha256)
    recorded_preregistration = preregistration_record["preregistration"]
    require(preregistration == recorded_preregistration and sha_json(preregistration) == preregistration_sha256, "experiment preregistration differs from the immutable pre-observation record")
    require(experiment["stage"] == preregistration["stage"], "experiment stage differs from preregistration")
    registered_at = parse_utc_timestamp(preregistration["registered_at"], "preregistration registered_at")
    recorded_at = parse_utc_timestamp(preregistration_record["recorded_by_lifecycle_at"], "preregistration lifecycle receipt")
    frozen_at = parse_utc_timestamp(experiment.get("artifacts_frozen_at"), "artifacts_frozen_at")
    completed_at = parse_utc_timestamp(experiment.get("observations_completed_at"), "observations_completed_at")
    require(registered_at <= recorded_at <= frozen_at <= completed_at, "preregistration lifecycle receipt, artifact freeze, and observation completion must be ordered")
    require(experiment.get("blind") is True and experiment.get("revealed_after_observations") is True, "experiment must remain blind through observation completion")
    require(experiment.get("llm_retention_role") == "proxy_only", "LLM retention remains proxy-only")
    story_package_id = safe_component(experiment.get("story_package_id"), "experiment story_package_id")
    require(story_package_id == preregistration["story_package_id"], "experiment story package differs from preregistration")
    package_evidence = evidence_by_hash(project, preregistration["story_package_evidence_sha256"])
    require(package_evidence["kind"] == "story_package" and package_evidence["artifact"]["story_package_id"] == story_package_id, "experiment is not bound to the frozen story package evidence")
    require(package_evidence["source_kind"] == preregistration["source_kind"] and package_evidence["synthetic"] is preregistration["synthetic"], "experiment source differs from preregistered package source")

    arms = experiment.get("arms")
    require(isinstance(arms, list) and len(arms) == 2, "P1 experiment requires exactly P0/P1 arms")
    labels: set[str] = set()
    treatments: set[str] = set()
    all_body_hashes: set[str] = set()
    arm_hashes: dict[str, str] = {}
    artifacts_by_label: dict[str, dict[int, dict[str, Any]]] = {}
    workflow_receipt_times: list[datetime] = []
    common_provenance: dict[str, set[str]] = {key: set() for key in ("creative_package_sha256", "author_identity_sha256", "writer_identity_sha256", "model_identity_sha256", "context_sha256")}
    common_control_fingerprints: set[str] = set()
    for arm in arms:
        require(isinstance(arm, dict), "experiment arms must be objects")
        label = safe_component(arm.get("label"), "experiment arm label")
        treatment = arm.get("treatment")
        require(label not in labels and treatment in {"P0", "P1"}, "experiment arm label/treatment is invalid")
        labels.add(label)
        treatments.add(treatment)
        provenance = arm.get("provenance")
        require(isinstance(provenance, dict), "experiment arm provenance must be an object")
        nonempty_text(provenance.get("workflow_version"), "workflow_version")
        require(provenance.get("arm_source_kind") == "workflow_generated", "P0/P1 causal arms must both be workflow-generated, not legacy/reference prose")
        require(provenance.get("story_package_id") == story_package_id, "experiment arm story package mismatch")
        require(provenance.get("story_package_evidence_sha256") == preregistration["story_package_evidence_sha256"], "experiment arm is not bound to frozen story package evidence")
        for key in common_provenance:
            digest = provenance.get(key)
            require(is_sha256(digest), f"arm provenance {key} must be SHA-256")
            common_provenance[key].add(str(digest))
        require(provenance.get("variant_budget") == preregistration["variant_budget"], "arm variant budget differs from preregistration")
        require(provenance.get("stop_rule") == preregistration["stop_rule"], "arm stop rule differs from preregistration")
        chapter_artifacts = arm.get("chapter_artifacts")
        require(isinstance(chapter_artifacts, list) and [row.get("chapter") for row in chapter_artifacts if isinstance(row, dict)] == list(range(1, 16)), "each experiment arm requires chapters 1-15")
        artifact_map: dict[int, dict[str, Any]] = {}
        hashes = []
        for row in chapter_artifacts:
            digest = require_bound_text_artifact(row, text_key="body", hash_key="revision", label=f"experiment arm {label}")
            require(digest not in all_body_hashes, "experiment arms must contain mutually exclusive body artifacts")
            all_body_hashes.add(digest)
            hashes.append(digest)
            artifact_map[int(row["chapter"])] = row
        arm_digest = sha_json([{"chapter": row["chapter"], "revision": row["revision"]} for row in chapter_artifacts])
        require(arm.get("arm_sha256") == arm_digest, f"experiment arm {label} hash mismatch")
        arm_hashes[label] = arm_digest
        artifacts_by_label[label] = artifact_map
        workflow_record = evidence_record_by_hash(project, provenance.get("workflow_evidence_sha256"))
        workflow = workflow_record["evidence"]
        workflow_receipt_times.append(parse_utc_timestamp(workflow_record["recorded_by_lifecycle_at"], "workflow lifecycle receipt"))
        require(workflow["kind"] == "workflow_run", "experiment arm lacks a recorded workflow run")
        require(workflow["artifact"]["story_package_id"] == story_package_id and workflow["artifact"]["treatment"] == treatment, "experiment arm workflow receipt treatment/story mismatch")
        require(workflow["artifact"]["story_package_evidence_sha256"] == preregistration["story_package_evidence_sha256"], "experiment arm workflow receipt package mismatch")
        require(workflow["artifact"]["workflow_version"] == provenance["workflow_version"], "experiment arm workflow version differs from its receipt")
        require(workflow["artifact"]["variant_budget"] == preregistration["variant_budget"] and workflow["artifact"]["stop_rule"] == preregistration["stop_rule"], "experiment arm workflow budget differs from its receipt")
        require(workflow["artifact"]["shared_max_visible_chars"] == preregistration["shared_max_visible_chars"], "experiment arm visible-character budget differs from preregistration")
        require(all(provenance[key] == workflow["artifact"]["common_provenance"][key] for key in common_provenance), "experiment arm common provenance is not derived from its workflow receipt")
        require(provenance.get("common_control_sha256") == workflow["artifact"]["common_control_sha256"], "experiment arm common-control fingerprint differs from its workflow receipt")
        common_control_fingerprints.add(workflow["artifact"]["common_control_sha256"])
        require(workflow["artifact"]["outputs"] == [{"chapter": row["chapter"], "revision": row["revision"]} for row in chapter_artifacts], "experiment arm bodies differ from the recorded workflow outputs")
        if experiment["stage"] == "formal":
            require(workflow["source_kind"] == "accepted_lifecycle" and workflow["synthetic"] is False, "formal experiment requires non-synthetic lifecycle workflow receipts")
    require(treatments == {"P0", "P1"}, "experiment must compare one P0 and one P1 arm")
    require(all(len(values) == 1 for values in common_provenance.values()), "P0/P1 arms must share the same frozen creative package, author/writer/model, and context")
    require(len(common_control_fingerprints) == 1, "P0/P1 arms do not share the same lifecycle-derived common control")
    require(next(iter(common_provenance["creative_package_sha256"])) == package_evidence["artifact"]["creative_package_sha256"], "arm creative package hash differs from the preregistered artifact")
    mapping = experiment.get("blind_mapping")
    require(isinstance(mapping, dict), "experiment requires a blind mapping")
    baseline_label = mapping.get("baseline_label")
    candidate_label = mapping.get("candidate_label")
    require({baseline_label, candidate_label} == labels, "blind mapping must identify distinct experiment arms")
    by_label = {arm["label"]: arm for arm in arms}
    require(by_label[baseline_label]["treatment"] == "P0" and by_label[candidate_label]["treatment"] == "P1", "blind mapping treatment origins are invalid")

    readers = experiment.get("human_cumulative_readers")
    require(isinstance(readers, list) and len(readers) >= 2, "experiment requires human cumulative readers")
    if experiment["stage"] == "formal":
        require(len(readers) >= 4 and experiment.get("held_out") is True, "formal experiment requires held-out human readers")
    reader_ids: set[str] = set()
    blind_codes: set[str] = set()
    orders: list[tuple[str, str]] = []
    allocation = []
    reader_results = []
    human_receipt_times: list[datetime] = []
    for row in readers:
        require(isinstance(row, dict), "human reader rows must be objects")
        reader_id = safe_component(row.get("reader_id"), "human reader_id")
        blind_code = safe_component(row.get("blind_code"), "human blind_code")
        require(reader_id not in reader_ids and blind_code not in blind_codes, "human reader IDs and blind codes must be unique")
        reader_ids.add(reader_id)
        blind_codes.add(blind_code)
        profile = row.get("persona_profile")
        require(isinstance(profile, dict), "human reader requires persona_profile")
        persona_id = safe_component(row.get("persona_id"), "human persona_id")
        require(row.get("persona_profile_sha256") == sha_json(profile), "human persona profile hash mismatch")
        source = row.get("human_evidence")
        require(isinstance(source, dict), "human reader requires a bound imported evidence record")
        human_record = evidence_record_by_hash(project, source.get("evidence_bundle_sha256"))
        human_bundle = human_record["evidence"]
        human_receipt_times.append(parse_utc_timestamp(human_record["recorded_by_lifecycle_at"], "human import lifecycle receipt"))
        require(human_bundle["kind"] == "human_reader_import", "human reader evidence must reference a recorded human import")
        require(human_bundle["artifact"]["story_package_ids"] == [story_package_id], "human reader import is not bound to this exact story package")
        imported_reader_id = safe_component(source.get("imported_reader_id"), "imported human reader ID")
        imported_reader = next((item for item in human_bundle["artifact"]["readers"] if item["reader_id"] == imported_reader_id), None)
        require(isinstance(imported_reader, dict), "experiment reader is absent from its human import")
        require(imported_reader_id == reader_id, "experiment reader ID differs from its imported evidence")
        require(imported_reader["blind_code"] == blind_code and imported_reader["persona_id"] == persona_id and imported_reader["persona_profile_sha256"] == row["persona_profile_sha256"], "experiment reader identity/profile differs from its import")
        order = row.get("arm_order")
        require(isinstance(order, list) and len(order) == 2 and set(order) == labels, "every human must read both blind arms")
        orders.append((order[0], order[1]))
        nonempty_text(row.get("randomization_nonce"), "human randomization_nonce")
        observations = row.get("arm_observations")
        require(isinstance(observations, dict) and set(observations) == labels, "human reader requires both arm observations")
        expected_raw_observations = {
            "arm_order": order,
            "randomization_nonce": row["randomization_nonce"],
            "arm_observations": observations,
            "final_preference": row.get("final_preference"),
            "final_reason": row.get("final_reason"),
        }
        require(
            imported_reader["raw_observations"] == expected_raw_observations
            and imported_reader["raw_observation_sha256"] == sha_json(expected_raw_observations),
            "human reader observations/preferences differ from the immutable import",
        )
        if experiment["stage"] == "formal":
            require(human_bundle["source_kind"] == "human_blind_import" and human_bundle["synthetic"] is False, "formal experiment cannot use synthetic reader evidence")
        for label in order:
            arm_rows = observations[label]
            require(isinstance(arm_rows, list) and [item.get("chapter") for item in arm_rows if isinstance(item, dict)] == list(range(1, 16)), "human arm observations must cover chapters 1-15")
            for observation in arm_rows:
                measurement_row = {
                    "reader_schema": READER_SCHEMA_V3,
                    "persona_id": persona_id,
                    "persona_profile": profile,
                    "persona_profile_sha256": row["persona_profile_sha256"],
                    "evidence_type": "human",
                    "measurements": observation.get("measurements"),
                }
                visible = len(re.sub(r"\s+", "", artifacts_by_label[label][int(observation["chapter"])]["body"]))
                validate_reader_measurements(measurement_row, candidate_visible_chars=visible)
        require(row.get("final_preference") in labels | {"tie"}, "human final preference is invalid")
        nonempty_text(row.get("final_reason"), "human final reason")
        allocation.append({key: row[key] for key in ("reader_id", "blind_code", "arm_order", "randomization_nonce", "persona_id", "persona_profile_sha256")})
        reader_results.append({"reader_id": reader_id, "arm_order": order, "arm_observations": observations, "final_preference": row["final_preference"], "final_reason": row["final_reason"]})
    require(experiment.get("allocation_sha256") == sha_json(allocation), "human allocation hash mismatch")
    require(workflow_receipt_times and human_receipt_times, "experiment lacks lifecycle evidence receipts")
    require(recorded_at <= min(workflow_receipt_times), "workflow evidence was recorded before the experiment preregistration")
    require(max(workflow_receipt_times) <= min(human_receipt_times), "human observations were imported before the experiment arms were frozen")
    require(frozen_at == max(workflow_receipt_times), "artifacts_frozen_at must equal the latest workflow lifecycle receipt")
    require(completed_at == max(human_receipt_times), "observations_completed_at must equal the latest human import lifecycle receipt")
    require(completed_at <= datetime.now(timezone.utc), "experiment observations_completed_at cannot be in the future")
    sample_rule = preregistration["sample_size_rule"]
    require(sample_rule["planned"] == len(readers), "completed readers do not match the preregistered exact sample size")
    enrollment = experiment.get("enrollment")
    require(isinstance(enrollment, dict), "experiment requires an enrollment/accounting record")
    included_ids = enrollment.get("included_reader_ids")
    excluded = enrollment.get("excluded")
    require(isinstance(included_ids, list) and included_ids == [row["reader_id"] for row in readers], "experiment included reader IDs must equal the analyzed cohort in order")
    require(isinstance(excluded, list), "experiment excluded readers must be a list")
    allowed_exclusion_ids = {row["rule_id"] for row in preregistration["exclusion_rules"]}
    for row in excluded:
        require(isinstance(row, dict) and safe_component(row.get("reader_id"), "excluded reader_id"), "excluded reader record is invalid")
        require(row.get("rule_id") in allowed_exclusion_ids, "excluded reader does not match a preregistered exclusion rule")
        nonempty_text(row.get("evidence"), "excluded reader evidence")
    require(enrollment.get("screened") == len(readers) + len(excluded), "experiment screened count is not derived from inclusion/exclusion accounting")
    first_orders = sum(order[0] == candidate_label for order in orders)
    require(abs(first_orders - (len(orders) - first_orders)) <= 1, "two-arm reading order is not counterbalanced")
    require(experiment.get("sequence_contamination_reported") is True, "paired reading must report order/repeated-reading contamination")

    candidate_votes = sum(row["final_preference"] == candidate_label for row in readers)
    baseline_votes = sum(row["final_preference"] == baseline_label for row in readers)
    ties = len(readers) - candidate_votes - baseline_votes
    winner = (
        "candidate" if candidate_votes * 2 > len(readers)
        else "baseline" if baseline_votes * 2 > len(readers)
        else "tie"
    )
    lower, upper = wilson_interval(candidate_votes, len(readers))
    expected_effect = {
        "unit": "reader",
        "candidate_votes": candidate_votes,
        "baseline_votes": baseline_votes,
        "ties": ties,
        "preference_rate": round(candidate_votes / len(readers), 6),
        "confidence_method": "wilson-95",
        "confidence_interval": [lower, upper],
    }
    require(experiment.get("effect_report") == expected_effect, "experiment effect report is not derived from reader-level results")
    outcome = experiment.get("outcome")
    require(isinstance(outcome, dict) and outcome.get("winner") == winner, "experiment outcome is not derived from human preferences")
    outcome_input = {"arm_hashes": arm_hashes, "reader_result_sha256s": [sha_json(row) for row in reader_results], "blind_mapping": mapping, "decision_rule": "strict-human-preference-majority-v2"}
    require(outcome.get("input_fingerprint") == sha_json(outcome_input), "experiment outcome fingerprint mismatch")
    # Formal result validation is descriptive until the lifecycle can recompute
    # cross-stage participant/content non-reuse and a preregistered power audit.
    # Keep the release bit fail-closed instead of converting a schema minimum
    # (currently four readers) into a product claim.
    product_release_pass = False
    require(outcome.get("product_release_pass") is False, "product release remains blocked pending power and cross-stage independence audits")
    return {
        "schema": SCHEMA,
        "status": "valid_experiment",
        "winner": winner,
        "product_release_pass": product_release_pass,
        "release_gate_status": "BLOCKED_PENDING_POWER_AND_INDEPENDENCE_AUDIT",
        "human_readers": len(readers),
        "story_package_sha256": next(iter(common_provenance["creative_package_sha256"])),
        "story_package_id": story_package_id,
        "preregistration_sha256": preregistration_sha256,
        "effect_report": expected_effect,
        "experiment_sha256": sha_json(experiment),
    }


def validate_experiment_v2(path: Path, project: Path) -> dict[str, Any]:
    return validate_experiment_v2_document(read_json(path, "P1 longitudinal experiment"), project)


def resolve_between_subject_preregistration(
    experiment: dict[str, Any],
    project: Path | None,
    expected_schema: str,
) -> tuple[Path, dict[str, Any], str, datetime]:
    require(project is not None, "between-subject experiment must resolve its immutable preregistration from a quality project")
    project = project.resolve()
    preregistration = experiment.get("preregistration")
    require(isinstance(preregistration, dict) and preregistration.get("schema") == expected_schema, "between-subject experiment preregistration schema mismatch")
    preregistration_sha256 = experiment.get("preregistration_sha256")
    record = experiment_preregistration_record_by_hash(project, preregistration_sha256)
    recorded = record["preregistration"]
    require(preregistration == recorded and sha_json(preregistration) == preregistration_sha256, "between-subject preregistration differs from its immutable record")
    require(experiment.get("study_id") == preregistration["study_id"], "between-subject experiment study_id differs from preregistration")
    require(experiment.get("stage") == preregistration["stage"], "between-subject experiment stage differs from preregistration")
    require(experiment.get("primary_endpoint") == preregistration["primary_endpoint"], "between-subject primary endpoint differs from preregistration")
    require(experiment.get("secondary_endpoints") == preregistration["secondary_endpoints"], "between-subject secondary endpoints differ from preregistration")
    recorded_at = parse_utc_timestamp(record["recorded_by_lifecycle_at"], "between-subject preregistration lifecycle receipt")
    registered_at = parse_utc_timestamp(preregistration["registered_at"], "between-subject preregistration registered_at")
    require(registered_at <= recorded_at, "between-subject preregistration claims a future registration time")
    return project, preregistration, str(preregistration_sha256), recorded_at


def load_between_subject_arms(
    project: Path,
    experiment: dict[str, Any],
    preregistration: dict[str, Any],
    preregistered_at: datetime,
) -> tuple[dict[str, dict[str, Any]], dict[str, str], list[datetime]]:
    rows = experiment.get("arms")
    require(isinstance(rows, list) and len(rows) == 2, "between-subject experiment requires exactly two arms")
    artifacts: dict[str, dict[str, Any]] = {}
    evidence_hashes: dict[str, str] = {}
    receipt_times: list[datetime] = []
    for row in rows:
        require(isinstance(row, dict) and set(row) == {"label", "evidence_sha256"}, "between-subject arm references must contain only label and evidence_sha256")
        label = safe_component(row.get("label"), "between-subject experiment arm label")
        require(label not in artifacts, "between-subject experiment arm labels must be distinct")
        record = evidence_record_by_hash(project, row.get("evidence_sha256"))
        evidence = record["evidence"]
        require(evidence["kind"] == "between_subject_arm" and evidence["source_kind"] == "frozen_study_artifact" and evidence["synthetic"] is False, "between-subject experiment arm must cite frozen non-synthetic evidence")
        artifact = evidence["artifact"]
        require(artifact["study_id"] == preregistration["study_id"] and artifact["study_kind"] == preregistration["study_kind"], "between-subject arm study identity mismatch")
        require(artifact["blind_label"] == label, "between-subject arm label differs from immutable evidence")
        artifacts[label] = artifact
        evidence_hashes[label] = str(row["evidence_sha256"])
        receipt_times.append(parse_utc_timestamp(record["recorded_by_lifecycle_at"], "between-subject arm lifecycle receipt"))
    require(set(artifacts) == set(preregistration["arm_labels"]), "between-subject arms differ from preregistered blind labels")
    require(preregistered_at <= min(receipt_times), "between-subject arms were frozen before preregistration")
    frozen_at = parse_utc_timestamp(experiment.get("artifacts_frozen_at"), "between-subject artifacts_frozen_at")
    require(frozen_at == max(receipt_times), "between-subject artifacts_frozen_at must equal the latest arm evidence receipt")
    return artifacts, evidence_hashes, receipt_times


def validate_between_subject_enrollment(
    experiment: dict[str, Any],
    preregistration: dict[str, Any],
    readers: list[dict[str, Any]],
) -> None:
    enrollment = experiment.get("enrollment")
    require(isinstance(enrollment, dict), "between-subject experiment requires enrollment accounting")
    included = enrollment.get("included_reader_ids")
    excluded = enrollment.get("excluded")
    require(isinstance(included, list) and included == [row["reader_id"] for row in readers], "between-subject included reader IDs must equal the analyzed cohort in order")
    require(isinstance(excluded, list), "between-subject excluded readers must be a list")
    allowed_rules = {row["rule_id"] for row in preregistration["exclusion_rules"]}
    for row in excluded:
        require(isinstance(row, dict), "between-subject excluded reader record must be an object")
        safe_component(row.get("reader_id"), "between-subject excluded reader_id")
        require(row.get("rule_id") in allowed_rules, "between-subject excluded reader does not match a preregistered rule")
        nonempty_text(row.get("evidence"), "between-subject excluded reader evidence")
    require(enrollment.get("screened") == len(readers) + len(excluded), "between-subject screened count is not derived from enrollment")


def validate_between_subject_readers(
    project: Path,
    experiment: dict[str, Any],
    preregistration: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    arm_receipt_times: list[datetime],
    *,
    require_humans: bool,
    voice_effect: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[datetime]]:
    readers = experiment.get("human_readers")
    require(isinstance(readers, list), "between-subject human_readers must be a list")
    if not readers:
        require(not require_humans, "revision appeal experiment requires human readers")
        return [], [], []
    planned = preregistration["sample_size_rule"]["planned"]
    require(len(readers) == planned, "between-subject completed readers do not match the exact preregistered sample")
    labels = set(artifacts)
    expected_chapters = list(range(preregistration["chapter_span"]["start"], preregistration["chapter_span"]["end"] + 1))
    reader_ids: set[str] = set()
    blind_codes: set[str] = set()
    arm_counts = {label: 0 for label in labels}
    results: list[dict[str, Any]] = []
    human_receipt_times: list[datetime] = []
    for row in readers:
        require(isinstance(row, dict), "between-subject reader rows must be objects")
        reader_id = safe_component(row.get("reader_id"), "between-subject reader_id")
        blind_code = safe_component(row.get("blind_code"), "between-subject blind_code")
        require(reader_id not in reader_ids and blind_code not in blind_codes, "between-subject reader IDs and blind codes must be unique")
        reader_ids.add(reader_id)
        blind_codes.add(blind_code)
        assignment = safe_component(row.get("assignment"), "between-subject reader assignment")
        require(assignment in labels, "between-subject reader assignment is not a preregistered arm")
        arm_counts[assignment] += 1
        profile = row.get("persona_profile")
        require(isinstance(profile, dict), "between-subject reader requires persona_profile")
        persona_id = safe_component(row.get("persona_id"), "between-subject persona_id")
        require(row.get("persona_profile_sha256") == sha_json(profile), "between-subject reader persona profile hash mismatch")
        observations = row.get("chapter_observations")
        require(isinstance(observations, list) and len(observations) == 15, "between-subject reader must report all 15 assigned-arm chapters in order")
        observation_chapters = []
        for item in observations:
            require(isinstance(item, dict), "between-subject chapter observation must be an object")
            observation_chapters.append(integer(item.get("chapter"), "between-subject observation chapter", minimum=1))
        require(observation_chapters == expected_chapters, "between-subject reader must report all 15 assigned-arm chapters in order")
        previous_measurements: dict[str, Any] | None = None
        for observation in observations:
            chapter = integer(observation["chapter"], "between-subject observation chapter", minimum=1)
            measurement_row = {
                "reader_schema": READER_SCHEMA_V3,
                "persona_id": persona_id,
                "persona_profile": profile,
                "persona_profile_sha256": row["persona_profile_sha256"],
                "evidence_type": "human",
                "measurements": observation.get("measurements"),
            }
            body = artifacts[assignment]["chapter_artifacts"][chapter - expected_chapters[0]]["body"]
            measurements = validate_reader_measurements(measurement_row, candidate_visible_chars=len(re.sub(r"\s+", "", body)))
            first_quit = measurements.get("first_quit_chapter")
            require(first_quit is None or expected_chapters[0] <= first_quit <= expected_chapters[-1], "between-subject first_quit_chapter must stay within the assigned 15-chapter span")
            if previous_measurements is not None:
                validate_reader_measurement_transition(previous_measurements, measurements, chapter)
            if first_quit is None:
                require(measurements["continued_by_choice"] is True and measurements["continued_for_study"] is False, "pre-quit reading must remain natural rather than study-forced")
            elif chapter == first_quit:
                require(measurements["continued_by_choice"] is False and measurements["continued_for_study"] is False, "natural quit chapter cannot be marked as study continuation")
            else:
                require(measurements["continued_by_choice"] is False and measurements["continued_for_study"] is True, "post-quit observations must be marked study continuation")
            previous_measurements = measurements
        source = row.get("human_evidence")
        require(isinstance(source, dict), "between-subject reader requires immutable human evidence")
        human_record = evidence_record_by_hash(project, source.get("evidence_bundle_sha256"))
        human_bundle = human_record["evidence"]
        require(human_bundle["kind"] == "human_reader_import" and human_bundle["source_kind"] == "human_blind_import" and human_bundle["synthetic"] is False, "between-subject reader evidence must be a non-synthetic human import")
        require(human_bundle["artifact"]["story_package_ids"] == [preregistration["study_id"]], "between-subject human import study identity mismatch")
        imported_id = safe_component(source.get("imported_reader_id"), "between-subject imported reader_id")
        imported = next((item for item in human_bundle["artifact"]["readers"] if item["reader_id"] == imported_id), None)
        require(isinstance(imported, dict) and imported_id == reader_id, "between-subject reader is absent from its human import")
        expected_raw: dict[str, Any] = {"assignment": assignment, "chapter_observations": observations}
        if voice_effect:
            voice_evaluation = row.get("voice_evaluation")
            require(isinstance(voice_evaluation, dict) and set(voice_evaluation) == {"target_reader_preference", "comprehension_regression", "continuity_regression", "voice_loss"}, "author voice reader evaluation is incomplete")
            integer(voice_evaluation.get("target_reader_preference"), "target_reader_preference", minimum=1, maximum=5)
            require(all(isinstance(voice_evaluation.get(key), bool) for key in ("comprehension_regression", "continuity_regression", "voice_loss")), "author voice regression observations must be boolean")
            expected_raw["voice_evaluation"] = voice_evaluation
        require(imported["evidence_type"] == "human", "between-subject imported reader cannot be an LLM proxy")
        require(imported["blind_code"] == blind_code and imported["persona_id"] == persona_id and imported["persona_profile_sha256"] == row["persona_profile_sha256"], "between-subject reader identity/profile differs from its import")
        require(imported["raw_observations"] == expected_raw and imported["raw_observation_sha256"] == sha_json(expected_raw), "between-subject observations differ from the immutable human import")
        human_receipt_times.append(parse_utc_timestamp(human_record["recorded_by_lifecycle_at"], "between-subject human import lifecycle receipt"))
        results.append({
            "reader_id": reader_id,
            "assignment": assignment,
            "first_quit_chapter": previous_measurements.get("first_quit_chapter") if previous_measurements else None,
            "raw_observation_sha256": imported["raw_observation_sha256"],
            **({"voice_evaluation": row["voice_evaluation"]} if voice_effect else {}),
        })
    require(all(count == planned // 2 for count in arm_counts.values()), "between-subject readers must be equally allocated across arms")
    validate_between_subject_enrollment(experiment, preregistration, readers)
    require(max(arm_receipt_times) <= min(human_receipt_times), "between-subject human observations were imported before both arms were frozen")
    completed_at = parse_utc_timestamp(experiment.get("observations_completed_at"), "between-subject observations_completed_at")
    require(completed_at == max(human_receipt_times) and completed_at <= datetime.now(timezone.utc), "between-subject observations_completed_at must equal the latest non-future human import receipt")
    return readers, results, human_receipt_times


def between_subject_outcome_fingerprint(
    preregistration_sha256: str,
    arm_evidence_hashes: dict[str, str],
    reader_results: list[dict[str, Any]],
    blind_mapping: dict[str, Any],
    decision_rule: dict[str, Any],
) -> str:
    return sha_json({
        "preregistration_sha256": preregistration_sha256,
        "arm_evidence_sha256s": arm_evidence_hashes,
        "reader_result_sha256s": [sha_json(row) for row in reader_results],
        "blind_mapping": blind_mapping,
        "decision_rule": decision_rule,
    })


def first_quit_effect_report(
    results: list[dict[str, Any]],
    labels: tuple[str, str],
    chapter_end: int,
) -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    for label in labels:
        rows = [row for row in results if row["assignment"] == label]
        quit_chapters = [row["first_quit_chapter"] for row in rows]
        scores = [chapter_end + 1 if chapter is None else chapter for chapter in quit_chapters]
        summaries[label] = {
            "reader_count": len(rows),
            "first_quit_chapters": quit_chapters,
            "censored_no_quit": sum(chapter is None for chapter in quit_chapters),
            "restricted_mean_first_quit_chapter": round(sum(scores) / len(scores), 6),
        }
    return {"unit": "reader", "arms": summaries}


def validate_revision_appeal_experiment_document(
    experiment: dict[str, Any],
    project: Path | None,
) -> dict[str, Any]:
    require(experiment.get("schema") == REVISION_APPEAL_EXPERIMENT_SCHEMA, f"revision appeal schema must be {REVISION_APPEAL_EXPERIMENT_SCHEMA}")
    project, preregistration, prereg_sha256, preregistered_at = resolve_between_subject_preregistration(
        experiment, project, REVISION_APPEAL_PREREG_SCHEMA,
    )
    require(experiment.get("blind") is True and experiment.get("mapping_revealed_after_observations") is True, "revision appeal experiment must remain blind through observation completion")
    require(experiment.get("llm_reader_role") == "proxy_only", "LLM readers cannot replace revision appeal human evidence")
    artifacts, arm_hashes, arm_receipts = load_between_subject_arms(project, experiment, preregistration, preregistered_at)
    mapping = experiment.get("blind_mapping")
    require(isinstance(mapping, dict) and set(mapping) == {"baseline_label", "candidate_label"}, "revision appeal blind_mapping is invalid")
    baseline_label = safe_component(mapping.get("baseline_label"), "revision appeal baseline_label")
    candidate_label = safe_component(mapping.get("candidate_label"), "revision appeal candidate_label")
    require({baseline_label, candidate_label} == set(artifacts), "revision appeal blind mapping must identify both arms")
    baseline = artifacts[baseline_label]["chapter_artifacts"]
    candidate = artifacts[candidate_label]["chapter_artifacts"]
    expected_chapters = list(range(preregistration["chapter_span"]["start"], preregistration["chapter_span"]["end"] + 1))
    require([row["chapter"] for row in baseline] == expected_chapters and [row["chapter"] for row in candidate] == expected_chapters, "revision appeal arms must match the preregistered continuous chapter span")
    changed = [
        chapter
        for chapter, left, right in zip(expected_chapters, baseline, candidate)
        if left["revision"] != right["revision"]
    ]
    require(changed, "revision appeal candidate must change at least one preregistered chapter")
    require(set(changed) <= set(preregistration["revised_chapters"]), "revision appeal candidate changes an unregistered chapter")
    readers, reader_results, _ = validate_between_subject_readers(
        project, experiment, preregistration, artifacts, arm_receipts,
        require_humans=True, voice_effect=False,
    )
    allocation = [
        {key: row[key] for key in ("reader_id", "blind_code", "assignment", "persona_id", "persona_profile_sha256")}
        for row in readers
    ]
    require(experiment.get("allocation_sha256") == sha_json(allocation), "revision appeal allocation hash mismatch")
    effect_report = first_quit_effect_report(reader_results, (baseline_label, candidate_label), expected_chapters[-1])
    decision = preregistration["decision_rule"]
    fingerprint = between_subject_outcome_fingerprint(prereg_sha256, arm_hashes, reader_results, mapping, decision)
    if preregistration["stage"] == "pilot":
        expected_outcome = {
            "status": "UNDERPOWERED_PILOT",
            "winner": None,
            "conclusion_allowed": False,
            "input_fingerprint": fingerprint,
        }
    else:
        baseline_mean = effect_report["arms"][baseline_label]["restricted_mean_first_quit_chapter"]
        candidate_mean = effect_report["arms"][candidate_label]["restricted_mean_first_quit_chapter"]
        gain = round(candidate_mean - baseline_mean, 6)
        threshold = decision["minimum_detectable_chapter_gain"]
        winner = "candidate" if gain >= threshold else "baseline" if gain <= -threshold else None
        expected_outcome = {
            "status": "POWERED_RESULT",
            "winner": winner,
            "conclusion_allowed": True,
            "observed_chapter_gain": gain,
            "single_book_only": True,
            "input_fingerprint": fingerprint,
        }
    require(experiment.get("outcome") == expected_outcome, "revision appeal outcome is not derived from the preregistered primary endpoint")
    return {
        "schema": SCHEMA,
        "status": expected_outcome["status"],
        "winner": expected_outcome["winner"],
        "human_readers": len(readers),
        "changed_chapters": changed,
        "primary_endpoint": "first_quit_chapter",
        "effect_report": effect_report,
        "experiment_sha256": sha_json(experiment),
    }


def voice_effect_report(results: list[dict[str, Any]], labels: tuple[str, str]) -> dict[str, Any]:
    summaries: dict[str, dict[str, Any]] = {}
    for label in labels:
        rows = [row["voice_evaluation"] for row in results if row["assignment"] == label]
        summaries[label] = {
            "reader_count": len(rows),
            "mean_target_reader_preference": round(sum(row["target_reader_preference"] for row in rows) / len(rows), 6),
            "comprehension_regressions": sum(row["comprehension_regression"] for row in rows),
            "continuity_regressions": sum(row["continuity_regression"] for row in rows),
            "voice_loss_reports": sum(row["voice_loss"] for row in rows),
        }
    return {"unit": "reader", "arms": summaries}


def validate_author_voice_effect_document(
    experiment: dict[str, Any],
    project: Path | None,
) -> dict[str, Any]:
    require(experiment.get("schema") == AUTHOR_VOICE_EFFECT_SCHEMA, f"author voice effect schema must be {AUTHOR_VOICE_EFFECT_SCHEMA}")
    project, preregistration, prereg_sha256, preregistered_at = resolve_between_subject_preregistration(
        experiment, project, AUTHOR_VOICE_EFFECT_PREREG_SCHEMA,
    )
    require(experiment.get("blind") is True, "author voice effect study must remain blind")
    require(experiment.get("llm_reader_role") == "proxy_only", "LLM readers cannot replace author voice human evidence")
    artifacts, arm_hashes, arm_receipts = load_between_subject_arms(project, experiment, preregistration, preregistered_at)
    mapping = experiment.get("blind_mapping")
    require(isinstance(mapping, dict) and set(mapping) == {"control_label", "voice_label"}, "author voice blind_mapping is invalid")
    control_label = safe_component(mapping.get("control_label"), "author voice control_label")
    voice_label = safe_component(mapping.get("voice_label"), "author voice voice_label")
    require({control_label, voice_label} == set(artifacts), "author voice blind mapping must identify both arms")
    control = artifacts[control_label]
    treatment = artifacts[voice_label]
    require(control["common_conditions"] == treatment["common_conditions"], "author voice arms must share plot, model, context, budget, and stop rule")
    require(control["treatment"] == {"voice_enabled": False, "voice_profile_sha256": None}, "author voice control arm must disable only the voice treatment")
    require(treatment["treatment"] == {"voice_enabled": True, "voice_profile_sha256": preregistration["voice_profile_sha256"]}, "author voice candidate arm must use the preregistered voice profile")
    expected_chapters = list(range(preregistration["chapter_span"]["start"], preregistration["chapter_span"]["end"] + 1))
    require(all([row["chapter"] for row in artifact["chapter_artifacts"]] == expected_chapters for artifact in artifacts.values()), "author voice arms must match the same preregistered chapter span")
    readers, reader_results, _ = validate_between_subject_readers(
        project, experiment, preregistration, artifacts, arm_receipts,
        require_humans=False, voice_effect=True,
    )
    decision = preregistration["decision_rule"]
    fingerprint = between_subject_outcome_fingerprint(prereg_sha256, arm_hashes, reader_results, mapping, decision)
    if not readers:
        require(experiment.get("observations_completed_at") is None, "author voice study without human evidence cannot claim observation completion")
        require(experiment.get("enrollment") is None, "author voice study without human evidence cannot claim enrollment")
        require(experiment.get("allocation_sha256") is None, "author voice study without human evidence cannot claim reader allocation")
        expected_outcome = {
            "status": "PENDING_HUMAN_EVIDENCE",
            "winner": None,
            "effect_pass": False,
            "input_fingerprint": fingerprint,
        }
        require(experiment.get("outcome") == expected_outcome, "author voice study without humans must remain PENDING_HUMAN_EVIDENCE")
        return {
            "schema": SCHEMA,
            "status": "PENDING_HUMAN_EVIDENCE",
            "treatment_conditions_pass": True,
            "effect_pass": False,
            "experiment_sha256": sha_json(experiment),
        }
    require(experiment.get("mapping_revealed_after_observations") is True, "author voice mapping can be revealed only after observations")
    allocation = [
        {key: row[key] for key in ("reader_id", "blind_code", "assignment", "persona_id", "persona_profile_sha256")}
        for row in readers
    ]
    require(experiment.get("allocation_sha256") == sha_json(allocation), "author voice allocation hash mismatch")
    effect_report = voice_effect_report(reader_results, (control_label, voice_label))
    if preregistration["stage"] == "pilot":
        expected_outcome = {
            "status": "UNDERPOWERED_PILOT",
            "winner": None,
            "effect_pass": False,
            "input_fingerprint": fingerprint,
        }
    else:
        control_report = effect_report["arms"][control_label]
        voice_report = effect_report["arms"][voice_label]
        gain = round(voice_report["mean_target_reader_preference"] - control_report["mean_target_reader_preference"], 6)
        guardrails_pass = (
            voice_report["comprehension_regressions"] <= control_report["comprehension_regressions"]
            and voice_report["continuity_regressions"] <= control_report["continuity_regressions"]
        )
        threshold = decision["minimum_detectable_preference_gain"]
        winner = "voice" if gain >= threshold and guardrails_pass else "control" if gain <= -threshold else None
        expected_outcome = {
            "status": "POWERED_RESULT",
            "winner": winner,
            "effect_pass": winner == "voice",
            "guardrails_pass": guardrails_pass,
            "observed_preference_gain": gain,
            "single_book_only": True,
            "input_fingerprint": fingerprint,
        }
    require(experiment.get("outcome") == expected_outcome, "author voice outcome is not derived from preregistered preference and guardrails")
    return {
        "schema": SCHEMA,
        "status": expected_outcome["status"],
        "winner": expected_outcome["winner"],
        "effect_pass": expected_outcome["effect_pass"],
        "human_readers": len(readers),
        "effect_report": effect_report,
        "experiment_sha256": sha_json(experiment),
    }


def validate_revision_appeal_experiment(path: Path, project: Path | None) -> dict[str, Any]:
    return validate_revision_appeal_experiment_document(read_json(path, "revision appeal experiment"), project)


def validate_author_voice_effect(path: Path, project: Path | None) -> dict[str, Any]:
    return validate_author_voice_effect_document(read_json(path, "author voice effect experiment"), project)


def validate_experiment(path: Path, project: Path | None = None) -> dict[str, Any]:
    document = read_json(path, "longitudinal experiment")
    if document.get("schema") == EXPERIMENT_SCHEMA:
        return validate_experiment_v1(path)
    if document.get("schema") == EXPERIMENT_SCHEMA_V2:
        return validate_experiment_v2_document(document, project)
    raise QualityError(f"unsupported longitudinal experiment schema: {document.get('schema')}")


def validate_system_experiment(path: Path, project: Path | None = None) -> dict[str, Any]:
    document = read_json(path, "system-level experiment")
    require(document.get("schema") == SYSTEM_EXPERIMENT_SCHEMA, f"system experiment schema must be {SYSTEM_EXPERIMENT_SCHEMA}")
    require(project is not None, "system experiment must resolve an immutable preregistration from its quality project")
    project = project.resolve()
    prereg = document.get("preregistration")
    require(isinstance(prereg, dict) and prereg.get("scope") == "system", "system experiment requires system preregistration")
    prereg_sha256 = document.get("preregistration_sha256")
    preregistration_record = experiment_preregistration_record_by_hash(project, prereg_sha256)
    recorded = preregistration_record["preregistration"]
    require(prereg == recorded and sha_json(prereg) == prereg_sha256, "system preregistration differs from its immutable record")
    minimum_packages = len(prereg["story_package_ids"])
    minimum_wins = prereg["minimum_candidate_wins"]
    experiments = document.get("experiments")
    require(isinstance(experiments, list) and len(experiments) == minimum_packages, "system experiment must use the exact preregistered story package set")
    system_recorded_at = parse_utc_timestamp(preregistration_record["recorded_by_lifecycle_at"], "system preregistration lifecycle receipt")
    freeze_times = [
        parse_utc_timestamp(row.get("experiment", {}).get("artifacts_frozen_at"), "system story artifacts_frozen_at")
        for row in experiments if isinstance(row, dict)
    ]
    require(
        len(freeze_times) == len(experiments)
        and all(system_recorded_at <= value for value in freeze_times),
        "system preregistration must be recorded before every story workflow freeze",
    )
    packages: set[str] = set()
    candidate_wins = 0
    results = []
    for row in experiments:
        require(isinstance(row, dict) and isinstance(row.get("experiment"), dict), "system experiment rows must embed an experiment")
        experiment = row["experiment"]
        require(row.get("experiment_sha256") == sha_json(experiment), "embedded experiment hash mismatch")
        require(experiment.get("stage") == "formal" and experiment.get("held_out") is True, "system evidence must be formal held-out experiments")
        result = validate_experiment_v2_document(experiment, project)
        package = result["story_package_sha256"]
        require(package not in packages, "system experiment story packages must be independent")
        packages.add(package)
        candidate_wins += result["winner"] == "candidate"
        results.append({"story_package_sha256": package, "winner": result["winner"], "experiment_sha256": result["experiment_sha256"]})
    require([row["experiment"]["story_package_id"] for row in experiments] == prereg["story_package_ids"], "system experiments do not match the preregistered package order")
    require([row["experiment"]["preregistration_sha256"] for row in experiments] == prereg["story_preregistration_sha256s"], "system experiments do not match preregistered story protocols")
    replication_signal = candidate_wins >= minimum_wins
    expected_outcome = {"candidate_wins": candidate_wins, "story_packages": len(experiments), "replication_signal": replication_signal, "system_pass": False}
    require(document.get("outcome") == expected_outcome, "system outcome is not derived from story-package replications or bypasses the release lock")
    return {"schema": SCHEMA, "status": "valid_system_experiment", "system_pass": False, "replication_signal": replication_signal, "release_gate_status": "BLOCKED_PENDING_POWER_AND_INDEPENDENCE_AUDIT", "candidate_wins": candidate_wins, "story_packages": len(experiments), "results": results}


def parse_metadata(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise QualityError(f"invalid --metadata JSON: {exc}") from exc
    require(isinstance(parsed, dict), "--metadata must be a JSON object")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "check", "rebuild", "graph"):
        sub = commands.add_parser(name)
        sub.add_argument("--project", type=Path, required=True)
    stage_parser = commands.add_parser("stage")
    stage_parser.add_argument("--project", type=Path, required=True)
    stage_parser.add_argument("--chapter", type=int, required=True)
    stage_parser.add_argument("--candidate", type=Path, required=True)
    stage_parser.add_argument("--tracking-input", type=Path, required=True)
    stage_parser.add_argument("--kind", choices=("draft", "revision"), required=True)
    stage_parser.add_argument("--resolution", choices=("within_user_band", "accepted_current_length"), default="within_user_band")
    stage_parser.add_argument("--metadata")
    rollback_parser = commands.add_parser("rollback")
    rollback_parser.add_argument("--project", type=Path, required=True)
    rollback_parser.add_argument("--chapter", type=int, required=True)
    rollback_parser.add_argument("--revision", required=True)
    rollback_parser.add_argument("--tracking-input", type=Path, required=True)
    rollback_parser.add_argument("--reason", required=True)
    rollback_parser.add_argument("--resolution", choices=("within_user_band", "accepted_current_length"), default="within_user_band")
    certify_parser = commands.add_parser("certify")
    certify_parser.add_argument("--project", type=Path, required=True)
    certify_parser.add_argument("--pending", required=True)
    certify_parser.add_argument("--input", type=Path, required=True)
    accept_parser = commands.add_parser("accept")
    accept_parser.add_argument("--project", type=Path, required=True)
    accept_parser.add_argument("--pending", required=True)
    replay_parser = commands.add_parser("replay")
    replay_parser.add_argument("--project", type=Path, required=True)
    replay_parser.add_argument("--input", type=Path, required=True)
    hot = commands.add_parser("hot-context")
    hot.add_argument("--project", type=Path, required=True)
    hot.add_argument("--dependencies", type=Path, required=True)
    outline = commands.add_parser("record-outline-revision")
    outline.add_argument("--project", type=Path, required=True)
    outline.add_argument("--old", type=Path, required=True)
    outline.add_argument("--new", type=Path, required=True)
    outline.add_argument("--input", type=Path, required=True)
    experiment = commands.add_parser("check-experiment")
    experiment.add_argument("--project", type=Path)
    experiment.add_argument("--input", type=Path, required=True)
    revision_appeal = commands.add_parser("check-revision-appeal-experiment")
    revision_appeal.add_argument("--project", type=Path, required=True)
    revision_appeal.add_argument("--input", type=Path, required=True)
    voice_effect = commands.add_parser("check-author-voice-effect")
    voice_effect.add_argument("--project", type=Path, required=True)
    voice_effect.add_argument("--input", type=Path, required=True)
    system_experiment = commands.add_parser("check-system-experiment")
    system_experiment.add_argument("--project", type=Path, required=True)
    system_experiment.add_argument("--input", type=Path, required=True)
    policy = commands.add_parser("configure-policy")
    policy.add_argument("--project", type=Path, required=True)
    policy.add_argument("--input", type=Path, required=True)
    calibration = commands.add_parser("record-calibration")
    calibration.add_argument("--project", type=Path, required=True)
    calibration.add_argument("--input", type=Path, required=True)
    evidence = commands.add_parser("record-evidence-bundle")
    evidence.add_argument("--project", type=Path, required=True)
    evidence.add_argument("--input", type=Path, required=True)
    treatment_open = commands.add_parser("open-treatment-run")
    treatment_open.add_argument("--project", type=Path, required=True)
    treatment_open.add_argument("--input", type=Path, required=True)
    treatment_close = commands.add_parser("close-treatment-run")
    treatment_close.add_argument("--project", type=Path, required=True)
    treatment_close.add_argument("--run", required=True)
    treatment_close.add_argument("--input", type=Path, required=True)
    treatment_close.add_argument("--pass-a-body", type=Path)
    treatment_close.add_argument("--pass-b-body", type=Path)
    treatment_close.add_argument("--single-body", type=Path)
    treatment_close.add_argument("--single-original-body", type=Path)
    treatment_close.add_argument("--single-repair-body", type=Path, action="append", default=[])
    prereg = commands.add_parser("record-experiment-preregistration")
    prereg.add_argument("--project", type=Path, required=True)
    prereg.add_argument("--input", type=Path, required=True)
    checkpoint = commands.add_parser("record-checkpoint")
    checkpoint.add_argument("--project", type=Path, required=True)
    checkpoint.add_argument("--input", type=Path, required=True)
    reopen = commands.add_parser("open-reopen")
    reopen.add_argument("--project", type=Path, required=True)
    reopen.add_argument("--input", type=Path, required=True)
    reopen_arm = commands.add_parser("record-reopen-arm")
    reopen_arm.add_argument("--project", type=Path, required=True)
    reopen_arm.add_argument("--case", required=True)
    reopen_arm.add_argument("--input", type=Path, required=True)
    reopen_arm.add_argument("--body", type=Path, required=True)
    reopen_arm.add_argument("--outline", type=Path)
    reopen_resolve = commands.add_parser("resolve-reopen")
    reopen_resolve.add_argument("--project", type=Path, required=True)
    reopen_resolve.add_argument("--case", required=True)
    reopen_resolve.add_argument("--input", type=Path, required=True)
    outline_search = commands.add_parser("record-outline-search")
    outline_search.add_argument("--project", type=Path, required=True)
    outline_search.add_argument("--input", type=Path, required=True)
    benchmark = commands.add_parser("record-structural-benchmark")
    benchmark.add_argument("--project", type=Path, required=True)
    benchmark.add_argument("--input", type=Path, required=True)
    golden = commands.add_parser("record-golden-three-plan")
    golden.add_argument("--project", type=Path, required=True)
    golden.add_argument("--input", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "init":
            with lifecycle_lock(args.project):
                result = initialize(args.project)
        elif args.command == "stage":
            with lifecycle_lock(args.project):
                result = stage(args.project, args.chapter, args.candidate, args.tracking_input, kind=args.kind, resolution=args.resolution, metadata=parse_metadata(args.metadata))
        elif args.command == "certify":
            with lifecycle_lock(args.project):
                result = certify(args.project, args.pending, args.input)
        elif args.command == "rollback":
            with lifecycle_lock(args.project):
                result = stage_rollback(args.project, args.chapter, args.revision, args.tracking_input, reason=args.reason, resolution=args.resolution)
        elif args.command == "accept":
            with lifecycle_lock(args.project):
                result = accept(args.project, args.pending)
        elif args.command == "check":
            result = check(args.project)
        elif args.command == "rebuild":
            with lifecycle_lock(args.project):
                result = rebuild(args.project)
        elif args.command == "replay":
            with lifecycle_lock(args.project):
                result = replay(args.project, args.input)
        elif args.command == "hot-context":
            result = hot_context(args.project, args.dependencies)
        elif args.command == "graph":
            result = graph(args.project)
        elif args.command == "record-outline-revision":
            with lifecycle_lock(args.project):
                result = record_outline_revision(args.project, args.old, args.new, args.input)
        elif args.command == "configure-policy":
            with lifecycle_lock(args.project):
                result = configure_policy(args.project, args.input)
        elif args.command == "record-calibration":
            with lifecycle_lock(args.project):
                result = record_calibration(args.project, args.input)
        elif args.command == "record-evidence-bundle":
            with lifecycle_lock(args.project):
                result = record_evidence_bundle(args.project, args.input)
        elif args.command == "open-treatment-run":
            with lifecycle_lock(args.project):
                result = open_treatment_run(args.project, args.input)
        elif args.command == "close-treatment-run":
            with lifecycle_lock(args.project):
                result = close_treatment_run(
                    args.project, args.run, args.input,
                    args.pass_a_body, args.pass_b_body, args.single_body,
                    args.single_original_body, args.single_repair_body,
                )
        elif args.command == "record-experiment-preregistration":
            with lifecycle_lock(args.project):
                result = record_experiment_preregistration(args.project, args.input)
        elif args.command == "record-checkpoint":
            with lifecycle_lock(args.project):
                result = record_checkpoint(args.project, args.input)
        elif args.command == "open-reopen":
            with lifecycle_lock(args.project):
                result = open_reopen_case(args.project, args.input)
        elif args.command == "record-reopen-arm":
            with lifecycle_lock(args.project):
                result = record_reopen_arm(args.project, args.case, args.input, args.body, args.outline)
        elif args.command == "resolve-reopen":
            with lifecycle_lock(args.project):
                result = resolve_reopen_case(args.project, args.case, args.input)
        elif args.command == "record-outline-search":
            with lifecycle_lock(args.project):
                result = record_outline_search(args.project, args.input)
        elif args.command == "record-structural-benchmark":
            with lifecycle_lock(args.project):
                result = record_structural_benchmark(args.project, args.input)
        elif args.command == "record-golden-three-plan":
            with lifecycle_lock(args.project):
                result = record_golden_three_plan(args.project, args.input)
        elif args.command == "check-system-experiment":
            result = validate_system_experiment(args.input, args.project)
        elif args.command == "check-revision-appeal-experiment":
            result = validate_revision_appeal_experiment(args.input, args.project)
        elif args.command == "check-author-voice-effect":
            result = validate_author_voice_effect(args.input, args.project)
        else:
            result = validate_experiment(args.input, args.project)
    except (QualityError, OSError, UnicodeError) as exc:
        emit({"schema": SCHEMA, "status": "error", "message": str(exc)})
        return 2
    emit(result)
    return 1 if result.get("status") == "replay_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
