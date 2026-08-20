"""pstack companion docs stay credited, allowlisted, and free of skipped skills."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

ABSENT_TOKENS = ("automate-me", "setup-pstack", "poteto-mode")

SKILL_COMPANION_TOKENS: list[tuple[Path, tuple[str, ...]]] = [
    (REPO_ROOT / "skills" / "code-review" / "SKILL.md", ("/interrogate",)),
    (REPO_ROOT / "skills" / "design" / "SKILL.md", ("/arena",)),
    (
        REPO_ROOT / "skills" / "diagnose" / "SKILL.md",
        ("/how", "/why", "/teach", "/blast-radius", "/tdd"),
    ),
    (REPO_ROOT / "skills" / "sketch" / "SKILL.md", ("/how", "/why")),
    (
        REPO_ROOT / "skills" / "evaluate" / "SKILL.md",
        ("/eval", "not a substitute for Forge evaluate"),
    ),
    (REPO_ROOT / "skills" / "takeover" / "SKILL.md", ("/recall",)),
    (
        REPO_ROOT / "skills" / "implement" / "SKILL.md",
        ("/swarm", "/tdd", "/typescript-best-practices", "/unslop"),
    ),
    (
        REPO_ROOT / "skills" / "plan" / "SKILL.md",
        ("/figure-it-out", "/show-me-your-work", "/technical-writing"),
    ),
    (REPO_ROOT / "skills" / "test" / "SKILL.md", ("/create-verification-skill",)),
    (REPO_ROOT / "skills" / "ux-review" / "SKILL.md", ("visual-parity",)),
    (
        REPO_ROOT / ".cursor" / "skills" / "ship" / "SKILL.md",
        ("/unslop", "/technical-writing"),
    ),
]

CONTRACT_PHRASES = (
    "Forge evaluate",
    "/eval",
    "/unslop",
    "/bro",
    "/typescript-best-practices",
    "Forge ship wins",
    "fail-soft",
    "github.com/cursor/plugins/tree/main/pstack/skills",
)


def _readme_pstack_section(text: str) -> str:
    marker = "### pstack"
    start = text.find(marker)
    assert start != -1, "README.md missing ### pstack heading"
    rest = text[start:]
    nxt = rest.find("\n### ", 1)
    if nxt == -1:
        nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def test_pstack_contract_exists_and_phrases() -> None:
    path = REPO_ROOT / "templates" / "pstack-contract.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    missing = [p for p in CONTRACT_PHRASES if p not in text]
    assert not missing, f"contract missing phrases: {missing}"
    assert "does not copy" in text or "does not vendor" in text
    packaged = REPO_ROOT / "forge_next" / "assets" / "templates" / "pstack-contract.md"
    assert packaged.is_file(), "Run scripts/release/sync_template_assets.py"
    assert packaged.read_text(encoding="utf-8") == text


def test_preamble_has_pstack_heading() -> None:
    path = REPO_ROOT / "templates" / "workflow-skill-preamble.md"
    text = path.read_text(encoding="utf-8")
    assert "## pstack" in text
    assert "pstack-contract.md" in text
    packaged = REPO_ROOT / "forge_next" / "assets" / "templates" / "workflow-skill-preamble.md"
    assert packaged.read_text(encoding="utf-8") == text


def test_using_forge_bro_and_forge_wins() -> None:
    text = (
        REPO_ROOT / "integrations" / "claude" / "skills" / "using-forge" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "/bro" in text
    assert "named forge skills always win" in text.lower()


def test_docs_and_index_pointers() -> None:
    docs = (REPO_ROOT / "docs" / "pstack.md").read_text(encoding="utf-8")
    assert "templates/pstack-contract.md" in docs
    assert "github.com/cursor/plugins/tree/main/pstack/skills" in docs
    assert "using-forge" in docs
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    section = _readme_pstack_section(readme)
    assert "docs/pstack.md" in section
    assert "github.com/cursor/plugins" in section
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## pstack" in agents
    integ = (REPO_ROOT / "integrations" / "README.md").read_text(encoding="utf-8")
    assert "### pstack" in integ
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "pstack.md" in docs_index
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'^version = "\d+\.\d+\.\d+"', pyproject, re.M)
    env = (REPO_ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
    assert "FORGE_SKIP_PSTACK" in env


def test_absent_tokens_not_in_forge_docs() -> None:
    paths = [
        REPO_ROOT / "templates" / "pstack-contract.md",
        REPO_ROOT / "docs" / "pstack.md",
        REPO_ROOT / "templates" / "workflow-skill-preamble.md",
        REPO_ROOT / "integrations" / "claude" / "skills" / "using-forge" / "SKILL.md",
    ]
    readme_section = _readme_pstack_section(
        (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    )
    blobs = [p.read_text(encoding="utf-8") for p in paths] + [readme_section]
    for token in ABSENT_TOKENS:
        for blob in blobs:
            assert token not in blob, f"forbidden token {token!r} leaked into Forge pstack docs"


@pytest.mark.parametrize(
    "path,tokens",
    SKILL_COMPANION_TOKENS,
    ids=[p.relative_to(REPO_ROOT).as_posix() for p, _ in SKILL_COMPANION_TOKENS],
)
def test_skill_companion_tokens(path: Path, tokens: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")
    for token in tokens:
        assert token in text, f"{path.relative_to(REPO_ROOT)} missing {token!r}"
    assert "templates/pstack-contract.md" in text
    assert "If pstack is not installed, skip" in text
