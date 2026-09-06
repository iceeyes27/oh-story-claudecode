"""Check the actual held-out edits against unchanged imported prose and tracking.

This is a model-reviewed feasibility check, not author adoption or human feedback.
Chapters 2 and 3 use facts revisions because disclosure and remembered events change.
"""
import copy
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

spec = importlib.util.spec_from_file_location("delivery", Path(__file__).with_name("build_delivery_checks.py"))
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
c = h.c


def protected(project):
    return {p.relative_to(project).as_posix(): c.sha256_file(p)
            for d in ("正文", "追踪") for p in (project / d).rglob("*")
            if p.is_file() and p.name != ".story-write.lock"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="heldout-actual-edits")
    parser.add_argument("--chapters", default="1,2,3")
    args = parser.parse_args()
    pilot = Path(Path(__file__).with_name("pilot-location.txt").read_text().strip()).resolve()
    destination = pilot / "revision-checks" / args.label
    assert not destination.exists(), "preserve every previous attempt"
    raw = sorted((pilot / "heldout/raw").glob("第*章*.md"))
    edited = sorted((pilot / "heldout/edited").glob("第*章*.md"))
    metadata = [h.read(pilot / f"heldout/metadata/chapter-{n:02d}.postwrite.json") for n in range(1, 4)]
    updated = [h.read(pilot / f"heldout/edited-metadata/chapter-{n:02d}.postwrite.json") for n in range(1, 4)]
    initial = h.read(pilot / "delivery-checks/heldout-raw-id-normalized/chapter-03/initial-input.json")
    initial["last_chapter"] = 3
    initial["context"]["recent_chapters"] = [{"chapter": n, "summary": m["summary"]} for n, m in enumerate(metadata, 1)]
    initial["context"]["next_chapter_commitments"] = []
    initial["context"]["position"]["scene"] = metadata[-1]["protagonist"]["location"]
    initial["character_snapshots"] = {"宋棠": metadata[-1]["protagonist"]}
    anchors = {
        1: ("这问题该留在她手边，不能先落进说明牌。", "宋棠原本已准备沿着站员去找，听他这么说，就在草纸上写下衣服两个字，后面添了一个问号。"),
        2: ("心里那条沿着职工名字往下找的路，到这里已走不通。", "把草纸上凭外套猜身份的那一行划掉。"),
        3: ("现在两个参与搬书的人说起箱子，前后就接上了。", "我早上说这只漏底，说岔了，漏的是前一只。"),
    }
    context_assessments = {
        1: ("这就是搬书那天。我记得这箱子，底下漏了，托着走才没散。", "第一章齐叔把漏底指向最终合影的箱子。第二章修改不触及这句；第三章需明确纠正它。联系寄件者、五人照片和留空姓名的因果仍保留。"),
        2: ("宋棠低头读：在旧站帮着搬了书，还得把剩下的信送完，晚些回。", "便条、借衣和电话邀请仍支撑第三章来访相认；第一章删一处原则复述不影响此章。原版过早排除职工方向仍单列为未采用相邻修订，不能宣称已修改。"),
        3: ("林琴看向程雪：\"你带我来就为这个？\"", "后章母女署名意愿不依赖第二章延迟披露关系，提前说明仍有前因。原第三章箱子互证存在已记录的局部矛盾，第二章修订不会自动修好，第三章候选另作事实修订。"),
    }
    results = []
    for n, candidate in enumerate(edited, 1):
        if n not in {int(value) for value in args.chapters.split(",")}:
            continue
        project = destination / f"chapter-{n:02d}"
        (project / "正文").mkdir(parents=True)
        for source in raw:
            shutil.copy2(source, project / "正文" / source.name)
        h.save(project / "initial-input.json", copy.deepcopy(initial))
        c.tracking.initialize(project, initial)
        before = protected(project)
        kind = "rhythm" if n == 1 else "facts"
        cli = [sys.executable, str(h.REPO / "skills/story-write/scripts/revision-commit.py")]
        prep = subprocess.run(cli + ["prepare", "--project", str(project), "--chapter", str(n), "--candidate", str(candidate), "--kind", kind,
                                     "--summary", "实际一次局部编辑：删原则复述、调整母女披露与推断、明确纠正箱子记忆"], capture_output=True, text=True)
        h.save(project / "prepare-result.json", {"exit_code": prep.returncode, "stdout": prep.stdout, "stderr": prep.stderr})
        assert prep.returncode == 0, prep.stderr
        prepared = json.loads(prep.stdout)
        review = h.read(Path(prepared["directory"]) / "review-template.json")
        reports = [pilot / f"blind/reviews/heldout-reader-H74-chapter-{i:02d}.json" for i in range(1, 4)]
        reports += [pilot / f"blind/reviews/heldout-reader-H82-chapter-{i:02d}.json" for i in range(1, 4)]
        review.update(status="pass", reviewer="root actual raw-prose and diff reading, with saved sequential model observations", reader_type="model",
                      facts_unchanged=(kind == "rhythm"), original_anchor=anchors[n][0], candidate_anchor=anchors[n][1])
        review["evidence_origin"] = [{"path": str(p), "sha256": c.sha256_file(p)} for p in reports]
        review["limits"] = "Root read all three raw chapters and actual edit diffs; earlier readers used same-version sequential prose. This check binds original adjacent chapters, not an adopted edited series. No human or author adoption. Separate edited-series candidate checks supply cumulative evidence."
        review["findings"] = [{"severity": "advisory", "message": "原则解释仍偏多；编辑不证明长篇追读收益。各章相邻原文中尚未采用的编辑不得当成已发生。"}]
        for row in review["context"]:
            chapter = c.chapter_of(Path(row["path"]).name)
            row["anchor"], row["assessment"] = context_assessments[chapter]
        review_path = project / "actual-model-review.json"
        h.save(review_path, review)
        extra = []
        if kind == "facts":
            context = {k: v for k, v in initial["context"].items() if k not in {"recent_chapters", "next_chapter_commitments"}}
            latest_snapshot = updated[-1]["protagonist"] if n == 3 else metadata[-1]["protagonist"]
            transaction = {"schema_version": 1, "mode": "revision", "chapter": n, "chapter_title": candidate.stem.split("_", 1)[1], "expected_state_revision": 0,
                           "delta": {"result": updated[n-1]["summary"], "character_changes": [{"name": "宋棠", "change": "已听齐叔明确纠正箱子记混，完成署名"}] if n == 3 else [], "foreshadow_changes": [], "timeline_events": [], "constraints": [],
                                     "next_chapter_commitments": updated[n-1]["commitments"]},
                           "context": context, "character_snapshots": {"宋棠": latest_snapshot} if n == 3 else {}, "metrics": {},
                           "metrics_unchanged_reason": "照片展修订不涉及收支或数值结算"}
            transaction_path = project / "actual-fact-transaction.json"
            h.save(transaction_path, transaction)
            extra = ["--transaction", str(transaction_path)]
        run = subprocess.run(cli + ["check", "--project", str(project), "--operation", prepared["operation"], "--review", str(review_path)] + extra, capture_output=True, text=True)
        after = protected(project)
        assert before == after, "preparation/check modified imported prose or tracking"
        result = {"chapter": n, "kind": kind, "exit_code": run.returncode, "stdout": run.stdout, "stderr": run.stderr,
                  "adopted": False, "formal_files_unchanged": before == after, "protected_before": before, "protected_after": after}
        h.save(project / "check-result.json", result)
        results.append(result)
    h.save(destination / "results.json", results)
    print(json.dumps([{k: r[k] for k in ("chapter", "kind", "exit_code", "formal_files_unchanged")} for r in results]))


if __name__ == "__main__":
    main()
