#!/usr/bin/env python3
"""Fail when upstream changes a source path absorbed by a unified skill.

The fork deliberately keeps the 11-skill layout while upstream still owns the
split story-long-* and story-short-* directories.  A normal merge can resolve
"upstream modified / fork deleted" by retaining the deletion, which makes the
merge look clean while discarding the upstream change.  This guard makes every
new upstream change in a mapped source directory an explicit review task.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = REPO_ROOT / "scripts" / "unified-skill-upstream-map.json"


def git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-ref", default="upstream/main")
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args()

    try:
        config = json.loads(args.map.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"FAIL: cannot read unified-skill map: {error}", file=sys.stderr)
        return 2

    baseline = config.get("upstream_baseline")
    mappings = config.get("mappings")
    if not isinstance(baseline, str) or not baseline or not isinstance(mappings, list):
        print("FAIL: map needs upstream_baseline and mappings", file=sys.stderr)
        return 2

    try:
        git("rev-parse", "--verify", f"{args.upstream_ref}^{{commit}}")
        git("rev-parse", "--verify", f"{baseline}^{{commit}}")
    except subprocess.CalledProcessError:
        print(
            f"FAIL: cannot resolve {args.upstream_ref} or baseline {baseline}; fetch upstream before this check.",
            file=sys.stderr,
        )
        return 2

    source_paths: list[str] = []
    for entry in mappings:
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str) or not isinstance(entry.get("target"), str):
            print("FAIL: every mapping needs source and target", file=sys.stderr)
            return 2
        source_paths.append(entry["source"])

    changed = git("diff", "--name-only", f"{baseline}..{args.upstream_ref}", "--", *source_paths)
    if not changed:
        print(f"OK: no mapped upstream skill changes after {baseline[:12]}")
        return 0

    print("FAIL: upstream changed paths that were renamed into unified skills:")
    for path in changed.splitlines():
        print(f"  {path}")
    print("Review each change, apply it to the mapped unified target, then advance upstream_baseline in scripts/unified-skill-upstream-map.json.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
