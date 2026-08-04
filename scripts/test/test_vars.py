"""Test skill template variables (no skill_runner import)."""

from __future__ import annotations

from pathlib import Path

from scripts.shared.orchestrator import (
    SkillState,
    consume_handoff,
    read_memory_file,
    save_state,
)
from scripts.test.test_legacy import _build_variables as _legacy_build_variables
from scripts.test.test_legacy import _normalize_target


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    del repo_root
    mode = str(state.custom.get("mode") or "run")
    if step == 1:
        if not state.custom.get("handoff_code_review"):
            state.custom["handoff_code_review"] = consume_handoff("code-review")
        if not state.custom.get("handoff_implement"):
            state.custom["handoff_implement"] = consume_handoff("implement")
        if "project_context" not in state.custom:
            state.custom["project_context"] = read_memory_file("project.md")
        if "test_results" not in state.custom:
            state.custom["test_results"] = {
                "passed": 0,
                "failed": 0,
                "skipped": 0,
                "total": 0,
                "coverage_pct": "N/A",
            }
        if "test_suites" not in state.custom:
            state.custom["test_suites"] = []
        # Normalize target if still a list
        target = state.custom.get("target")
        if isinstance(target, list):
            joined, tokens = _normalize_target(target)
            state.custom["target"] = joined
            state.custom["target_tokens"] = tokens
        if mode == "flows":
            from scripts.test.test_flows import (
                initialize_flow_custom,
                prepare_flow_step_1,
            )
            import argparse

            ns = argparse.Namespace(
                flow_type=state.custom.get("flow_type"),
                framework=state.custom.get("framework"),
                entry_point=state.custom.get("entry_point"),
                no_db=bool(state.custom.get("no_db")),
                roles=state.custom.get("roles")
                if isinstance(state.custom.get("roles"), str)
                else (
                    ",".join(state.custom["roles"])
                    if isinstance(state.custom.get("roles"), list)
                    else None
                ),
            )
            if "flow_files" not in state.custom:
                initialize_flow_custom(state, ns)
            if state_path is not None:
                # Pre-write recommendation sidecar when --flow-type overrides.
                prepare_flow_step_1(state_path, state.custom.get("flow_type"))
        if state_path is not None:
            save_state(state, state_path)

    # Recommendation ingest is a declared flows step-3 gate (schema + python).
    # Do not ingest here — gates run after vars and need the sidecar on disk.

    return _legacy_build_variables(state, state_path)


def ingest_recommendation_gate(
    *, state: SkillState, step: int, state_path: Path, gate: object
) -> None:
    """Manifest python gate — ingest recommendation sidecar after schema shape check."""
    del gate
    if step != 3:
        return
    if str(state.custom.get("mode") or "") != "flows":
        return
    from scripts.test._sidecar import ingest_recommendation_sidecar

    rec = ingest_recommendation_sidecar(state_path.parent)
    state.custom["recommendation"] = rec
    if rec.get("chosen"):
        state.custom["flow_type"] = rec["chosen"]
    save_state(state, state_path)


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    del repo_root
    results = state.custom.get("test_results") or {}
    return {
        "Mode": str(state.custom.get("mode") or "run"),
        "Target": str(state.custom.get("target") or ""),
        "Passed": str(results.get("passed", 0)),
        "Failed": str(results.get("failed", 0)),
    }
