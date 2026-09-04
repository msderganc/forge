"""Uncodixfy companion docs stay credited and fail-soft."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CONTRACT_PHRASES = (
    "github.com/cyxzdev/Uncodixfy",
    "/uncodixfy",
    "does not vendor",
    "If Uncodixfy is not installed, skip",
    "Named Forge skills always win",
    "--skip-uncodixfy",
    "FORGE_SKIP_UNCODIXFY",
)

GALLERY_URLS = (
    "https://www.awwwards.com/",
    "https://godly.design/",
    "https://ui.shadcn.com/blocks",
    "https://mobbin.com/",
    "https://www.navbar.gallery/",
)


def test_uncodixfy_contract_exists_and_phrases() -> None:
    path = REPO_ROOT / "templates" / "uncodixfy-contract.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    missing = [p for p in CONTRACT_PHRASES if p not in text]
    assert not missing, f"contract missing phrases: {missing}"
    packaged = REPO_ROOT / "forge_next" / "assets" / "templates" / "uncodixfy-contract.md"
    assert packaged.is_file(), "Run scripts/release/sync_template_assets.py"
    assert packaged.read_text(encoding="utf-8") == text


def test_web_design_references_catalog() -> None:
    path = REPO_ROOT / "templates" / "web-design-references.md"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    missing = [u for u in GALLERY_URLS if u not in text]
    assert not missing, f"gallery missing urls: {missing}"
    assert "uncodixfy-contract.md" in text
    packaged = (
        REPO_ROOT / "forge_next" / "assets" / "templates" / "web-design-references.md"
    )
    assert packaged.is_file(), "Run scripts/release/sync_template_assets.py"
    assert packaged.read_text(encoding="utf-8") == text


def test_docs_and_index_pointers() -> None:
    docs = (REPO_ROOT / "docs" / "uncodixfy.md").read_text(encoding="utf-8")
    assert "templates/uncodixfy-contract.md" in docs
    assert "github.com/cyxzdev/Uncodixfy" in docs
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/uncodixfy.md" in readme
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "## Uncodixfy" in agents
    integ = (REPO_ROOT / "integrations" / "README.md").read_text(encoding="utf-8")
    assert "### Uncodixfy" in integ
    docs_index = (REPO_ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "uncodixfy.md" in docs_index
    env = (REPO_ROOT / "docs" / "environment.md").read_text(encoding="utf-8")
    assert "FORGE_SKIP_UNCODIXFY" in env


def test_design_and_implement_attach() -> None:
    design = (REPO_ROOT / "skills" / "design" / "SKILL.md").read_text(encoding="utf-8")
    assert "templates/web-design-references.md" in design
    assert "templates/uncodixfy-contract.md" in design
    assert "If Uncodixfy is not installed, skip" in design
    implement = (REPO_ROOT / "skills" / "implement" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    assert "templates/uncodixfy-contract.md" in implement
    assert "If Uncodixfy is not installed, skip" in implement
    solution = (REPO_ROOT / "prompts" / "design" / "solution.md").read_text(
        encoding="utf-8"
    )
    assert "web-design-references.md" in solution
    assert "uncodixfy-contract.md" in solution
