"""forge install / uninstall — download integrations and optional onboarding."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from forge_next.cli_install_claude import (
    apply_claude_graphify_hooks,
    install_claude_commands,
    install_claude_skills,
    list_claude_skill_names,
    uninstall_claude_skills,
)
from forge_next.cli_install_codex import apply_codex_agents_config, install_codex_skills
from forge_next.cli_install_cursor import install_cursor_plugin
from forge_next.cli_install_io import (
    default_claude_commands_dir,
    default_claude_skills_dir,
    default_codex_skills_dir,
    default_cursor_local_plugins_dir,
    with_downloaded_repo,
)
from forge_next.cli_install_pstack import run_pstack_install, uninstall_pstack
from forge_next.cli_install_report import (
    build_install_payload,
    emit_install_result,
    run_structural_install,
)


def _normalize_install_flags(
    install_cursor: bool,
    install_claude: bool,
    install_codex: bool,
    install_all: bool,
) -> tuple[bool, bool, bool]:
    if not (install_cursor or install_claude or install_codex or install_all):
        install_all = True
    if install_all:
        return True, True, True
    return install_cursor, install_claude, install_codex


def _install_integrations_from_repo(
    repo_root: Path,
    *,
    install_cursor: bool,
    install_claude: bool,
    install_codex: bool,
    cursor_dir: str | None,
    claude_dir: str | None,
    codex_dir: str | None,
) -> tuple[dict[str, str], list[str]]:
    installed: dict[str, str] = {}
    warnings: list[str] = []

    if install_cursor:
        path, w = install_cursor_plugin(repo_root, cursor_dir=cursor_dir)
        warnings.extend(w)
        if path:
            installed["cursor_plugin"] = path

    if install_claude:
        path, w = install_claude_commands(repo_root, claude_dir=claude_dir)
        warnings.extend(w)
        if path:
            installed["claude_commands"] = path
        path, w = install_claude_skills(repo_root)
        warnings.extend(w)
        if path:
            installed["claude_skills"] = path

    if install_codex:
        path, w = install_codex_skills(repo_root, codex_dir=codex_dir)
        warnings.extend(w)
        if path:
            installed["codex_skills"] = path

    return installed, warnings


def run_install(
    *,
    json_output: bool,
    repo_url: str,
    ref: str,
    install_cursor: bool,
    install_claude: bool,
    install_codex: bool,
    install_all: bool,
    skip_structural_tools: bool,
    skip_pstack: bool,
    pstack_repo_url: str,
    pstack_ref: str,
    cursor_dir: str | None,
    claude_dir: str | None,
    codex_dir: str | None,
) -> None:
    install_cursor, install_claude, install_codex = _normalize_install_flags(
        install_cursor, install_claude, install_codex, install_all
    )

    def from_repo(repo_root: Path) -> tuple[dict[str, str], list[str]]:
        return _install_integrations_from_repo(
            repo_root,
            install_cursor=install_cursor,
            install_claude=install_claude,
            install_codex=install_codex,
            cursor_dir=cursor_dir,
            claude_dir=claude_dir,
            codex_dir=codex_dir,
        )

    installed, warnings = with_downloaded_repo(repo_url, ref, from_repo)

    if install_claude:
        path, w = apply_claude_graphify_hooks()
        warnings.extend(w)
        if path:
            installed["claude_graphify_hooks"] = path

    if install_codex:
        path, w = apply_codex_agents_config()
        warnings.extend(w)
        if path:
            installed["codex_developer_instructions"] = path

    structural_result, structural_skipped, struct_warnings = run_structural_install(
        skip_structural_tools=skip_structural_tools,
    )
    warnings.extend(struct_warnings)

    pstack_cursor = Path(cursor_dir).expanduser() if cursor_dir else None
    pstack_codex = Path(codex_dir).expanduser() if codex_dir else None
    pstack_installed, pstack_warnings = run_pstack_install(
        skip=skip_pstack,
        repo_url=pstack_repo_url,
        ref=pstack_ref,
        cursor_plugins_dir=pstack_cursor,
        claude_skills_dir=None,
        codex_skills_dir=pstack_codex,
    )
    installed.update(pstack_installed)
    warnings.extend(pstack_warnings)
    pstack_skipped = skip_pstack or not pstack_installed

    payload = build_install_payload(
        repo_url=repo_url,
        ref=ref,
        installed=installed,
        warnings=warnings,
        structural_result=structural_result,
        pstack_skipped=pstack_skipped,
    )
    emit_install_result(
        payload,
        json_output=json_output,
        install_claude=install_claude,
        install_codex=install_codex,
        structural_result=structural_result,
        structural_skipped=structural_skipped,
        pstack_skipped=pstack_skipped,
    )


def run_uninstall(
    *,
    json_output: bool,
    uninstall_cursor: bool,
    uninstall_claude: bool,
    uninstall_codex: bool,
    uninstall_all: bool,
    cursor_dir: str | None,
    claude_dir: str | None,
    codex_dir: str | None,
) -> None:
    if not (uninstall_cursor or uninstall_claude or uninstall_codex or uninstall_all):
        uninstall_all = True
    if uninstall_all:
        uninstall_cursor = uninstall_claude = uninstall_codex = True

    removed: dict[str, str] = {}
    missing: list[str] = []
    warnings: list[str] = []

    def rm_tree(path: Path, key: str) -> None:
        if path.exists():
            try:
                shutil.rmtree(path)
                removed[key] = str(path)
            except Exception as e:
                warnings.append(f"Failed to remove {path}: {e}")
        else:
            missing.append(str(path))

    if uninstall_cursor:
        base = (
            Path(cursor_dir).expanduser()
            if cursor_dir
            else default_cursor_local_plugins_dir()
        )
        rm_tree(base / "forge", "cursor_plugin")

    if uninstall_claude:
        base = (
            Path(claude_dir).expanduser()
            if claude_dir
            else default_claude_commands_dir()
        )
        rm_tree(base / "forge", "claude_commands")
        # Prefer skill names from the live checkout when available; fall back to
        # whatever forge-* / using-forge dirs exist under ~/.claude/skills.
        repo_guess = Path(__file__).resolve().parent.parent
        skill_names = list_claude_skill_names(repo_guess)
        if not skill_names:
            skills_base = default_claude_skills_dir()
            if skills_base.is_dir():
                skill_names = [
                    p.name
                    for p in skills_base.iterdir()
                    if p.is_dir()
                    and (p.name == "using-forge" or p.name.startswith("forge-"))
                ]
        skill_removed, skill_missing = uninstall_claude_skills(skill_names=skill_names)
        removed.update(skill_removed)
        missing.extend(skill_missing)

    if uninstall_codex:
        base = (
            Path(codex_dir).expanduser()
            if codex_dir
            else default_codex_skills_dir()
        )
        rm_tree(base / "forge", "codex_skills")

    pstack_removed, pstack_missing = uninstall_pstack(
        cursor_plugins_dir=(
            Path(cursor_dir).expanduser() if cursor_dir else None
        ),
        claude_skills_dir=None,
        codex_skills_dir=(Path(codex_dir).expanduser() if codex_dir else None),
    )
    removed.update(pstack_removed)
    missing.extend(pstack_missing)

    payload = {
        "command": "uninstall",
        "removed": removed,
        "missing": missing,
        "warnings": warnings,
        "error": None,
    }

    if json_output:
        print(json.dumps(payload, ensure_ascii=True))
        return

    title = (
        "forge - uninstall"
        if os.environ.get("FORGE_ASCII") == "1"
        else "forge — uninstall"
    )
    print(title)
    print("=" * 60)
    for k, v in removed.items():
        print(f"{k}: removed {v}")
    if missing:
        print("")
        print("Not found (already absent):")
        for p in missing:
            print(f"- {p}")
    if warnings:
        print("")
        print("Warnings:")
        for w in warnings:
            print(f"- {w}")
