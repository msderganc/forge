"""Phase slug → step resolution helpers (extracted from skill_phases)."""

from __future__ import annotations

import sys

from scripts.shared.skill_phases import (
    _slug_index,
    apply_phase_slug_alias,
    canonical_skill_name,
)


def _evaluate_step_with_variant(skill: str, key: str, variant: str) -> int:
    key = apply_phase_slug_alias(skill, key)
    index = _slug_index(skill, variant)
    if key in index:
        return index[key]
    known = ", ".join(sorted(index.keys()))
    sys.exit(
        f"ERROR: unknown phase {key!r} for evaluate mode {variant!r}. Known: {known}"
    )


def _evaluate_step_unscoped(skill: str, key: str) -> int:
    key = apply_phase_slug_alias(skill, key)
    matches: list[tuple[str, int]] = []
    for mode in ("pre", "post", "review"):
        idx = _slug_index(skill, mode)
        if key in idx:
            matches.append((mode, idx[key]))
    if not matches:
        known = ", ".join(
            sorted(
                f"{m}-{s}"
                for m in ("pre", "post", "review")
                for s in _slug_index(skill, m).keys()
            )
        )
        sys.exit(f"ERROR: unknown phase {key!r} for evaluate. Known: {known}")
    steps = {step for _, step in matches}
    if len(steps) > 1:
        modes = ", ".join(f"{m} (step {s})" for m, s in matches)
        sys.exit(
            f"ERROR: phase {key!r} is ambiguous for evaluate ({modes}). "
            "Use --mode or a prefixed slug (e.g. post-discussion)."
        )
    return matches[0][1]


def resolve_evaluate_step(skill: str, key: str, variant: str | None) -> int:
    for prefix in ("pre", "post", "review"):
        if key.startswith(f"{prefix}-"):
            return resolve_evaluate_step(skill, key[len(prefix) + 1 :], variant=prefix)
    if variant is not None:
        return _evaluate_step_with_variant(skill, key, variant)
    return _evaluate_step_unscoped(skill, key)


def resolve_generic_step(
    skill: str,
    key: str,
    variant: str | None,
) -> int:
    key = apply_phase_slug_alias(skill, key)
    index = _slug_index(skill, variant)
    if key in index:
        return index[key]
    if variant is None:
        from scripts.shared.skill_phases import _SKILL_PHASE_NAMES

        for var_key in _SKILL_PHASE_NAMES.get(skill, {}):
            idx = _slug_index(skill, var_key if var_key is not None else None)
            if key in idx:
                return idx[key]
    known = ", ".join(sorted(index.keys()))
    sys.exit(f"ERROR: unknown phase {key!r} for skill {skill!r}. Known: {known}")
