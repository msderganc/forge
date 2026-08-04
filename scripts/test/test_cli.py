"""Test skill CLI helpers for declarative engine (no skill_runner import)."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def reject_ux_mode(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    """``pre_run``: real-browser UX lives in ``forge ux-review``, not ``test --mode ux``."""
    if getattr(args, "mode", None) == "ux":
        print(
            "ERROR: `forge test --mode ux` was removed to avoid overlapping "
            "`forge ux-review`.\n"
            "       Use: forge ux-review --step 1 [--base-url URL]\n"
            "       (suite runs: --mode run; mock flows: --mode flows)",
            file=sys.stderr,
        )
        raise SystemExit(2)
    ensure_flows_prompts(args=args, manifest=manifest, repo_root=repo_root)


def ensure_flows_prompts(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    """Optional helper: abort when flows mode lacks required prompts."""
    del manifest, repo_root
    if getattr(args, "mode", None) != "flows":
        return
    from scripts.evaluate.template_engine import load_template
    from scripts.shared.template_engine import default_prompts_root
    from scripts.test.test_flows import required_flow_prompts

    missing = []
    for p in required_flow_prompts():
        try:
            load_template(f"test/{p}")
        except FileNotFoundError:
            missing.append(p)
    if missing:
        prompts_root = default_prompts_root()
        print(
            f"ERROR: flows mode unavailable — missing prompts in active template "
            f"root ({prompts_root}): {missing}",
            file=sys.stderr,
        )
        raise SystemExit(1)


def pre_run(*, args: Any, manifest: Any = None, repo_root: Path | None = None) -> None:
    """Combined pre_run: reject ux, then verify flows prompts when needed."""
    reject_ux_mode(args=args, manifest=manifest, repo_root=repo_root)
    ensure_flows_prompts(args=args, manifest=manifest, repo_root=repo_root)
