"""Install Uncodixfy from git into Cursor/Claude/Codex skill dirs.

Canonical contract: templates/uncodixfy-contract.md. Forge does not vendor the
skill body; forge install copies it into the user's editor skill dirs.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from forge_next.cli_install_io import (
    default_claude_skills_dir,
    default_codex_skills_dir,
    default_cursor_local_plugins_dir,
    download_repo_zip,
    extract_zip,
    repo_top_from_extract,
)

SKILL_NAME = "uncodixfy"
UNCODIXFY_REPO_URL_DEFAULT = "https://github.com/cyxzdev/Uncodixfy"
UNCODIXFY_REF_DEFAULT = "main"
_PLUGIN_JSON = {
    "name": "uncodixfy",
    "description": (
        "Prevent generic AI UI patterns when generating frontend "
        "(https://github.com/cyxzdev/Uncodixfy)."
    ),
    "components": {"skills": {"include": ["skills/**/SKILL.md"]}},
}
_SKIP_COPY_NAMES = frozenset({".git", "images", ".github"})


def skip_uncodixfy_env() -> bool:
    return os.environ.get("FORGE_SKIP_UNCODIXFY", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _copy_skill_payload(src_root: Path, dst: Path) -> None:
    """Copy skill files from an extracted Uncodixfy repo into dst."""
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for item in sorted(src_root.iterdir()):
        if item.name in _SKIP_COPY_NAMES:
            continue
        if item.is_file():
            shutil.copy2(item, dst / item.name)
        elif item.is_dir():
            shutil.copytree(item, dst / item.name)


def install_uncodixfy_from_tree(
    repo_root: Path,
    *,
    cursor_plugins_dir: Path,
    claude_skills_dir: Path,
    codex_skills_dir: Path,
) -> tuple[dict[str, str], list[str]]:
    """Copy Uncodixfy SKILL.md from an extracted git tree into host dirs."""
    warnings: list[str] = []
    installed: dict[str, str] = {}
    skill_md = repo_root / "SKILL.md"
    if not skill_md.is_file():
        warnings.append("Uncodixfy SKILL.md not found in downloaded tree.")
        return installed, warnings

    cursor_plugin = cursor_plugins_dir / SKILL_NAME
    cursor_skill = cursor_plugin / "skills" / SKILL_NAME
    _copy_skill_payload(repo_root, cursor_skill)
    plugin_meta = cursor_plugin / ".cursor-plugin"
    plugin_meta.mkdir(parents=True, exist_ok=True)
    (plugin_meta / "plugin.json").write_text(
        json.dumps(_PLUGIN_JSON, indent=2) + "\n", encoding="utf-8"
    )
    for name in ("LICENSE", "README.md"):
        src = repo_root / name
        if src.is_file():
            shutil.copy2(src, cursor_plugin / name)

    claude_dst = claude_skills_dir / SKILL_NAME
    _copy_skill_payload(repo_root, claude_dst)
    codex_dst = codex_skills_dir / SKILL_NAME
    _copy_skill_payload(repo_root, codex_dst)

    installed["cursor_uncodixfy"] = str(cursor_plugin)
    installed["claude_uncodixfy"] = str(claude_dst)
    installed["codex_uncodixfy"] = str(codex_dst)
    return installed, warnings


def run_uncodixfy_install(
    *,
    skip: bool,
    repo_url: str,
    ref: str,
    cursor_plugins_dir: Path | None = None,
    claude_skills_dir: Path | None = None,
    codex_skills_dir: Path | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Download Uncodixfy and install the skill. Fail-soft."""
    if skip or skip_uncodixfy_env():
        reason = "--skip-uncodixfy" if skip else "FORGE_SKIP_UNCODIXFY=1"
        return {}, [f"Uncodixfy skill install skipped ({reason})."]

    cursor_plugins_dir = cursor_plugins_dir or default_cursor_local_plugins_dir()
    claude_skills_dir = claude_skills_dir or default_claude_skills_dir()
    codex_skills_dir = codex_skills_dir or default_codex_skills_dir()

    try:
        with tempfile.TemporaryDirectory(prefix="forge-uncodixfy-") as td:
            td_path = Path(td)
            zip_path = td_path / "repo.zip"
            extract_dir = td_path / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            download_repo_zip(repo_url, ref, zip_path)
            extract_zip(zip_path, extract_dir)
            top = repo_top_from_extract(extract_dir)
            return install_uncodixfy_from_tree(
                top,
                cursor_plugins_dir=cursor_plugins_dir,
                claude_skills_dir=claude_skills_dir,
                codex_skills_dir=codex_skills_dir,
            )
    except SystemExit as e:
        return {}, [f"Uncodixfy download failed (Forge install continues): {e}"]
    except Exception as e:
        return {}, [f"Uncodixfy download failed (Forge install continues): {e}"]


def uninstall_uncodixfy(
    *,
    cursor_plugins_dir: Path | None = None,
    claude_skills_dir: Path | None = None,
    codex_skills_dir: Path | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Remove Forge-installed Uncodixfy dests; leave using-forge / forge-* alone."""
    cursor_plugins_dir = cursor_plugins_dir or default_cursor_local_plugins_dir()
    claude_skills_dir = claude_skills_dir or default_claude_skills_dir()
    codex_skills_dir = codex_skills_dir or default_codex_skills_dir()
    removed: dict[str, str] = {}
    missing: list[str] = []

    def _rm(path: Path, key: str) -> None:
        if path.exists():
            shutil.rmtree(path)
            removed[key] = str(path)
        else:
            missing.append(str(path))

    _rm(cursor_plugins_dir / SKILL_NAME, "cursor_uncodixfy")
    _rm(claude_skills_dir / SKILL_NAME, "claude_uncodixfy")
    _rm(codex_skills_dir / SKILL_NAME, "codex_uncodixfy")
    return removed, missing
