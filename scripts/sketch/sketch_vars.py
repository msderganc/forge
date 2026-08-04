"""Sketch template variables and handoff context (must not import the runner)."""

from __future__ import annotations

from pathlib import Path

from scripts.shared.orchestrator import (
    SkillState,
    runtime_memory_dir,
    runtime_memory_dir_relative,
)


def sketch_decisions_rel(repo_root: Path | None = None) -> str:
    mem_rel = runtime_memory_dir_relative(repo_root)
    return f"{mem_rel}/sketch-decisions.md"


def sketch_decisions_path(repo_root: Path | None = None) -> Path:
    return runtime_memory_dir(repo_root) / "sketch-decisions.md"


def detect_domain_docs(repo_root: Path) -> str:
    lines: list[str] = []
    ctx = repo_root / "CONTEXT.md"
    cmap = repo_root / "CONTEXT-MAP.md"
    adr = repo_root / "docs" / "adr"
    if cmap.is_file():
        lines.append("- `CONTEXT-MAP.md` present at repo root.")
    elif ctx.is_file():
        lines.append("- `CONTEXT.md` present at repo root.")
    else:
        lines.append("- No root `CONTEXT.md` or `CONTEXT-MAP.md` yet.")
    if adr.is_dir() and any(adr.glob("*.md")):
        lines.append(f"- ADRs under `docs/adr/` ({len(list(adr.glob('*.md')))} file(s)).")
    else:
        lines.append("- No `docs/adr/` entries yet (create lazily when needed).")
    return "\n".join(lines)


def no_edit_policy(with_domain_docs: bool, repo_root: Path) -> str:
    mem_rel = runtime_memory_dir_relative(repo_root)
    base = (
        "## Permission to modify files\n\n"
        "**Default:** Read-only on the codebase unless exploring answers a question.\n\n"
        f"**Session memory (always allowed):** `{mem_rel}/` — "
        f"especially `{mem_rel}/sketch-decisions.md` and `{mem_rel}/project.md`.\n\n"
        "**Do not write** `docs/forge/specs/*-design.md` — that is **design's** named spec.\n"
    )
    if with_domain_docs:
        base += (
            "\n**`--with-domain-docs` is on:** You may create or update:\n"
            "- `CONTEXT.md` (glossary only — see `templates/CONTEXT-FORMAT.md`)\n"
            "- `docs/adr/*.md` when all three ADR criteria apply (see `templates/ADR-FORMAT.md`)\n"
            "- `CONTEXT-MAP.md` only when the repo has multiple bounded contexts\n"
        )
    else:
        base += (
            "\n**Domain docs off:** Do not edit `CONTEXT.md` or `docs/adr/` in this session.\n"
        )
    return base


def build_variables(state: SkillState, repo_root: Path) -> dict[str, str]:
    """Build template variables for sketch prompts."""
    with_docs = bool(state.custom.get("with_domain_docs"))
    decisions_rel = sketch_decisions_rel(repo_root)
    return {
        "SKETCH_NO_EDIT_POLICY": no_edit_policy(with_docs, repo_root),
        "WITH_DOMAIN_DOCS": "yes" if with_docs else "no",
        "SKETCH_DECISIONS_PATH": decisions_rel,
        "SKETCH_DECISIONS_REL": decisions_rel,
        "DOMAIN_DOCS_STATUS": detect_domain_docs(repo_root),
        "TOPIC": str(state.custom.get("topic", "")).strip() or "(set during startup dialogue)",
    }


# Alias matching former sketch._build_variables name for tests / callers.
_build_variables = build_variables


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    """Context rows for write_handoff on sketch completion."""
    decisions_path = sketch_decisions_path(repo_root)
    decisions_rel = sketch_decisions_rel(repo_root)
    decisions_note = (
        decisions_rel
        if decisions_path.is_file()
        else f"({decisions_rel} not found — create before handoff)"
    )
    return {
        "Topic": str(state.custom.get("topic", "")),
        "Domain docs mode": (
            "with-domain-docs"
            if state.custom.get("with_domain_docs")
            else "memory-only"
        ),
        "Decisions artifact": decisions_note,
        "Next": (
            "Run forge design — design investigates, scores solutions, "
            "and writes docs/forge/specs/...-design.md when scope is medium/large."
        ),
    }
