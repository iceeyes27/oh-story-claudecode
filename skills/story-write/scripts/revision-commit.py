#!/usr/bin/env python3
"""Ordinary, reviewable prose revisions using the existing tracking authority.

prepare freezes a reversible proposal; check is read-only; accept journals every
changed projection before writing. Research lifecycle books keep their own HEAD.
Review statements are semantic evidence, not a machine proof of unchanged facts.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

from project_lock import project_lock, assert_no_unfinished_adoption, ProjectLockError

_spec = importlib.util.spec_from_file_location("revision_candidate", Path(__file__).with_name("candidate-commit.py"))
assert _spec and _spec.loader
candidate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(candidate)
tracking = candidate.tracking
require = candidate.require
Error = candidate.CandidateError
sha = candidate.sha256_bytes
STATE = "追踪/_tracking-state.json"
KINDS = ("wording", "rhythm", "facts")


def safe_path(project: Path, relative: str, *, exists: bool = True) -> Path:
    require(isinstance(relative, str) and relative and not Path(relative).is_absolute(), "path must be project relative")
    path = project / relative
    require(".." not in Path(relative).parts, "parent path is not allowed")
    current = project
    for part in Path(relative).parts:
        current = current / part
        require(not current.is_symlink(), f"symlink is not allowed: {relative}")
    require(os.path.commonpath([path.resolve(), project.resolve()]) == str(project.resolve()), "path escapes project")
    require(not exists or path.is_file(), f"missing file: {relative}")
    return path


def ordinary(project: Path) -> None:
    for relative in ("追踪", "候选", "候选/_历史", ".story-quality"):
        safe_path(project, relative, exists=False)
    for path in (project / "追踪").rglob("*"):
        require(not path.is_symlink(), "symlink in tracking is not allowed")
    require(not (project / ".story-quality/HEAD.json").exists(),
            "quality lifecycle HEAD exists; use quality_lifecycle.py stage/certify/accept")
    require(not (project / ".story-quality/HEAD.json").is_symlink(), "lifecycle HEAD is a symlink")


def inventory(project: Path) -> dict[str, str]:
    safe_path(project, "正文", exists=False)
    result, chapters = {}, set()
    for path in sorted((project / "正文").rglob("*")):
        relative = path.relative_to(project).as_posix()
        require(not path.is_symlink(), f"symlink in prose: {relative}")
        if not path.is_file() or path.suffix != ".md":
            continue
        number = candidate.chapter_of(path.name)
        if number is None:
            continue
        require(number not in chapters, f"duplicate chapter {number}")
        chapters.add(number)
        result[relative] = candidate.sha256_file(path)
    return result


def revision_dir(project: Path, operation: str) -> Path:
    require(bool(re.fullmatch(r"r[1-9][0-9]*-[0-9a-f]{20}", operation)), "invalid revision operation")
    return safe_path(project, f"候选/_修订/{operation}", exists=False)


def operation_id(manifest: dict) -> str:
    identity = {k: v for k, v in manifest.items() if k != "operation"}
    return f"r{manifest['chapter']}-{sha(candidate.canonical_json(identity))[:20]}"


def load(project: Path, operation: str) -> tuple[Path, dict]:
    directory = revision_dir(project, operation)
    manifest = candidate.read_json(directory / "manifest.json", "revision manifest")
    require(manifest.get("schema") == "ordinary-revision/v1", "unsupported revision manifest")
    require(operation_id(manifest) == operation == manifest.get("operation"), "revision manifest changed")
    for name, key in (("original.md", "original_sha256"), ("candidate.md", "candidate_sha256"), ("diff.patch", "diff_sha256")):
        path = safe_path(project, (directory / name).relative_to(project).as_posix())
        require(candidate.sha256_file(path) == manifest[key], f"frozen revision changed: {name}")
    return directory, manifest


def prepare(project: Path, chapter: int, source: Path, kind: str, summary: str) -> dict:
    ordinary(project)
    require(chapter > 0 and summary.strip(), "chapter and revision summary are required")
    with project_lock(project):
        assert_no_unfinished_adoption(project)
        state = tracking.check_project(project)
        files = inventory(project)
        matches = [name for name in files if candidate.chapter_of(Path(name).name) == chapter]
        require(len(matches) == 1, "revision needs one adopted chapter")
        require(chapter <= state["last_committed_chapter"], "chapter is not in tracking state")
        final = safe_path(project, matches[0])
        require(not source.is_symlink(), "candidate cannot be a symlink")
        revised = source.read_text(encoding="utf-8-sig")
        original = final.read_text(encoding="utf-8-sig")
        require(revised.strip() and revised != original, "candidate is empty or unchanged")
        # Always bind the previous/next *existing* chapter, including volume dirs.
        numbers = sorted(candidate.chapter_of(Path(name).name) for name in files)
        before = max((n for n in numbers if n < chapter), default=None)
        after = min((n for n in numbers if n > chapter), default=None)
        context = {name: digest for name, digest in files.items()
                   if candidate.chapter_of(Path(name).name) in {before, after}
                   or (kind == "facts" and candidate.chapter_of(Path(name).name) > chapter)}
        if after is None:
            outlines = [p for p in (project / "大纲").glob("细纲_第*章.md")
                        if re.fullmatch(rf"细纲_第0*{chapter + 1}章\.md", p.name)]
            require(len(outlines) <= 1, "duplicate next chapter outline")
            for outline in outlines:
                relative = outline.relative_to(project).as_posix()
                context[relative] = candidate.sha256_file(safe_path(project, relative))
        diff = "".join(difflib.unified_diff(original.splitlines(True), revised.splitlines(True),
                                         fromfile=matches[0], tofile="revision candidate"))
        manifest = {"schema": "ordinary-revision/v1", "chapter": chapter, "kind": kind,
                    "summary": summary.strip(), "final": matches[0], "inventory": files,
                    "context": context, "state_sha256": candidate.sha256_file(project / STATE),
                    "expected_state_revision": state["state_revision"],
                    "original_sha256": sha(final.read_bytes()), "candidate_sha256": sha(revised.encode()),
                    "diff_sha256": sha(diff.encode())}
        manifest["operation"] = operation_id(manifest)
        directory = revision_dir(project, manifest["operation"])
        if not directory.exists():
            directory.mkdir(parents=True)
            # Preserve original bytes, including BOM/line endings.
            (directory / "original.md").write_bytes(final.read_bytes())
            (directory / "candidate.md").write_bytes(revised.encode())
            (directory / "diff.patch").write_bytes(diff.encode())
            candidate.atomic_json(directory / "manifest.json", manifest)
            template = {"reviewer": "", "reader_type": "model", "status": "pending",
                        "original_sha256": manifest["original_sha256"],
                        "candidate_sha256": manifest["candidate_sha256"], "diff_sha256": manifest["diff_sha256"],
                        "facts_unchanged": None, "findings": [], "original_anchor": "", "candidate_anchor": "",
                        "metric_source_updates": {},
                        "context": [{"path": name, "sha256": digest, "anchor": "", "assessment": ""}
                                    for name, digest in context.items()]}
            candidate.atomic_json(directory / "review-template.json", template)
        load(project, manifest["operation"])
        return {"action": "prepare", "operation": manifest["operation"], "directory": str(directory),
                "kind": kind, "review_scope": list(context), "adopted": False}


def valid_review(project: Path, directory: Path, manifest: dict, review: dict) -> None:
    require(review.get("status") == "pass" and bool(str(review.get("reviewer", "")).strip()), "completed reading review required")
    require(review.get("reader_type") in {"human", "model"}, "reader_type must disclose human or model")
    for key in ("original_sha256", "candidate_sha256", "diff_sha256"):
        require(review.get(key) == manifest[key], f"review {key} is stale")
    for field, name in (("original_anchor", "original.md"), ("candidate_anchor", "candidate.md")):
        anchor = review.get(field)
        require(isinstance(anchor, str) and anchor.strip() and anchor in (directory / name).read_text(encoding="utf-8-sig"), f"review {field} cannot be located")
    findings = review.get("findings")
    require(isinstance(findings, list) and all(isinstance(f, dict) and f.get("severity") == "advisory" and f.get("message") for f in findings), "unresolved or malformed reading findings")
    if manifest["kind"] != "facts":
        require(review.get("facts_unchanged") is True, "wording/rhythm needs a review of unchanged story facts; otherwise prepare kind=facts")
    rows = review.get("context")
    require(isinstance(rows, list) and len(rows) == len(manifest["context"]), "review must cover the bound context")
    require({r.get("path") for r in rows if isinstance(r, dict)} == set(manifest["context"]), "review context paths differ")
    for row in rows:
        name = row["path"]
        require(row.get("sha256") == manifest["context"][name], f"context review stale: {name}")
        anchor = row.get("anchor")
        require(isinstance(anchor, str) and anchor.strip() and anchor in safe_path(project, name).read_text(encoding="utf-8-sig"), f"context anchor missing: {name}")
        require(isinstance(row.get("assessment"), str) and row["assessment"].strip(), f"context assessment missing: {name}")


def build_changes(project: Path, directory: Path, manifest: dict, review: dict, transaction: dict | None) -> tuple[dict, dict]:
    ordinary(project)
    state = tracking.check_project(project)
    tracking_before = {p.relative_to(project).as_posix(): p.read_bytes().hex()
                       for p in (project / "追踪").rglob("*") if p.is_file()}
    require(inventory(project) == manifest["inventory"], "adopted prose changed since revision preparation")
    require(candidate.sha256_file(project / STATE) == manifest["state_sha256"], "tracking changed since revision preparation")
    for name, digest in manifest["context"].items():
        require(candidate.sha256_file(safe_path(project, name)) == digest, f"revision context changed: {name}")
    valid_review(project, directory, manifest, review)
    text = (directory / "candidate.md").read_text(encoding="utf-8")
    length = candidate.wordcount.fanqie_length(text)
    require(length["status"] == "pass", f"revision length must be 2200–2800, actual={length['actual']}")
    # Scan a correctly named file: title checking and author-rule scope remain intact.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="ordinary-revision-check-") as temporary:
        prose = Path(temporary) / Path(manifest["final"]).name
        prose.write_text(text, encoding="utf-8")
        candidate.validate_titles(project, prose)
        findings = candidate.scan_gate(prose, project=project, target=project / manifest["final"])
        require(findings is None, f"revision deterministic check failed: {findings}")
    next_state = copy.deepcopy(state)
    outputs = {manifest["final"]: text}
    if manifest["kind"] == "facts":
        require(isinstance(transaction, dict), "fact revision needs an updated tracking transaction")
        require(transaction.get("mode") == "revision" and transaction.get("chapter") == manifest["chapter"], "tracking transaction must revise the same chapter")
        require("wordcount" not in transaction, "old body wordcount must not be reused; it is invalidated automatically")
        normalized = tracking.normalize_transaction(project, state, transaction)
        next_state = tracking.merge_transaction(state, normalized)
        relative = tracking.delta_path(project / "追踪", manifest["chapter"]).relative_to(project).as_posix()
        outputs[relative] = tracking.render_delta(normalized["chapter"], normalized["title"], normalized["delta"], set(next_state["characters"]))
    else:
        require(transaction is None, "wording/rhythm cannot silently change tracking facts")
        next_state["state_revision"] += 1
        updates = review.get("metric_source_updates", {})
        require(isinstance(updates, dict), "metric_source_updates must be a mapping of metric names to new prose anchors")
        for name, anchor in updates.items():
            record = next_state.get("metrics", {}).get(name)
            require(isinstance(record, dict) and record["as_of_chapter"] == manifest["chapter"], "source refresh must refer to a fact recorded in the revised chapter")
            require(isinstance(anchor, str) and anchor.strip() and anchor in text, "refreshed metric source cannot be located")
            # Review binds the new quote to unchanged value and fact chapter.
            # This cannot update amounts, dates, or facts from other chapters.
            record["source_phrase"] = anchor
    # Stale measurements must not survive changed prose. Semantic summaries stay
    # only after an explicit unchanged-facts review, or the facts transaction.
    next_state["wordcount_records"].pop(str(manifest["chapter"]), None)
    for record in next_state.get("metrics", {}).values():
        if record["as_of_chapter"] == manifest["chapter"]:
            require(record["source_phrase"] in text, "tracking metric anchor disappeared; revise facts/source evidence")
    next_state = tracking.normalize_state(next_state)
    metric_before = copy.deepcopy(state.get("metrics", {}))
    if manifest["kind"] != "facts":
        # Refreshed sources support an unchanged value, not a new settlement.
        # Exclude the old value from delta arithmetic (old + 0 is no proof).
        for name in review.get("metric_source_updates", {}):
            metric_before.pop(name, None)
    candidate.metrics_settlement_gate(directory / "candidate.md", manifest["chapter"],
                                      metric_before, next_state.get("metrics", {}),
                                      (transaction or {}).get("metrics_unchanged_reason") if manifest["kind"] == "facts"
                                      else "reviewed wording/rhythm revision; story facts unchanged")
    outputs.update({f"追踪/{name}": value for name, value in tracking.render_views(next_state).items()})
    outputs[STATE] = tracking.json_payload(next_state)
    changes = {}
    for name, after in outputs.items():
        path = safe_path(project, name, exists=False)
        before = ((directory / "original.md").read_bytes().hex() if name == manifest["final"]
                  else tracking_before.get(name))
        require((path.read_bytes().hex() if path.exists() else None) == before,
                f"projection changed during revision checks: {name}")
        encoded = after.encode("utf-8").hex()
        if before != encoded:
            changes[name] = {"before": before, "after": encoded}
    return changes, {"length": length, "state_revision": next_state["state_revision"],
                     "invalidated": ["previous reading receipts for changed prose/context", "previous candidate bindings", "chapter wordcount record"],
                     "reader_type": review["reader_type"], "review_scope": list(manifest["context"])}


def check(project: Path, operation: str, review: dict, transaction: dict | None) -> dict:
    assert_no_unfinished_adoption(project)
    directory, manifest = load(project, operation)
    _, report = build_changes(project, directory, manifest, review, transaction)
    return {"action": "check", "ok": True, "operation": operation, "adopted": False, **report}


def fault(phase: str) -> None:
    if os.environ.get("STORY_REVISION_FAIL_AFTER") == phase:
        os._exit(97)


def recover_locked(project: Path, operation: str) -> dict:
    ordinary(project)
    directory, manifest = load(project, operation)
    path = safe_path(project, f"候选/_历史/修订事务-{operation}.json")
    journal = candidate.read_json(path, "revision journal")
    payload = journal.get("payload")
    require(isinstance(payload, dict) and sha(candidate.canonical_json(payload)) == journal.get("payload_sha256"), "revision journal payload changed")
    require(payload.get("operation") == operation and payload.get("manifest") == manifest, "revision journal does not match proposal")
    require(journal.get("phase") in {"prepared", "prose_written", "done"}, "invalid revision phase")
    valid_review(project, directory, manifest, payload["review"])
    changes = payload["changes"]
    # A crash may leave each output at either the old or intended version. Never
    # overwrite an unrelated edit; state is written last and remains authoritative.
    current_inventory = inventory(project)
    require(set(current_inventory) == set(manifest["inventory"]), "prose file set changed during revision")
    for name, digest in current_inventory.items():
        expected = {manifest["inventory"][name]}
        if name == manifest["final"]:
            expected.add(manifest["candidate_sha256"])
        require(digest in expected, f"prose changed during revision: {name}")
    for name, digest in manifest["context"].items():
        require(candidate.sha256_file(safe_path(project, name)) == digest, f"context changed during revision: {name}")
    for name, versions in changes.items():
        target = safe_path(project, name, exists=False)
        actual = target.read_bytes().hex() if target.exists() else None
        allowed = {versions["after"]} if journal["phase"] == "done" else {versions["before"], versions["after"]}
        require(actual in allowed, f"revision output changed outside transaction: {name}")
    if journal["phase"] != "done":
        order = [manifest["final"], *sorted(set(changes) - {manifest["final"], STATE}), STATE]
        for name in order:
            if name not in changes:
                continue
            target = safe_path(project, name, exists=False)
            tracking.atomic_write_text(target, bytes.fromhex(changes[name]["after"]).decode("utf-8"))
            if name == manifest["final"]:
                journal["phase"] = "prose_written"
                candidate.atomic_json(path, journal)
                fault("prose_written")
            elif name != STATE:
                fault("views_written")
        fault("state_written")
        tracking.check_project(project)
        journal["phase"] = "done"
        candidate.atomic_json(path, journal)
    return {"action": "accept", "operation": operation, "adopted": True,
            "original": str(directory / "original.md"), **payload["report"]}


def accept(project: Path, operation: str, review: dict, transaction: dict | None, approval: str) -> dict:
    ordinary(project)
    require(approval.strip(), "record the author's actual adoption instruction")
    with project_lock(project):
        assert_no_unfinished_adoption(project)
        directory, manifest = load(project, operation)
        changes, report = build_changes(project, directory, manifest, review, transaction)
        # External editors do not take our project lock. Bind again after slow
        # scans, before persisting a transaction that would block other writers.
        load(project, operation)
        require(inventory(project) == manifest["inventory"], "prose changed during revision checks")
        require(candidate.sha256_file(project / STATE) == manifest["state_sha256"], "tracking changed during revision checks")
        for name, digest in manifest["context"].items():
            require(candidate.sha256_file(safe_path(project, name)) == digest, "context changed during revision checks")
        for name, versions in changes.items():
            target = safe_path(project, name, exists=False)
            require((target.read_bytes().hex() if target.exists() else None) == versions["before"], "projection changed during revision checks")
        journal_path = safe_path(project, f"候选/_历史/修订事务-{operation}.json", exists=False)
        require(not journal_path.exists(), "revision already has a journal; use recover")
        payload = {"operation": operation, "manifest": manifest, "review": review,
                   "tracking_transaction": transaction, "author_approval": approval,
                   "changes": changes, "report": report}
        candidate.atomic_json(journal_path, {"phase": "prepared", "payload": payload,
                                           "payload_sha256": sha(candidate.canonical_json(payload))})
        fault("prepared")
        return recover_locked(project, operation)


def abort(project: Path, operation: str, reason: str) -> dict:
    """Cancel only a prepared transaction that has not changed any projection."""
    ordinary(project)
    require(reason.strip(), "abort reason is required")
    revision_dir(project, operation)  # validate identifier without requiring damaged proposal files
    with project_lock(project):
        path = safe_path(project, f"候选/_历史/修订事务-{operation}.json")
        journal = candidate.read_json(path, "revision journal")
        payload = journal["payload"]
        require(sha(candidate.canonical_json(payload)) == journal.get("payload_sha256"), "revision journal payload changed")
        require(payload.get("operation") == operation and journal.get("phase") == "prepared", "only an unstarted prepared revision can be aborted")
        for name, versions in payload["changes"].items():
            target = safe_path(project, name, exists=False)
            actual = target.read_bytes().hex() if target.exists() else None
            require(actual == versions["before"], "projections already changed; recover instead of abort")
        journal.update(phase="aborted", abort_reason=reason)
        candidate.atomic_json(path, journal)
        return {"action": "abort", "operation": operation, "adopted": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("prepare", "check", "accept", "recover", "abort"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--project", type=Path, required=True)
        if name == "prepare":
            cmd.add_argument("--chapter", type=int, required=True)
            cmd.add_argument("--candidate", type=Path, required=True)
            cmd.add_argument("--kind", choices=KINDS, required=True)
            cmd.add_argument("--summary", required=True)
        else:
            cmd.add_argument("--operation", required=True)
        if name in {"check", "accept"}:
            cmd.add_argument("--review", type=Path, required=True)
            cmd.add_argument("--transaction", type=Path)
        if name == "accept":
            cmd.add_argument("--author-approval", required=True)
        if name == "abort":
            cmd.add_argument("--reason", required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        if args.command == "prepare":
            result = prepare(project, args.chapter, args.candidate, args.kind, args.summary)
        elif args.command == "recover":
            ordinary(project)
            with project_lock(project):
                result = recover_locked(project, args.operation)
        elif args.command == "abort":
            result = abort(project, args.operation, args.reason)
        else:
            review = candidate.read_json(args.review, "reading review")
            transaction = candidate.read_json(args.transaction, "tracking transaction") if args.transaction else None
            result = (check(project, args.operation, review, transaction) if args.command == "check"
                      else accept(project, args.operation, review, transaction, args.author_approval))
        candidate.emit(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (Error, ProjectLockError, tracking.TrackingError, OSError, UnicodeError, ValueError, KeyError, TypeError) as exc:
        candidate.emit(f"ERROR: {exc}", error=True)
        return 1 if args.command == "check" else 2


if __name__ == "__main__":
    raise SystemExit(main())
