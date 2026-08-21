"""forge install copies allowlisted pstack skills from a git tree; skip-list stays off disk."""

from __future__ import annotations

from pathlib import Path

import pytest

from forge_next.cli_install_pstack import (
    PSTACK_SKILL_ALLOWLIST,
    PSTACK_SKILL_SKIP,
    install_pstack_from_tree,
    run_pstack_install,
    uninstall_pstack,
)


def _write_skill(root: Path, name: str) -> None:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")


def _fake_plugins_repo(tmp_path: Path) -> Path:
    pstack = tmp_path / "cursor-plugins" / "pstack"
    skills = pstack / "skills"
    skills.mkdir(parents=True)
    (pstack / "LICENSE").write_text("MIT\n", encoding="utf-8")
    (pstack / "README.md").write_text("pstack\n", encoding="utf-8")
    plugin = pstack / ".cursor-plugin"
    plugin.mkdir()
    (plugin / "plugin.json").write_text('{"name":"pstack"}\n', encoding="utf-8")
    for name in sorted(PSTACK_SKILL_ALLOWLIST | PSTACK_SKILL_SKIP | {"architect"}):
        _write_skill(skills, name)
    (pstack / "agents").mkdir()
    (pstack / "agents" / "x.md").write_text("nope\n", encoding="utf-8")
    return tmp_path / "cursor-plugins"


def test_install_pstack_from_tree_allowlist_only(tmp_path: Path) -> None:
    repo = _fake_plugins_repo(tmp_path)
    cursor = tmp_path / "cursor-plugins-local"
    claude = tmp_path / "claude-skills"
    codex = tmp_path / "codex-skills"
    installed, warnings = install_pstack_from_tree(
        repo,
        cursor_plugins_dir=cursor,
        claude_skills_dir=claude,
        codex_skills_dir=codex,
    )
    assert not warnings
    dest = cursor / "pstack"
    assert (dest / "LICENSE").is_file()
    assert (dest / "skills" / "bro" / "SKILL.md").is_file()
    assert (dest / "skills" / "arena" / "SKILL.md").is_file()
    assert (dest / "skills" / "unslop" / "SKILL.md").is_file()
    for skipped in PSTACK_SKILL_SKIP:
        assert not (dest / "skills" / skipped).exists()
    assert not (dest / "skills" / "architect").exists()
    assert not (dest / "agents").exists()
    assert (claude / "bro" / "SKILL.md").is_file()
    assert not (claude / "poteto-mode").exists()
    assert (codex / "pstack" / "bro" / "SKILL.md").is_file()
    assert "cursor_pstack" in installed
    assert "claude_pstack" in installed
    assert "codex_pstack" in installed


def test_skip_env_and_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cursor = tmp_path / "cursor-plugins-local"
    monkeypatch.setenv("FORGE_SKIP_PSTACK", "1")
    installed, warnings = run_pstack_install(
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

    monkeypatch.delenv("FORGE_SKIP_PSTACK")
    installed, warnings = run_pstack_install(
        skip=True,
        repo_url="https://example.invalid/nope",
        ref="main",
        cursor_plugins_dir=cursor,
        claude_skills_dir=tmp_path / "claude",
        codex_skills_dir=tmp_path / "codex",
    )
    assert installed == {}
    assert any("skipped" in w.lower() for w in warnings)


def test_download_failure_is_warning_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    installed, warnings = run_pstack_install(
        skip=False,
        repo_url="https://example.invalid/nope",
        ref="main",
        cursor_plugins_dir=tmp_path / "cursor",
        claude_skills_dir=tmp_path / "claude",
        codex_skills_dir=tmp_path / "codex",
    )
    assert installed == {}
    assert warnings
    assert any("pstack" in w.lower() and "fail" in w.lower() for w in warnings)


def test_uninstall_pstack(tmp_path: Path) -> None:
    repo = _fake_plugins_repo(tmp_path)
    cursor = tmp_path / "cursor-plugins-local"
    claude = tmp_path / "claude-skills"
    codex = tmp_path / "codex-skills"
    (claude / "using-forge").mkdir(parents=True)
    (claude / "using-forge" / "SKILL.md").write_text("keep\n", encoding="utf-8")
    install_pstack_from_tree(
        repo,
        cursor_plugins_dir=cursor,
        claude_skills_dir=claude,
        codex_skills_dir=codex,
    )
    removed, missing = uninstall_pstack(
        cursor_plugins_dir=cursor,
        claude_skills_dir=claude,
        codex_skills_dir=codex,
    )
    assert missing == []
    assert not (cursor / "pstack").exists()
    assert not (codex / "pstack").exists()
    assert not (claude / "bro").exists()
    assert (claude / "using-forge" / "SKILL.md").is_file()
    assert "cursor_pstack" in removed


def test_allowlist_does_not_include_skip() -> None:
    assert PSTACK_SKILL_SKIP.isdisjoint(PSTACK_SKILL_ALLOWLIST)
    assert "bro" in PSTACK_SKILL_ALLOWLIST
    assert "interrogate" in PSTACK_SKILL_ALLOWLIST


def test_install_parser_pstack_flags() -> None:
    from forge_next.cli import build_parser

    parser = build_parser()
    default = parser.parse_args(["install"])
    assert default.skip_pstack is False
    assert default.pstack_repo_url == "https://github.com/cursor/plugins"
    assert default.pstack_ref == "main"
    skipped = parser.parse_args(["install", "--skip-pstack"])
    assert skipped.skip_pstack is True
    custom = parser.parse_args(
        [
            "install",
            "--pstack-repo-url",
            "https://example.invalid/plugins",
            "--pstack-ref",
            "dev",
        ]
    )
    assert custom.pstack_repo_url == "https://example.invalid/plugins"
    assert custom.pstack_ref == "dev"
