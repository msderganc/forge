"""Install allowlisted pstack skills from the cursor/plugins git tree.

Canonical allowlist: templates/pstack-contract.md. Forge does not vendor these
bodies into the forge-next source tree; forge install copies them into the
user's editor skill dirs.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from forge_next.cli_install_io import (
    copytree_replace,
    default_claude_skills_dir,
    default_codex_skills_dir,
    default_cursor_local_plugins_dir,
    download_repo_zip,
    extract_zip,
    repo_top_from_extract,
)

# Keep in sync with templates/pstack-contract.md attach map.
PSTACK_SKILL_ALLOWLIST: frozenset[str] = frozenset(
    {
        "arena",
        "blast-radius",
        "bro",
        "create-verification-skill",
        "figure-it-out",
        "how",
        "interrogate",
        "recall",
        "reflect",
        "show-me-your-work",
        "swarm",
        "tdd",
        "teach",
        "technical-writing",
        "typescript-best-practices",
        "unslop",
        "why",
    }
)
PSTACK_SKILL_SKIP: frozenset[str] = frozenset(
    {"automate-me", "setup-pstack", "poteto-mode"}
)
PSTACK_REPO_URL_DEFAULT = "https://github.com/cursor/plugins"
PSTACK_REF_DEFAULT = "main"


def skip_pstack_env() -> bool:
    return os.environ.get("FORGE_SKIP_PSTACK", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _copy_skill_dir(src: Path, dst: Path) -> None:
    copytree_replace(src, dst)


def install_pstack_from_tree(
    plugins_repo_root: Path,
    *,
    cursor_plugins_dir: Path,
    claude_skills_dir: Path,
    codex_skills_dir: Path,
) -> tuple[dict[str, str], list[str]]:
    """Copy allowlisted pstack/skills from an extracted cursor/plugins tree."""
    warnings: list[str] = []
    installed: dict[str, str] = {}
    pstack = plugins_repo_root / "pstack"
    skills_src = pstack / "skills"
    if not skills_src.is_dir():
        warnings.append("pstack/skills not found in downloaded cursor/plugins tree.")
        return installed, warnings

    cursor_dst = cursor_plugins_dir / "pstack"
    cursor_skills = cursor_dst / "skills"
    if cursor_dst.exists():
        shutil.rmtree(cursor_dst)
    cursor_skills.mkdir(parents=True, exist_ok=True)

    plugin_json = pstack / ".cursor-plugin" / "plugin.json"
    if plugin_json.is_file():
        plugin_dst = cursor_dst / ".cursor-plugin"
        plugin_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin_json, plugin_dst / "plugin.json")
    for name in ("LICENSE", "README.md"):
        src = pstack / name
        if src.is_file():
            shutil.copy2(src, cursor_dst / name)

    copied: list[str] = []
    missing: list[str] = []
    for name in sorted(PSTACK_SKILL_ALLOWLIST):
        if name in PSTACK_SKILL_SKIP:
            continue
        src = skills_src / name
        if not (src.is_dir() and (src / "SKILL.md").is_file()):
            missing.append(name)
            continue
        _copy_skill_dir(src, cursor_skills / name)
        _copy_skill_dir(src, claude_skills_dir / name)
        _copy_skill_dir(src, codex_skills_dir / "pstack" / name)
        copied.append(name)

    if missing:
        warnings.append(
            "pstack allowlist names missing upstream (skipped): " + ", ".join(missing)
        )
    if not copied:
        warnings.append("No pstack skills were copied (empty allowlist match).")
        return installed, warnings

    installed["cursor_pstack"] = str(cursor_dst)
    installed["claude_pstack"] = str(claude_skills_dir)
    installed["codex_pstack"] = str(codex_skills_dir / "pstack")
    return installed, warnings


def run_pstack_install(
    *,
    skip: bool,
    repo_url: str,
    ref: str,
    cursor_plugins_dir: Path | None = None,
    claude_skills_dir: Path | None = None,
    codex_skills_dir: Path | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Download cursor/plugins and install allowlisted pstack skills. Fail-soft."""
    if skip or skip_pstack_env():
        reason = "--skip-pstack" if skip else "FORGE_SKIP_PSTACK=1"
        return {}, [f"pstack skills install skipped ({reason})."]

    cursor_plugins_dir = cursor_plugins_dir or default_cursor_local_plugins_dir()
    claude_skills_dir = claude_skills_dir or default_claude_skills_dir()
    codex_skills_dir = codex_skills_dir or default_codex_skills_dir()

    try:
        with tempfile.TemporaryDirectory(prefix="forge-pstack-") as td:
            td_path = Path(td)
            zip_path = td_path / "repo.zip"
            extract_dir = td_path / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            download_repo_zip(repo_url, ref, zip_path)
            extract_zip(zip_path, extract_dir)
            top = repo_top_from_extract(extract_dir)
            return install_pstack_from_tree(
                top,
                cursor_plugins_dir=cursor_plugins_dir,
                claude_skills_dir=claude_skills_dir,
                codex_skills_dir=codex_skills_dir,
            )
    except SystemExit as e:
        return {}, [f"pstack download failed (Forge install continues): {e}"]
    except Exception as e:
        return {}, [f"pstack download failed (Forge install continues): {e}"]


def uninstall_pstack(
    *,
    cursor_plugins_dir: Path | None = None,
    claude_skills_dir: Path | None = None,
    codex_skills_dir: Path | None = None,
) -> tuple[dict[str, str], list[str]]:
    """Remove Forge-installed pstack dests; leave using-forge / forge-* alone."""
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

    _rm(cursor_plugins_dir / "pstack", "cursor_pstack")
    _rm(codex_skills_dir / "pstack", "codex_pstack")
    claude_hit = False
    for name in sorted(PSTACK_SKILL_ALLOWLIST):
        path = claude_skills_dir / name
        if path.is_dir():
            shutil.rmtree(path)
            removed[f"claude_pstack:{name}"] = str(path)
            claude_hit = True
    if claude_hit:
        removed["claude_pstack"] = str(claude_skills_dir)
    return removed, missing
