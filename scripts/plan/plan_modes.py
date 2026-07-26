"""Planning mode matrix, preference storage, and recommendation heuristics.

Modes control ceremony/verbosity, not correctness. Both `default` and `lite`
require executor-ready tasks: exact paths, verification commands, expected
outcomes, and no placeholder language.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from scripts.shared.orchestrator import runtime_memory_dir

PLAN_MODES = ("default", "lite")
# Prefer lite when CLI/session/preference do not resolve — small/uncertain bias.
DEFAULT_MODE = "lite"
PREFERENCE_FILENAME = "plan-preference.json"


def normalize_mode(mode: str | None) -> str:
    """Return a valid plan mode, falling back to DEFAULT_MODE."""
    if mode and mode.strip().lower() in PLAN_MODES:
        return mode.strip().lower()
    return DEFAULT_MODE


def preference_path(search_dir: Path | None = None) -> Path:
    return runtime_memory_dir(search_dir) / PREFERENCE_FILENAME


def load_persisted_preference(search_dir: Path | None = None) -> str | None:
    """Load saved default mode, or None if unset/invalid."""
    path = preference_path(search_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    mode = data.get("default_mode")
    if mode and normalize_mode(mode) in PLAN_MODES:
        return normalize_mode(mode)
    return None


def save_persisted_preference(mode: str, search_dir: Path | None = None) -> Path:
    """Persist user's default plan mode for future new sessions."""
    path = preference_path(search_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"default_mode": normalize_mode(mode)}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def resolve_mode_for_step1(
    cli_mode: str | None,
    *,
    resumed_session: bool = False,
    stored_mode: str | None = None,
) -> tuple[str, str]:
    """Resolve mode at step 1.

    Returns (mode, resolution_source) where source is one of:
    cli, session, preference, fallback.
    """
    if cli_mode:
        return normalize_mode(cli_mode), "cli"
    if resumed_session and stored_mode:
        return normalize_mode(stored_mode), "session"
    return DEFAULT_MODE, "fallback"


def hydrate_legacy_mode(state_custom: dict[str, Any]) -> tuple[str, bool]:
    """Ensure plan_mode exists on legacy state; return (mode, migrated)."""
    if state_custom.get("plan_mode"):
        return normalize_mode(state_custom["plan_mode"]), False
    state_custom["plan_mode"] = DEFAULT_MODE
    return DEFAULT_MODE, True


def recommend_mode(
    handoff_content: str = "",
    plan_context: str = "",
) -> tuple[str, str]:
    """Recommend default or lite from scope/risk signals.

    Returns (recommended_mode, one_line_rationale).
    Bias: insufficient or tied signals → ``lite`` (minimal ceremony).
    Explicit trivial/small scope → ``lite``.
    """
    text = f"{handoff_content}\n{plan_context}".lower()
    # Strong small/trivial signals win even if mixed with generic words
    if re.search(
        r"\b(scope[_\s-]?tier\s*[:=]\s*trivial|trivial\s+scope|size\s*[:=]\s*small|"
        r"small\s+scope|recommended\s+scope)\b",
        text,
    ) or re.search(r'"scope_tier"\s*:\s*"trivial"', text):
        return (
            "lite",
            "Scope tier is trivial/small — use concise planning with full task rigor.",
        )
    lite_signals = [
        r"\b(hotfix|quick fix|small fix|one[- ]file|single file|typo|copy change)\b",
        r"\b(isolated|localized|narrow scope|ad hoc|adhoc|trivial)\b",
        r"\b(bugfix|patch|tweak|minor)\b",
        r"\b(size\s*[:=]\s*small|small\s*/\s*trivial)\b",
    ]
    default_signals = [
        r"\b(refactor|architecture|multi[- ]module|cross[- ]cutting)\b",
        r"\b(migration|schema|breaking|interface contract)\b",
        r"\b(epic|large feature|greenfield|scope[_\s-]?tier\s*[:=]\s*large)\b",
        r"\b(parallel|wave|sub[- ]system)\b",
        r"\b(size\s*[:=]\s*large|scope[_\s-]?tier\s*[:=]\s*medium)\b",
    ]
    lite_score = sum(1 for p in lite_signals if re.search(p, text))
    default_score = sum(1 for p in default_signals if re.search(p, text))
    if default_score > lite_score:
        return (
            "default",
            "Scope looks multi-module, architectural, or higher-risk — use full governance.",
        )
    if lite_score > default_score:
        return (
            "lite",
            "Scope looks small, isolated, and low-risk — use concise planning with full task rigor.",
        )
    # Tied or no signals — prefer lite (minimal ceremony bias)
    return (
        "lite",
        "Insufficient or tied scope signals — lite is the preferred starting point; escalate to default only with clear risk.",
    )


def format_mode_selection_block(
    *,
    recommended: str,
    rationale: str,
    persisted: str | None,
    resolved_mode: str | None,
    resolution_source: str,
) -> str:
    """Markdown block for step-1 prompts when mode must be confirmed."""
    if resolution_source == "cli":
        return (
            f"## Plan mode\n\n"
            f"**Active mode:** `{resolved_mode}` (from CLI — no confirmation needed).\n"
        )

    if resolution_source == "session":
        note = ""
        if resolved_mode:
            return (
                f"## Plan mode\n\n"
                f"**Active mode:** `{resolved_mode}` (resumed session — unchanged).\n"
            )
        return note

    persisted_line = (
        f"Saved preference: `{persisted}` (used as recommendation hint only until you confirm).\n"
        if persisted
        else "No saved plan-mode preference yet.\n"
    )
    return (
        "## Plan mode selection (required)\n\n"
        f"**Recommended:** `{recommended}` — {rationale}\n\n"
        f"{persisted_line}\n"
        "Ask the user to choose before continuing past step 1 "
        "(per `templates/user-questions.md`):\n\n"
        "**Question:** How detailed should this plan be?\n"
        "**Context:** Both modes require concrete tasks (exact files, a check command, "
        "and expected result). The difference is how much surrounding ceremony you want.\n\n"
        "- **`lite`** — Shorter plan for small or uncertain work; fewer sections, same "
        "correctness bar.\n"
        "- **`default`** — Fuller plan when several modules or higher risk are in play: "
        "deeper architecture, wave map, interface contracts, richer risk/rollback and docs.\n"
        "- Optional: **Save as my default** for future sessions.\n\n"
        "Record the choice in `state.custom['plan_mode']` via planner notes in "
        "`.codex/forge/memory/planner.md` and proceed with that mode for steps 2–7.\n"
    )


def mode_contract_for_template(mode: str) -> str:
    """Mode-specific instructions injected into plan prompts."""
    mode = normalize_mode(mode)
    shared = (
        "**Shared rigor (both modes):** No placeholders (`TBD`, `TODO`, \"implement later\", "
        "\"add validation\", \"handle edge cases\" without specifics). Every task lists exact "
        "file paths, a verification command, and expected outcome. TDD for runtime code changes.\n"
    )
    if mode == "lite":
        return (
            f"## Plan mode: lite\n\n{shared}\n"
            "**Lite depth:** Keep narrative concise. Architecture overview and risk/rollback "
            "can be compact. Parallelization map only when multiple tasks exist. Interface "
            "contracts required when tasks depend on each other. Documentation section: "
            "right-sized matrix/DoD rows — complete but not verbose.\n"
        )
    return (
        f"## Plan mode: default\n\n{shared}\n"
        "**Default depth:** Full architecture rationale, complete wave/dependency map, "
        "explicit interface contracts, expanded risk register and rollback steps, and "
        "complete documentation applicability matrix and DoD table.\n"
    )


def execution_path_recommendation(mode: str, task_count: int | None = None) -> str:
    """Suggest implement execution style based on mode and scale."""
    mode = normalize_mode(mode)
    if mode == "lite" or (task_count is not None and task_count <= 2):
        return (
            "**Execution recommendation:** Serial or single-agent inline implement — "
            "scope is small enough that wave parallelization adds little value."
        )
    return (
        "**Execution recommendation:** Wave-based implement with parallel subagents "
        "where the parallelization map shows independent tasks in the same wave."
    )


def review_expectations_for_mode(mode: str, quick_mode: bool) -> str:
    """Review-loop guidance by plan mode (orthogonal to --quick)."""
    mode = normalize_mode(mode)
    if quick_mode:
        return (
            "**Quick + plan mode:** Abbreviated review loop; still enforce no placeholders "
            "and verification evidence on every task.\n"
        )
    if mode == "lite":
        return (
            "**Lite review:** Same correctness checks as default (placeholders, paths, "
            "verification, TDD pairing) with shorter finding narratives.\n"
        )
    return ""  # Full table lives in review_loop template
