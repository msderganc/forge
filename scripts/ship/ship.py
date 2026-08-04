#!/usr/bin/env python3
"""Ship skill entry — declarative engine shim.

Kill-switch: ``FORGE_SKILL_ENGINE=0`` → ``ship_legacy``. Else ``run_skill("ship")``.

Engine manifest: ``skills/ship/manifest.yaml``. Human SKILL docs stay under
``.cursor/skills/ship/`` (dual layout).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Compatibility re-exports for tests / callers
from scripts.ship.ship_legacy import MAX_STEP, PHASE_NAMES, PHASE_TODOS, SKILL_NAME  # noqa: E402

__all__ = ["MAX_STEP", "PHASE_NAMES", "PHASE_TODOS", "SKILL_NAME", "main"]


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.ship.ship_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("ship", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
