"""Cursor install bundles agent skills into the plugin tree."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_next.cli_install_cursor import install_cursor_plugin

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_install_cursor_plugin_bundles_skills(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "forge_next.cli_install_cursor.default_cursor_local_plugins_dir",
        lambda: tmp_path / "plugins" / "local",
    )

    path, warnings = install_cursor_plugin(REPO_ROOT, cursor_dir=None)
    assert path is not None
    assert not warnings

    plugin = Path(path)
    skills_root = plugin / "skills"
    assert skills_root.is_dir()
    assert (skills_root / "forge-plan" / "SKILL.md").is_file()
    assert (skills_root / "templates" / "plan-modes.md").is_file()
    # Skill wrappers resolve `templates/...` relative to the skill dir.
    assert (
        skills_root / "forge-ux-review" / "templates" / "ux-review-criteria.md"
    ).is_file()
    assert (skills_root / "forge-plan" / "templates" / "plan-modes.md").is_file()
    assert (
        skills_root / "forge-diagnose" / "templates" / "diagnose-execution-playbooks.md"
    ).is_file()

    manifest = (plugin / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8")
    assert '"skills"' in manifest
