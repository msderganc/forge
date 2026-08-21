"""Integration layout: Cursor/Claude commands and Codex skills match install expectations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _split_yaml_frontmatter(text: str) -> tuple[str | None, str]:
    """Return (frontmatter_block, body) for markdown with --- delimiters, or (None, full text)."""
    normalized = text.replace("\r\n", "\n").lstrip("\ufeff")
    if not normalized.startswith("---\n"):
        return None, text
    parts = normalized.split("---", 2)
    if len(parts) < 3:
        return None, text
    return parts[1].strip(), parts[2]


def _frontmatter_has_keys(fm: str, *keys: str) -> bool:
    return all(f"{k}:" in fm for k in keys)


@pytest.fixture(scope="module")
def spec_commands() -> dict:
    path = REPO_ROOT / "integrations" / "spec" / "commands.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_spec_commands_include_ship(spec_commands: dict):
    ids = [c["id"] for c in spec_commands["commands"]]
    assert "forge:ship" in ids
    assert len(spec_commands["commands"]) == 14


def test_spec_cli_package_is_forge_next(spec_commands: dict):
    assert spec_commands["cli"]["package"] == "forge-next"


def test_spec_commands_have_matching_codex_skill_dirs(spec_commands: dict):
    missing: list[str] = []
    for cmd in spec_commands["commands"]:
        sub = cmd["cli_subcommand"]
        skill_md = (
            REPO_ROOT / "integrations" / "codex" / "skills" / f"forge-{sub}" / "SKILL.md"
        )
        if not skill_md.is_file():
            missing.append(str(skill_md.relative_to(REPO_ROOT)))
    assert not missing, f"Missing Codex SKILL.md for spec command: {missing}"


def test_spec_commands_have_matching_cursor_and_claude_files(spec_commands: dict):
    missing_cursor: list[str] = []
    missing_claude: list[str] = []
    for cmd in spec_commands["commands"]:
        sub = cmd["cli_subcommand"]
        name = f"{sub}.md"
        cpath = REPO_ROOT / "integrations" / "cursor-plugin" / "commands" / name
        lpath = REPO_ROOT / "integrations" / "claude" / "commands" / name
        if not cpath.is_file():
            missing_cursor.append(str(cpath.relative_to(REPO_ROOT)))
        if not lpath.is_file():
            missing_claude.append(str(lpath.relative_to(REPO_ROOT)))
    assert not missing_cursor, f"Missing Cursor command files: {missing_cursor}"
    assert not missing_claude, f"Missing Claude command files: {missing_claude}"


@pytest.mark.parametrize(
    "cmd_dir",
    [
        REPO_ROOT / "integrations" / "cursor-plugin" / "commands",
        REPO_ROOT / "integrations" / "claude" / "commands",
    ],
)
def test_slash_command_markdown_files_have_valid_frontmatter(cmd_dir: Path):
    for path in sorted(cmd_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        fm, body = _split_yaml_frontmatter(text)
        assert fm is not None, f"{path.relative_to(REPO_ROOT)} must start with --- YAML frontmatter"
        assert _frontmatter_has_keys(fm, "description"), f"{path} frontmatter needs description:"
        assert body.strip(), f"{path} must have non-empty markdown body after frontmatter"


def test_generate_integrations_check_passes():
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "generate_integrations.py"), "--check"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_workflow_skill_preamble_exists():
    path = REPO_ROOT / "templates" / "workflow-skill-preamble.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "## Simplicity (YAGNI)" in text
    assert "One-liners where readable" in text
    assert "5–10 min" in text
    assert "Honor ceremony as a duration hint" in text
    packaged = REPO_ROOT / "forge_next" / "assets" / "templates" / "workflow-skill-preamble.md"
    assert packaged.is_file(), "Run scripts/release/sync_template_assets.py"
    assert packaged.read_text(encoding="utf-8") == text


def test_codex_skills_use_skill_md_layout():
    skills_root = REPO_ROOT / "integrations" / "codex" / "skills"
    dirs = [p for p in skills_root.iterdir() if p.is_dir()]
    assert dirs, "Expected at least one Codex skill directory"
    for d in dirs:
        skill = d / "SKILL.md"
        assert skill.is_file(), f"Missing {skill.relative_to(REPO_ROOT)}"
        text = skill.read_text(encoding="utf-8")
        fm, body = _split_yaml_frontmatter(text)
        assert fm is not None, f"{skill.relative_to(REPO_ROOT)} must use --- frontmatter"
        assert _frontmatter_has_keys(fm, "name", "description"), (
            f"{skill.relative_to(REPO_ROOT)} frontmatter needs name: and description:"
        )
        assert body.strip(), f"{skill.relative_to(REPO_ROOT)} needs a non-empty body"


def test_claude_skills_use_skill_md_layout(spec_commands: dict):
    skills_root = REPO_ROOT / "integrations" / "claude" / "skills"
    assert (skills_root / "using-forge" / "SKILL.md").is_file()
    for cmd in spec_commands["commands"]:
        sub = cmd["cli_subcommand"]
        skill = skills_root / f"forge-{sub}" / "SKILL.md"
        assert skill.is_file(), f"Missing Claude skill {skill.relative_to(REPO_ROOT)}"
        text = skill.read_text(encoding="utf-8")
        fm, body = _split_yaml_frontmatter(text)
        assert fm is not None, f"{skill.relative_to(REPO_ROOT)} must use --- frontmatter"
        assert f"name: forge-{sub}" in fm
        assert "description:" in fm
        assert "Use when" in fm
        assert body.strip()

