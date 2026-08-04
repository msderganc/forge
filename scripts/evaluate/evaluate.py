#!/usr/bin/env python3
"""Evaluate skill entry — declarative engine shim.

Kill-switch: ``FORGE_SKILL_ENGINE=0`` → ``evaluate_legacy``. Else ``run_skill``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.evaluate.evaluate_legacy import (  # noqa: E402
    PHASE_NAMES,
    PHASE_TODOS,
    POST_PHASES,
    PRE_PHASES,
    REVIEW_PHASES,
    _build_variables,
    _findings_sidecar_path,
    _format_output,
    _ingest_findings_sidecars,
    _max_step_for_mode,
    handle_step_n,
)

__all__ = [
    "PHASE_NAMES",
    "PHASE_TODOS",
    "POST_PHASES",
    "PRE_PHASES",
    "REVIEW_PHASES",
    "_build_variables",
    "_findings_sidecar_path",
    "_format_output",
    "_ingest_findings_sidecars",
    "_max_step_for_mode",
    "handle_step_n",
    "main",
]


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.evaluate.evaluate_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("evaluate", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
