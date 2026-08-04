#!/usr/bin/env python3
"""Code-review skill entry — declarative engine shim.

Kill-switch: ``FORGE_SKILL_ENGINE=0`` → ``code_review_legacy``. Else ``run_skill``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.code_review import code_review_legacy as _legacy  # noqa: E402
from scripts.code_review.code_review_legacy import (  # noqa: E402
    MAX_STEP,
    MODE_TEMPLATES,
    PHASE_NAMES,
    PHASE_TODOS,
    SKILL_NAME,
    _build_variables,
    _code_review_state_dir,
    _detect_mode,
    _normalize_target,
    _probe_status_one_liner,
    _prompt_archive_dir,
    format_step_output,
    load_template,
    render_template,
)


def handle_step_n(step, **kwargs):
    """Delegate to legacy, propagating any attrs monkeypatched on this shim."""
    mod = sys.modules[__name__]
    _legacy.format_step_output = mod.format_step_output
    _legacy.load_template = mod.load_template
    _legacy.render_template = mod.render_template
    return _legacy.handle_step_n(step, **kwargs)

__all__ = [
    "MAX_STEP",
    "MODE_TEMPLATES",
    "PHASE_NAMES",
    "PHASE_TODOS",
    "SKILL_NAME",
    "_build_variables",
    "_code_review_state_dir",
    "_detect_mode",
    "_normalize_target",
    "_probe_status_one_liner",
    "_prompt_archive_dir",
    "format_step_output",
    "handle_step_n",
    "load_template",
    "render_template",
    "main",
]


def main() -> None:
    if os.environ.get("FORGE_SKILL_ENGINE", "1").strip() == "0":
        from scripts.code_review.code_review_legacy import main as legacy_main

        legacy_main()
        return

    from scripts.shared.skill_runner import run_skill

    code = run_skill("code-review", sys.argv[1:])
    if code:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
