"""Install Claude command pack, skills pack, and optional Graphify hooks."""

from __future__ import annotations

import shutil
from pathlib import Path

from forge_next.cli_install_io import (
    copytree_replace,
    default_claude_commands_dir,
    default_claude_skills_dir,
)


def install_claude_commands(
    repo_root: Path,
    *,
    claude_dir: str | None,
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    src = repo_root / "integrations" / "claude" / "commands"
    if not src.is_dir():
        warnings.append("Claude commands folder not found in downloaded repo.")
        return None, warnings
    base = (
        Path(claude_dir).expanduser()
        if claude_dir
        else default_claude_commands_dir()
    )
    dst = base / "forge"
    copytree_replace(src, dst)
    return str(dst), warnings


def install_claude_skills(
    repo_root: Path,
    *,
    claude_skills_dir: str | None = None,
) -> tuple[str | None, list[str]]:
    """Install using-forge + forge-* skills into ~/.claude/skills/ (flat).

    Claude Code auto-matches skill ``description`` fields — slash commands alone
    do not. Each skill directory is copied as a sibling under the skills root
    (same layout as other personal skills such as graphify).
    """
    warnings: list[str] = []
    src = repo_root / "integrations" / "claude" / "skills"
    if not src.is_dir():
        warnings.append("Claude skills folder not found in downloaded repo.")
        return None, warnings

    base = (
        Path(claude_skills_dir).expanduser()
        if claude_skills_dir
        else default_claude_skills_dir()
    )
    base.mkdir(parents=True, exist_ok=True)

    installed_dirs: list[str] = []
    for skill_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            warnings.append(f"Skipping {skill_dir.name}: missing SKILL.md")
            continue
        dst = base / skill_dir.name
        copytree_replace(skill_dir, dst)
        installed_dirs.append(skill_dir.name)

    if not installed_dirs:
        warnings.append("No Claude skills were installed (empty skills pack).")
        return None, warnings

    return str(base), warnings


def list_claude_skill_names(repo_root: Path) -> list[str]:
    """Return skill directory names shipped under integrations/claude/skills/."""
    src = repo_root / "integrations" / "claude" / "skills"
    if not src.is_dir():
        return []
    return sorted(
        p.name
        for p in src.iterdir()
        if p.is_dir() and (p / "SKILL.md").is_file()
    )


def uninstall_claude_skills(
    *,
    skill_names: list[str],
    claude_skills_dir: str | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Remove Forge-owned skill dirs only; leave unrelated personal skills alone."""
    removed: dict[str, str] = {}
    missing: list[str] = []
    base = (
        Path(claude_skills_dir).expanduser()
        if claude_skills_dir
        else default_claude_skills_dir()
    )
    for name in skill_names:
        path = base / name
        if path.is_dir():
            shutil.rmtree(path)
            removed[f"claude_skill:{name}"] = str(path)
        else:
            missing.append(str(path))
    return removed, missing


def apply_claude_graphify_hooks() -> tuple[str | None, list[str]]:
    from forge_next.claude_graphify import (
        apply_claude_graphify_settings,
        default_claude_settings_path,
    )

    warnings: list[str] = []
    rc = apply_claude_graphify_settings(default_claude_settings_path())
    if rc == 0:
        return str(default_claude_settings_path()), warnings
    warnings.append(
        "Claude Graphify hooks were not written; run `forge claude-graphify` "
        "after fixing settings.json."
    )
    return None, warnings
