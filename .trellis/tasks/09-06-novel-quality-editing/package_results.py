"""Archive trial evidence without touching prior frozen samples or real books."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]
DEST = ROOT / "docs/evaluations/2026-09-06-quality-editing"


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, value):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    pilot = args.pilot.resolve()
    evidence = DEST / "evidence"
    assert not evidence.exists(), "preserve archive; inspect before creating another"
    for directory in ("fixed", "designed", "heldout", "blind", "delivery-checks", "revision-checks"):
        if (pilot / directory).exists():
            shutil.copytree(pilot / directory, evidence / directory,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".story-write.lock"))
    for name in ("runtime-manifest.json", "blind-map.json"):
        shutil.copy2(pilot / name, evidence / name)
    frozen = json.loads((pilot / "runtime-manifest.json").read_text(encoding="utf-8"))
    for relative, expected in frozen.items():
        source = pilot / "runtime" / relative
        assert digest(source) == expected, f"generation runtime changed: {relative}"
        target = evidence / "generation-runtime" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    save(DEST / "version-map.json", {"R31": "fixed/raw", "R69": "fixed/edited", "R58": "designed/raw", "H74": "heldout/raw", "H82": "heldout/edited"})
    drift = []
    for old in (pilot / "runtime/.agents/skills").rglob("*"):
        if old.is_file() and "__pycache__" not in old.parts and old.suffix != ".pyc":
            relative = old.relative_to(pilot / "runtime/.agents/skills")
            new = ROOT / "skills" / relative
            if not new.exists() or digest(old) != digest(new):
                drift.append({"path": relative.as_posix(), "generation_sha256": digest(old), "delivery_sha256": digest(new) if new.exists() else None})
    save(DEST / "runtime-stage-differences.json", {"generation_runtime": str(pilot / "runtime"), "differences": drift,
         "meaning": "Writing used frozen template and core inputs. Final ordinary-revision/candidate validations used current runtime after independent review fixes; no raw prose was regenerated."})
    for code, directory in (("R31", "fixed/raw"), ("R69", "fixed/edited"), ("R58", "designed/raw"), ("H74", "heldout/raw"), ("H82", "heldout/edited")):
        chapters = sorted((pilot / directory).glob("第*章*.md"))
        if chapters:
            out = DEST / "readings" / f"{code}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("\n\n---\n\n".join(p.read_text(encoding="utf-8").strip() for p in chapters) + "\n", encoding="utf-8")
    baseline = Path("/var/folders/9d/3jyz3rns17gcm_0r_9zbhjn40000gn/T/story-round2-baseline-cbwpvtwo")
    old_manifest = json.loads((baseline / "snapshot-manifest.json").read_text(encoding="utf-8"))
    prior = {p: sha for p, sha in old_manifest.items() if p.startswith("docs/evaluations/2026-09-06-reader-first/")}
    mismatches = [p for p, sha in prior.items() if not (ROOT / p).is_file() or digest(ROOT / p) != sha]
    assert not mismatches, mismatches
    save(DEST / "preservation-check.json", {"baseline": str(baseline), "prior_evaluation_files": len(prior), "mismatches": mismatches,
         "real_book_modified_by_this_task": False, "commit_or_push_performed": False})
    checks = DEST / "checks"
    for name in ("story-round2-quality-gate.json", "story-round2-quality-gate.log", "story-round2-final-quality-gate.json", "story-round2-final-quality-gate.log",
                 "story-round2-completion-quality-gate.json", "story-round2-completion-quality-gate.log", "story-round2-candidate-final.log", "story-round2-lifecycle-tests.log", "story-round2-codex-check.log", "story-round2-deployment-check.log", "story-round2-contracts.log"):
        source = Path("/tmp") / name
        if source.exists():
            checks.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, checks / name)
    task = Path(__file__).parent
    for source in task.glob("resume-*"):
        if source.is_file():
            checks.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, checks / source.name)
    for source in task.glob("*.py"):
        target = evidence / "trial-tools" / source.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    current = {p.relative_to(ROOT).as_posix(): digest(p) for d in ("skills", "scripts") for p in (ROOT / d).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
    save(DEST / "delivery-code-manifest.json", current)
    manifest = {p.relative_to(DEST).as_posix(): digest(p) for p in DEST.rglob("*") if p.is_file() and p.name != "artifact-manifest.json"}
    save(DEST / "artifact-manifest.json", manifest)
    print(json.dumps({"files": len(manifest), "prior_files_unchanged": len(prior), "runtime_differences": len(drift)}))


if __name__ == "__main__":
    main()
