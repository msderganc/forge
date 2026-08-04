"""Takeover CLI pre_run (cleanup) — no skill_runner import."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def pre_run(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    """Handle --cleanup before the declarative step loop."""
    del manifest, repo_root
    if getattr(args, "cleanup", False) and int(getattr(args, "step", 1) or 1) == 1:
        from scripts.takeover.cleanup import run_cleanup

        run_cleanup(
            force=bool(getattr(args, "force", False)),
            all_stale=bool(getattr(args, "all_stale", False)),
        )
        raise SystemExit(0)
