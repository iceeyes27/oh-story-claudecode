"""Real prose + real model observations; isolated imported state; check only."""
import argparse
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

helper_spec = importlib.util.spec_from_file_location("delivery", Path(__file__).with_name("build_delivery_checks.py"))
h = importlib.util.module_from_spec(helper_spec)
helper_spec.loader.exec_module(h)
c = h.c


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    pilot = args.pilot.resolve()
    raw = sorted((pilot / "fixed/raw").glob("第*章*.md"))
    edited = sorted((pilot / "fixed/edited").glob("第*章*.md"))
    meta = h.normalize_extractions([h.read(pilot / f"fixed/metadata/chapter-{n:02d}.postwrite.json") for n in range(1, 4)], raw)
    initial = h.read(pilot / "delivery-checks/fixed-contract-repaired/chapter-03/initial-input.json")
    initial["last_chapter"] = 3
    initial["context"]["recent_chapters"] = [{"chapter": n, "summary": m["summary"]} for n, m in enumerate(meta, 1)]
    initial["context"]["next_chapter_commitments"] = meta[-1]["commitments"]
    initial["context"]["position"]["scene"] = meta[-1]["protagonist"]["location"]
    initial["character_snapshots"] = {"周小满": meta[-1]["protagonist"]}
    initial["metrics"] = meta[-1]["metrics"]
    pairs = [pilot / f"blind/reviews/reader-{reader}-paired.json" for reader in ("a", "b")]
    for p in pairs:
        pair = next(row for row in h.read(p)["comparisons"] if set(row["pair"]) == {"R31", "R69"})
        # Both independently recorded unchanged core facts; do not infer it from a score.
        change = pair.get("fact_meaning_changed", {})
        assert (change.get("changed") if isinstance(change, dict) else change) is False, str(p)
    records = h.read(pilot / "fixed/edited/edit-record.json")
    results = []
    for n, (original, candidate, record) in enumerate(zip(raw, edited, records), 1):
        project = pilot / "revision-checks" / args.label / f"chapter-{n:02d}"
        assert not project.exists(), "preserve existing attempt; use fresh label"
        (project / "正文").mkdir(parents=True)
        for p in raw:
            shutil.copy2(p, project / "正文" / p.name)
        h.save(project / "initial-input.json", copy.deepcopy(initial))
        c.tracking.initialize(project, initial)
        before = {p.relative_to(project).as_posix(): c.sha256_file(p) for d in ("正文", "追踪") for p in (project / d).rglob("*") if p.is_file() and p.name != ".story-write.lock"}
        command = [sys.executable, str(h.REPO / "skills/story-write/scripts/revision-commit.py")]
        prep = subprocess.run(command + ["prepare", "--project", str(project), "--chapter", str(n), "--candidate", str(candidate), "--kind", "rhythm", "--summary", "根据真实模型顺读，缩短重复确认；保留人物认可与关系动作"], capture_output=True, text=True)
        h.save(project / "prepare-result.json", {"exit_code": prep.returncode, "stdout": prep.stdout, "stderr": prep.stderr})
        assert prep.returncode == 0, prep.stderr
        prepared = json.loads(prep.stdout)
        directory = Path(prepared["directory"])
        review = h.read(directory / "review-template.json")
        review.update(status="pass", reviewer="root context review plus independent reader-a and reader-b comparisons", reader_type="model", facts_unchanged=True,
                      original_anchor=record["edits"][0][0], candidate_anchor=record["edits"][0][1])
        review["evidence_origin"] = [{"path": str(p), "sha256": c.sha256_file(p)} for p in pairs]
        review["limits"] = "Model observations only. Prior raw chapters imported for isolated check, no real author adoption. Each candidate checked against original adjacent chapters, not an already adopted edited series."
        review["findings"] = [{"severity": "advisory", "message": "两位模型读者仅小幅偏好删改，追读动力未明显增强；第二章空间展示减少，第一章三两下问答删除使下一章对应变弱。保留此取舍供作者阅读。"}]
        for row in review["context"]:
            context_n = c.chapter_of(Path(row["path"]).name)
            observations = h.read(pilot / f"blind/reviews/reader-a-R31-chapter-{context_n:02d}.json")
            evidence = observations["rc-03"]["evidence"][0]
            row["anchor"] = evidence["anchor"] if isinstance(evidence, dict) else evidence
            row["assessment"] = {
                1: "前章已明确配件下午到、先付100元且总价300元、临存费另算；本章删减未改变条件或人物目标。",
                2: "相邻章临存条件、另付30元、父亲未指挥与下午维修仍成立；三两下回顾精确性略损失，已保留为advisory。",
                3: "后章仍有稳定降温后搬鱼、傍晚前归还、200元尾款结清和姓名认可；相邻删减没有改写其原因。",
            }[context_n]
        if n == 3:
            review["metric_source_updates"] = {"已收服务费": "小满翻开本子，在今天收清的三百下面记下排风扇和明早的约定。", "未收服务费": "小满接过钱，在早上的记录后写好余款已收，拿给何桂香看。"}
        review_path = project / "actual-model-review.json"
        h.save(review_path, review)
        run = subprocess.run(command + ["check", "--project", str(project), "--operation", prepared["operation"], "--review", str(review_path)], capture_output=True, text=True)
        after = {p.relative_to(project).as_posix(): c.sha256_file(p) for d in ("正文", "追踪") for p in (project / d).rglob("*") if p.is_file() and p.name != ".story-write.lock"}
        assert before == after, "check changed adopted prose/tracking"
        result = {"chapter": n, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr, "adopted": False, "formal_files_unchanged": before == after}
        h.save(project / "check-result.json", result)
        results.append(result)
    h.save(pilot / "revision-checks" / args.label / "results.json", results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
