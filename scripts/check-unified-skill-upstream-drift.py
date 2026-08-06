#!/usr/bin/env python3
"""Check upstream changes that must be migrated into unified skills.

The fork deliberately keeps the 11-skill layout while upstream still owns the
split story-long-* and story-short-* directories.  A normal merge can resolve
"upstream modified / fork deleted" by retaining the deletion, which makes the
merge look clean while discarding the upstream change. This guard makes every
new upstream change in a mapped source directory an explicit review task.
``--report`` keeps the check read-only and prints the source-to-target mapping
needed for that review.
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
    parser.add_argument(
        "--report",
        action="store_true",
        help="print a migration report and return success when mapped changes exist",
    )
    args = parser.parse_args()

    map_path = args.map if args.map.is_absolute() else REPO_ROOT / args.map

    try:
        config = json.loads(map_path.read_text(encoding="utf-8"))
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

    source_to_target: dict[str, str] = {}
    for entry in mappings:
        if not isinstance(entry, dict) or not isinstance(entry.get("source"), str) or not isinstance(entry.get("target"), str):
            print("FAIL: every mapping needs source and target", file=sys.stderr)
            return 2
        source = entry["source"].strip().strip("/")
        target = entry["target"].strip().strip("/")
        if not source or not target or source in source_to_target:
            print("FAIL: mappings must contain unique non-empty source paths", file=sys.stderr)
            return 2
        if not (REPO_ROOT / target).is_dir():
            print(f"FAIL: mapped unified target directory is missing: {target}", file=sys.stderr)
            return 2
        source_to_target[source] = target

    source_paths = list(source_to_target)

    changed = git("diff", "--name-status", f"{baseline}..{args.upstream_ref}", "--", *source_paths)
    if not changed:
        print(f"OK: no mapped upstream skill changes after {baseline[:12]}")
        return 0

    rows: list[tuple[str, str, str]] = []
    for line in changed.splitlines():
        fields = line.split("\t")
        status = fields[0]
        paths = fields[1:]
        path = " -> ".join(paths)
        source = next(
            (
                candidate
                for candidate in source_paths
                if any(item == candidate or item.startswith(f"{candidate}/") for item in paths)
            ),
            None,
        )
        target = source_to_target[source] if source is not None else "<review map>"
        rows.append((status, path, target))

    if args.report:
        print("Unified upstream migration report")
    else:
        print("FAIL: upstream changed paths that were renamed into unified skills:")
    print(f"Baseline: {baseline[:12]}")
    print(f"Upstream: {args.upstream_ref}")
    for status, path, target in rows:
        print(f"  {status:4} {path} -> {target}")
    print(
        "Review each source change, apply its semantics to the mapped unified target, "
        "then advance upstream_baseline in scripts/unified-skill-upstream-map.json."
    )
    return 0 if args.report else 1


if __name__ == "__main__":
    raise SystemExit(main())
