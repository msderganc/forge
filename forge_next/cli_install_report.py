"""Human and JSON output for forge install."""

from __future__ import annotations

import json
import os
from typing import Any

from forge_next.beads import (
    beads_availability,
    beads_install_notice_lines,
)
from forge_next.graphify import graphify_availability, graphify_install_notice_lines
from forge_next.structural_tools import (
    install_structural_tools as run_structural_tools_install,
    skip_structural_tools as env_skip_structural_tools,
    structural_tools_install_notice_lines,
    structural_tools_missing_warnings,
)


def run_structural_install(
    *,
    skip_structural_tools: bool,
) -> tuple[Any | None, bool, list[str]]:
    """Return (structural_result, skipped, extra_warnings)."""
    warnings: list[str] = []
    structural_skipped = skip_structural_tools or env_skip_structural_tools()
    structural_result = None
    if not structural_skipped:
        structural_result = run_structural_tools_install()
        if structural_result.warnings:
            warnings.extend(structural_result.warnings)
    elif skip_structural_tools:
        warnings.append(
            "Structural quality tools install skipped (--skip-structural-tools)."
        )
    warnings.extend(structural_tools_missing_warnings())
    return structural_result, structural_skipped, warnings


def build_install_payload(
    *,
    repo_url: str,
    ref: str,
    installed: dict[str, str],
    warnings: list[str],
    structural_result: Any | None,
    pstack_skipped: bool = False,
) -> dict[str, Any]:
    graphify_available, graphify_status = graphify_availability()
    beads_available, beads_status, beads_details = beads_availability()
    return {
        "command": "install",
        "repo_url": repo_url,
        "ref": ref,
        "installed": installed,
        "warnings": warnings,
        "graphify_available": graphify_available,
        "graphify_status": graphify_status,
        "graphify_onboarding": graphify_install_notice_lines(),
        "beads_available": beads_available,
        "beads_status": beads_status,
        "beads": beads_details,
        "beads_onboarding": beads_install_notice_lines(),
        "structural_tools": structural_result.to_dict() if structural_result else None,
        "structural_tools_onboarding": structural_tools_install_notice_lines(
            structural_result
        ),
        "pstack_skipped": pstack_skipped,
        "pstack": {"skipped": pstack_skipped},
        "error": None,
    }


def _ascii_mode() -> bool:
    return os.environ.get("FORGE_ASCII") == "1"


def _section(emoji: str, label: str) -> str:
    """Section header; emoji dropped when ``FORGE_ASCII=1`` / ``--ascii``."""
    if _ascii_mode():
        return label
    return f"{emoji} {label}"


def print_install_human(
    *,
    installed: dict[str, str],
    warnings: list[str],
    structural_result: Any | None,
    structural_skipped: bool,
    install_claude: bool,
    install_codex: bool,
    pstack_skipped: bool = False,
) -> None:
    title = (
        "forge - install" if _ascii_mode() else "forge — install"
    )
    print(_section("📦", title))
    print("=" * 60)
    print("")
    print(_section("✅", "Installed"))
    for k, v in installed.items():
        print(f"  {k}: {v}")
    if warnings:
        print("")
        print(_section("⚠️", "Warnings"))
        for w in warnings:
            print(f"  - {w}")
    for line in graphify_install_notice_lines():
        print(line.rstrip())
    for line in beads_install_notice_lines():
        print(line.rstrip())
    for line in structural_tools_install_notice_lines(structural_result):
        print(line.rstrip())
    print("")
    print(_section("➡️", "Next steps"))
    print("  - Restart your editor/agent environment(s) so new commands are picked up.")
    print("  - Run: forge doctor")
    if install_claude:
        print(
            "  - Claude: slash commands under ~/.claude/commands/forge/; "
            "skills (using-forge + forge-*) under ~/.claude/skills/ — restart Claude Code"
        )
        print(
            "  - Claude: Graphify hooks merged into ~/.claude/settings.json "
            "(re-run: forge claude-graphify)"
        )
    if install_codex:
        print(
            "  - Codex: run `forge codex-agents --force` if developer_instructions "
            "were not updated"
        )
    if structural_skipped:
        print(
            "  - Structural tools were skipped; re-run `forge install` without "
            "--skip-structural-tools or use `forge structural-tools install`"
        )
    if pstack_skipped:
        print(
            "  - pstack skills were skipped or failed; re-run `forge install` "
            "without --skip-pstack (see docs/pstack.md)"
        )
    beads_ok, _, _ = beads_availability()
    if not beads_ok:
        print(
            "  - Optional: install Beads (`bd`) for issue tracking — "
            "https://github.com/steveyegge/beads"
        )


def _path_onboarding_warnings() -> list[str]:
    """Warn when PATH hides the pipx ``forge`` binary after install."""
    try:
        from forge_next.claude_graphify import _pipx_bin_dir, path_shadows_pipx_forge

        shadowed, which_path, pipx_path = path_shadows_pipx_forge()
        if not shadowed or which_path is None or pipx_path is None:
            return []
        bin_dir = _pipx_bin_dir()
        return [
            f"`forge` on PATH is {which_path}, but pipx installs to {pipx_path}. "
            f"Run `pipx ensurepath --prepend` so {bin_dir} comes first, then open a "
            "new shell (or uninstall the shadowed `pip install --user` copy)."
        ]
    except Exception:
        return []


def emit_install_result(
    payload: dict[str, Any],
    *,
    json_output: bool,
    install_claude: bool,
    install_codex: bool,
    structural_result: Any | None,
    structural_skipped: bool,
    pstack_skipped: bool = False,
) -> None:
    path_warns = _path_onboarding_warnings()
    if path_warns:
        payload["warnings"] = list(payload.get("warnings") or []) + path_warns
        payload["path_onboarding"] = path_warns
    if json_output:
        print(json.dumps(payload, ensure_ascii=True))
        return
    print_install_human(
        installed=payload["installed"],
        warnings=payload["warnings"],
        structural_result=structural_result,
        structural_skipped=structural_skipped,
        install_claude=install_claude,
        install_codex=install_codex,
        pstack_skipped=pstack_skipped,
    )
