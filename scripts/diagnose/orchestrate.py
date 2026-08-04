#!/usr/bin/env python3
"""Diagnose skill entry — declarative engine shim.

Kill-switch: ``FORGE_SKILL_ENGINE=0`` → ``orchestrate_legacy``. Else ``run_skill``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.diagnose.orchestrate_legacy import (  # noqa: E402
    AUTONOMY_GATES,
    MAX_STEP,
    PHASE_NAMES,
    PHASE_TEMPLATES,
    PHASE_TODOS,
    SKILL_NAME,
)

__all__ = [
    "AUTONOMY_GATES",
    "MAX_STEP",
    "PHASE_NAMES",
    "PHASE_TEMPLATES",
    "PHASE_TODOS",
    "SKILL_NAME",
    "main",
]


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.diagnose.orchestrate_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("diagnose", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
