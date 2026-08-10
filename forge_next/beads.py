"""Beads (`bd`) availability for install/doctor onboarding.

Beads is optional issue tracking for Forge workflows. Forge never installs it;
we only detect the CLI and report how to get it. See ``templates/beads-integration.md``.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any


BEADS_INSTALL_HINT = (
    "Install Beads (`bd`) from https://github.com/steveyegge/beads — "
    "then re-run `forge doctor`. Workflows degrade to memory-file IDs without it."
)


def _ascii_mode() -> bool:
    return os.environ.get("FORGE_ASCII") == "1"


def _status_mark(present: bool) -> str:
    if _ascii_mode():
        return "[OK]" if present else "[X]"
    no_color = os.environ.get("NO_COLOR") is not None
    if present:
        return "✓" if no_color else "\033[32m✓\033[0m"
    return "✗" if no_color else "\033[31m✗\033[0m"


def _split_bd_command(raw: str) -> list[str]:
    text = raw.strip()
    if not text:
        return []
    if " " in text or "\t" in text:
        return shlex.split(text, posix=os.name != "nt")
    return [text]


def resolve_bd_executable() -> str | None:
    override = (os.environ.get("FORGE_BD_COMMAND") or "").strip()
    if override:
        parts = _split_bd_command(override)
        return parts[0] if parts else None
    return shutil.which("bd")


def beads_availability(repo_root: Path | None = None) -> tuple[bool, str, dict[str, Any]]:
    """Return (available, summary, details).

    ``available`` means the ``bd`` CLI is resolvable (PATH or ``FORGE_BD_COMMAND``).
    Repo ``.beads/`` presence is reported in details but does not gate availability.
    """
    details: dict[str, Any] = {
        "bd_path": None,
        "bd_version": None,
        "beads_dir": None,
        "beads_dir_exists": None,
        "via": None,
    }
    override = (os.environ.get("FORGE_BD_COMMAND") or "").strip()
    if override:
        parts = _split_bd_command(override)
        if not parts:
            return False, "not available (`bd` not on PATH; FORGE_BD_COMMAND unset)", details
        display = override
        details["bd_path"] = display
        details["via"] = "FORGE_BD_COMMAND"
        probe_cmd = override
    else:
        bd = shutil.which("bd")
        if not bd:
            return False, "not available (`bd` not on PATH; FORGE_BD_COMMAND unset)", details
        display = bd
        details["bd_path"] = bd
        details["via"] = "path"
        probe_cmd = bd

    version = _probe_bd_version(probe_cmd)
    if version:
        details["bd_version"] = version

    if repo_root is not None:
        beads_dir = Path(repo_root) / ".beads"
        details["beads_dir"] = str(beads_dir)
        details["beads_dir_exists"] = beads_dir.is_dir()

    summary = f"available (`{display}`"
    if version:
        summary += f", {version}"
    summary += f", via {details['via']})"
    return True, summary, details


def _probe_bd_version(bd_cmd: str) -> str | None:
    """Best-effort version string; never raises."""
    parts = _split_bd_command(bd_cmd)
    if not parts:
        return None
    for flag in ("version", "--version", "-V"):
        try:
            proc = subprocess.run(
                [*parts, flag],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=8,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, UnicodeError):
            continue
        out = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode == 0 and out:
            first = out.splitlines()[0].strip()
            return first[:120] if first else None
    return None


def beads_install_notice_lines(repo_root: Path | None = None) -> list[str]:
    """Human-readable Beads block for ``forge install`` output."""
    available, summary, details = beads_availability(repo_root)
    header = "Beads" if _ascii_mode() else "📿 Beads"
    lines = [
        "",
        header,
        f"  {_status_mark(available)} Beads: {summary}",
        "  Optional issue tracking for epics / findings / tasks "
        "(workflows degrade to memory-file IDs without it).",
    ]
    if available:
        if details.get("beads_dir_exists") is True:
            lines.append(f"  Repo store: {details['beads_dir']}")
        elif details.get("beads_dir_exists") is False:
            lines.append(
                f"  Repo store: missing ({details['beads_dir']}) — "
                "run `bd init` in the app repo when you want Beads tracking."
            )
        lines.extend(
            [
                "  Guide: templates/beads-integration.md",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"  {BEADS_INSTALL_HINT}",
                "  Or set FORGE_BD_COMMAND to how you invoke `bd`.",
                "  Guide: templates/beads-integration.md",
                "",
            ]
        )
    return lines


def doctor_checks(repo_root: Path | None = None) -> dict[str, Any]:
    available, summary, details = beads_availability(repo_root)
    return {
        "available": available,
        "summary": summary,
        **details,
    }


def beads_warnings_for_doctor(repo_root: Path | None = None) -> list[str]:
    available, _summary, details = beads_availability(repo_root)
    if not available:
        return [BEADS_INSTALL_HINT]
    if repo_root is not None and details.get("beads_dir_exists") is False:
        return [
            "Beads CLI is available but this repo has no `.beads/` directory. "
            "Run `bd init` when you want Forge to track issues in Beads "
            "(optional — degraded mode uses memory files)."
        ]
    return []
