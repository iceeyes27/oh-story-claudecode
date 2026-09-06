"""Package real pilot prose/reader observations into isolated candidate checks.

Previous generated chapters are imported as simulated adopted context. No real
author adoption or human evidence is implied. No fabricated PASS is generated.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "skills/story-write/scripts"))
spec = importlib.util.spec_from_file_location("pilot_candidate", REPO / "skills/story-write/scripts/candidate-commit.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def read(p):
    return json.loads(p.read_text(encoding="utf-8"))


def save(p, data):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_extractions(meta, raw):
    names = {"agreed_total_service_fee_yuan": "约定服务费", "service_fee_agreed": "约定服务费",
             "received_service_fee_yuan": "已收服务费", "service_fee_received": "已收服务费",
             "remaining_service_fee_yuan": "未收服务费", "service_fee_outstanding": "未收服务费",
             "separate_storage_fee_paid_yuan": "已付临存费", "temporary_storage_fee_paid_to_chen": "已付临存费",
             "received_this_chapter_yuan": "本章收到尾款", "service_fee_final_payment": "本章收到尾款",
             "stored_fish_boxes": "临存鱼箱数", "returned_empty_boxes": "归还空箱数"}
    previous = {}
    for item, source in zip(meta, raw):
        item["commitments"] = [v["promise"] if isinstance(v, dict) else v for v in item["commitments"]]
        metrics = item["metrics"]
        entries = metrics.items() if isinstance(metrics, dict) else [(v["name"], v) for v in metrics]
        current = dict(previous)
        for key, row in entries:
            name = names.get(key, key)
            value = str(row["value"]) + row.get("unit", "元")
            if name in current and current[name]["value"] == value:
                continue  # unchanged fact keeps its original source chapter/anchor
            current[name] = {"value": value, "as_of_chapter": row.get("source_chapter", row.get("as_of_chapter")), "source_phrase": row["source_phrase"]}
        item["metrics"] = previous = current
        text = source.read_text(encoding="utf-8")
        coverage = []
        for row in item["coverage"]:
            evidence = row["evidence"]
            if isinstance(evidence, list):
                quotes = [v["evidence"] for v in evidence]
                assert all(q in text for q in quotes)
                start = min(text.index(q) for q in quotes)
                end = max(text.index(q) + len(q) for q in quotes)
                evidence = text[start:end]
            item_id = row.get("id", row.get("o_id"))
            if isinstance(item_id, str) and re.fullmatch(r"O-0*[1-9][0-9]*", item_id):
                item_id = f"O{int(item_id[2:])}"
            coverage.append({"id": item_id, "evidence": evidence})
        item["coverage"] = coverage
    return meta


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--arm", required=True)
    parser.add_argument("--reader", required=True)
    parser.add_argument("--output-label")
    parser.add_argument("--prose-dir", default="raw")
    parser.add_argument("--metadata-dir", default="metadata")
    parser.add_argument("--repair-first-contract", action="store_true")
    parser.add_argument("--protagonist", default="周小满")
    parser.add_argument("--book-title", default="小满修理铺")
    parser.add_argument("--volume", default="第一单")
    parser.add_argument("--initial-scene", default="修理铺")
    args = parser.parse_args()
    pilot = args.pilot.resolve()
    arm = pilot / args.arm
    raw = sorted((arm / args.prose_dir).glob("第*章*.md"))
    assert raw, "no prose to check"
    metadata_paths = [arm / args.metadata_dir / f"chapter-{n:02d}.postwrite.json" for n in range(1, len(raw) + 1)]
    original_ids = [[row.get("id", row.get("o_id")) for row in read(p)["coverage"]] for p in metadata_paths]
    meta = normalize_extractions([read(p) for p in metadata_paths], raw)
    label = args.output_label or args.arm
    results = []
    for n, source in enumerate(raw, 1):
        project = pilot / "delivery-checks" / label / f"chapter-{n:02d}"
        if project.exists():
            raise RuntimeError(f"preserve existing run; use a fresh delivery folder: {project}")
        for d in ("正文", "候选", "大纲", "骨架"):
            (project / d).mkdir(parents=True, exist_ok=True)
        save(project / "validation-normalizations.json", {
            "source": str(metadata_paths[n - 1]), "source_sha256": c.sha256_file(metadata_paths[n - 1]),
            "coverage_ids_before": original_ids[n - 1],
            "coverage_ids_after": [row["id"] for row in meta[n - 1]["coverage"]],
            "meaning": "O-01 spelling mapped to skeleton O1; production gate unchanged; original extraction and prose preserved"})
        for p in raw[:n - 1]:
            shutil.copy2(p, project / "正文" / p.name)
        prose = project / "候选" / source.name
        shutil.copy2(source, prose)
        for d in ("大纲", "骨架"):
            for p in (arm / d).glob("*.md"):
                shutil.copy2(p, project / d / p.name)
        if args.repair_first_contract and n == 1:
            outline = project / "大纲/细纲_第1章.md"
            before = outline.read_text(encoding="utf-8")
            addition = "\n- 目标情绪：日常\n- 结尾拍ID/类型：EB-01 goal；到陈望店里谈条件\n- 期待ID/类型：EX-01 goal；能否谈妥临时存鱼\n- 读者验收预期：must_know=缺配件及先保鱼，已付100元；may_believe=她能完成维修；must_not_know=借柜条件和维修结果；open_ids=EX-01\n- 前因：开篇无前因\n- 后果指向：双方到包子铺商量临存\n- 读者已知：小满接单，已说明需要下午配件，陈望尚未同意\n"
            outline.write_text(before + addition, encoding="utf-8")
            save(project / "contract-format-repair.json", {"original_input_preserved": str(arm / "大纲/细纲_第1章.md"), "added_fields": addition, "story_events_changed": False, "not_a_claim_of_prewrite_validation": True})
        current = meta[n - 1]
        previous = meta[n - 2] if n > 1 else None
        position = {"volume": args.volume, "volume_start_chapter": 1,
                    "story_time": "当天" if previous else "开篇前", "scene": previous["protagonist"]["location"] if previous else args.initial_scene}
        context = {"position": position, "long_term_constraints": [],
                   "active_character_names": [args.protagonist] if previous else [], "continuity_risks": [],
                   "recent_chapters": [{"chapter": i + 1, "summary": m["summary"]} for i, m in enumerate(meta[:n - 1])],
                   "next_chapter_commitments": previous["commitments"] if previous else []}
        initial = {"schema_version": 1, "book_title": args.book_title + "（隔离流程模拟）", "last_chapter": n - 1,
                   "context": context, "character_snapshots": {args.protagonist: previous["protagonist"]} if previous else {},
                   "foreshadow": [], "timeline_events": [], "metrics": previous["metrics"] if previous else {}}
        save(project / "initial-input.json", initial)
        c.tracking.initialize(project, initial)
        reader_path = pilot / "blind/reviews" / f"{args.reader}-chapter-{n:02d}.json"
        observation = read(reader_path)
        prose_files, rows = [], []
        paths = c.reader_view_paths(project, prose)
        for p in paths:
            name, digest = p.relative_to(project).as_posix(), c.sha256_file(p)
            prose_files.append({"path": name, "sha256": digest})
            rows.append(f"{name}\0{digest}")
        set_sha = c.sha256_bytes("\n".join(sorted(rows)).encode())
        checks = {}
        for rid in c.RC_IDS:
            observed = observation[rid]
            anchors = []
            for evidence in observed["evidence"]:
                anchor = evidence["anchor"] if isinstance(evidence, dict) else evidence
                found = next((p for p in paths if anchor in p.read_text(encoding="utf-8")), None)
                if found is None:
                    raise RuntimeError(f"reader anchor not found: {anchor}")
                anchors.append({"path": found.relative_to(project).as_posix(), "anchor": anchor})
            checks[rid] = {"run_id": f"native-{args.reader}-{n}-{rid}", "status": observed["status"],
                           "findings": observed["findings"], "evidence": anchors,
                           "candidate_sha256": c.sha256_file(prose), "prose_files": prose_files,
                           "prose_set_sha256": set_sha}
        rc_report = c.rerun_rc01(project, prose)
        checks["rc-01"]["result_sha256"] = c.sha256_bytes(c.canonical_json(rc_report))
        outline = next(p for p in (project / "大纲").glob("细纲_第*章.md") if c.chapter_of(p.name.removeprefix("细纲_")) == n)
        skeleton = next(p for p in (project / "骨架").glob("*.md") if c.chapter_of(p.name) == n)
        context = {key: val for key, val in context.items() if key not in {"recent_chapters", "next_chapter_commitments"}}
        context["active_character_names"] = [args.protagonist]
        context["position"] = {"volume": args.volume, "volume_start_chapter": 1, "story_time": "当天", "scene": current["protagonist"]["location"]}
        tx = {"schema_version": 1, "mode": "append", "chapter": n, "chapter_title": source.stem.split("_", 1)[-1],
              "expected_state_revision": 0,
              "delta": {"result": current["summary"], "character_changes": [{"name": args.protagonist, "change": current["protagonist"]["state"]}],
                        "foreshadow_changes": [], "timeline_events": [], "constraints": [], "next_chapter_commitments": current["commitments"]},
              "context": context, "character_snapshots": {args.protagonist: current["protagonist"]}, "metrics": current["metrics"],
              "candidate_binding": {"schema_version": 2, "quality_profile": c.QUALITY_PROFILE,
                                    **{k: {"path": p.relative_to(project).as_posix(), "sha256": c.sha256_file(p)} for k, p in (("prose", prose), ("outline", outline), ("skeleton", skeleton))},
                                    "coverage": [{"id": row["id"], "evidence": row["evidence"]} for row in current["coverage"]], "logic_checks": checks}}
        save(project / "候选" / f"第{n:03d}章_追踪事务.json", tx)
        save(project / "evidence-origin.json", {"reader_type": "model", "reader_report": str(reader_path),
             "reader_report_sha256": c.sha256_file(reader_path), "postwrite_extraction": str(metadata_paths[n - 1]),
             "prior_context": "generated prior chapters imported only for isolated preflight; no author adoption", "actual_author_adoption": False})
        run = subprocess.run([sys.executable, str(REPO / "skills/story-write/scripts/candidate-commit.py"), "check", "--project", str(project), "--chapter", str(n), "--json"], capture_output=True, text=True)
        result = {"chapter": n, "project": str(project), "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr, "adopted": False}
        save(project / "check-result.json", result)
        results.append(result)
    save(pilot / "delivery-checks" / label / "results.json", results)
    print(json.dumps([{"chapter": row["chapter"], "exit_code": row["exit_code"]} for row in results]))


if __name__ == "__main__":
    main()
