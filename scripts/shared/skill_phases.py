"""Named workflow phases and step resolution for Forge skills."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.shared.skill_state import SkillState

# Canonical phase names per skill (and optional variant, e.g. evaluate mode).
# Keys: skill name -> variant (None for default) -> step -> display name
# Migrated skills load phases from skills/<skill>/manifest.yaml via load_manifest.
_SKILL_PHASE_NAMES: dict[str, dict[str | None, dict[int, str]]] = {
    # diagnose phases live in skills/diagnose/manifest.yaml (migrated Wave 6)
    "iterate": {
        None: {
            1: "Initialize",
            2: "Diagnose",
            3: "Plan",
            4: "Evaluate (pre)",
            5: "Implement",
            6: "Evaluate (post)",
            7: "Code review",
            8: "Test + metric",
            9: "Report",
        },
    },
}

# CLI / script folder token -> canonical skill name for phase lookup and agent tokens.
_SCRIPT_SKILL_ALIASES: dict[str, str] = {
    "develop": "design",
}

# Legacy --phase slugs that still resolve after spine renames (resume / muscle memory).
_PHASE_SLUG_ALIASES: dict[str, dict[str, str]] = {
    "plan": {
        "context-detection": "frame",
        "architecture-dispatch": "orient-architecture",
        "plan-creation-dispatch": "deepen-plan-creation",
        "plan-review-loop": "deepen-review",
        "user-approval": "decide",
        "documentation-planning": "verify-documentation",
    },
    "design": {
        "startup": "frame",
        "scope-team": "orient",
        "investigation-dispatch": "deepen-investigation",
        "investigation-review": "deepen-investigation-review",
        "solution-dispatch": "deepen-solutions",
        "solution-review-approval": "decide",
        "spec-issues": "verify-spec-issues",
    },
    "diagnose": {
        "frame-the-problem": "frame",
        "reproduce-observe": "orient-reproduce",
        "analyze-rank": "decide-analyze-rank",
        "solution-generation": "act-solutions",
        "implement-validate": "verify-fix",
        "report-prevention": "handoff",
    },
    "implement": {
        "plan-detection": "frame",
        "branch-setup": "orient-branch",
        "wave-dispatch": "act-wave-dispatch",
        "wave-review": "decide-wave-review",
        "wave-completion": "act-wave-complete",
        "integration-verification": "verify-integration",
        "documentation": "verify-documentation",
    },
    "code-review": {
        "target-detection": "frame",
        "mode-selection": "orient-mode",
        "team-dispatch": "orient-dispatch",
        "deep-dive": "deepen",
        "discussion": "decide",
        "report": "handoff",
    },
    "test": {
        "context-detection": "frame",
        "test-discovery": "orient-discovery",
        "test-execution": "act-execution",
        "failure-analysis": "deepen-failures",
        "coverage-gap-analysis": "verify-coverage",
        "report": "handoff",
        "flow-context-detection": "frame-flows",
        "flow-type-recommendation": "orient-flow-type",
        "scope-definition": "decide-scope",
        "scaffolding": "act-scaffold",
        "mock-authoring": "act-author",
        "execution-iteration": "verify-execute",
        "report-handoff": "handoff",
    },
    "evaluate": {
        "plan-parsing": "frame-plan-parsing",
        "feasibility": "orient-feasibility",
        "completeness": "orient-completeness",
        "codebase-alignment": "deepen-codebase-alignment",
        "risk-dependencies": "deepen-risk",
        "discussion": "decide",
        "report": "handoff",
        "completeness-audit": "orient-completeness-audit",
        "correctness": "deepen-correctness",
        "code-quality": "deepen-code-quality",
        "performance": "deepen-performance",
        "operational-readiness": "verify-operational",
    },
}


def apply_phase_slug_alias(skill: str, key: str) -> str:
    """Map a legacy phase slug onto the current spine slug when known."""
    aliases = _PHASE_SLUG_ALIASES.get(canonical_skill_name(skill), {})
    return aliases.get(key, key)


def phase_slug(name: str) -> str:
    """Stable kebab-case slug from a display phase name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().strip())
    return slug.strip("-")


def canonical_skill_name(skill_or_token: str) -> str:
    """Map legacy script tokens (develop) to canonical skill names (design)."""
    key = skill_or_token.strip().replace("_", "-")
    return _SCRIPT_SKILL_ALIASES.get(key, key)


def agent_skill_token(skill_name: str) -> str:
    """Hyphenated token for ``$forge:`` / ``/forge:`` continuations."""
    return canonical_skill_name(skill_name).replace("_", "-")


def phase_names_for(skill_name: str, variant: str | None = None) -> dict[int, str]:
    """Return {step: display name} for a skill (and optional variant).

    Migrated skills: prefer ``load_manifest`` phase names. Unmigrated skills:
    fall back to ``_SKILL_PHASE_NAMES``.
    """
    skill = canonical_skill_name(skill_name)
    from_manifest = _phase_names_from_manifest(skill, variant)
    if from_manifest:
        return from_manifest
    variants = _SKILL_PHASE_NAMES.get(skill, {})
    if variant is not None and variant in variants:
        return dict(variants[variant])
    if None in variants:
        return dict(variants[None])
    if variants:
        return dict(next(iter(variants.values())))
    return {}


def _phase_names_from_manifest(
    skill: str, variant: str | None
) -> dict[int, str]:
    """Load phase names from a skill manifest when available."""
    try:
        from scripts.shared.skill_manifest import SkillManifestError, load_manifest
        from scripts.shared.orchestrator import _detect_repo_root
    except ImportError:
        return {}
    try:
        repo_root = _detect_repo_root(Path.cwd())
        manifest = load_manifest(skill, repo_root)
    except (SkillManifestError, OSError, ValueError):
        return {}
    if variant is not None and manifest.variants and variant in manifest.variants:
        steps = manifest.variants[variant].steps
        return {s.step: s.phase for s in steps}
    if manifest.steps:
        return {s.step: s.phase for s in manifest.steps}
    return {}


def max_step_for(skill_name: str, variant: str | None = None) -> int:
    names = phase_names_for(skill_name, variant)
    return max(names) if names else 0


def _slug_index(skill_name: str, variant: str | None) -> dict[str, int]:
    names = phase_names_for(skill_name, variant)
    index: dict[str, int] = {}
    for step, display in names.items():
        slug = phase_slug(display)
        if slug in index and index[slug] != step:
            prefixed = f"{variant}-{slug}" if variant else f"step-{step}-{slug}"
            index[prefixed] = step
        index[slug] = step
    if variant:
        for step, display in names.items():
            index[f"{variant}-{phase_slug(display)}"] = step
    return index


def phase_for_step(skill_name: str, step: int, *, variant: str | None = None) -> str:
    """Return the primary slug for a step."""
    skill = canonical_skill_name(skill_name)
    names = phase_names_for(skill, variant)
    display = names.get(step, f"step-{step}")
    slug = phase_slug(display)
    if skill == "evaluate" and variant:
        return f"{variant}-{slug}"
    return slug


def step_for_phase(skill_name: str, phase: str, *, variant: str | None = None) -> int:
    """Resolve a phase slug (or step number as string) to a step index."""
    from scripts.shared.skill_phase_resolve import (
        resolve_evaluate_step,
        resolve_generic_step,
    )

    raw = (phase or "").strip()
    if not raw:
        sys.exit("ERROR: --phase requires a non-empty phase name")
    if raw.isdigit():
        return int(raw)
    skill = canonical_skill_name(skill_name)
    key = raw.lower().replace("_", "-")

    if skill == "evaluate":
        return resolve_evaluate_step(skill, key, variant)
    return resolve_generic_step(skill, key, variant)


def _session_dict_from_path(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        return data
    return SkillState.from_dict(data).to_dict() if hasattr(SkillState, "from_dict") else {}


def infer_resume_step(
    session: dict[str, Any],
) -> int:
    """Mirror ``resume._resume_step`` using a loaded session dict."""
    current = session.get("current_step", 1)
    last_completed = session.get("last_completed_step", 0)
    max_step = session.get("max_step", 6)
    last_completed = min(last_completed, current)
    if current <= 0:
        return 1
    if current >= max_step and last_completed >= max_step:
        return max_step
    if last_completed == current and current < max_step:
        return current + 1
    return max(current, 1)


def _load_session_dict(
    *,
    skill_name: str,
    state_file: str | None,
    session_id: str | None,
    search_dir: Path | None = None,
) -> dict[str, Any] | None:
    from scripts.shared.session_store import session_json_path
    from scripts.shared.orchestrator import _detect_repo_root, validate_state_path

    repo_root = _detect_repo_root(search_dir).resolve()
    if session_id:
        path = session_json_path(session_id, repo_root)
        if not path.is_file():
            return None
        return _session_dict_from_path(path)
    if state_file:
        sp = validate_state_path(state_file, canonical_skill_name(skill_name))
        if sp is None or not sp.is_file():
            sp = Path(state_file)
            if not sp.is_file():
                return None
        return _session_dict_from_path(sp)
    return None


def variant_from_session(session: dict[str, Any], skill_name: str) -> str | None:
    """Infer phase variant (test mode, evaluate mode) from persisted state."""
    skill = canonical_skill_name(skill_name)
    if skill == "test":
        custom = session.get("custom") or {}
        mode = custom.get("mode", "run")
        return str(mode) if mode in ("run", "flows") else "run"
    if skill == "evaluate":
        mode = session.get("mode")
        return str(mode) if mode in ("pre", "post", "review") else "pre"
    return None


def resolve_workflow_step(
    *,
    skill_name: str,
    max_step: int,
    step: int | None,
    phase: str | None,
    state_file: str | None = None,
    session_id: str | None = None,
    variant: str | None = None,
    search_dir: Path | None = None,
) -> int:
    """Resolve CLI ``--step`` / ``--phase`` / session inference to a step number."""
    skill = canonical_skill_name(skill_name)

    if step is not None and phase is not None:
        resolved = step_for_phase(skill, phase, variant=variant)
        if resolved != step:
            sys.exit(
                f"ERROR: --step {step} conflicts with --phase {phase!r} (resolves to step {resolved})"
            )
        return step

    if phase is not None:
        return step_for_phase(skill, phase, variant=variant)

    if step is not None:
        return step

    session = _load_session_dict(
        skill_name=skill,
        state_file=state_file,
        session_id=session_id,
        search_dir=search_dir,
    )
    if session is not None:
        var = variant or variant_from_session(session, skill)
        _ = var  # variant used when re-resolving phase-only invocations later
        return infer_resume_step(session)

    # New workflow: default to step 1.
    return 1


def format_phase_list(skill_name: str, variant: str | None = None) -> str:
    """Comma-separated phase slugs for argparse help text."""
    names = phase_names_for(skill_name, variant)
    return ", ".join(phase_slug(v) for v in names.values())
