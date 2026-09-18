"""Read-only review-process evidence checks, not proof of honest or good reading."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

POLICY = "review-quality-v2"
DIAGNOSTIC_AXES = {"events", "causes", "turns", "presence_space", "objects", "quantities_practice", "repetition"}


def previous_participant_identities(project, chapter, reference):
    """Collect all prior participants; do not rejudge historical literary reports."""
    identities, paths = set(), set()
    while reference is not None:
        require(isinstance(reference, dict) and isinstance(reference.get('path'), str), "invalid history reference")
        require(reference['path'] not in paths and len(paths) < 64, "cyclic/excessive reader history")
        paths.add(reference['path'])
        record = read_reference(project, reference)
        require(record.get('schema_version') == 1 and record.get('policy_version') == POLICY and record.get('chapter') == chapter, "historical scope mismatch")
        reports = record.get('reports')
        require(isinstance(reports, dict) and set(reports) == {'editor', 'natural', 'diagnostic'}, "historical reports missing")
        for role, report_ref in reports.items():
            report = read_reference(project, report_ref)
            require(report.get('role') == role and report.get('chapter') == chapter and report.get('candidate_sha256') == record.get('candidate_sha256') and nonempty(report.get('reviewer_run_id')) and nonempty(report.get('run_id')), "historical participant mismatch")
            identities.add(report['reviewer_run_id'])
        require(nonempty(record.get('writer_run_id')), "historical writer identity missing")
        identities.add(record['writer_run_id'])
        change = record.get('change')
        require(isinstance(change, dict) and change.get('kind') in ('none', 'minor', 'substantial'), "historical change missing")
        reference = change.get('previous')
        require((change['kind'] == 'none') == (reference is None), "historical chain incomplete")
    return identities


class ReviewProcessError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ReviewProcessError("review_process: " + message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_reference(project, reference):
    require(isinstance(reference, dict), "missing reference")
    name = reference.get("path")
    require(isinstance(name, str) and name, "reference path missing")
    root = project.resolve()
    path = root / name
    resolved = path.resolve()
    require(resolved.is_relative_to(root) and resolved.relative_to(root).as_posix() == name, "reference path not canonical")
    for part in [path, *list(path.parents)[:len(Path(name).parts) - 1]]:
        require(not part.is_symlink() and not (hasattr(part, "is_junction") and part.is_junction()), "linked reference forbidden")
    require(path.is_file() and digest(path) == reference.get("sha256"), "missing/stale reference: " + name)
    try:
        document = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_pairs)
    except (ValueError, UnicodeError) as exc:
        raise ReviewProcessError("invalid report JSON: " + name) from exc
    require(isinstance(document, dict), "report must be object")
    return document


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _record(project, chapter, reference):
    record = read_reference(project, reference)
    require(record.get("schema_version") == 1 and record.get("policy_version") == POLICY, "unsupported process policy")
    require(type(record.get("chapter")) is int and record["chapter"] == chapter, "chapter mismatch")
    require(nonempty(record.get("candidate_sha256")), "candidate hash missing")
    files = record.get("prose_files")
    require(isinstance(files, list) and files, "prose snapshot missing")
    texts = {}
    for item in files:
        require(isinstance(item, dict) and nonempty(item.get("path")) and isinstance(item.get("text"), str), "invalid prose snapshot")
        require(item["path"] not in texts, "duplicate prose snapshot")
        require(hashlib.sha256(item["text"].encode("utf-8")).hexdigest() == item.get("sha256"), "prose snapshot digest mismatch")
        texts[item["path"]] = item
    candidate_path = record.get("candidate_path")
    require(isinstance(candidate_path, str) and candidate_path in texts and texts[candidate_path]["sha256"] == record["candidate_sha256"], "candidate snapshot missing")
    reports = record.get("reports")
    require(isinstance(reports, dict) and set(reports) == {"editor", "natural", "diagnostic"}, "three reports required")
    loaded, important = {}, {}
    for role, ref in reports.items():
        report = read_reference(project, ref)
        require(report.get("role") == role and report.get("candidate_sha256") == record["candidate_sha256"] and report.get("chapter") == chapter, "report scope mismatch")
        require(nonempty(report.get("run_id")) and nonempty(report.get("reviewer_run_id")), "actual call identity missing")
        require(type(report.get("completed_order")) is int and report["completed_order"] >= 0, "actual completion order missing")
        require(type(report.get("started_order")) is int and 0 <= report["started_order"] <= report["completed_order"], "actual start order missing")
        findings = report.get("findings")
        require(isinstance(findings, list), "report findings missing")
        identifiers = set()
        for finding in findings:
            require(isinstance(finding, dict) and nonempty(finding.get("id")), "finding identity missing")
            require(finding["id"] not in identifiers and type(finding.get("important")) is bool, "duplicate finding or missing importance")
            identifiers.add(finding["id"])
            require(nonempty(finding.get("impact")), "finding impact missing")
            _evidence(finding.get("evidence"), texts)
            if finding["important"]:
                important[report["run_id"] + "/" + finding["id"]] = finding
        observations = report.get("observations")
        expected = {"understanding", "engagement", "confusion", "skimming", "reward_expectation"} if role == "natural" else ({"accuracy", "clarity", "naturalness", "continuity"} if role == "editor" else DIAGNOSTIC_AXES)
        require(isinstance(observations, dict) and observations, "semantic observations missing")
        require(expected is None or set(observations) == expected, "natural reading dimensions missing")
        for observation in observations.values():
            require(isinstance(observation, dict) and nonempty(observation.get("assessment")), "observation assessment missing")
            _evidence(observation.get("evidence"), texts, candidate_path)
        loaded[role] = report
    editor, natural, diagnostic = (loaded[k] for k in ("editor", "natural", "diagnostic"))
    require(len({r["run_id"] for r in loaded.values()}) == 3, "tasks must have distinct call IDs")
    require(editor["reviewer_run_id"] != natural["reviewer_run_id"] == diagnostic["reviewer_run_id"], "reader/editor independence mismatch")
    require(editor["completed_order"] < natural["started_order"] and natural["completed_order"] < diagnostic["started_order"], "natural report must precede diagnostic task")
    require(diagnostic.get("natural_report_sha256") == reports["natural"]["sha256"], "diagnostic task must reference frozen natural result")
    change = record.get("change")
    require(isinstance(change, dict) and change.get("kind") in ("none", "minor", "substantial"), "change classification missing")
    require(nonempty(change.get("reason")), "change classification reason missing")
    previous = change.get("previous")
    if change["kind"] == "none":
        require(previous is None, "none cannot conceal previous reading")
        require(natural.get("reading_kind") == "first_read", "initial reading must be first_read")
    else:
        require(isinstance(previous, dict) and previous.get('path') != reference.get('path') and previous.get('sha256') != reference.get('sha256'), "self-referencing history")
        old = read_reference(project, previous)
        prior_readers = previous_participant_identities(project, chapter, previous)
        require(old.get("schema_version") == 1 and old.get("policy_version") == POLICY and old.get("chapter") == chapter, "invalid previous process")
        old_reports = old.get("reports")
        require(isinstance(old_reports, dict) and set(old_reports) == {"editor", "natural", "diagnostic"}, "previous reports missing")
        old_loaded = {role: read_reference(project, ref) for role, ref in old_reports.items()}
        require(not ({report['run_id'] for report in loaded.values()} & {report.get('run_id') for report in old_loaded.values() if isinstance(report.get('run_id'), str)}), "new report cannot reuse previous task ID")
        inherited = {}
        for role, report in old_loaded.items():
            require(report.get("role") == role and report.get("candidate_sha256") == old.get("candidate_sha256") and report.get("chapter") == chapter, "previous report mismatch")
            require(nonempty(report.get("run_id")) and nonempty(report.get("reviewer_run_id")) and isinstance(report.get("findings"), list), "invalid previous report")
            for finding in report["findings"]:
                require(isinstance(finding, dict) and nonempty(finding.get("id")) and type(finding.get("important")) is bool, "invalid previous finding")
                if finding["important"]:
                    inherited[report["run_id"] + "/" + finding["id"]] = finding
        old_dispositions = old.get("dispositions")
        require(isinstance(old_dispositions, list), "previous dispositions missing")
        for item in old_dispositions:
            require(isinstance(item, dict) and nonempty(item.get("finding_id")), "invalid previous disposition")
            inherited.setdefault(item["finding_id"], item)
        require(old["candidate_sha256"] != record["candidate_sha256"], "revision must change candidate")
        important = {**inherited, **important}
        if change["kind"] == "substantial":
            require(natural.get("reading_kind") == "first_read" and natural["reviewer_run_id"] not in prior_readers, "substantial revision needs new blind reader")
        else:
            require(natural.get("reading_kind") in ("first_read", "targeted_recheck"), "invalid minor rereading")
            if natural["reading_kind"] == "targeted_recheck":
                require(natural["reviewer_run_id"] == old_loaded["natural"]["reviewer_run_id"], "targeted review reader changed")
            else:
                require(natural["reviewer_run_id"] not in prior_readers, "same reader cannot claim fresh reading")
    dispositions = record.get("dispositions")
    require(isinstance(dispositions, list), "dispositions missing")
    mapped = {}
    for item in dispositions:
        require(isinstance(item, dict) and nonempty(item.get("finding_id")) and item["finding_id"] not in mapped, "duplicate/invalid disposition")
        require(item.get("decision") in ("accepted", "partial", "rejected", "pending", "deferred"), "invalid disposition decision")
        require(nonempty(item.get("reason")), "disposition reason missing")
        _evidence(item.get("evidence"), texts)
        mapped[item["finding_id"]] = item
    require(set(mapped) == set(important), "important source IDs must all be accounted for")
    return record, loaded, important


def _evidence(evidence, texts, candidate_path=None):
    require(isinstance(evidence, list) and evidence, "evidence missing")
    for item in evidence:
        require(isinstance(item, dict) and isinstance(item.get("path"), str) and item["path"] in texts, "evidence outside reading view")
        require(nonempty(item.get("anchor")) and item["anchor"] in texts[item["path"]]["text"], "evidence quotation missing")
    require(candidate_path is None or any(item["path"] == candidate_path for item in evidence), "candidate evidence missing")


def validate(project: Path, chapter: int, candidate: Path, reference, *, editor: dict, readers: list[dict], moved_to: Path | None = None):
    record, reports, _ = _record(project, chapter, reference)
    actual = moved_to if moved_to is not None and not candidate.exists() else candidate
    require(record["candidate_path"] == candidate.resolve().relative_to(project.resolve()).as_posix() and record["candidate_sha256"] == digest(actual), "current candidate mismatch")
    require(nonempty(record.get('writer_run_id')) and record['writer_run_id'] == editor.get('writer_run_id'), "writer receipt/process identity mismatch")
    require(reports["editor"]["reviewer_run_id"] == editor.get("reviewer_run_id"), "editor receipt mismatch")
    require(reports["natural"]["reviewer_run_id"] != editor.get("writer_run_id"), "writer cannot be reader")
    require(isinstance(readers, list) and readers, "reader receipts missing")
    for receipt in readers:
        require(receipt.get("reviewer_run_id") == reports["diagnostic"]["reviewer_run_id"] and receipt.get("run_id") == reports["diagnostic"]["run_id"], "reader receipt/report identity mismatch")
        require(receipt.get("reading_kind") == reports["natural"].get("reading_kind"), "reading kind mismatch")
    for item in record["prose_files"]:
        relative = item["path"]
        bound = actual if relative == record["candidate_path"] else project / relative
        require(bound.resolve().is_relative_to(project.resolve()) and bound.is_file() and digest(bound) == item["sha256"], "current context changed")
    expected_files = {}
    for item in [*editor.get("context_files", []), *(item for reader in readers for item in reader.get("prose_files", []))]:
        require(isinstance(item, dict) and isinstance(item.get('path'), str), "invalid bound review file")
        require(item['path'] not in expected_files or expected_files[item['path']] == item.get('sha256'), "review context digests disagree")
        expected_files[item['path']] = item.get('sha256')
    require({item['path']: item['sha256'] for item in record['prose_files']} == expected_files, "process context must equal bound review union")
    return {"status": "VERIFIED", "policy_version": POLICY, "process_sha256": reference["sha256"]}
