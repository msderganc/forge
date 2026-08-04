"""Takeover gate-wait escapes for declarative engine (no skill_runner import)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.shared.orchestrator import (
    SkillState,
    clear_state_file,
    now_iso,
    runtime_memory_dir,
    save_state,
)
from scripts.takeover.deviations import write_deviations, write_summary
from scripts.takeover.takeover_legacy import (
    DEFAULT_MAX_INNER,
    _child_resume_command,
    _ensure_gates_dir,
    _gate_ref,
    _handle_primary_then_metric_stage,
    _metric_gate_not_equal,
    _metric_gate_open,
    _read_gate,
    _route_plan_from_custom,
)


def run_takeover_gate_step(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Python escape for takeover steps 2–6 — gate waits set ``_await_same_step``."""
    del gate
    if step < 2:
        return

    gd = _ensure_gates_dir()
    plan = _route_plan_from_custom(state.custom)
    max_inner = int(state.custom.get("max_inner", DEFAULT_MAX_INNER))
    goal = str(state.custom.get("goal", "ship-ready"))
    dev = state.custom.setdefault("deviations", {})

    body = ""
    await_gate = False

    if step == 2:
        if plan and plan.active_session_path:
            cmd = _child_resume_command(
                plan.entry_skill, plan.active_session_path, plan.active_session_id
            )
            body = (
                f"## Continue active session\n\nRun:\n\n`{cmd}`\n\n"
                "When the child skill completes its handoff, write "
                f"{_gate_ref('upstream.json')} with "
                '`{"status": "pass"}` and re-run **step 2**.'
            )
            await_gate = True
        elif plan and plan.upstream_skills:
            g = _read_gate(gd / "upstream.json")
            if not g or g.get("status") != "pass":
                skills = ", ".join(plan.upstream_skills)
                body = (
                    f"## Upstream ({skills})\n\n"
                    f"Complete upstream skills: **{skills}**. "
                    f"Write {_gate_ref('upstream.json')} with `status: pass` when "
                    "intent/design is ready."
                )
                await_gate = True
            else:
                state.mark_step_complete(2)
                body = "## Upstream complete\n\nProceed to **step 3** (plan)."
        else:
            state.mark_step_complete(2)
            body = "## Upstream skipped\n\nRun **step 3** for plan + evaluate (pre)."

    elif step == 3:
        skip_eval = bool(plan and plan.skip_evaluate)
        if plan and plan.short_circuit_to_test and skip_eval:
            if _read_gate(gd / "implement.json") or _read_gate(gd / "test.json"):
                state.mark_step_complete(3)
                state.mark_step_complete(4)
                body = (
                    "## Short-circuit (simple diagnose)\n\n"
                    "Small/simple fix path — plan + evaluate skipped. Run **step 5** "
                    f"(code-review `--effort {plan.code_review_effort}` + test)."
                )
            else:
                body, _log, awaiting = _handle_primary_then_metric_stage(
                    gd,
                    state,
                    primary_gate="plan.json",
                    primary_body=(
                        f"## Plan\n\nComplete **plan** (lite). Write {_gate_ref('plan.json')} "
                        "with `status: pass`."
                    ),
                    secondary_gate="evaluate-pre.json",
                    metric_key="open_findings_total",
                    inner_key="inner_eval_pre",
                    inner=int(state.custom.get("inner_eval_pre", 0)),
                    max_inner=max_inner,
                    cap_body=f"## Evaluate (pre) — inner cap ({max_inner})",
                    pending_body="",
                    pass_body=(
                        "## Plan clean (evaluate skipped — small scope)\n\n"
                        "Run **step 4** for implement."
                    ),
                    complete_step=3,
                    await_primary_log="Await plan gate",
                    pending_log="Evaluate pre pending",
                    pass_log="Plan pass (eval skipped)",
                    skip_secondary=True,
                    skip_secondary_body=(
                        "## Plan clean (evaluate skipped — small scope)\n\n"
                        "Run **step 4** for implement."
                    ),
                )
                await_gate = awaiting
        else:
            body, _log, awaiting = _handle_primary_then_metric_stage(
                gd,
                state,
                primary_gate="plan.json",
                primary_body=(
                    f"## Plan\n\nComplete **plan**. Write {_gate_ref('plan.json')} "
                    "with `status: pass`."
                ),
                secondary_gate="evaluate-pre.json",
                metric_key="open_findings_total",
                inner_key="inner_eval_pre",
                inner=int(state.custom.get("inner_eval_pre", 0)),
                max_inner=max_inner,
                cap_body=f"## Evaluate (pre) — inner cap ({max_inner})",
                pending_body=(
                    "## Evaluate (pre)\n\nRun **evaluate** pre mode. "
                    f"Write {_gate_ref('evaluate-pre.json')} with `blocking_findings: 0` "
                    "(critical+warning only; suggestions advisory)."
                ),
                pass_body="## Plan + evaluate (pre) clean\n\nRun **step 4** for implement.",
                complete_step=3,
                await_primary_log="Await plan gate",
                pending_log="Evaluate pre pending",
                pass_log="Plan + eval pre pass",
                skip_secondary=skip_eval,
                skip_secondary_body=(
                    "## Plan clean (evaluate skipped — small scope)\n\n"
                    "Run **step 4** for implement."
                ),
            )
            await_gate = awaiting

    elif step == 4:
        skip_eval = bool(plan and plan.skip_evaluate)
        body, _log, awaiting = _handle_primary_then_metric_stage(
            gd,
            state,
            primary_gate="implement.json",
            primary_body=(
                f"## Implement\n\nComplete **implement**. Write {_gate_ref('implement.json')} "
                "with `status: pass`."
            ),
            secondary_gate="evaluate-post.json",
            metric_key="open_findings_total",
            inner_key="inner_eval_post",
            inner=int(state.custom.get("inner_eval_post", 0)),
            max_inner=max_inner,
            cap_body="## Evaluate (post) — inner cap",
            pending_body=(
                "## Evaluate (post)\n\nRun **evaluate** post mode. "
                f"Write {_gate_ref('evaluate-post.json')} with `blocking_findings: 0` "
                "(critical+warning only; suggestions advisory)."
            ),
            pass_body="## Implement + evaluate (post) clean\n\nRun **step 5**.",
            complete_step=4,
            await_primary_log="Await implement gate",
            pending_log="Evaluate post pending",
            pass_log="Implement stage pass",
            skip_secondary=skip_eval,
            skip_secondary_body=(
                "## Implement clean (evaluate skipped — small scope)\n\nRun **step 5**."
            ),
        )
        await_gate = awaiting

    elif step == 5:
        inner = int(state.custom.get("inner_cr", 0))
        cr_effort = (plan.code_review_effort if plan else "standard") or "standard"
        if _metric_gate_open(gd, "code-review.json", "open_findings_total"):
            inner += 1
            state.custom["inner_cr"] = inner
            if inner > max_inner:
                body = "## Code review — inner cap"
                state.mark_step_complete(5)
            else:
                body = (
                    f"## Code review\n\nRun **code-review --effort {cr_effort}** "
                    "(structural review always on). "
                    f"Write {_gate_ref('code-review.json')} with `blocking_findings: 0` "
                    "(critical+warning only; suggestions advisory)."
                )
                await_gate = True
        elif _metric_gate_not_equal(gd, "test.json", "failed", 0):
            body = (
                f"## Test\n\nRun **test** (run mode). Write {_gate_ref('test.json')} "
                "with `failed: 0`."
            )
            await_gate = True
        else:
            state.mark_step_complete(5)
            state.custom["ship_ready"] = True
            state.custom["inner_cr"] = 0
            body = (
                "## Ship-ready gates passed\n\n"
                "Run **step 6** for report + handoff to ship."
            )

    elif step == 6:
        sidecar = state_path.parent / "sidecars" / ".takeover-deviations.json"
        sidecar.parent.mkdir(parents=True, exist_ok=True)
        write_deviations(sidecar, dev if isinstance(dev, dict) else {})
        mem = runtime_memory_dir()
        write_summary(
            mem / "takeover-summary.md",
            dev if isinstance(dev, dict) else {},
            outcome="ship_ready",
            goal=goal,
        )
        state.custom["ship_ready"] = True
        body = "\n".join(
            [
                "## Takeover — complete",
                "",
                f"**Goal:** {goal}",
                "**Outcome:** ship-ready quality gates passed.",
                "",
                f"Deviations: `{sidecar}`",
                f"Summary: `{mem / 'takeover-summary.md'}`",
            ]
        )

    state.current_step = step
    # Prefer replacing body via _append_body (prompt is {{BODY}} which may be empty)
    state.custom["_append_body"] = body
    if await_gate:
        state.custom["_await_same_step"] = True
    save_state(state, state_path)
