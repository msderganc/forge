"""Orchestrator gate checks for diagnose sidecars."""

from __future__ import annotations

from pathlib import Path

from scripts.diagnose.activated_techniques import (
    requires_first_principles,
    requires_hypothesis_register,
    requires_mece_tree,
    resolve_activated_techniques,
)
from scripts.diagnose.barriers_register import FILENAME as BARRIERS_FILENAME
from scripts.diagnose.barriers_register import load_register as load_barriers
from scripts.diagnose.barriers_register import validate as validate_barriers
from scripts.diagnose.diagnose_registers import (
    DiagnoseGateResult,
    GateSection,
    has_override,
    merge_gate_results,
    resolve_sidecar_path,
)
from scripts.diagnose.first_principles_register import FILENAME as FP_FILENAME
from scripts.diagnose.first_principles_register import load_register as load_fp
from scripts.diagnose.first_principles_register import validate as validate_fp
from scripts.diagnose.five_whys_register import FILENAME as FIVE_WHYS_FILENAME
from scripts.diagnose.five_whys_register import load_register as load_five_whys
from scripts.diagnose.five_whys_register import validate_chains
from scripts.diagnose.hypothesis_register import (
    REGISTER_FILENAME as HYPOTHESIS_FILENAME,
    load_register as load_hypotheses,
    validate_elimination,
    validate_register,
)
from scripts.diagnose.mece_tree_register import FILENAME as MECE_FILENAME
from scripts.diagnose.mece_tree_register import load_register as load_mece
from scripts.diagnose.mece_tree_register import validate as validate_mece
from scripts.diagnose.problem_spec_register import FILENAME as PROBLEM_SPEC_FILENAME
from scripts.diagnose.problem_spec_register import load_register as load_problem_spec
from scripts.diagnose.problem_spec_register import validate as validate_problem_spec
from scripts.diagnose.repro_loop_register import FILENAME as REPRO_LOOP_FILENAME
from scripts.diagnose.repro_loop_register import load_register as load_repro_loop
from scripts.diagnose.repro_loop_register import (
    requires_override_to_proceed,
    validate as validate_repro_loop,
)
from scripts.diagnose.technique_coverage import COVERAGE_FILENAME
from scripts.diagnose.technique_coverage import load_sidecar as load_coverage
from scripts.diagnose.technique_coverage import validate_coverage
from scripts.diagnose.technique_coverage_policy import is_high_severity
from scripts.shared.orchestrator import SkillState

PHASE_NAMES: dict[int, str] = {}


def _confirmed_hypothesis_ids(reg_data: dict | None) -> set[str]:
    if not reg_data or not isinstance(reg_data.get("hypotheses"), list):
        return set()
    return {
        str(h["id"])
        for h in reg_data["hypotheses"]
        if isinstance(h, dict) and str(h.get("status")) == "confirmed" and h.get("id")
    }


def _section(
    title: str,
    issues: list[str],
    state: SkillState,
    override_key: str,
) -> GateSection:
    return GateSection(
        title=title,
        issues=issues,
        override_key=override_key,
        bypassed=has_override(state.custom, override_key),
    )


def check_problem_spec_gate(
    state: SkillState,
    sp: Path,
    step: int,
    *,
    strict: bool = False,
) -> DiagnoseGateResult:
    """Step 2: light problem-spec validation."""
    if has_override(state.custom, "problem_spec_override_reason"):
        return DiagnoseGateResult(passed=True)

    spec_file = resolve_sidecar_path(sp, PROBLEM_SPEC_FILENAME)
    data = load_problem_spec(spec_file)
    ok, issues = validate_problem_spec(data, path=spec_file, strict=strict)
    if ok:
        return DiagnoseGateResult(passed=True)

    attempts = int(state.custom.get("problem_spec_regen_attempts", 0))
    retry = 1 if attempts < 1 and strict else None
    if attempts < 1:
        state.custom["problem_spec_regen_attempts"] = attempts + 1

    sections = [_section("Problem specification", issues, state, "problem_spec_override_reason")]
    return merge_gate_results(
        sections,
        phase=PHASE_NAMES.get(step, f"Step {step}"),
        retry_step=retry,
        attempt=attempts,
        max_attempts=1,
        state_path=str(sp),
    )


def check_repro_loop_gate(state: SkillState, sp: Path, step: int) -> DiagnoseGateResult:
    """Step 3: require feedback loop sidecar before 5 Whys."""
    if has_override(state.custom, "repro_loop_override_reason"):
        return DiagnoseGateResult(passed=True)

    reg_file = resolve_sidecar_path(sp, REPRO_LOOP_FILENAME)
    data = load_repro_loop(reg_file)
    ok, issues = validate_repro_loop(data, path=reg_file)
    if ok and requires_override_to_proceed(data):
        ok = False
        issues = [
            "Sidecar documents cannot_build_loop — set state "
            "'repro_loop_override_reason' after user provides access/artifacts, "
            "or build a runnable loop and update the sidecar."
        ]

    if ok:
        return DiagnoseGateResult(passed=True)

    attempts = int(state.custom.get("repro_loop_regen_attempts", 0))
    retry = 2 if attempts < 1 else None
    if attempts < 1:
        state.custom["repro_loop_regen_attempts"] = attempts + 1

    sections = [_section("Feedback loop / reproduction", issues, state, "repro_loop_override_reason")]
    return merge_gate_results(
        sections,
        phase=PHASE_NAMES.get(step, f"Step {step}"),
        retry_step=retry,
        attempt=attempts,
        max_attempts=1,
        state_path=str(sp),
    )


def check_register_gate(state: SkillState, sp: Path, step: int) -> DiagnoseGateResult:
    activated = resolve_activated_techniques(sp, state.custom)
    if not requires_hypothesis_register(activated):
        return DiagnoseGateResult(passed=True)

    if has_override(state.custom, "hypothesis_override_reason"):
        return DiagnoseGateResult(passed=True)
    reg_file = resolve_sidecar_path(sp, HYPOTHESIS_FILENAME)
    reg_data = load_hypotheses(reg_file)
    min_required = int(state.custom.get("hypothesis_min", 10))
    ok, issues = validate_register(reg_data, min_required=min_required, path=reg_file)
    if ok:
        return DiagnoseGateResult(passed=True)

    attempts = int(state.custom.get("hypothesis_regen_attempts", 0))
    retry = 3 if attempts < 1 else None
    if attempts < 1:
        state.custom["hypothesis_regen_attempts"] = attempts + 1

    sections = [_section("Hypothesis register", issues, state, "hypothesis_override_reason")]
    return merge_gate_results(
        sections,
        phase=PHASE_NAMES.get(step, f"Step {step}"),
        retry_step=retry,
        attempt=attempts,
        max_attempts=1,
        state_path=str(sp),
    )


def check_quartet_gate(state: SkillState, sp: Path, step: int) -> DiagnoseGateResult:
    """Optional first-principles + MECE when activated in problem spec."""
    activated = resolve_activated_techniques(sp, state.custom)
    if not requires_first_principles(activated) and not requires_mece_tree(activated):
        return DiagnoseGateResult(passed=True)

    if has_override(state.custom, "quartet_override_reason"):
        return DiagnoseGateResult(passed=True)

    active_sections: list[GateSection] = []

    if requires_first_principles(activated):
        fp_file = resolve_sidecar_path(sp, FP_FILENAME)
        fp_data = load_fp(fp_file)
        ok, issues = validate_fp(fp_data, path=fp_file)
        if not ok:
            active_sections.append(
                _section("First-principles", issues, state, "quartet_override_reason")
            )

    if requires_mece_tree(activated):
        mece_file = resolve_sidecar_path(sp, MECE_FILENAME)
        mece_data = load_mece(mece_file)
        ok2, issues2 = validate_mece(mece_data, path=mece_file)
        if not ok2:
            active_sections.append(_section("MECE tree", issues2, state, "quartet_override_reason"))

    if not active_sections:
        return DiagnoseGateResult(passed=True)

    attempts = int(state.custom.get("quartet_regen_attempts", 0))
    retry = 3 if attempts < 1 else None
    if attempts < 1:
        state.custom["quartet_regen_attempts"] = attempts + 1

    return merge_gate_results(
        active_sections,
        phase=PHASE_NAMES.get(step, f"Step {step}"),
        retry_step=retry,
        attempt=attempts,
        max_attempts=1,
        state_path=str(sp),
    )


def check_step5_bundle_gate(state: SkillState, sp: Path, step: int) -> DiagnoseGateResult:
    """Hypothesis elimination + five whys + routed technique coverage."""
    sections: list[GateSection] = []

    reg_file = resolve_sidecar_path(sp, HYPOTHESIS_FILENAME)
    activated = resolve_activated_techniques(sp, state.custom)
    reg_data = load_hypotheses(reg_file)
    if requires_hypothesis_register(activated) and not has_override(
        state.custom, "hypothesis_override_reason"
    ):
        ok, issues = validate_elimination(reg_data, path=reg_file)
        if not ok:
            sections.append(_section("Hypothesis elimination", issues, state, "hypothesis_override_reason"))

    confirmed = _confirmed_hypothesis_ids(reg_data) if requires_hypothesis_register(activated) else set()
    if not has_override(state.custom, "five_whys_override_reason"):
        five_whys_file = resolve_sidecar_path(sp, FIVE_WHYS_FILENAME)
        fw_data = load_five_whys(five_whys_file)
        ok, issues = validate_chains(
            fw_data,
            path=five_whys_file,
            require_confirmed_link=bool(confirmed),
            confirmed_ids=confirmed,
        )
        if not ok:
            sections.append(_section("Five Whys chains", issues, state, "five_whys_override_reason"))

    if not has_override(state.custom, "technique_coverage_override_reason"):
        coverage_file = resolve_sidecar_path(sp, COVERAGE_FILENAME)
        cov_data = load_coverage(coverage_file)
        ok, issues, _ = validate_coverage(
            cov_data,
            path=coverage_file,
            routed_only=True,
            allow_override_skips=True,
            adaptive=True,
            activated=activated,
        )
        if not ok:
            sections.append(
                _section("Technique coverage (routed)", issues, state, "technique_coverage_override_reason")
            )

    if not sections:
        return DiagnoseGateResult(passed=True)

    attempts = int(state.custom.get("step5_bundle_attempts", 0))
    retry = 4 if attempts < 1 else None
    if attempts < 1:
        state.custom["step5_bundle_attempts"] = attempts + 1

    return merge_gate_results(
        sections,
        phase=PHASE_NAMES.get(step, f"Step {step}"),
        retry_step=retry,
        attempt=attempts,
        max_attempts=1,
        state_path=str(sp),
    )


def check_step7_closure_gate(state: SkillState, sp: Path, step: int) -> DiagnoseGateResult:
    """Activated techniques + five whys + optional sidecars."""
    activated = resolve_activated_techniques(sp, state.custom)
    sections: list[GateSection] = []
    non_overridable: list[str] = []

    reg_data = load_hypotheses(resolve_sidecar_path(sp, HYPOTHESIS_FILENAME))
    confirmed = (
        _confirmed_hypothesis_ids(reg_data)
        if requires_hypothesis_register(activated)
        else set()
    )

    coverage_file = resolve_sidecar_path(sp, COVERAGE_FILENAME)
    if not has_override(state.custom, "technique_coverage_override_reason"):
        cov_data = load_coverage(coverage_file)
        ok, issues, policy = validate_coverage(
            cov_data,
            path=coverage_file,
            routed_only=True,
            allow_override_skips=False,
            adaptive=True,
            activated=activated,
        )
        non_overridable.extend(policy)
        if not ok:
            sections.append(
                _section(
                    "Technique coverage (activated techniques)",
                    issues,
                    state,
                    "technique_coverage_override_reason",
                )
            )

    if not has_override(state.custom, "five_whys_override_reason"):
        five_whys_file = resolve_sidecar_path(sp, FIVE_WHYS_FILENAME)
        fw_data = load_five_whys(five_whys_file)
        ok, issues = validate_chains(
            fw_data,
            path=five_whys_file,
            require_confirmed_link=True,
            confirmed_ids=confirmed,
        )
        if not ok:
            sections.append(_section("Five Whys chains", issues, state, "five_whys_override_reason"))

    if not has_override(state.custom, "quartet_override_reason"):
        if requires_first_principles(activated):
            fp_file = resolve_sidecar_path(sp, FP_FILENAME)
            fp_data = load_fp(fp_file)
            ok, issues = validate_fp(fp_data, path=fp_file)
            if not ok:
                sections.append(
                    _section("First-principles", issues, state, "quartet_override_reason")
                )

        if requires_mece_tree(activated):
            mece_file = resolve_sidecar_path(sp, MECE_FILENAME)
            mece_data = load_mece(mece_file)
            ok2, issues2 = validate_mece(mece_data, path=mece_file)
            if not ok2:
                sections.append(_section("MECE tree", issues2, state, "quartet_override_reason"))

    cov_data = load_coverage(coverage_file)
    high_barrier = is_high_severity(cov_data)
    if high_barrier and not has_override(state.custom, "barriers_override_reason"):
        barriers_file = resolve_sidecar_path(sp, BARRIERS_FILENAME)
        b_data = load_barriers(barriers_file)
        ok, issues = validate_barriers(b_data, path=barriers_file, required=True)
        if not ok:
            sections.append(_section("Barrier analysis", issues, state, "barriers_override_reason"))

    if not sections and not non_overridable:
        return DiagnoseGateResult(passed=True)

    attempts = int(state.custom.get("step7_closure_attempts", 0))
    retry = 5 if attempts < 1 else 4
    if attempts < 1:
        state.custom["step7_closure_attempts"] = attempts + 1

    return merge_gate_results(
        sections,
        phase=PHASE_NAMES.get(step, f"Step {step}"),
        retry_step=retry,
        attempt=attempts,
        max_attempts=1,
        state_path=str(sp),
        non_overridable=non_overridable or None,
    )


# ---------------------------------------------------------------------------
# Declarative skill_runner adapters (soft-gate; no skill_runner import)
# ---------------------------------------------------------------------------

_GATE_PASSED_KEY = "_diagnose_gate_passed"
_GATE_NEXT_KEY = "_diagnose_gate_next"
_GATE_BODY_KEY = "_diagnose_gate_body"


def _apply_cached_soft_gate(state: SkillState, *, step: int) -> None:
    """Apply runner control flags from vars-cached gate result.

    ``diagnose_vars`` runs the real ``check_*`` validators (so template
    placeholders get gate bodies before render). Declared gates call these
    adapters afterward to set ``_await_same_step`` / ``_next_step`` without
    double-incrementing regen attempt counters.
    """
    passed = state.custom.pop(_GATE_PASSED_KEY, True)
    if passed in (True, "True", "true", "1"):
        state.custom.pop(_GATE_NEXT_KEY, None)
        state.custom.pop(_GATE_BODY_KEY, None)
        return

    state.custom["_await_same_step"] = True
    next_raw = state.custom.pop(_GATE_NEXT_KEY, None)
    if next_raw is not None:
        try:
            state.custom["_next_step"] = int(next_raw)
        except (TypeError, ValueError):
            state.custom["_next_step"] = step
    body = state.custom.pop(_GATE_BODY_KEY, None)
    if body:
        existing = str(state.custom.get("_append_body") or "")
        block = str(body).strip()
        state.custom["_append_body"] = (
            f"{existing}\n\n---\n\n{block}" if existing else f"\n\n---\n\n{block}"
        )


def run_problem_spec_advisory_gate(
    *, state: SkillState, step: int, state_path: Path, gate: object
) -> None:
    """Step 2: advisory only (vars already appended warning)."""
    del state_path, gate
    if step != 2:
        return
    # Advisory — never block progression.
    state.custom.pop(_GATE_PASSED_KEY, None)
    state.custom.pop(_GATE_NEXT_KEY, None)
    state.custom.pop(_GATE_BODY_KEY, None)


def run_repro_loop_gate(
    *, state: SkillState, step: int, state_path: Path, gate: object
) -> None:
    del state_path, gate
    if step != 3:
        return
    _apply_cached_soft_gate(state, step=step)


def run_register_and_quartet_gate(
    *, state: SkillState, step: int, state_path: Path, gate: object
) -> None:
    del state_path, gate
    if step != 4:
        return
    _apply_cached_soft_gate(state, step=step)


def run_step5_bundle_gate(
    *, state: SkillState, step: int, state_path: Path, gate: object
) -> None:
    del state_path, gate
    if step != 5:
        return
    _apply_cached_soft_gate(state, step=step)


def run_step7_closure_gate(
    *, state: SkillState, step: int, state_path: Path, gate: object
) -> None:
    del state_path, gate
    if step != 7:
        return
    _apply_cached_soft_gate(state, step=step)
