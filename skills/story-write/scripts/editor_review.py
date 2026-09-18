"""Validate declared editing evidence; hashes cannot prove that reading occurred."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


class EditorReviewError(ValueError):
    pass


def require(ok, message):
    if not ok:
        raise EditorReviewError("editor_review: " + message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_first_read(project: Path, receipt, *, chapter: int):
    """Check a targeted reread's immutable first-read reference, not its truth."""
    reference = receipt.get("first_read")
    require(isinstance(reference, dict) and isinstance(reference.get("path"), str), "missing first_read reference")
    root = project.resolve()
    path = (root / reference['path']).resolve()
    require(path.is_relative_to(root) and path.relative_to(root).as_posix() == reference['path'], "invalid first_read path")
    require(path.is_file() and digest(path) == reference.get('sha256'), "stale first_read record")
    try:
        original = json.loads(path.read_text(encoding='utf-8-sig'))
    except (ValueError, UnicodeError) as exc:
        raise EditorReviewError('invalid first_read JSON') from exc
    require(isinstance(original, dict), "invalid first_read record")
    require(type(chapter) is int and chapter > 0 and type(original.get('chapter')) is int and original['chapter'] == chapter and type(receipt.get('chapter')) is int and receipt['chapter'] == chapter, "first_read chapter mismatch")
    require(original.get('source') == 'independent' and original.get('reading_kind') == 'first_read', "reference is not independent first read")
    require(isinstance(receipt.get('first_read_run_id'), str) and receipt['first_read_run_id'].strip() and original.get('run_id') == receipt['first_read_run_id'], "first_read run mismatch")
    require(original.get('reviewer_run_id') == receipt.get('reviewer_run_id'), "first_read reviewer mismatch")
    require(isinstance(original.get('candidate_sha256'), str) and re.fullmatch('[0-9a-f]{64}', original['candidate_sha256']) is not None, "invalid first_read candidate digest")
    require(receipt.get('first_read_candidate_sha256') == original['candidate_sha256'], "first_read candidate mismatch")
    require(isinstance(original.get('findings'), list) and all(isinstance(item, dict) for item in original['findings']), "first_read findings missing")
    rows = original.get('prose_files')
    require(isinstance(rows, list) and rows, "first_read prose_files missing")
    retained_paths = set()
    original_candidate = original.get('candidate_path')
    require(isinstance(original_candidate, str), "first_read candidate_path missing")
    valid_candidate = re.fullmatch(rf"候选/第0*{chapter}章[^/]*\.md", original_candidate) or re.fullmatch(rf"候选/_修订/r{chapter}-[0-9a-f]{{20}}/candidate\.md", original_candidate)
    require(valid_candidate is not None, "first_read candidate_path chapter mismatch")
    candidate_bound = False
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get('path'), str) and row['path'], "invalid first_read prose file")
        name = row['path']
        logical = (root / name).resolve()
        require(logical.is_relative_to(root) and logical.relative_to(root).as_posix() == name and name not in retained_paths, "invalid first_read prose path")
        require(isinstance(row.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', row['sha256']) is not None, "invalid first_read prose digest")
        retained_paths.add(name)
        candidate_bound |= name == original_candidate and row['sha256'] == original['candidate_sha256']
    require(candidate_bound, "first_read candidate absent from prose_files")
    observations = original.get('observations')
    if observations is not None:
        require(isinstance(observations, dict) and observations, "first_read observations missing")
        groups = list(observations.values())
        require(all(isinstance(item, dict) and isinstance(item.get('assessment'), str) and item['assessment'].strip() for item in groups), "first_read assessment missing")
        evidence_groups = [item.get('evidence') for item in groups]
    else:
        evidence_groups = [original.get('evidence')]
    for evidence in evidence_groups:
        require(isinstance(evidence, list) and evidence, "first_read semantic evidence missing")
        for item in evidence:
            require(isinstance(item, dict) and isinstance(item.get('path'), str) and item['path'] in retained_paths, "first_read evidence outside retained view")
            require(isinstance(item.get('anchor'), str) and item['anchor'].strip(), "first_read evidence anchor missing")
    return original


def validate(project: Path, chapter: int, candidate: Path, receipt, *, moved_to=None):
    root = project.resolve()
    require(isinstance(receipt, dict), "missing receipt")
    require(receipt.get("schema_version") == 1 and receipt.get("policy_version") == "independent-editor-v1", "unsupported policy")
    actual_candidate = moved_to if moved_to is not None and not candidate.exists() else candidate
    candidate_hash = digest(actual_candidate)
    require(receipt.get("candidate_sha256") == candidate_hash, "stale candidate")
    require(receipt.get("source") in ("independent", "self_check"), "invalid source")
    require(receipt.get("status") in ("PASS", "NOT_EVALUATED"), "invalid status")
    for key in ("writer_run_id", "reviewer_run_id"):
        require(isinstance(receipt.get(key), str) and receipt[key].strip(), "missing " + key)
    if receipt["source"] == "independent":
        require(receipt["writer_run_id"] != receipt["reviewer_run_id"], "writer cannot be independent editor")
    else:
        require(receipt["status"] == "NOT_EVALUATED", "self check cannot pass independent review")
    files = receipt.get("context_files")
    require(isinstance(files, list) and files, "missing context files")
    seen = set()
    sources = {}
    candidate_relative = candidate.resolve().relative_to(root).as_posix()
    for item in files:
        require(isinstance(item, dict), "invalid context entry")
        relative = item.get("path")
        require(isinstance(relative, str), "invalid context path")
        path = (root / relative).resolve()
        require(path.is_relative_to(root) and path.relative_to(root).as_posix() == relative, "noncanonical context path")
        require(relative not in seen, "duplicate context")
        seen.add(relative)
        match = re.match(r"^第0*(\d+)章", path.name)
        require(relative == candidate_relative or (match is not None and int(match[1]) < chapter), "context must be prose before current chapter")
        prose_relative = path.relative_to(root / "正文") if path.is_relative_to(root / "正文") else None
        require(relative == candidate_relative or (prose_relative is not None and not any(part.startswith((".", "_")) or part in {"候选", "历史", "原稿"} for part in prose_relative.parts)), "planning/non-prose context forbidden")
        lexical = root / relative
        require(all(not parent.is_symlink() and not (hasattr(parent, 'is_junction') and parent.is_junction()) for parent in [lexical, *list(lexical.parents)[:len(Path(relative).parts) - 1]]), "linked context forbidden")
        actual = actual_candidate if relative == candidate_relative else path
        require(actual.is_file() and item.get("sha256") == digest(actual), "stale/missing context: " + relative)
        sources[relative] = actual.read_text(encoding="utf-8-sig")
    require(candidate_relative in seen, "candidate absent from coverage")
    previous = []
    for path in (root / "正文").rglob("第*章*.md"):
        match = re.match(r"^第0*(\d+)章", path.name)
        if match and int(match[1]) < chapter and not any(part.startswith((".", "_")) or part in {"候选", "历史", "原稿"} for part in path.relative_to(root / "正文").parts):
            previous.append((int(match[1]), path.relative_to(root).as_posix()))
    if previous:
        nearest = max(number for number, _ in previous)
        required = [path for number, path in previous if number == nearest]
        require(len(required) == 1 and required[0] in seen, "nearest previous chapter absent/duplicated")
    waiver = receipt.get("waiver")
    if waiver is not None:
        require(isinstance(waiver, dict), "invalid waiver")
        require(waiver.get("chapter") == chapter and waiver.get("candidate_sha256") == candidate_hash, "waiver scope stale")
        for key in ("author_approval", "reason"):
            require(isinstance(waiver.get(key), str) and waiver[key].strip(), "waiver missing " + key)
        require(receipt["status"] == "NOT_EVALUATED", "waiver must retain NOT_EVALUATED")
        return {"status": "WAIVED", "source": receipt["source"]}
    require(receipt["status"] == "PASS" and receipt["source"] == "independent", "independent review NOT_EVALUATED")
    passes = receipt.get("passes")
    require(isinstance(passes, list) and len(passes) == 2, "two reading passes required")
    require(all(isinstance(p, dict) and p.get('kind') in ('comprehension', 'sentence') for p in passes), "invalid reading passes")
    require({p['kind'] for p in passes} == {"comprehension", "sentence"}, "invalid reading passes")
    for entry in passes:
        coverage = entry.get("files")
        require(isinstance(coverage, list) and all(isinstance(p, str) for p in coverage), "invalid pass coverage")
        require(len(coverage) == len(set(coverage)) and set(coverage) == seen, "incomplete pass coverage")
        require(isinstance(entry.get('assessment'), str) and entry['assessment'].strip(), "pass needs assessment")
        evidence = entry.get('evidence')
        require(isinstance(evidence, list) and evidence, "pass needs evidence")
        candidate_anchor = False
        for item in evidence:
            require(isinstance(item, dict), "invalid pass evidence")
            evidence_path, anchor = item.get('path'), item.get('anchor')
            require(isinstance(evidence_path, str) and evidence_path in sources and isinstance(anchor, str) and anchor.strip() and anchor in sources[evidence_path], "pass evidence anchor absent")
            candidate_anchor |= evidence_path == candidate_relative
        require(candidate_anchor, "pass needs candidate evidence")
    findings = receipt.get("findings")
    require(isinstance(findings, list), "findings must be array")
    ids = set()
    uncertain = False
    for finding in findings:
        require(isinstance(finding, dict), "invalid finding")
        for key in ("id", "path", "anchor", "impact", "reason"):
            require(isinstance(finding.get(key), str) and finding[key].strip(), "finding missing " + key)
        require(finding["id"] not in ids, "duplicate finding id")
        ids.add(finding["id"])
        # Resolved findings preserve their original quotation, which may no longer exist.
        if finding.get("disposition") != "resolved":
            require(finding["path"] in sources and finding["anchor"] in sources[finding["path"]], "finding anchor absent")
        else:
            original = finding.get("original_evidence")
            require(isinstance(original, dict) and isinstance(original.get("path"), str), "resolved finding needs original evidence")
            original_path = (root / original["path"]).resolve()
            require(original_path.is_relative_to(root) and original_path.relative_to(root).as_posix() == original["path"], "invalid original evidence path")
            require(original_path.is_file() and original.get("sha256") == digest(original_path), "stale original evidence")
            require(finding["anchor"] in original_path.read_text(encoding="utf-8-sig"), "original quotation absent")
        require(finding.get("severity") in ("blocking", "advisory", "uncertain"), "invalid severity")
        require(type(finding.get("critical")) is bool, "critical must be boolean")
        require(finding.get("disposition") in ("resolved", "retained", "unresolved"), "invalid disposition")
        unresolved = finding["disposition"] != "resolved"
        require(not (unresolved and (finding["severity"] == "blocking" or finding["critical"])), "unresolved blocking/critical finding")
        uncertain |= unresolved and finding["severity"] == "uncertain"
    signoff = receipt.get("signoff")
    require(isinstance(signoff, dict) and signoff.get("candidate_sha256") == candidate_hash, "stale/missing signoff")
    limitations = signoff.get("limitations")
    require(isinstance(limitations, list) and all(isinstance(x, str) and x.strip() for x in limitations), "invalid limitations")
    require(not uncertain or limitations, "uncertainty requires signoff limitation")
    return {"status": "PASS", "source": "independent"}
