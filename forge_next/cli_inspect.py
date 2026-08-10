"""forge status / doctor and JSON orchestrator output helpers."""

from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from forge_next import cli_runtime


def capture_human_output(
    module_name: str, argv: list[str], repo_root: Path
) -> tuple[str, int]:
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    rc = 0
    with redirect_stdout(buf_out), redirect_stderr(buf_err):
        try:
            rc = cli_runtime.run_module_main(module_name, argv, repo_root)
        except SystemExit as e:
            rc = int(e.code) if isinstance(e.code, int) else 1
        except Exception:
            rc = 1
    human = buf_out.getvalue()
    if buf_err.getvalue():
        human += ("\n" if human and not human.endswith("\n") else "") + buf_err.getvalue()
    return human, rc


def _parse_step_from_title(human_output: str) -> tuple[int | None, int | None]:
    """Parse ``(step, max_step)`` from orchestrator title lines."""
    import re

    match = re.search(r"\(Step\s+(\d+)\s+of\s+(\d+)\)", human_output)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _extract_structural_probes_summary(human_output: str) -> str | None:
    """Return structural probe markdown block when present in step output."""
    marker = "## Structural probes"
    start = human_output.find(marker)
    if start < 0:
        return None
    tail = human_output[start:]
    end = tail.find("\n---\n")
    block = tail[:end].strip() if end >= 0 else tail.strip()
    return block or None


def summarize_orchestrator_output(
    repo_root: Path, command: str, human_output: str
) -> dict:
    """Best-effort JSON summary based on orchestrator output format."""
    warnings: list[str] = []
    error: str | None = None
    state_path: str | None = None
    next_cmd: str | None = None

    for line in human_output.splitlines():
        if line.startswith("STATE FILE:"):
            state_path = line.replace("STATE FILE:", "", 1).strip()

    for line in reversed(human_output.splitlines()):
        stripped = line.strip()
        if "--step" not in stripped:
            continue
        if (
            stripped.startswith("forge ")
            or stripped.startswith("$forge-")
            or stripped.startswith("/forge-")
            or stripped.startswith("$forge:")
            or stripped.startswith("/forge:")
        ):
            next_cmd = stripped
            break

    phase_todos = []
    if "```json" in human_output:
        try:
            start = human_output.index("```json") + len("```json")
            end = human_output.index("```", start)
            block = human_output[start:end].strip()
            phase_todos = json.loads(block)
        except Exception:
            warnings.append("Failed to parse phase_todos JSON block.")

    step, max_step = _parse_step_from_title(human_output)
    structural_probes_summary = _extract_structural_probes_summary(human_output)

    return {
        "command": command,
        "repo_root": str(repo_root),
        "mode": None,
        "step": step,
        "max_step": max_step,
        "state_path": state_path,
        "next_cmd": next_cmd,
        "phase_todos": phase_todos,
        "structural_probes_summary": structural_probes_summary,
        "warnings": warnings,
        "error": error,
    }


def run_status(repo_root: Path, json_output: bool = False) -> None:
    from scripts.shared.orchestrator import (
        collect_session_leak_hints,
        collect_unreadable_state_files,
        detect_active_sessions,
        runtime_memory_dir,
        runtime_state_dir,
    )
    from scripts.shared.session_store import (
        format_sessions_table,
        run_session_cleanup,
        sessions_root,
    )

    old = Path.cwd()
    try:
        os.chdir(repo_root)
        run_session_cleanup(search_dir=repo_root)
        mem_dir = runtime_memory_dir(repo_root)
        state_dir = runtime_state_dir(repo_root)
        sess_dir = sessions_root(repo_root)
        sessions = detect_active_sessions(repo_root)
        leak_hints = collect_session_leak_hints(repo_root)
        state_issues = collect_unreadable_state_files(repo_root)
        from scripts.shared.structural_probes_gate import collect_probe_gate_hints

        probe_gate_hints = collect_probe_gate_hints(repo_root)
        warnings = [*leak_hints, *state_issues, *probe_gate_hints]

        if json_output:
            payload = {
                "command": "status",
                "repo_root": str(repo_root),
                "memory_dir": str(mem_dir),
                "state_dir": str(state_dir),
                "sessions_dir": str(sess_dir),
                "handoffs": [
                    p.name for p in sorted(mem_dir.glob("handoff-*.md"))
                ]
                if mem_dir.is_dir()
                else [],
                "active_sessions": [
                    {
                        "skill": s.get("skill"),
                        "session_id": s.get("session_id"),
                        "label": s.get("label"),
                        "current_step": s.get("current_step"),
                        "max_step": s.get("max_step"),
                        "path": str(s.get("path")),
                    }
                    for s in sessions
                ],
                "warnings": warnings,
                "error": None,
            }
            print(json.dumps(payload, ensure_ascii=True))
            return

        title = (
            "forge - status" if os.environ.get("FORGE_ASCII") == "1" else "forge — status"
        )
        print(title)
        print("=" * 60)
        print(f"Repo: {repo_root}")
        print(f"Memory: {mem_dir}")
        print(f"State:  {state_dir}")
        print(f"Sessions: {sess_dir}")
        print("")

        handoffs = sorted(mem_dir.glob("handoff-*.md")) if mem_dir.is_dir() else []
        print(f"Handoffs ({len(handoffs)}):")
        if handoffs:
            for p in handoffs:
                print(f"- {p.name}")
        else:
            print("- (none)")
        print("")
        print(f"Active sessions ({len(sessions)}):")
        if not sessions:
            print("- (none)")
        else:
            from scripts.shared.resume_context import load_resume_snapshot
            from scripts.shared.session_store import list_active_sessions

            infos = list_active_sessions(repo_root)
            snap, _ = load_resume_snapshot(repo_root)
            focus = (snap or {}).get("focus") if snap else None
            if focus:
                print(f"Focus: {focus}")
            if infos:
                print(format_sessions_table(infos, focus=focus))
            else:
                for s in sessions:
                    skill = s.get("skill")
                    cur = s.get("current_step")
                    mx = s.get("max_step")
                    path = s.get("path")
                    print(f"- {skill}: step {cur}/{mx} — {path}")
        if warnings:
            print("")
            print("Warnings:")
            for hint in warnings:
                print(f"- {hint}")
    finally:
        os.chdir(old)


def run_doctor(repo_root: Path, json_output: bool = False) -> None:
    from scripts.shared.session_store import run_session_cleanup

    run_session_cleanup(search_dir=repo_root)
    from forge_next.cli_doctor_checks import (
        check_beads,
        check_claude_graphify,
        check_codex_anchor,
        check_forge_path,
        check_runtime_state_dir,
        check_session_leaks,
        check_structural_tools,
        check_studio_assets,
        check_vendored_snapshots,
        check_workflow_prompts,
        collect_environment_checks,
    )

    warnings: list[str] = []
    checks: dict[str, object] = {"repo_root": str(repo_root)}
    env_checks, env_warn = collect_environment_checks()
    checks.update(env_checks)
    warnings.extend(env_warn)

    for partial, partial_warn in (
        check_codex_anchor(repo_root),
        check_runtime_state_dir(repo_root),
        check_forge_path(),
        check_claude_graphify(),
        check_studio_assets(),
        check_structural_tools(),
        check_beads(repo_root),
        check_vendored_snapshots(repo_root),
        check_workflow_prompts(),
    ):
        checks.update(partial)
        warnings.extend(partial_warn)

    warnings.extend(check_session_leaks(repo_root))
    from scripts.shared.structural_probes_gate import collect_probe_gate_hints
    from scripts.shared.runtime_adaptation import load_adaptation_profile

    probe_gate_hints = collect_probe_gate_hints(repo_root)
    warnings.extend(probe_gate_hints)
    checks["structural_probe_gates"] = probe_gate_hints
    adaptation = load_adaptation_profile(repo_root)
    checks["runtime_adaptation"] = adaptation or "(no .forge/adaptation.json yet)"

    payload = {
        "command": "doctor",
        "repo_root": str(repo_root),
        "checks": checks,
        "warnings": warnings,
        "error": None,
    }

    if json_output:
        print(json.dumps(payload, ensure_ascii=True))
        return

    title = "forge - doctor" if os.environ.get("FORGE_ASCII") == "1" else "forge — doctor"
    print(title)
    print("=" * 60)
    for k, v in checks.items():
        print(f"{k}: {v}")
    if warnings:
        print("")
        print("Warnings:")
        for w in warnings:
            print(f"- {w}")
