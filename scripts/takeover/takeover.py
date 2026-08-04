#!/usr/bin/env python3
"""Takeover skill entry — declarative engine shim (gate-heavy, not thin).

Kill-switch: ``FORGE_SKILL_ENGINE=0`` → ``takeover_legacy``. Else ``run_skill``.
Gate helpers remain importable from ``takeover_legacy`` / this package.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.takeover.takeover_legacy import (  # noqa: E402
    DEFAULT_MAX_INNER,
    GATE_SUBDIR,
    MAX_STEP,
    SKILL_NAME,
    TAKEOVER_PHASE_NAMES,
    TAKEOVER_PHASE_TODOS,
    _blocking_findings_count,
    _blocking_gate_open,
    _ensure_gates_dir,
    _gate_path,
    _gate_ref,
    _handle_primary_then_metric_stage,
    _legacy_gates_dir,
    _metric_gate_not_equal,
    _metric_gate_open,
    _read_gate,
    gates_dir,
    gates_dir_relative,
    handle_step_1,
)

__all__ = [
    "DEFAULT_MAX_INNER",
    "GATE_SUBDIR",
    "MAX_STEP",
    "SKILL_NAME",
    "TAKEOVER_PHASE_NAMES",
    "TAKEOVER_PHASE_TODOS",
    "_blocking_findings_count",
    "_blocking_gate_open",
    "_ensure_gates_dir",
    "_gate_path",
    "_gate_ref",
    "_handle_primary_then_metric_stage",
    "_legacy_gates_dir",
    "_metric_gate_not_equal",
    "_metric_gate_open",
    "_read_gate",
    "gates_dir",
    "gates_dir_relative",
    "handle_step_1",
    "main",
]


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.takeover.takeover_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("takeover", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
