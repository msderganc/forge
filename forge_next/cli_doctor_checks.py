"""Individual doctor checks (keeps run_doctor thin)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def collect_environment_checks() -> tuple[dict[str, object], list[str]]:
    checks: dict[str, object] = {
        "python_executable": sys.executable,
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "pythonutf8": os.environ.get("PYTHONUTF8"),
        "forge_use_launcher": os.environ.get("FORGE_USE_LAUNCHER"),
        "forge_ascii": os.environ.get("FORGE_ASCII"),
    }
    return checks, []


def check_codex_anchor(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    codex_anchor = repo_root / ".codex"
    forge_runtime = repo_root / ".forge"
    legacy_forge = codex_anchor / "forge"
    legacy_fc = codex_anchor / "forge-codex"
    checks = {
        "codex_anchor_exists": codex_anchor.exists(),
        "codex_anchor_is_dir": codex_anchor.is_dir(),
        "forge_runtime_exists": forge_runtime.is_dir(),
        "legacy_codex_forge_exists": legacy_forge.is_dir(),
        "legacy_forge_codex_exists": legacy_fc.is_dir(),
    }
    if codex_anchor.exists() and not codex_anchor.is_dir():
        warnings.append(
            "`.codex` exists but is not a directory; Forge still writes under `.forge/`."
        )
    if legacy_forge.is_dir() or legacy_fc.is_dir():
        warnings.append(
            "Legacy `.codex/forge*` runtime tree(s) still present alongside `.forge/`. "
            "Run any workflow step 1 (or `forge doctor` after a skill start) to migrate "
            "and archive them under `.forge/_archive/`. "
            "Set FORGE_KEEP_LEGACY_RUNTIME=1 to keep them."
        )
    return checks, warnings


def check_runtime_state_dir(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    try:
        from scripts.shared.orchestrator import runtime_state_dir

        state_dir = runtime_state_dir(repo_root)
        state_dir.mkdir(parents=True, exist_ok=True)
        return {"runtime_state_dir": str(state_dir)}, warnings
    except Exception as e:
        warnings.append(f"Failed to create runtime state dir: {e}")
        return {}, warnings


def check_forge_path() -> tuple[dict[str, object], list[str]]:
    """Warn when PATH's ``forge`` is not the preferred pipx install."""
    warnings: list[str] = []
    try:
        from forge_next.claude_graphify import (
            _pipx_bin_dir,
            path_shadows_pipx_forge,
            resolve_forge_executable,
        )

        preferred = resolve_forge_executable()
        shadowed, which_path, pipx_path = path_shadows_pipx_forge()
        checks: dict[str, object] = {
            "forge_executable": str(preferred),
            "forge_on_path": str(which_path) if which_path else None,
            "forge_pipx": str(pipx_path) if pipx_path else None,
            "forge_path_shadowed": shadowed,
        }
        if shadowed and which_path is not None and pipx_path is not None:
            bin_dir = _pipx_bin_dir()
            warnings.append(
                f"`forge` on PATH is {which_path}, but pipx installs to {pipx_path}. "
                f"The pipx copy is preferred for hooks/install. Fix with: "
                f"`pipx ensurepath --prepend` (puts {bin_dir} first), then open a new shell. "
                "Or uninstall the shadowed copy (`pip uninstall forge-next` if it was "
                "`pip install --user`)."
            )
        return checks, warnings
    except FileNotFoundError as exc:
        return {"forge_executable": None, "forge_path_shadowed": None}, [str(exc)]
    except Exception as exc:
        return {}, [f"Forge PATH check failed: {exc}"]


def check_claude_graphify() -> tuple[dict[str, object], list[str]]:
    warnings: list[str] = []
    try:
        from forge_next.claude_graphify import audit_claude_graphify_hooks

        return {}, list(audit_claude_graphify_hooks())
    except FileNotFoundError as exc:
        return {}, [str(exc)]
    except Exception as exc:
        return {}, [f"Claude Graphify hook audit failed: {exc}"]


def check_studio_assets() -> tuple[dict[str, object], list[str]]:
    try:
        from forge_next.studio.assets import asset_text

        asset_text("frame.html")
        asset_text("studio.js")
        return {"studio_assets": "ok"}, []
    except Exception as exc:
        return {"studio_assets": "missing"}, [f"Forge Studio assets unavailable: {exc}"]


def check_structural_tools() -> tuple[dict[str, object], list[str]]:
    try:
        from forge_next.structural_tools import (
            doctor_checks,
            structural_tools_warnings_for_doctor,
        )

        return {"structural_tools": doctor_checks()}, list(
            structural_tools_warnings_for_doctor()
        )
    except Exception as exc:
        return {"structural_tools": "error"}, [f"Structural tools check failed: {exc}"]


def check_beads(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    try:
        from forge_next.beads import beads_warnings_for_doctor, doctor_checks

        return {"beads": doctor_checks(repo_root)}, list(
            beads_warnings_for_doctor(repo_root)
        )
    except Exception as exc:
        return {"beads": "error"}, [f"Beads check failed: {exc}"]


def check_vendored_snapshots(repo_root: Path) -> tuple[dict[str, object], list[str]]:
    vendored = sorted(repo_root.glob("forge_next-0.14.*"))
    if not vendored:
        return {}, []
    return {
        "vendored_forge_snapshots": [p.name for p in vendored],
    }, [
        "Vendored PyPI extract dirs present (forge_next-0.14.*); safe to delete locally — "
        "they are gitignored and skipped by structural probes."
    ]


def check_workflow_prompts() -> tuple[dict[str, object], list[str]]:
    try:
        from scripts.evaluate.template_engine import validate_workflow_prompts

        missing = validate_workflow_prompts()
        status = "ok" if not missing else f"missing {len(missing)}"
        warnings: list[str] = []
        if missing:
            sample = ", ".join(missing[:8])
            extra = "" if len(missing) <= 8 else f" (+{len(missing) - 8} more)"
            warnings.append(
                "Workflow prompt templates unavailable: "
                f"{sample}{extra}. "
                "Upgrade forge-next or run scripts/release/sync_prompt_assets.py "
                "in a source checkout."
            )
        return {"workflow_prompts": status}, warnings
    except Exception as exc:
        return {"workflow_prompts": "error"}, [f"Workflow prompt validation failed: {exc}"]


def check_session_leaks(repo_root: Path) -> list[str]:
    old = Path.cwd()
    try:
        os.chdir(repo_root)
        from scripts.shared.orchestrator import collect_session_leak_hints

        return list(collect_session_leak_hints(repo_root))
    except Exception as exc:
        return [f"Session leak hint scan failed: {exc}"]
    finally:
        os.chdir(old)
