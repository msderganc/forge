"""Evaluate template variables + findings sidecar ingest (no skill_runner import)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.evaluate.mode_detector import detect_mode, extract_file_references
from scripts.evaluate.plan_resolver import format_native_plan_hints
from scripts.shared.orchestrator import SkillState, _detect_repo_root, save_state


def findings_sidecar_path(state_dir: Path, step: int) -> Path:
    return state_dir / f".evaluate-findings-step{step}.json"


def ingest_findings_sidecars(state: SkillState, state_dir: Path, current_step: int) -> int:
    """Ingest prior-step findings sidecars (warn-and-skip malformed — do not harden)."""
    ingested = 0
    for step in range(1, current_step):
        sidecar = findings_sidecar_path(state_dir, step)
        if not sidecar.exists():
            continue
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(
                f"WARNING: skipping malformed findings sidecar {sidecar}: {e}",
                file=sys.stderr,
            )
            continue
        if not isinstance(data, list):
            print(
                f"WARNING: findings sidecar {sidecar} is not a JSON array, skipping",
                file=sys.stderr,
            )
            continue
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                state.add_finding(
                    phase=str(entry.get("phase", f"step{step}")),
                    severity=str(entry.get("severity", "warning")),
                    title=str(entry.get("title", "(untitled)")),
                    detail=str(entry.get("detail", "")),
                )
                ingested += 1
            except Exception as e:
                print(
                    f"WARNING: failed to add finding from {sidecar}: {e}",
                    file=sys.stderr,
                )
        try:
            sidecar.unlink()
        except OSError:
            pass
    return ingested


def ingest_findings_gate(
    *, state: SkillState, step: int, state_path: Path, gate: Any
) -> None:
    """Manifest python gate — ingest sidecars before rendering later steps."""
    del gate
    if step <= 1:
        return
    ingested = ingest_findings_sidecars(state, state_path.parent, step)
    if ingested:
        save_state(state, state_path)


def _max_step_for_mode(mode: str | None) -> int:
    if mode == "review":
        return 5
    if mode == "post":
        return 8
    return 7


def _ensure_step1_plan(state: SkillState, repo_root: Path) -> str:
    """Initialize plan/mode on step 1; return plan content."""
    plan_raw = str(state.custom.get("plan") or state.custom.get("plan_path") or "")
    if not plan_raw:
        return "(no plan)"
    plan_path = Path(plan_raw)
    if not plan_path.is_file():
        return f"(plan missing: {plan_raw})"
    plan_content = plan_path.read_text(encoding="utf-8")
    refs = extract_file_references(plan_content)
    plan_mtime = datetime.fromtimestamp(
        plan_path.stat().st_mtime, tz=timezone.utc
    ).isoformat()
    forced = state.custom.get("mode")
    if forced in ("pre", "post"):
        mode = str(forced)
    else:
        mode, _matched, _total = detect_mode(refs, str(repo_root), plan_mtime)
    state.custom["mode"] = mode
    state.custom["plan_path"] = str(plan_path.resolve())
    state.custom["plan_name"] = plan_path.stem
    state.custom["referenced_files"] = refs
    state.custom.setdefault("review_round", 0)

    from scripts.evaluate.evaluate_effort import (
        apply_size_to_custom,
        infer_size_from_plan,
    )

    quick = bool(state.custom.get("quick_mode") or state.quick_mode)
    size, size_rationale = infer_size_from_plan(
        plan_content,
        referenced_files=refs,
        cli_effort=state.custom.get("effort"),
        quick=quick,
    )
    apply_size_to_custom(state.custom, size, size_rationale, quick=quick)
    state.max_step = _max_step_for_mode(mode)
    return plan_content


def build_variables(
    state: SkillState,
    repo_root: Path,
    step: int = 1,
    state_path: Path | None = None,
) -> dict[str, str]:
    plan_content = "(no plan)"
    if step == 1 or not state.custom.get("plan_path"):
        plan_content = _ensure_step1_plan(state, repo_root)
        if state_path is not None:
            save_state(state, state_path)
    else:
        plan_path = Path(str(state.custom.get("plan_path") or ""))
        if plan_path.is_file():
            plan_content = plan_path.read_text(encoding="utf-8")

    findings_text = ""
    if state.findings:
        for f in state.findings:
            status = f" [{f['status']}]" if f.get("status") != "open" else ""
            note = f" — User: {f['user_note']}" if f.get("user_note") else ""
            findings_text += (
                f"- **{f['id']}** ({f['severity']}): {f['title']}{status}{note}\n"
                f"  {f['detail']}\n\n"
            )
    else:
        findings_text = "(No findings yet)"

    sidecar_path = ""
    if state_path is not None:
        sidecar_path = str(findings_sidecar_path(state_path.parent, step))

    mode = str(state.custom.get("mode") or "pre")
    probe_summary = "_Structural probes: not run (pre mode or no sidecar)._"
    state_dir = state_path.parent if state_path is not None else None
    if state.custom.get("structural_probes_sidecar") or state_dir:
        from scripts.shared.structural_probes import resolve_probe_summary_for_state

        probe_summary = (
            resolve_probe_summary_for_state(
                state.custom,
                state_dir,
                style="full" if step == _max_step_for_mode(mode) else "brief",
            ).strip()
            or probe_summary
        )

    return {
        "PLAN_CONTENT": plan_content,
        "PLAN_PATH": str(state.custom.get("plan_path") or ""),
        "PLAN_NAME": str(state.custom.get("plan_name") or ""),
        "MODE": mode,
        "REFERENCED_FILES": (
            ", ".join(state.custom.get("referenced_files") or [])
            if state.custom.get("referenced_files")
            else "(none extracted yet)"
        ),
        "PREVIOUS_FINDINGS": findings_text.strip(),
        "REVIEW_ROUND": str(state.custom.get("review_round") or 0),
        "QUICK_MODE_NOTE": (
            "Quick/minimal-scope mode: heavy phases may be skipped "
            f"(eval_size={state.custom.get('eval_size', 'unknown')})."
            if state.custom.get("quick_mode") or state.quick_mode
            else ""
        ),
        "FINDINGS_SIDECAR": sidecar_path,
        "NATIVE_PLAN_HINTS": format_native_plan_hints(_detect_repo_root(Path.cwd())),
        "STRUCTURAL_PROBES_SUMMARY": probe_summary,
    }


def build_handoff_context(state: SkillState, repo_root: Path) -> dict[str, str]:
    del repo_root
    return {
        "Plan": str(state.custom.get("plan_path") or ""),
        "Mode": str(state.custom.get("mode") or "pre"),
        "Findings": str(len(state.findings)),
    }
