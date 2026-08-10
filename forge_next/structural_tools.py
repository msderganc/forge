"""Install and resolve structural quality CLI tools (knip, madge, jscn, pyscn, skylos).

Used by ``forge install --structural-tools`` and ``forge structural-tools install``.
"""

from __future__ import annotations

import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# Pinned majors for reproducible installs under the Forge-managed npm prefix.
KNIP_VERSION = "^5.62.0"
MADGE_VERSION = "^8.0.0"
JSCN_NPM_PACKAGE = "@msderganc/jscn"
NPM_PACKAGE_JSON = {
    "name": "forge-structural-tools",
    "private": True,
    "description": "Forge-managed knip, madge, and jscn for code-review / evaluate probes",
    "devDependencies": {
        "knip": KNIP_VERSION,
        "madge": MADGE_VERSION,
        JSCN_NPM_PACKAGE: "*",
    },
}

MANIFEST_VERSION = 1


def skip_structural_tools() -> bool:
    return os.environ.get("FORGE_SKIP_STRUCTURAL_TOOLS", "").strip() in ("1", "true", "yes")


def default_prefix() -> Path:
    """User-level directory for npm-installed knip/madge."""
    override = (os.environ.get("FORGE_STRUCTURAL_TOOLS_PREFIX") or "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        # Use ~/.forge, not %LOCALAPPDATA%\forge. Microsoft Store Python redirects
        # writes under LocalAppData into the package sandbox; npm/node (non-packaged)
        # then cannot see package.json at the real LocalAppData path.
        return Path.home() / ".forge" / "structural-tools"
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "forge" / "structural-tools"
    return Path.home() / ".local" / "share" / "forge" / "structural-tools"


def legacy_windows_localappdata_prefix() -> Path | None:
    """Pre-0.14.6 Windows prefix (%LOCALAPPDATA%\\forge\\structural-tools)."""
    if sys.platform != "win32":
        return None
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        return None
    return Path(base) / "forge" / "structural-tools"


def manifest_path() -> Path:
    return default_prefix().parent / "structural-tools.json"


def _legacy_manifest_paths() -> list[Path]:
    paths: list[Path] = []
    legacy_prefix = legacy_windows_localappdata_prefix()
    if legacy_prefix is not None:
        paths.append(legacy_prefix.parent / "structural-tools.json")
    return paths


def _npm_executable() -> str | None:
    for name in ("npm", "npm.cmd"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _npx_executable() -> str | None:
    return shutil.which("npx") or shutil.which("npx.cmd")


def _node_available() -> tuple[bool, str]:
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        return False, "node not on PATH"
    try:
        proc = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding="utf-8",
            errors="replace",
        )
        ver = (proc.stdout or proc.stderr or "").strip()
        if proc.returncode != 0:
            return False, f"node --version failed ({proc.returncode})"
        return True, ver or "unknown"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def _run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 600,
) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def _tool_version(cmd: list[str]) -> str | None:
    code, out = _run(cmd, timeout=60)
    if code != 0:
        return None
    first = (out.splitlines() or [""])[0].strip()
    return first or out[:120] or None


@dataclass
class StructuralToolsInstallResult:
    ok: bool
    prefix: str
    manifest_path: str
    knip: str | None = None
    madge: str | None = None
    jscn: str | None = None
    pyscn: str | None = None
    pyscn_via: str | None = None
    skylos: str | None = None
    skylos_via: str | None = None
    node_version: str | None = None
    warnings: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bin_in_prefix(prefix: Path, name: str) -> Path:
    if sys.platform == "win32":
        return prefix / "node_modules" / ".bin" / f"{name}.cmd"
    return prefix / "node_modules" / ".bin" / name


def _install_npm_tools(prefix: Path, result: StructuralToolsInstallResult) -> None:
    node_ok, node_ver = _node_available()
    result.node_version = node_ver if node_ok else None
    if not node_ok:
        result.warnings.append(f"Node.js unavailable ({node_ver}); skipped knip/madge install.")
        return

    npm = _npm_executable()
    if not npm:
        result.warnings.append("npm not on PATH; skipped knip/madge install.")
        return

    prefix.mkdir(parents=True, exist_ok=True)
    pkg_path = prefix / "package.json"
    pkg_path.write_text(json.dumps(NPM_PACKAGE_JSON, indent=2) + "\n", encoding="utf-8")
    result.steps.append(f"Wrote {pkg_path}")
    if not pkg_path.exists():
        result.warnings.append(
            f"Could not create {pkg_path} (path not visible after write). "
            "On Windows Store Python, set FORGE_STRUCTURAL_TOOLS_PREFIX to a folder under your profile "
            "(e.g. %USERPROFILE%\\.forge\\structural-tools) or install Python from python.org."
        )
        return

    code, out = _run([npm, "install", "--no-fund", "--no-audit"], cwd=prefix, timeout=600)
    if code != 0:
        result.warnings.append(f"npm install failed ({code}): {out[:500]}")
        return
    result.steps.append("npm install completed for knip, madge, and jscn")

    knip_bin = _bin_in_prefix(prefix, "knip")
    madge_bin = _bin_in_prefix(prefix, "madge")
    jscn_bin = _bin_in_prefix(prefix, "jscn")
    if knip_bin.is_file():
        result.knip = str(knip_bin)
    else:
        result.warnings.append(f"knip binary missing after install: {knip_bin}")
    if madge_bin.is_file():
        result.madge = str(madge_bin)
    else:
        result.warnings.append(f"madge binary missing after install: {madge_bin}")
    if jscn_bin.is_file():
        result.jscn = str(jscn_bin)
    else:
        result.warnings.append(f"jscn binary missing after install: {jscn_bin}")

    npx = _npx_executable()
    if npx:
        for warmup in (
            [npx, "--yes", f"knip@{KNIP_VERSION.lstrip('^')}", "--version"],
            [npx, "--yes", f"madge@{MADGE_VERSION.lstrip('^')}", "--version"],
            [npx, "--yes", JSCN_NPM_PACKAGE, "--version"],
        ):
            wcode, _ = _run(warmup, timeout=120)
            if wcode == 0:
                result.steps.append(" ".join(warmup[:4]) + " (cache warm)")
            else:
                result.warnings.append(f"npx warm-up failed: {' '.join(warmup[:3])}")


def _install_skylos(result: StructuralToolsInstallResult) -> None:
    if shutil.which("skylos"):
        result.skylos = shutil.which("skylos")
        result.skylos_via = "path"
        result.steps.append("skylos already on PATH")
        return

    pipx = shutil.which("pipx")
    if pipx:
        code, out = _run([pipx, "install", "skylos", "--force"], timeout=300)
        if code == 0 and shutil.which("skylos"):
            result.skylos = shutil.which("skylos")
            result.skylos_via = "pipx"
            result.steps.append("Installed skylos via pipx")
            return
        result.warnings.append(f"pipx install skylos failed ({code}): {out[:300]}")

    uv = shutil.which("uv")
    if uv:
        code, out = _run([uv, "tool", "install", "skylos"], timeout=300)
        if code == 0:
            skylos = shutil.which("skylos")
            if skylos:
                result.skylos = skylos
                result.skylos_via = "uv"
                result.steps.append("Installed skylos via uv tool")
                return
        result.warnings.append(f"uv tool install skylos failed ({code}): {out[:300]}")

    uvx = shutil.which("uvx") or shutil.which("uv")
    if uvx:
        code, out = _run([uvx, "skylos@latest", "--version"], timeout=120)
        if code == 0:
            result.skylos = f"{uvx} skylos@latest"
            result.skylos_via = "uvx"
            result.steps.append("skylos available via uvx (no global install)")
            return
        result.warnings.append(f"uvx skylos probe failed ({code}): {out[:200]}")

    result.warnings.append(
        "skylos not installed. Install with: pipx install skylos  OR  uv tool install skylos  OR  uvx skylos@latest"
    )


def _install_pyscn(result: StructuralToolsInstallResult) -> None:
    if shutil.which("pyscn"):
        result.pyscn = shutil.which("pyscn")
        result.pyscn_via = "path"
        result.steps.append("pyscn already on PATH")
        return

    pipx = shutil.which("pipx")
    if pipx:
        code, out = _run([pipx, "install", "pyscn", "--force"], timeout=300)
        if code == 0 and shutil.which("pyscn"):
            result.pyscn = shutil.which("pyscn")
            result.pyscn_via = "pipx"
            result.steps.append("Installed pyscn via pipx")
            return
        result.warnings.append(f"pipx install pyscn failed ({code}): {out[:300]}")

    uv = shutil.which("uv")
    if uv:
        code, out = _run([uv, "tool", "install", "pyscn"], timeout=300)
        if code == 0:
            # uv tool install puts binaries on PATH via ~/.local/bin typically
            pyscn = shutil.which("pyscn")
            if pyscn:
                result.pyscn = pyscn
                result.pyscn_via = "uv"
                result.steps.append("Installed pyscn via uv tool")
                return
        result.warnings.append(f"uv tool install pyscn failed ({code}): {out[:300]}")

    uvx = shutil.which("uvx") or shutil.which("uv")
    if uvx:
        code, out = _run([uvx, "pyscn@latest", "check", "--help"], timeout=120)
        if code == 0:
            result.pyscn = f"{uvx} pyscn@latest"
            result.pyscn_via = "uvx"
            result.steps.append("pyscn available via uvx (no global install)")
            return
        result.warnings.append(f"uvx pyscn probe failed ({code}): {out[:200]}")

    result.warnings.append(
        "pyscn not installed. Install with: pipx install pyscn  OR  uv tool install pyscn  OR  uvx pyscn@latest check ."
    )


def write_manifest(prefix: Path, result: StructuralToolsInstallResult) -> Path:
    mp = manifest_path()
    mp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": MANIFEST_VERSION,
        "platform": platform.system(),
        "node_prefix": str(prefix),
        "knip": result.knip,
        "madge": result.madge,
        "jscn": result.jscn,
        "pyscn": result.pyscn,
        "pyscn_via": result.pyscn_via,
        "skylos": result.skylos,
        "skylos_via": result.skylos_via,
        "knip_npx": f"knip@{KNIP_VERSION.lstrip('^')}",
        "madge_npx": f"madge@{MADGE_VERSION.lstrip('^')}",
        "jscn_npx": JSCN_NPM_PACKAGE,
    }
    mp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    result.manifest_path = str(mp)
    return mp


def install_structural_tools(*, prefix: Path | None = None) -> StructuralToolsInstallResult:
    """Install knip/madge under prefix and pyscn via pipx/uv/uvx."""
    if skip_structural_tools():
        return StructuralToolsInstallResult(
            ok=True,
            prefix="",
            manifest_path=str(manifest_path()),
            warnings=["FORGE_SKIP_STRUCTURAL_TOOLS=1 — install skipped."],
        )

    root = prefix or default_prefix()
    result = StructuralToolsInstallResult(ok=True, prefix=str(root), manifest_path="")
    _install_npm_tools(root, result)
    _install_pyscn(result)
    _install_skylos(result)
    write_manifest(root, result)
    result.ok = not any("failed" in w.lower() for w in result.warnings) or bool(
        result.knip or result.madge or result.jscn or result.pyscn or result.skylos
    )
    return result


def _split_override_command(raw: str) -> list[str]:
    """Parse ``FORGE_*_COMMAND`` env overrides (``shlex`` when whitespace present)."""
    text = raw.strip()
    if not text:
        return []
    if " " in text or "\t" in text:
        return shlex.split(text, posix=os.name != "nt")
    return [text]


def load_manifest() -> dict[str, Any] | None:
    for mp in (manifest_path(), *_legacy_manifest_paths()):
        if not mp.is_file():
            continue
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None


def resolve_knip_command() -> list[str]:
    override = (os.environ.get("FORGE_KNIP_COMMAND") or "").strip()
    if override:
        return _split_override_command(override)
    manifest = load_manifest()
    if manifest and manifest.get("knip"):
        p = Path(str(manifest["knip"]))
        if p.is_file():
            return [str(p)]
    which = shutil.which("knip")
    if which:
        return [which]
    npx = _npx_executable()
    pin = (manifest or {}).get("knip_npx", f"knip@{KNIP_VERSION.lstrip('^')}")
    if npx:
        return [npx, "--yes", str(pin)]
    return []


def resolve_madge_command() -> list[str]:
    override = (os.environ.get("FORGE_MADGE_COMMAND") or "").strip()
    if override:
        return _split_override_command(override)
    manifest = load_manifest()
    if manifest and manifest.get("madge"):
        p = Path(str(manifest["madge"]))
        if p.is_file():
            return [str(p)]
    which = shutil.which("madge")
    if which:
        return [which]
    npx = _npx_executable()
    pin = (manifest or {}).get("madge_npx", f"madge@{MADGE_VERSION.lstrip('^')}")
    if npx:
        return [npx, "--yes", str(pin)]
    return []


def resolve_jscn_command() -> list[str]:
    override = (os.environ.get("FORGE_JSCN_COMMAND") or "").strip()
    if override:
        return _split_override_command(override)
    manifest = load_manifest()
    if manifest and manifest.get("jscn"):
        p = Path(str(manifest["jscn"]))
        if p.is_file():
            return [str(p)]
    which = shutil.which("jscn")
    if which:
        return [which]
    npx = _npx_executable()
    pin = (manifest or {}).get("jscn_npx", JSCN_NPM_PACKAGE)
    if npx:
        return [npx, "--yes", str(pin)]
    return []


def resolve_skylos_command() -> list[str]:
    override = (os.environ.get("FORGE_SKYLOS_COMMAND") or "").strip()
    if override:
        return _split_override_command(override)
    manifest = load_manifest()
    skylos = manifest.get("skylos") if manifest else None
    via = (manifest or {}).get("skylos_via") if manifest else None
    if skylos and via == "uvx":
        return _split_override_command(str(skylos))
    if skylos:
        p = Path(str(skylos))
        if p.is_file() or shutil.which(str(skylos)):
            return [str(skylos)]
    which = shutil.which("skylos")
    if which:
        return [which]
    uvx = shutil.which("uvx") or shutil.which("uv")
    if uvx:
        return [uvx, "skylos@latest"]
    return []


def resolve_pyscn_command() -> list[str]:
    override = (os.environ.get("FORGE_PYSCN_COMMAND") or "").strip()
    if override:
        return _split_override_command(override)
    manifest = load_manifest()
    pyscn = manifest.get("pyscn") if manifest else None
    via = (manifest or {}).get("pyscn_via") if manifest else None
    if pyscn and via == "uvx":
        return _split_override_command(str(pyscn))
    if pyscn:
        p = Path(str(pyscn))
        if p.is_file() or shutil.which(str(pyscn)):
            return [str(pyscn)]
    which = shutil.which("pyscn")
    if which:
        return [which]
    uvx = shutil.which("uvx") or shutil.which("uv")
    if uvx:
        return [uvx, "pyscn@latest"]
    return []


def doctor_checks() -> dict[str, Any]:
    """Return structural-tools section for forge doctor."""
    manifest = load_manifest()
    prefix = default_prefix()
    node_ok, node_ver = _node_available()
    checks: dict[str, Any] = {
        "prefix": str(prefix),
        "manifest": str(manifest_path()) if manifest_path().is_file() else None,
        "node": node_ver if node_ok else False,
        "knip": None,
        "madge": None,
        "jscn": None,
        "pyscn": None,
        "skylos": None,
        "knip_command": resolve_knip_command(),
        "madge_command": resolve_madge_command(),
        "jscn_command": resolve_jscn_command(),
        "pyscn_command": resolve_pyscn_command(),
        "skylos_command": resolve_skylos_command(),
    }
    knip = resolve_knip_command()
    if knip:
        checks["knip"] = _tool_version([*knip, "--version"])
    madge = resolve_madge_command()
    if madge:
        checks["madge"] = _tool_version([*madge, "--version"])
    jscn = resolve_jscn_command()
    if jscn:
        checks["jscn"] = _tool_version([*jscn, "--version"])
    pyscn = resolve_pyscn_command()
    if pyscn:
        checks["pyscn"] = _tool_version([*pyscn, "check", "--help"]) or _tool_version(
            [*pyscn, "--version"]
        )
    skylos = resolve_skylos_command()
    if skylos:
        checks["skylos"] = _tool_version([*skylos, "--version"])
    if manifest:
        checks["manifest_pyscn_via"] = manifest.get("pyscn_via")
        checks["manifest_skylos_via"] = manifest.get("skylos_via")
    return checks


def structural_tools_missing_warnings() -> list[str]:
    """Warn for each probe CLI (knip, madge, jscn, pyscn, skylos) that cannot be resolved."""
    if skip_structural_tools():
        return []
    warnings: list[str] = []
    reinstall = "`forge install` or `forge structural-tools install`"
    if not resolve_knip_command():
        warnings.append(
            f"knip not available — re-run {reinstall} (requires Node.js/npm), "
            "or set FORGE_KNIP_COMMAND"
        )
    if not resolve_madge_command():
        warnings.append(
            f"madge not available — re-run {reinstall} (requires Node.js/npm), "
            "or set FORGE_MADGE_COMMAND"
        )
    if not resolve_jscn_command():
        warnings.append(
            f"jscn not available — re-run {reinstall} (requires Node.js/npm), "
            "or set FORGE_JSCN_COMMAND / use `npx @msderganc/jscn`"
        )
    if not resolve_pyscn_command():
        warnings.append(
            f"pyscn not available — re-run {reinstall} (pipx/uv), "
            "or set FORGE_PYSCN_COMMAND / use `uvx pyscn@latest`"
        )
    if not resolve_skylos_command():
        warnings.append(
            f"skylos not available — re-run {reinstall} (pipx/uv), "
            "or set FORGE_SKYLOS_COMMAND / use `uvx skylos@latest`"
        )
    return warnings


def structural_tools_warnings_for_doctor() -> list[str]:
    """Same as :func:`structural_tools_missing_warnings` (forge doctor)."""
    return structural_tools_missing_warnings()


def _structural_tool_mark(present: bool) -> str:
    """Green check / red X for install notices; ASCII or NO_COLOR safe."""
    ascii_mode = os.environ.get("FORGE_ASCII") == "1"
    if ascii_mode:
        return "[OK]" if present else "[X]"
    no_color = os.environ.get("NO_COLOR") is not None
    if present:
        return "✓" if no_color else "\033[32m✓\033[0m"
    return "✗" if no_color else "\033[31m✗\033[0m"


def _structural_tool_status_line(name: str, value: str | None, *, detail: str | None = None) -> str:
    mark = _structural_tool_mark(bool(value))
    if value:
        suffix = f" ({detail})" if detail else ""
        return f"  {mark} {name}: {value}{suffix}"
    return f"  {mark} {name}: not found"


def structural_tools_install_notice_lines(result: StructuralToolsInstallResult | None = None) -> list[str]:
    """Human-readable block for forge install output."""
    ascii_mode = os.environ.get("FORGE_ASCII") == "1"
    header = (
        "Structural quality tools"
        if ascii_mode
        else "🔧 Structural quality tools"
    )
    if skip_structural_tools():
        return [
            "",
            header,
            "  Skipped (FORGE_SKIP_STRUCTURAL_TOOLS=1).",
            "",
        ]

    if result is None:
        manifest = load_manifest()
        if manifest:
            result = StructuralToolsInstallResult(
                ok=True,
                prefix=manifest.get("node_prefix", str(default_prefix())),
                manifest_path=str(manifest_path()),
                knip=manifest.get("knip"),
                madge=manifest.get("madge"),
                jscn=manifest.get("jscn"),
                pyscn=manifest.get("pyscn"),
                pyscn_via=manifest.get("pyscn_via"),
                skylos=manifest.get("skylos"),
                skylos_via=manifest.get("skylos_via"),
            )
        else:
            result = StructuralToolsInstallResult(
                ok=False,
                prefix=str(default_prefix()),
                manifest_path=str(manifest_path()),
                warnings=["Not installed yet."],
            )

    lines = [
        "",
        header,
        "  knip, madge, jscn, pyscn, skylos — code-review / evaluate Pass B",
        f"  Prefix: {result.prefix}",
        _structural_tool_status_line("knip", result.knip),
        _structural_tool_status_line("madge", result.madge),
        _structural_tool_status_line("jscn", result.jscn),
        _structural_tool_status_line("pyscn", result.pyscn, detail=result.pyscn_via),
        _structural_tool_status_line("skylos", result.skylos, detail=result.skylos_via),
    ]
    if result.warnings:
        lines.append("  Warnings:")
        for w in result.warnings:
            lines.append(f"    - {w}")
    bin_hint = _bin_in_prefix(Path(result.prefix), "knip")
    if bin_hint.parent.is_dir():
        lines.append(f"  Optional PATH: {bin_hint.parent}")
    lines.extend(
        [
            "  Reinstall: forge structural-tools install",
            "  Script: scripts/install/structural_tools.sh (or .ps1 on Windows)",
            "  Skip: FORGE_SKIP_STRUCTURAL_TOOLS=1",
            "",
        ]
    )
    return lines


def main(argv: list[str] | None = None) -> int:
    """CLI entry: python -m forge_next.structural_tools [install]."""
    args = list(argv) if argv is not None else sys.argv[1:]
    sub = args[0] if args else "install"
    if sub != "install":
        print(f"Unknown subcommand: {sub}", file=sys.stderr)
        return 2
    result = install_structural_tools()
    print(json.dumps(result.to_dict(), indent=2))
    for line in structural_tools_install_notice_lines(result):
        print(line.rstrip())
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
