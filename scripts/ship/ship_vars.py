"""Ship template variables (must not import skill_runner)."""

from __future__ import annotations

from pathlib import Path

from scripts.shared.orchestrator import SkillState
from scripts.ship.ship_effects import last_effects, run_ship_side_effects


def build_variables(state: SkillState, repo_root: Path, step: int = 1) -> dict[str, str]:
    """Build template variables for ship prompts."""
    effects = last_effects()
    if effects is None:
        effects = run_ship_side_effects(repo_root)

    deferred = ""
    if effects.deferred_probe_lines:
        deferred = (
            "\n## Structural probes (deferred to ship)\n\n"
            + "\n".join(f"- {line}" for line in effects.deferred_probe_lines)
            + "\n"
        )
    return {
        "REFRESH_NOTE": effects.refresh_note,
        "DEFERRED_PROBES_SECTION": deferred,
        "REPO_ROOT": str(repo_root),
    }


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    return {
        "Repo": str(repo_root),
        "Next": "Follow .cursor/skills/ship/SKILL.md for commit/PR/publish",
    }
