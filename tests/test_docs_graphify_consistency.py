"""User-facing docs must not claim per-step orchestrator GRAPHIFY banners."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

STALE_PATTERNS = [
    re.compile(r"prints a \*\*GRAPHIFY\*\* block every step", re.I),
    re.compile(r"Every `forge <skill> --step", re.I),
    re.compile(r"per-step \*\*GRAPHIFY\*\* banner", re.I),
    re.compile(r"follow \*\*GRAPHIFY\*\* blocks in every `forge --step`", re.I),
    re.compile(r"orchestrator steps print a \*\*GRAPHIFY\*\* block when an index", re.I),
]


def _doc_paths() -> list[Path]:
    paths = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "integrations" / "README.md",
    ]
    for sub in ("cursor-plugin/commands", "claude/commands"):
        cmd_dir = REPO_ROOT / "integrations" / sub
        if cmd_dir.is_dir():
            paths.extend(sorted(cmd_dir.glob("*.md")))
    graphify_skill = (
        REPO_ROOT / "integrations" / "codex" / "skills" / "forge-graphify" / "SKILL.md"
    )
    if graphify_skill.is_file():
        paths.append(graphify_skill)
    return paths


def test_no_stale_per_step_graphify_claims():
    hits: list[str] = []
    for path in _doc_paths():
        text = path.read_text(encoding="utf-8")
        for pattern in STALE_PATTERNS:
            if pattern.search(text):
                hits.append(f"{path.relative_to(REPO_ROOT)}: {pattern.pattern}")
    assert not hits, "stale Graphify claims:\n" + "\n".join(hits)
