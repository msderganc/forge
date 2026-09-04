"""forge install copies Uncodixfy from git; uninstall removes only those dests."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_next.cli_install_uncodixfy import (
    SKILL_NAME,
    UNCODIXFY_REPO_URL_DEFAULT,
    install_uncodixfy_from_tree,
    run_uncodixfy_install,
    uninstall_uncodixfy,
)


def _fake_uncodixfy_repo(tmp_path: Path) -> Path:
    root = tmp_path / "Uncodixfy-main"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: uncodixfy\n---\n# Uncodixfy\n", encoding="utf-8"
    )
    (root / "Uncodixfy.md").write_text("# Uncodixfy body\n", encoding="utf-8")
    (root / "README.md").write_text("# Uncodixfy\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (root / "images").mkdir()
    (root / "images" / "before.png").write_text("nope\n", encoding="utf-8")
    return root


def test_install_uncodixfy_from_tree(tmp_path: Path) -> None:
    repo = _fake_uncodixfy_repo(tmp_path)
    cursor = tmp_path / "cursor-plugins-local"
    claude = tmp_path / "claude-skills"
    codex = tmp_path / "codex-skills"
    installed, warnings = install_uncodixfy_from_tree(
        repo,
        cursor_plugins_dir=cursor,
        claude_skills_dir=claude,
        codex_skills_dir=codex,
    )
    assert not warnings
    plugin = cursor / SKILL_NAME
    skill = plugin / "skills" / SKILL_NAME
    assert (skill / "SKILL.md").is_file()
    assert (skill / "Uncodixfy.md").is_file()
    assert (plugin / "LICENSE").is_file()
    assert (plugin / ".cursor-plugin" / "plugin.json").is_file()
    assert not (plugin / "images").exists()
    assert not (skill / "images").exists()
    assert (claude / SKILL_NAME / "SKILL.md").is_file()
    assert (codex / SKILL_NAME / "SKILL.md").is_file()
    assert "cursor_uncodixfy" in installed
    assert "claude_uncodixfy" in installed
    assert "codex_uncodixfy" in installed


def test_install_missing_skill_md_warns(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    installed, warnings = install_uncodixfy_from_tree(
        empty,
        cursor_plugins_dir=tmp_path / "c",
        claude_skills_dir=tmp_path / "cl",
        codex_skills_dir=tmp_path / "cx",
    )
    assert installed == {}
    assert any("SKILL.md" in w for w in warnings)


def test_skip_env_and_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = tmp_path / "cursor-plugins-local"
    monkeypatch.setenv("FORGE_SKIP_UNCODIXFY", "1")
    installed, warnings = run_uncodixfy_install(
        skip=False,
        repo_url="https://example.invalid/nope",
        ref="main",
        cursor_plugins_dir=cursor,
        claude_skills_dir=tmp_path / "claude",
        codex_skills_dir=tmp_path / "codex",
    )
    assert installed == {}
    assert any("skipped" in w.lower() for w in warnings)
    assert not cursor.exists()

    monkeypatch.delenv("FORGE_SKIP_UNCODIXFY")
    installed, warnings = run_uncodixfy_install(
        skip=True,
        repo_url="https://example.invalid/nope",
        ref="main",
        cursor_plugins_dir=cursor,
        claude_skills_dir=tmp_path / "claude",
        codex_skills_dir=tmp_path / "codex",
    )
    assert installed == {}
    assert any("skipped" in w.lower() for w in warnings)


def test_download_failure_is_warning_not_fatal(tmp_path: Path) -> None:
    installed, warnings = run_uncodixfy_install(
        skip=False,
        repo_url="https://example.invalid/nope",
        ref="main",
        cursor_plugins_dir=tmp_path / "cursor",
        claude_skills_dir=tmp_path / "claude",
        codex_skills_dir=tmp_path / "codex",
    )
    assert installed == {}
    assert warnings
    assert any("uncodixfy" in w.lower() and "fail" in w.lower() for w in warnings)


def test_uninstall_uncodixfy_leaves_forge_skills(tmp_path: Path) -> None:
    repo = _fake_uncodixfy_repo(tmp_path)
    cursor = tmp_path / "cursor-plugins-local"
    claude = tmp_path / "claude-skills"
    codex = tmp_path / "codex-skills"
    (claude / "using-forge").mkdir(parents=True)
    (claude / "using-forge" / "SKILL.md").write_text("keep\n", encoding="utf-8")
    (claude / "forge-design").mkdir()
    (claude / "forge-design" / "SKILL.md").write_text("keep\n", encoding="utf-8")
    install_uncodixfy_from_tree(
        repo,
        cursor_plugins_dir=cursor,
        claude_skills_dir=claude,
        codex_skills_dir=codex,
    )
    removed, missing = uninstall_uncodixfy(
        cursor_plugins_dir=cursor,
        claude_skills_dir=claude,
        codex_skills_dir=codex,
    )
    assert missing == []
    assert not (cursor / SKILL_NAME).exists()
    assert not (claude / SKILL_NAME).exists()
    assert not (codex / SKILL_NAME).exists()
    assert (claude / "using-forge" / "SKILL.md").is_file()
    assert (claude / "forge-design" / "SKILL.md").is_file()
    assert "cursor_uncodixfy" in removed


def test_install_parser_uncodixfy_flags() -> None:
    from forge_next.cli import build_parser

    parser = build_parser()
    default = parser.parse_args(["install"])
    assert default.skip_uncodixfy is False
    assert default.uncodixfy_repo_url == UNCODIXFY_REPO_URL_DEFAULT
    assert default.uncodixfy_ref == "main"
    skipped = parser.parse_args(["install", "--skip-uncodixfy"])
    assert skipped.skip_uncodixfy is True
    custom = parser.parse_args(
        [
            "install",
            "--uncodixfy-repo-url",
            "https://example.invalid/Uncodixfy",
            "--uncodixfy-ref",
            "dev",
        ]
    )
    assert custom.uncodixfy_repo_url == "https://example.invalid/Uncodixfy"
    assert custom.uncodixfy_ref == "dev"
