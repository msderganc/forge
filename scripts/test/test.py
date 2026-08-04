#!/usr/bin/env python3
"""Test skill entry — declarative engine shim.

Kill-switch: ``FORGE_SKILL_ENGINE=0`` → ``test_legacy``. Else ``run_skill``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.test.test_legacy import (  # noqa: E402
    MAX_STEP,
    PHASE_NAMES,
    PHASE_TODOS,
    SKILL_NAME,
    _build_variables,
    _max_step_for_mode,
    _normalize_target,
)

__all__ = [
    "MAX_STEP",
    "PHASE_NAMES",
    "PHASE_TODOS",
    "SKILL_NAME",
    "_build_variables",
    "_max_step_for_mode",
    "_normalize_target",
    "main",
]


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.test.test_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("test", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
