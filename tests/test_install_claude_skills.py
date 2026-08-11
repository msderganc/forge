"""Claude install bundles auto-triggerable skills (using-forge + forge-*)."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_next.cli_install_claude import (
    install_claude_commands,
    install_claude_skills,
    list_claude_skill_names,
    uninstall_claude_skills,
)
from forge_next.cli_install_io import default_claude_skills_dir

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_claude_skills_pack_includes_using_forge() -> None:
    names = list_claude_skill_names(REPO_ROOT)
    assert "using-forge" in names
    assert "forge-plan" in names
    assert "forge-implement" in names
    meta = (REPO_ROOT / "integrations" / "claude" / "skills" / "using-forge" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "name: using-forge" in meta
    assert "Routing table" in meta
    assert "forge-plan" in meta
    plan = (REPO_ROOT / "integrations" / "claude" / "skills" / "forge-plan" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "name: forge-plan" in plan
    assert "Use when the user asks to plan" in plan


def test_install_claude_skills_flat_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skills_root = tmp_path / "skills"
    monkeypatch.setattr(
        "forge_next.cli_install_claude.default_claude_skills_dir",
        lambda: skills_root,
    )

    path, warnings = install_claude_skills(REPO_ROOT)
    assert path == str(skills_root)
    assert not warnings
    assert (skills_root / "using-forge" / "SKILL.md").is_file()
    assert (skills_root / "forge-plan" / "SKILL.md").is_file()
    assert (skills_root / "forge-ship" / "SKILL.md").is_file()

    removed, missing = uninstall_claude_skills(
        skill_names=list_claude_skill_names(REPO_ROOT),
        claude_skills_dir=str(skills_root),
    )
    assert missing == []
    assert f"claude_skill:using-forge" in removed
    assert not (skills_root / "using-forge").exists()


def test_install_claude_commands_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "forge_next.cli_install_claude.default_claude_commands_dir",
        lambda: tmp_path / "commands",
    )
    path, warnings = install_claude_commands(REPO_ROOT, claude_dir=None)
    assert path is not None
    assert not warnings
    assert (Path(path) / "plan.md").is_file()


def test_default_claude_skills_dir_under_dot_claude() -> None:
    path = default_claude_skills_dir()
    assert path.name == "skills"
    assert path.parent.name == ".claude"
