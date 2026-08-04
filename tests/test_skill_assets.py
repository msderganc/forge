"""Authoring ↔ packaged skill/schema asset parity (mirrors test_prompt_assets)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def add_repo_to_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def _assert_tree_parity(src_root: Path, packaged_root: Path, pattern: str) -> None:
    if not src_root.is_dir():
        return
    drift: list[str] = []
    for path in sorted(src_root.rglob(pattern)):
        rel = path.relative_to(src_root)
        packaged = packaged_root / rel
        if not packaged.is_file():
            drift.append(f"missing in assets: {rel}")
            continue
        if path.read_bytes() != packaged.read_bytes():
            drift.append(f"content drift: {rel}")
    assert not drift, f"Skill/schema sync required under {src_root.name}:\n" + "\n".join(drift)


def test_all_repo_skill_yaml_mirrored_in_packaged_assets() -> None:
    _assert_tree_parity(
        REPO_ROOT / "skills",
        REPO_ROOT / "forge_next" / "assets" / "skills",
        "*.yaml",
    )


def test_all_repo_schema_json_mirrored_in_packaged_assets() -> None:
    _assert_tree_parity(
        REPO_ROOT / "schemas",
        REPO_ROOT / "forge_next" / "assets" / "schemas",
        "*.json",
    )


def test_sync_skill_assets_importable_and_main_returns_zero() -> None:
    mod = importlib.import_module("scripts.release.sync_skill_assets")
    assert hasattr(mod, "main")
    assert mod.main() == 0


def test_pyproject_has_pyyaml_jsonschema_and_skill_package_data() -> None:
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "PyYAML" in text or "pyyaml" in text.lower()
    assert "jsonschema" in text.lower()
    assert "assets/skills/**/*.yaml" in text
    assert "assets/schemas/**/*.json" in text
