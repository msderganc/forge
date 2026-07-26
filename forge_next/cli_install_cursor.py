"""Install Cursor plugin pack from a extracted forge repo tree."""

from __future__ import annotations

import shutil
from pathlib import Path

from forge_next.cli_install_io import copytree_replace, default_cursor_local_plugins_dir
from forge_next.cli_install_templates import bundle_skill_templates


def _install_cursor_plugin_ship_skill(repo_root: Path, plugin_root: Path) -> None:
    """Copy the Cursor `ship` skill into the plugin's bundled skills/ship/."""
    src = repo_root / ".cursor" / "skills" / "ship" / "SKILL.md"
    if not src.is_file():
        return
    dst_dir = plugin_root / "skills" / "ship"
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / "SKILL.md")


def _install_cursor_plugin_skills(repo_root: Path, plugin_root: Path) -> list[str]:
    """Bundle Codex SKILL.md packs under the Cursor plugin for agent discovery."""
    warnings: list[str] = []
    src = repo_root / "integrations" / "codex" / "skills"
    if not src.is_dir():
        warnings.append("Codex skills folder not found; Cursor plugin has commands only.")
        return warnings

    skills_dst = plugin_root / "skills"
    if skills_dst.exists():
        shutil.rmtree(skills_dst)
    shutil.copytree(src, skills_dst)

    bundle_skill_templates(repo_root, skills_dst)

    _install_cursor_plugin_ship_skill(repo_root, plugin_root)

    return warnings


def install_cursor_plugin(
    repo_root: Path,
    *,
    cursor_dir: str | None,
) -> tuple[str | None, list[str]]:
    """Copy integrations/cursor-plugin and bundle agent skills; return (path, warnings)."""
    warnings: list[str] = []
    src = repo_root / "integrations" / "cursor-plugin"
    if not src.is_dir():
        warnings.append("Cursor plugin folder not found in downloaded repo.")
        return None, warnings
    base = (
        Path(cursor_dir).expanduser()
        if cursor_dir
        else default_cursor_local_plugins_dir()
    )
    dst = base / "forge"
    copytree_replace(src, dst)
    warnings.extend(_install_cursor_plugin_skills(repo_root, dst))
    return str(dst), warnings
