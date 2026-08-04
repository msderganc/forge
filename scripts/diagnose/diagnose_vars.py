"""Diagnose template variables (must not import skill_runner)."""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.diagnose import diagnose_gates
from scripts.diagnose.diagnose_steps import (
    append_complexity_gate_notes,
    apply_gate_template_variables,
    resolve_step_gate,
    routing_label_for_complexity,
    suggested_next_for_complexity,
)
from scripts.diagnose.five_whys_register import load_register as load_five_whys
from scripts.diagnose.five_whys_register import register_path as five_whys_register_path
from scripts.diagnose.five_whys_register import summarize_chains
from scripts.diagnose.first_principles_register import load_register as load_fp_register
from scripts.diagnose.first_principles_register import register_path as fp_register_path
from scripts.diagnose.first_principles_register import summarize as summarize_fp
from scripts.diagnose.hypothesis_register import (
    load_register,
    register_path,
    summarize_register,
)
from scripts.diagnose.mece_tree_register import load_register as load_mece_register
from scripts.diagnose.mece_tree_register import register_path as mece_register_path
from scripts.diagnose.mece_tree_register import summarize as summarize_mece
from scripts.diagnose.problem_spec_register import load_register as load_problem_spec_register
from scripts.diagnose.problem_spec_register import register_path as problem_spec_register_path
from scripts.diagnose.problem_spec_register import summarize as summarize_problem_spec
from scripts.diagnose.repro_loop_register import load_register as load_repro_loop_register
from scripts.diagnose.repro_loop_register import register_path as repro_loop_register_path
from scripts.diagnose.repro_loop_register import summarize as summarize_repro_loop
from scripts.diagnose.technique_coverage import coverage_path
from scripts.diagnose.technique_coverage import load_sidecar as load_coverage
from scripts.diagnose.technique_coverage import summarize_coverage
from scripts.shared.orchestrator import SkillState
from scripts.shared.runtime_layout import repo_relative_path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent

PHASE_NAMES: dict[int, str] = {
    1: "Frame the Problem",
    2: "Reproduce & Observe",
    3: "Deepen (5 Whys)",
    4: "Analyze & Rank",
    5: "Solution Generation",
    6: "Implement & Validate",
    7: "Report & Prevention",
}

AUTONOMY_GATES = {
    "guided": {2, 4, 6},
    "autonomous": set(),
    "interactive": {1, 2, 3, 4, 5, 6, 7},
}

# Soft-gate cache keys (vars run checks; declared gates apply runner control flags).
_GATE_PASSED_KEY = "_diagnose_gate_passed"
_GATE_NEXT_KEY = "_diagnose_gate_next"
_GATE_BODY_KEY = "_diagnose_gate_body"


def ensure_diagnose_custom(state: SkillState) -> None:
    """Initialize diagnose-specific custom defaults."""
    cli_mode = state.custom.get("mode")
    if isinstance(cli_mode, str) and cli_mode in AUTONOMY_GATES:
        state.custom["autonomy_mode"] = cli_mode
    state.custom.setdefault("autonomy_mode", "guided")
    state.custom.setdefault("fix_complexity", "unknown")
    state.custom.setdefault("hypothesis_min", 5)
    state.custom.setdefault("hypothesis_regen_attempts", 0)
    state.custom.setdefault("hypothesis_validation_attempts", 0)
    state.custom.setdefault("problem_spec_regen_attempts", 0)
    state.custom.setdefault("quartet_regen_attempts", 0)
    state.custom.setdefault("step5_bundle_attempts", 0)
    state.custom.setdefault("step7_closure_attempts", 0)
    diagnose_gates.PHASE_NAMES = PHASE_NAMES


def _cache_soft_gate(
    state: SkillState,
    gate_result: diagnose_gates.DiagnoseGateResult | None,
) -> None:
    if gate_result is None or gate_result.passed:
        state.custom[_GATE_PASSED_KEY] = True
        state.custom.pop(_GATE_NEXT_KEY, None)
        state.custom.pop(_GATE_BODY_KEY, None)
        return
    state.custom[_GATE_PASSED_KEY] = False
    if gate_result.next_step_override is not None:
        state.custom[_GATE_NEXT_KEY] = int(gate_result.next_step_override)
    else:
        state.custom.pop(_GATE_NEXT_KEY, None)
    body = (gate_result.gate_body or "").strip()
    if body:
        state.custom[_GATE_BODY_KEY] = body
    else:
        state.custom.pop(_GATE_BODY_KEY, None)


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    """Build template variable dict from state (no skill_runner import)."""
    del repo_root  # kept for skill_runner signature parity
    ensure_diagnose_custom(state)

    mode = str(state.custom.get("autonomy_mode", "guided"))
    complexity = str(state.custom.get("fix_complexity", "unknown"))
    hypothesis_min = int(state.custom.get("hypothesis_min", 5))
    hypothesis_gate = ""
    hypothesis_summary = "(Not evaluated yet)"
    five_whys_summary = "(Not evaluated yet)"
    technique_coverage_summary = "(Not evaluated yet)"
    first_principles_summary = "(Not evaluated yet)"
    mece_summary = "(Not evaluated yet)"
    problem_spec_summary = "(Not evaluated yet)"
    repro_loop_summary = "(Not evaluated yet)"
    diagnose_artifact_gate = ""

    state_dir_rel = ""
    if state_path is not None:
        from scripts.diagnose.diagnose_registers import state_dir_from_state_path

        sd = state_dir_from_state_path(state_path)
        state_dir_rel = repo_relative_path(sd)
        if step == 1:
            print(
                f"STATE DIR: {sd}  (write .diagnose-*.json here)\n",
                file=sys.stderr,
            )
        reg_file = register_path(sd)
        reg_data = load_register(reg_file)
        hypothesis_summary = summarize_register(reg_data)
        five_whys_summary = summarize_chains(load_five_whys(five_whys_register_path(sd)))
        technique_coverage_summary = summarize_coverage(load_coverage(coverage_path(sd)))
        first_principles_summary = summarize_fp(load_fp_register(fp_register_path(sd)))
        mece_summary = summarize_mece(load_mece_register(mece_register_path(sd)))
        problem_spec_summary = summarize_problem_spec(
            load_problem_spec_register(problem_spec_register_path(sd))
        )
        repro_loop_summary = summarize_repro_loop(
            load_repro_loop_register(repro_loop_register_path(sd))
        )
        if step >= 4 and reg_data:
            state.custom["hypothesis_register_summary"] = hypothesis_summary

    findings_text = ""
    if state.findings:
        for f in state.findings:
            status = f" [{f['status']}]" if f.get("status") != "open" else ""
            findings_text += (
                f"- **{f['id']}** ({f['severity']}): {f['title']}{status}\n"
                f"  {f['detail']}\n\n"
            )
    else:
        findings_text = "(No findings yet)"

    dispatch_text = ""
    if state.dispatches:
        for d in state.dispatches:
            agent = d.agent if hasattr(d, "agent") else d.get("agent", "?")
            d_step = d.step if hasattr(d, "step") else d.get("step", "?")
            done = d.completed if hasattr(d, "completed") else d.get("completed", False)
            mark = "done" if done else "pending"
            dispatch_text += f"- {agent} (step {d_step}): {mark}\n"
    else:
        dispatch_text = "(None yet)"

    gates = AUTONOMY_GATES.get(mode, AUTONOMY_GATES["guided"])
    if state.current_step in gates:
        autonomy_gate = (
            f"**AUTONOMY GATE ({mode} mode):** Pause here. Present findings to "
            f"the user and wait for approval before proceeding to the next phase."
        )
    else:
        autonomy_gate = (
            f"**Mode: {mode}** — No pause required at this phase. "
            f"Proceed directly to the next step."
        )

    if complexity == "simple":
        complexity_check = (
            "Complexity assessment: **SIMPLE** (<=2 files, no architectural changes).\n"
            "Proceed with implementation below."
        )
    elif complexity == "complex":
        complexity_check = (
            "Complexity assessment: **COMPLEX** (multi-file or architectural, but a single "
            "dominant implementation path is clear).\n"
            "Skip this phase. Hand off to **`plan`** then `implement`.\n"
            "Write the handoff file with root causes and recommended solution."
        )
    elif complexity == "large":
        complexity_check = (
            "Complexity assessment: **LARGE / SYSTEMIC** (under-specified solution space, "
            "major cross-subsystem trade-offs, or multiple viable architectures).\n"
            "Skip quick implementation in this phase. Hand off to **`design`** first for "
            "design/brainstorming, then **`plan`**.\n"
            "Write the handoff file with root causes, constraints, and known unknowns."
        )
    else:
        complexity_check = (
            "Complexity not yet assessed. Before proceeding, evaluate:\n"
            "- How many files does the fix touch?\n"
            "- Does it require architectural changes?\n"
            "- Is there one clear implementation shape, or are major design choices still open?\n\n"
            "If <=2 files and no architectural changes → set `fix_complexity` to `simple` and proceed.\n"
            "If multi-file / architectural **and** one dominant fix path → set to `complex` and hand off to `plan`.\n"
            "If systemic / multi-strategy / unclear best shape → set to `large` and hand off to `design` first."
        )

    variables: dict[str, str] = {
        "AUTONOMY_MODE": mode,
        "AUTONOMY_GATE": autonomy_gate,
        "FIX_COMPLEXITY": complexity,
        "COMPLEXITY_CHECK": complexity_check,
        "PREVIOUS_FINDINGS": findings_text.strip(),
        "DISPATCH_HISTORY": dispatch_text.strip(),
        "PLUGIN_ROOT": str(REPO_ROOT),
        "SCRIPT_DIR": str(SCRIPT_DIR),
        "STATE_DIR": state_dir_rel or ".forge/sessions/<id>",
        "HYPOTHESIS_MIN": str(hypothesis_min),
        "HYPOTHESIS_GATE": hypothesis_gate,
        "HYPOTHESIS_REGISTER_SUMMARY": hypothesis_summary,
        "FIVE_WHYS_SUMMARY": five_whys_summary,
        "TECHNIQUE_COVERAGE_SUMMARY": technique_coverage_summary,
        "FIRST_PRINCIPLES_SUMMARY": first_principles_summary,
        "MECE_SUMMARY": mece_summary,
        "PROBLEM_SPEC_SUMMARY": problem_spec_summary,
        "REPRO_LOOP_SUMMARY": repro_loop_summary,
        "DIAGNOSE_ARTIFACT_GATE": diagnose_artifact_gate,
        "FIVE_WHYS_GATE": diagnose_artifact_gate,
        "TECHNIQUE_COVERAGE_GATE": diagnose_artifact_gate,
        "QUARTET_GATE": diagnose_artifact_gate,
    }

    append = ""
    if state_path is not None and step >= 2:
        gate_result, step2_warning = resolve_step_gate(step, state, state_path)
        apply_gate_template_variables(variables, gate_result)
        if step in (2, 3, 4, 5, 7):
            _cache_soft_gate(state, gate_result)
        else:
            state.custom.pop(_GATE_PASSED_KEY, None)
            state.custom.pop(_GATE_NEXT_KEY, None)
            state.custom.pop(_GATE_BODY_KEY, None)
        if step2_warning:
            append += step2_warning
        seeded = append_complexity_gate_notes(step, "", state)
        if seeded:
            append += seeded
    else:
        state.custom.pop(_GATE_PASSED_KEY, None)
        state.custom.pop(_GATE_NEXT_KEY, None)
        state.custom.pop(_GATE_BODY_KEY, None)

    if state.quick_mode and step == 1:
        append += (
            "\n\n---\n\n"
            "**QUICK MODE:** Investigator-only. Skip full team dispatch.\n"
            "Phase 2 still requires a feedback loop (`.diagnose-feedback-loop.json`) "
            "before step 3; the step-3 gate applies in quick mode.\n"
            "Then abbreviated analyze, fix, and report.\n"
        )

    if append:
        variables["__APPEND__"] = append
    return variables


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    del repo_root
    complexity = str(state.custom.get("fix_complexity", "unknown"))
    return {
        "Root cause": str(state.custom.get("root_cause", "see report")),
        "Fix complexity": complexity,
        "Routing": routing_label_for_complexity(complexity),
        "Autonomy mode": str(state.custom.get("autonomy_mode", "guided")),
        "Open findings": str(len(state.open_findings())),
        "Suggested next": suggested_next_for_complexity(complexity),
    }
