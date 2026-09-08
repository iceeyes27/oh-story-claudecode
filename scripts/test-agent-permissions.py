#!/usr/bin/env python3
"""Behavior tests for capability-derived multi-CLI agent permissions."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_GENERATOR = REPO_ROOT / "scripts/generate-codex-agents.py"
ANTIGRAVITY_GENERATOR = (
    REPO_ROOT / "skills/story-setup/scripts/generate-antigravity-agents.mjs"
)
TEMPLATES = REPO_ROOT / "skills/story-setup/references/templates"
CODEX_BASELINE = REPO_ROOT / "skills/story-setup/references/codex/agents"


def run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def write_agent(
    directory: Path,
    name: str,
    tools: list[str],
    disallowed: list[str] | None = None,
) -> None:
    disallowed_line = (
        f"disallowedTools: [{', '.join(disallowed)}]\n" if disallowed else ""
    )
    write_raw_agent(
        directory, name, f"tools: [{', '.join(tools)}]\n{disallowed_line}"
    )


def write_raw_agent(directory: Path, name: str, capability_lines: str) -> None:
    text = (
        "---\n"
        f"name: {name}\n"
        f"description: {name} fixture\n"
        f"{capability_lines.rstrip()}\n"
        "maxTurns: 3\n"
        "---\n"
        f"# {name}\n\nCapability fixture.\n"
    )
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.md").write_text(text, encoding="utf-8")


def codex_documents(directory: Path) -> dict[str, dict[str, object]]:
    return {
        path.stem: tomllib.loads(path.read_text(encoding="utf-8"))
        for path in directory.glob("*.toml")
    }


def antigravity_tools(path: Path) -> list[str]:
    tools: list[str] = []
    in_tools = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "tools:":
            in_tools = True
            continue
        if in_tools and line.startswith("  - "):
            tools.append(line.removeprefix("  - "))
            continue
        if in_tools:
            break
    return tools


def assert_invalid_capabilities_fail_before_publish(capability_lines: str) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-capability-invalid-") as tmp:
        root = Path(tmp)
        source = root / "sources"
        write_raw_agent(source, "invalid-capabilities", capability_lines)

        codex_dest = root / "codex"
        codex_dest.mkdir()
        codex_sentinel = codex_dest / "existing.toml"
        codex_sentinel.write_text("existing codex output\n", encoding="utf-8")
        result = run(
            str(CODEX_GENERATOR),
            "--source",
            str(source),
            "--dest",
            str(codex_dest),
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert codex_sentinel.read_text(encoding="utf-8") == "existing codex output\n"
        assert not (codex_dest / "invalid-capabilities.toml").exists()

        antigravity_dest = root / "antigravity"
        antigravity_dest.mkdir()
        antigravity_sentinel = antigravity_dest / "existing.txt"
        antigravity_sentinel.write_text(
            "existing antigravity output\n", encoding="utf-8"
        )
        result = subprocess.run(
            [
                "node",
                str(ANTIGRAVITY_GENERATOR),
                "--source",
                str(source),
                "--dest",
                str(antigravity_dest),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0, result.stdout + result.stderr
        assert (
            antigravity_sentinel.read_text(encoding="utf-8")
            == "existing antigravity output\n"
        )
        assert not (antigravity_dest / "invalid-capabilities").exists()


def test_generated_agents_are_in_sync() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-permissions-baseline-") as tmp:
        root = Path(tmp)
        codex_dest = root / "codex"
        result = run(
            str(CODEX_GENERATOR),
            "--source",
            str(TEMPLATES / "agents"),
            "--dest",
            str(codex_dest),
        )
        assert result.returncode == 0, result.stdout + result.stderr
        expected_codex = sorted(path.name for path in CODEX_BASELINE.glob("*.toml"))
        assert sorted(path.name for path in codex_dest.glob("*.toml")) == expected_codex
        for filename in expected_codex:
            assert (codex_dest / filename).read_bytes() == (
                CODEX_BASELINE / filename
            ).read_bytes(), filename



def test_permissions_follow_capabilities_not_names() -> None:
    cases = {
        "renamed-reader": "tools: [Read, Glob, Grep]\ndisallowedTools: [Write, Edit, Bash]",
        "implicit-reader": "tools: [Read]",
        "renamed-writer": "tools: [Read, Write, Edit]",
        "write-without-edit": "tools: [Read, Write]\ndisallowedTools: [Edit]",
        "edit-without-write": "tools: [Read, Edit]\ndisallowedTools: [Write]",
        "shell-reader": "tools: [Read, Bash]",
        "denials-win": "tools: [Read, Write, Edit, Bash]\ndisallowedTools: [Write, Edit, Bash]",
        "story-researcher": "tools: [Read]\ndisallowedTools: [Write, Edit, Bash]",
        "mixed-read-like": "tools: [Read, Glob, Grep]\ndisallowedTools: [Read, Grep]",
    }
    with tempfile.TemporaryDirectory(prefix="agent-permissions-fixture-") as tmp:
        root = Path(tmp)
        source = root / "sources"
        for name, declaration in cases.items():
            write_raw_agent(source, name, declaration)
        result = run(str(CODEX_GENERATOR), "--source", str(source), "--dest", str(root / "codex"))
        assert result.returncode == 0, result.stdout + result.stderr
        codex = codex_documents(root / "codex")
        for name in ("renamed-reader", "implicit-reader", "denials-win", "story-researcher", "mixed-read-like"):
            assert codex[name].get("sandbox_mode") == "read-only", name
        for name in ("renamed-writer", "write-without-edit", "edit-without-write", "shell-reader"):
            assert "sandbox_mode" not in codex[name], name

        result = subprocess.run(
            ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(source), "--dest", str(root / "agy")],
            text=True, capture_output=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert antigravity_tools(root / "agy/denials-win/agent.md") == ["view_file"]
        assert antigravity_tools(root / "agy/mixed-read-like/agent.md") == ["find_by_name"]
        assert antigravity_tools(root / "agy/write-without-edit/agent.md") == ["view_file", "write_to_file"]
        assert antigravity_tools(root / "agy/edit-without-write/agent.md") == ["view_file", "replace_file_content", "multi_replace_file_content"]


def test_empty_and_inherited_tools_are_distinct() -> None:
    cases = {
        "empty": "tools: []",
        "all-denied": "tools: [Read, Glob, Grep]\ndisallowedTools: [Read, Glob, Grep]",
        "inherit": "",
        "inherit-minus-glob": "disallowedTools: [Glob, Write, Edit, Bash]",
    }
    with tempfile.TemporaryDirectory(prefix="agent-permissions-inheritance-") as tmp:
        root = Path(tmp)
        for name, declaration in cases.items():
            source = root / name / "sources"
            write_raw_agent(source, name, declaration)
            result = run(str(CODEX_GENERATOR), "--source", str(source), "--dest", str(root / name / "codex"))
            if name in {"empty", "all-denied"}:
                assert result.returncode != 0 and "zero effective tools" in result.stderr, result.stderr
                assert not (root / name / "codex").exists()
            else:
                assert result.returncode == 0, result.stderr
                assert "sandbox_mode" not in codex_documents(root / name / "codex")[name]
            result = subprocess.run(
                ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(source), "--dest", str(root / name / "agy")],
                text=True, capture_output=True,
            )
            assert result.returncode != 0, name
            assert not (root / name / "agy").exists()


def test_codex_recognizes_other_mutating_tools() -> None:
    with tempfile.TemporaryDirectory(prefix="codex-mutating-tools-") as tmp:
        root = Path(tmp)
        for tool in ("NotebookEdit", "PowerShell"):
            write_agent(root / "sources", tool, ["Read", tool])
            write_agent(root / "sources", f"denied-{tool}", ["Read", tool], [tool])
        result = run(str(CODEX_GENERATOR), "--source", str(root / "sources"), "--dest", str(root / "codex"))
        assert result.returncode == 0, result.stderr
        docs = codex_documents(root / "codex")
        for tool in ("NotebookEdit", "PowerShell"):
            assert "sandbox_mode" not in docs[tool]
            assert docs[f"denied-{tool}"]["sandbox_mode"] == "read-only"
        result = subprocess.run(
            ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(root / "sources"), "--dest", str(root / "agy")],
            text=True, capture_output=True,
        )
        assert result.returncode != 0 and "unsupported Antigravity capability" in result.stderr


def test_invalid_capability_declarations_fail_closed() -> None:
    cases = [
        "tools: [Read, NotARealTool]",
        "tools: [Read]\ndisallowedTools: [NotARealTool]",
        "tools: Read, Write",
        "tools: [Read, Write]\ndisallowedTools: [Write",
        "tools: []\ndisallowedTools: Write, Edit",
        'tools: ["Read", "Write"]junk',
        "tools:\n  - Read\n  - Write",
    ]
    for capability_lines in cases:
        assert_invalid_capabilities_fail_before_publish(capability_lines)


def test_antigravity_accepts_crlf_frontmatter() -> None:
    with tempfile.TemporaryDirectory(prefix="agent-crlf-") as tmp:
        root = Path(tmp)
        source = root / "source"
        write_agent(source, "reader", ["Read"])
        agent = source / "reader.md"
        text = agent.read_text(encoding="utf-8")
        for label, newline in (("lf", "\n"), ("crlf", "\r\n")):
            agent.write_bytes(text.replace("\n", newline).encode("utf-8"))
            result = subprocess.run(
                ["node", str(ANTIGRAVITY_GENERATOR), "--source", str(source), "--dest", str(root / label)],
                text=True, capture_output=True,
            )
            assert result.returncode == 0, result.stdout + result.stderr
        assert (root / "lf/reader/agent.md").read_bytes() == (root / "crlf/reader/agent.md").read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    test_antigravity_accepts_crlf_frontmatter()
    test_generated_agents_are_in_sync()
    test_permissions_follow_capabilities_not_names()
    test_empty_and_inherited_tools_are_distinct()
    test_codex_recognizes_other_mutating_tools()
    test_invalid_capability_declarations_fail_closed()
    print("PASS: agent permissions derive from canonical capabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
