"""Graphify integration: refresh index metadata and optional git post-commit hook.

Graphify is optional third-party tooling. Forge never requires it for core
workflows; `forge takeover` reads `graphify-status.json` when present.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOOK_BEGIN = "# >>> forge-graphify-hook (managed by forge-next)"
HOOK_END = "# <<< forge-graphify-hook"

# Debounce rapid SessionStart / per-step triggers (seconds).
REFRESH_SPAWN_DEBOUNCE_SEC = 120
REFRESH_LOCK_FILENAME = "graphify-refresh.lock"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def _git_head(repo: Path) -> str | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            return (r.stdout or "").strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _write_status(repo: Path, payload: dict) -> Path:
    """Write graphify-status.json under Forge runtime state directory.

    Returns the path to the status file.
    """
    # Import inside function so `forge graphify` works with minimal path setup.
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from scripts.shared.orchestrator import ensure_runtime_dirs, runtime_state_dir

    ensure_runtime_dirs(repo)
    out = runtime_state_dir(repo) / "graphify-status.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".tmp")
    try:
        os.close(fd)
        Path(tmp).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        Path(tmp).replace(out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return out


def skip_graphify_refresh_spawn(repo_root: Path | None = None) -> bool:
    """Return True when automatic background refresh should not run."""
    from forge_next.graphify_enforcement import graphify_refresh_disabled

    root = repo_root
    if root is None:
        try:
            from scripts.shared.orchestrator import REPO_ROOT

            root = REPO_ROOT
        except Exception:
            root = Path.cwd()
    return graphify_refresh_disabled(root)


def _refresh_lock_path(repo_root: Path) -> Path:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.shared.orchestrator import runtime_state_dir

    return runtime_state_dir(repo_root) / REFRESH_LOCK_FILENAME


def _read_status(repo_root: Path) -> dict:
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from scripts.shared.resume_context import read_graphify_status

    return read_graphify_status(repo_root)


def refresh_needed(repo_root: Path) -> bool:
    """True when graphify is available and status is missing, stale, or behind HEAD."""
    if skip_graphify_refresh_spawn(repo_root):
        return False
    if not graphify_availability()[0]:
        return False
    head = _git_head(repo_root)
    status = _read_status(repo_root)
    st = str(status.get("status") or "missing")
    if st in ("missing", "error"):
        return True
    if head and status.get("repo_head") and status.get("repo_head") != head:
        return True
    if st == "stale":
        return True
    last = status.get("last_refresh")
    if last:
        try:
            lr = datetime.fromisoformat(str(last).replace("Z", "+00:00"))
            if lr.tzinfo is None:
                lr = lr.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - lr
            if age > timedelta(hours=24):
                return True
        except Exception:
            return True
    return False


def _resolve_forge_spawn_argv(repo_root: Path) -> list[str] | None:
    forge = shutil.which("forge")
    if forge:
        return [forge, "graphify", "refresh", "--repo", str(repo_root.resolve())]
    return None


def spawn_refresh_background(repo_root: Path, *, force: bool = False) -> bool:
    """Start a detached ``forge graphify refresh`` when metadata is out of date.

    When ``force`` is True, spawn even if status looks fresh (e.g. ship preflight).

    Returns True if a child process was started. Never raises.
    """
    if not force and not refresh_needed(repo_root):
        return False
    try:
        lock = _refresh_lock_path(repo_root)
        lock.parent.mkdir(parents=True, exist_ok=True)
        if lock.is_file():
            age = time.time() - lock.stat().st_mtime
            if age < REFRESH_SPAWN_DEBOUNCE_SEC:
                return False
        lock.write_text(str(os.getpid()), encoding="utf-8")
    except OSError:
        return False

    cmd = _resolve_forge_spawn_argv(repo_root)
    if not cmd:
        return False

    try:
        kwargs: dict = {
            "cwd": str(repo_root.resolve()),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if sys.platform == "win32":
            detached = getattr(subprocess, "DETACHED_PROCESS", 0)
            kwargs["creationflags"] = (  # type: ignore[attr-defined]
                subprocess.CREATE_NEW_PROCESS_GROUP | detached
            )
        else:
            kwargs["close_fds"] = True
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)
        print(
            "forge graphify: started background refresh "
            f"(repo={repo_root.resolve()}).",
            file=sys.stderr,
        )
        return True
    except OSError:
        try:
            lock.unlink(missing_ok=True)
        except OSError:
            pass
        return False


def refresh(repo_root: Path, *, background: bool = True, force: bool = False) -> int:
    """Attempt to run Graphify (or FORGE_GRAPHIFY_COMMAND), then write status.

    When ``background`` is True (default), spawns a detached refresh and returns
    immediately. Pass ``background=False`` to run synchronously in this process.
    Use ``force=True`` with background to spawn even when status looks fresh.

    Returns 0 always (fail-soft for CI/hooks); failures are recorded in JSON.
    """
    if background:
        spawn_refresh_background(repo_root, force=force)
        return 0
    head = _git_head(repo_root)
    custom = (os.environ.get("FORGE_GRAPHIFY_COMMAND") or "").strip()
    cmd: list[str] | None = None
    if custom:
        try:
            cmd = shlex.split(custom)
        except ValueError as e:
            sp = _write_status(
                repo_root,
                {
                    "status": "error",
                    "last_refresh": _utc_iso(),
                    "error": f"Invalid FORGE_GRAPHIFY_COMMAND: {e}",
                    "repo_head": head,
                    "graphify_available": False,
                },
            )
            print(f"forge graphify: invalid FORGE_GRAPHIFY_COMMAND ({e}). Status: {sp}", file=sys.stderr)
            return 0
    elif shutil.which("graphify"):
        # Plain `graphify` may print help and exit 0 without rebuilding output.
        # Use the project-safe explicit refresh command by default.
        cmd = ["graphify", "update", "."]

    if not cmd:
        sp = _write_status(
            repo_root,
            {
                "status": "missing",
                "last_refresh": _utc_iso(),
                "error": "Graphify not found on PATH. Install Graphify or set FORGE_GRAPHIFY_COMMAND.",
                "repo_head": head,
                "graphify_available": False,
            },
        )
        print(
            "forge graphify: no `graphify` on PATH and FORGE_GRAPHIFY_COMMAND is unset.\n"
            f"  Recorded status ({sp.name}): status=missing — exiting 0 (fail-soft for hooks).\n"
            "  Install Graphify or set FORGE_GRAPHIFY_COMMAND; see docs/graphify.md.",
            file=sys.stderr,
        )
        return 0

    def _clear_refresh_lock() -> None:
        try:
            _refresh_lock_path(repo_root).unlink(missing_ok=True)
        except OSError:
            pass

    try:
        r = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=600,
        )
        ok = r.returncode == 0
        err_tail = ((r.stderr or "") + (r.stdout or ""))[-800:]
        sp = _write_status(
            repo_root,
            {
                "status": "fresh" if ok else "error",
                "last_refresh": _utc_iso(),
                "error": None if ok else (err_tail or f"exit {r.returncode}"),
                "repo_head": head,
                "graphify_available": True,
            },
        )
        _clear_refresh_lock()
        if ok:
            print("forge graphify: refresh finished (status file updated).", file=sys.stderr)
        else:
            print(
                f"forge graphify: Graphify exited {r.returncode}. Details in {sp}.\n{err_tail}",
                file=sys.stderr,
            )
    except subprocess.TimeoutExpired:
        sp = _write_status(
            repo_root,
            {
                "status": "error",
                "last_refresh": _utc_iso(),
                "error": "Graphify command timed out",
                "repo_head": head,
                "graphify_available": True,
            },
        )
        _clear_refresh_lock()
        print(f"forge graphify: command timed out. Status: {sp}", file=sys.stderr)
    except OSError as e:
        sp = _write_status(
            repo_root,
            {
                "status": "error",
                "last_refresh": _utc_iso(),
                "error": str(e),
                "repo_head": head,
                "graphify_available": bool(cmd),
            },
        )
        _clear_refresh_lock()
        print(f"forge graphify: {e}. Status: {sp}", file=sys.stderr)
    return 0


def _hook_body() -> str:
    return "\n".join(
        [
            HOOK_BEGIN,
            "# Rebuild Graphify metadata after each commit (fail-soft).",
            'REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"',
            'if command -v forge >/dev/null 2>&1 && [ -n "$REPO_ROOT" ]; then',
            '  (cd "$REPO_ROOT" && (forge graphify refresh >/dev/null 2>&1 &) ) || true',
            "fi",
            HOOK_END,
            "",
        ]
    )


def install_post_commit_hook(repo_root: Path) -> tuple[bool, str]:
    """Insert or replace the Forge Graphify block in .git/hooks/post-commit."""
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    block = _hook_body()
    hook_path.parent.mkdir(parents=True, exist_ok=True)
    existing = hook_path.read_text(encoding="utf-8", errors="replace") if hook_path.exists() else ""
    if HOOK_BEGIN in existing and HOOK_END in existing:
        pre, _, rest = existing.partition(HOOK_BEGIN)
        _, _, post = rest.partition(HOOK_END)
        new_content = pre + block + post.lstrip("\n")
    else:
        sep = "\n" if existing and not existing.endswith("\n") else ""
        new_content = existing + sep + block
    hook_path.write_text(new_content, encoding="utf-8")
    try:
        hook_path.chmod(hook_path.stat().st_mode | 0o111)
    except OSError:
        pass
    return True, f"Updated {hook_path} with Forge Graphify post-commit block."


def uninstall_post_commit_hook(repo_root: Path) -> tuple[bool, str]:
    """Remove the Forge Graphify block from .git/hooks/post-commit."""
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    if not hook_path.is_file():
        return True, "No post-commit hook present; nothing to remove."
    text = hook_path.read_text(encoding="utf-8", errors="replace")
    if HOOK_BEGIN not in text or HOOK_END not in text:
        return True, "Forge Graphify block not found in post-commit hook."
    pre, _, rest = text.partition(HOOK_BEGIN)
    _, _, post = rest.partition(HOOK_END)
    new_content = pre + post
    hook_path.write_text(new_content.lstrip("\n"), encoding="utf-8")
    return True, f"Removed Forge Graphify block from {hook_path}."


def graphify_set_disabled(repo_root: Path, *, disabled: bool) -> tuple[bool, str]:
    from forge_next.graphify_enforcement import (
        graphify_prefs_summary,
        set_graphify_disabled,
    )

    path = set_graphify_disabled(repo_root, disabled=disabled)
    state = graphify_prefs_summary(repo_root)
    if disabled:
        return True, f"Graphify enforcement disabled for this repo ({state}). Prefs: {path}"
    return True, f"Graphify enforcement enabled for this repo ({state})."


def graphify_set_defer_implement_waves(repo_root: Path, *, defer: bool) -> tuple[bool, str]:
    from forge_next.graphify_enforcement import (
        graphify_prefs_summary,
        set_graphify_defer_implement_waves,
    )

    path = set_graphify_defer_implement_waves(repo_root, defer=defer)
    state = graphify_prefs_summary(repo_root)
    if defer:
        return (
            True,
            "Graphify banners deferred for implement wave steps 3–5 "
            f"({state}). Prefs: {path}",
        )
    return True, f"Implement wave defer cleared ({state})."


def graphify_status_message(repo_root: Path) -> tuple[bool, str]:
    from forge_next.graphify_enforcement import graphify_prefs_summary

    return True, f"Graphify enforcement: {graphify_prefs_summary(repo_root)}."


def graphify_availability() -> tuple[bool, str]:
    """Return whether Graphify can be invoked and a one-line summary for install output."""
    custom = (os.environ.get("FORGE_GRAPHIFY_COMMAND") or "").strip()
    if custom:
        return True, "available (FORGE_GRAPHIFY_COMMAND is set)"
    if shutil.which("graphify"):
        return True, "available (`graphify` on PATH)"
    return False, "not available (`graphify` not on PATH; FORGE_GRAPHIFY_COMMAND unset)"


def graphify_install_notice_lines() -> list[str]:
    """Human-readable onboarding for `forge install` output (status first, then steps)."""
    available, summary = graphify_availability()
    ascii_mode = os.environ.get("FORGE_ASCII") == "1"
    header = "Graphify" if ascii_mode else "🗺️ Graphify"
    lines = [
        "",
        header,
        f"  Graphify: {summary}",
        "  Optional — gives `forge takeover` a codebase map, not your chat history.",
        "",
    ]
    if available:
        lines.extend(
            [
                "  1) In each **git clone** of your app repo, run **forge graphify refresh** once from that repo",
                "     (or `forge graphify refresh --repo \"C:/path/to/repo\"` from any directory).",
                "     That writes **graphify-status.json** under your Forge runtime state folder (e.g. `.forge/state/`).",
                "  2) Optional: **forge graphify install-hook** in the same repo adds a **post-commit** snippet so every",
                "     commit re-runs refresh in the background (`|| true` so commits never fail).",
                "     Remove later with **forge graphify uninstall-hook**.",
                "  3) Open **docs/graphify.md** in the Forge package/repo for the full picture.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "  1) Install Graphify so a `graphify` command works on your PATH, **or** set environment variable",
                "     FORGE_GRAPHIFY_COMMAND to exactly how you run it (defaults to `graphify update .`).",
                "  2) In each **git clone** of your app repo, run **forge graphify refresh** once from that repo",
                "     (or `forge graphify refresh --repo \"C:/path/to/repo\"` from any directory).",
                "     That writes **graphify-status.json** under your Forge runtime state folder (e.g. `.forge/state/`).",
                "  3) Optional: **forge graphify install-hook** in the same repo adds a **post-commit** snippet so every",
                "     commit re-runs refresh in the background (`|| true` so commits never fail).",
                "     Remove later with **forge graphify uninstall-hook**.",
                "  4) Open **docs/graphify.md** in the Forge package/repo for the full picture.",
                "",
            ]
        )
    return lines
