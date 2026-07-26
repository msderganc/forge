"""Shared template bundling for forge install integrations."""

from __future__ import annotations

import shutil
from pathlib import Path

BUNDLED_SKILL_TEMPLATE_FILES = (
    "plan-modes.md",
    "writing-plans.md",
    "structural-quality-probes.md",
    "diagnose-execution-playbooks.md",
    "ux-review-criteria.md",
    "ux-review-coverage-checklist.md",
    "ux-review-report.md",
    "workflow-skill-preamble.md",
)


def copy_skill_templates(repo_root: Path, templates_dst: Path) -> None:
    """Copy canonical workflow templates into one templates directory."""
    templates_src = repo_root / "templates"
    if not templates_src.is_dir():
        return
    templates_dst.mkdir(parents=True, exist_ok=True)
    for name in BUNDLED_SKILL_TEMPLATE_FILES:
        src_file = templates_src / name
        if src_file.is_file():
            shutil.copy2(src_file, templates_dst / name)


def bundle_skill_templates(repo_root: Path, skills_root: Path) -> None:
    """Copy templates for skill-relative `templates/...` resolution.

    Agents resolve paths in SKILL.md relative to the skill directory, so
    `Read templates/ux-review-criteria.md` looks under
    ``<skill>/templates/``, not a sibling shared folder. Keep a shared
    ``skills_root/templates`` copy as well for callers that already use it.
    """
    if not skills_root.is_dir():
        return
    copy_skill_templates(repo_root, skills_root / "templates")
    for child in skills_root.iterdir():
        if not child.is_dir() or child.name == "templates":
            continue
        if not (child / "SKILL.md").is_file():
            continue
        copy_skill_templates(repo_root, child / "templates")
