"""Ship side effects for declarative engine (must not import skill_runner).

``pre_run`` invokes Graphify refresh + deferred structural probe passes and
stashes results for ``ship_vars.build_variables``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ShipEffectsResult:
    refresh_note: str = (
        "Graphify refresh was not run (no CLI or `FORGE_SKIP_GRAPHIFY=1`)."
    )
    deferred_probe_lines: list[str] = field(default_factory=list)


_LAST: ShipEffectsResult | None = None


def last_effects() -> ShipEffectsResult | None:
    return _LAST


def clear_effects() -> None:
    global _LAST
    _LAST = None


def run_ship_side_effects(repo_root: Path) -> ShipEffectsResult:
    """Run deferred probes + background Graphify refresh; return notes for prompt."""
    global _LAST
    result = ShipEffectsResult()

    from forge_next.graphify_enforcement import graphify_fully_disabled

    if not graphify_fully_disabled(repo_root):
        try:
            from scripts.shared.structural_probes_gate import (
                run_ship_deferred_probe_passes,
            )

            result.deferred_probe_lines = list(
                run_ship_deferred_probe_passes(repo_root) or []
            )
        except Exception as exc:
            result.deferred_probe_lines = [
                f"Deferred structural probes failed (non-fatal): {exc}"
            ]

    print(
        "forge: ship step 1 — starting graphify refresh in the background…",
        file=sys.stderr,
        flush=True,
    )
    if not graphify_fully_disabled(repo_root):
        try:
            from forge_next.graphify import refresh
            from scripts.shared.graphify_contract import graph_index_present

            refresh(
                repo_root,
                background=True,
                force=graph_index_present(repo_root),
            )
            result.refresh_note = (
                "Started **`forge graphify refresh`** in the background "
                "(ship does not wait). "
                "Continue commit/PR; the index catches up asynchronously. "
                "If the CLI was missing, set `FORGE_GRAPHIFY_COMMAND` or "
                "install `graphify`."
            )
        except Exception as exc:
            result.refresh_note = f"Graphify refresh failed (non-fatal): {exc}"

    _LAST = result
    return result


def pre_run(*, args: Any, manifest: Any, repo_root: Path) -> None:
    """Manifest ``pre_run`` entry — run ship side effects after CLI parse."""
    run_ship_side_effects(Path(repo_root))
