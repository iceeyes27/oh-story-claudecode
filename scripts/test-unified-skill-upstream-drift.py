#!/usr/bin/env python3
"""Regression tests for the unified-skill upstream migration checker."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts/check-unified-skill-upstream-drift.py"


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def run_checker(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(root / "scripts/check-unified-skill-upstream-drift.py"), *args],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="story-unified-drift-") as tmp:
        root = Path(tmp)
        (root / "scripts").mkdir()
        (root / "skills/story-long-write").mkdir(parents=True)
        (root / "skills/story-write").mkdir(parents=True)
        shutil.copy2(CHECKER, root / "scripts/check-unified-skill-upstream-drift.py")

        git(root, "init", "-q")
        git(root, "branch", "-M", "main")
        git(root, "config", "user.name", "unified-drift-test")
        git(root, "config", "user.email", "unified-drift-test@example.invalid")
        (root / "skills/story-long-write/SKILL.md").write_text("baseline\n", encoding="utf-8")
        (root / "skills/story-write/SKILL.md").write_text("target\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "baseline")
        baseline = git(root, "rev-parse", "HEAD")

        git(root, "checkout", "-qb", "upstream-work")
        (root / "skills/story-long-write/SKILL.md").write_text("upstream change\n", encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-qm", "upstream change")
        git(root, "branch", "upstream/main")
        git(root, "checkout", "-q", "main")
        policy_path = root / "scripts/upstream-integration.json"
        policy_path.write_text(
            json.dumps(
                {
                    "upstream": {"baseline": baseline},
                    "unified_mappings": [
                        {"source": "skills/story-long-write", "target": "skills/story-write"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = run_checker(root, "--upstream-ref=upstream/main")
        assert result.returncode == 1, result.stdout + result.stderr
        assert "skills/story-long-write/SKILL.md -> skills/story-write" in result.stdout, result.stdout

        report = run_checker(root, "--upstream-ref=upstream/main", "--report")
        assert report.returncode == 0, report.stdout + report.stderr
        assert "Unified upstream migration report" in report.stdout, report.stdout

        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["upstream"]["baseline"] = git(root, "rev-parse", "upstream/main")
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        reverse = run_checker(root, "--upstream-ref=main")
        assert reverse.returncode == 2, reverse.stdout + reverse.stderr
        assert "is not an ancestor" in reverse.stderr, reverse.stderr

    print("PASS: unified upstream checker reports source-to-target migration paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
