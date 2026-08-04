#!/usr/bin/env python3
"""Sketch skill entry — declarative engine shim.

Authoritative kill-switch: ``FORGE_SKILL_ENGINE=0`` imports ``sketch_legacy``
and does not call ``run_skill``. Unset/other → ``run_skill("sketch", ...)``.

``forge_next.cli_dispatch`` still maps ``sketch`` → this module; the shim owns
the engine vs legacy branch (dispatch does not duplicate the switch).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.sketch.sketch_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("sketch", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
