#!/usr/bin/env python3
"""E2E prompt walk: invoke every declarative skill step and verify prompts render.

Runs each skill's orchestrator through all steps (variants for evaluate/test),
injecting minimal gate sidecars / overrides so hard gates do not block prompt
render checks. Writes per-step stdout under ``.forge/e2e-prompt-walk/``.

Exit 0 when all skills pass; non-zero with a summary of failures.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / ".forge" / "e2e-prompt-walk"

SCRIPTS: dict[str, Path] = {
    "sketch": REPO / "scripts/sketch/sketch.py",
    "ship": REPO / "scripts/ship/ship.py",
    "ux-review": REPO / "scripts/ux_review/ux_review.py",
    "plan": REPO / "scripts/plan/plan.py",
    "implement": REPO / "scripts/implement/implement.py",
    "code-review": REPO / "scripts/code_review/code_review.py",
    "takeover": REPO / "scripts/takeover/takeover.py",
    "design": REPO / "scripts/design/design.py",
    "evaluate": REPO / "scripts/evaluate/evaluate.py",
    "test": REPO / "scripts/test/test.py",
    "diagnose": REPO / "scripts/diagnose/orchestrate.py",
}

# Expected substrings in rendered output (case-insensitive) proving the right prompt loaded.
PROMPT_MARKERS: dict[str, dict[int, list[str]]] = {
    "sketch": {
        1: ["sketch", "intent"],
        2: ["sketch", "session"],
        3: ["handoff", "sketch"],
    },
    "ship": {1: ["ship", "graphify"]},
    "ux-review": {
        1: ["ux", "orient"],
        2: ["plan"],
        3: ["walk"],
        4: ["state"],
        5: ["finding"],
        6: ["report"],
    },
    "plan": {
        1: ["plan", "context"],
        2: ["architect"],
        3: ["plan"],
        4: ["review"],
        5: ["approv"],
        6: ["document"],
        7: ["handoff"],
    },
    "implement": {
        1: ["implement", "plan"],
        2: ["branch"],
        3: ["wave"],
        4: ["review"],
        5: ["wave"],
        6: ["integrat"],
        7: ["document"],
        8: ["handoff"],
    },
    "code-review": {
        1: ["code-review", "target"],
        2: ["mode"],
        3: ["dispatch", "structural"],
        4: ["deep"],
        5: ["discuss"],
        6: ["report"],
    },
    "takeover": {1: ["takeover"], 2: ["takeover"], 6: ["takeover"]},
    "design": {
        1: ["design", "startup"],
        2: ["scope"],
        3: ["investigat"],
        4: ["review"],
        5: ["solution"],
        6: ["approv"],
        7: ["issue"],
        8: ["handoff"],
    },
    "evaluate:pre": {
        1: ["plan", "pars"],
        2: ["feasib"],
        3: ["complet"],
        4: ["align"],
        5: ["risk"],
        6: ["discuss"],
        7: ["report"],
    },
    "evaluate:post": {
        1: ["plan", "pars"],
        2: ["complet"],
        3: ["correct"],
        4: ["quality"],
        5: ["perform"],
        6: ["operational", "readiness"],
        7: ["discuss"],
        8: ["report"],
    },
    "test:run": {
        1: ["test", "context"],
        2: ["discover"],
        3: ["execution", "test"],
        5: ["coverage"],
        6: ["report"],
    },
    "test:flows": {
        1: ["flow", "context"],
        2: ["recommend"],
        3: ["scope"],
        4: ["scaffold"],
        5: ["author", "mock"],
        6: ["execut"],
        7: ["report", "handoff"],
    },
    "diagnose": {
        1: ["diagnose", "frame"],
        2: ["reproduc", "evidence"],
        3: ["5 why", "whys", "deepen"],
        4: ["analy"],
        5: ["solution"],
        6: ["validate", "fix", "implement"],
        7: ["report", "prevention"],
    },
    "plan:ceremony-light": {
        1: ["plan", "frame"],
        2: ["architect", "orient"],
    },
}


@dataclass
class StepResult:
    skill: str
    step: int
    ok: bool
    exit_code: int
    detail: str = ""
    out_chars: int = 0


@dataclass
class SkillResult:
    skill: str
    steps: list[StepResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["FORGE_SKIP_SESSION_OPTIN"] = "1"
    env["FORGE_SKIP_GRAPHIFY"] = "1"
    env["FORGE_SKIP_GRAPHIFY_SESSION_REFRESH"] = "1"
    env["FORGE_SKIP_AUTO_CLOSE"] = "1"
    return env


def _run(script: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=REPO,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _find_session(skill: str, label: str) -> Path | None:
    from scripts.shared.session_store import iter_session_json_paths
    from scripts.shared.skill_aliases import skills_match

    matches: list[Path] = []
    for path in iter_session_json_paths(REPO, include_archive=False):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not skills_match(str(data.get("skill_name", "")), skill):
            continue
        # label lives in index / custom; also match session id prefix from label
        sid = str(data.get("session_id") or path.parent.name)
        if label in sid or label in path.parent.name:
            matches.append(path)
            continue
        custom = data.get("custom") or {}
        if custom.get("label") == label or data.get("label") == label:
            matches.append(path)
    if matches:
        return max(matches, key=lambda p: p.stat().st_mtime)
    # Fallback: newest session for skill started in this walk window
    newest: Path | None = None
    newest_mtime = 0.0
    for path in iter_session_json_paths(REPO, include_archive=False):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if skills_match(str(data.get("skill_name", "")), skill):
            m = path.stat().st_mtime
            if m > newest_mtime:
                newest_mtime = m
                newest = path
    return newest


def _patch_state(state_path: Path, mutator) -> None:
    data = json.loads(state_path.read_text(encoding="utf-8"))
    mutator(data)
    state_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _inject_diagnose_overrides(state_path: Path) -> None:
    side = state_path.parent
    if state_path.name != "session.json":
        side = state_path.parent
    # Prefer session dir; also write under sidecars/ if used
    targets = [side, side / "sidecars"]
    for t in targets:
        t.mkdir(parents=True, exist_ok=True)

    problem = {
        "framing_entry": "evidence_snapshot",
        "problem_statement": "E2E prompt-walk synthetic incident for gate bypass validation",
        "activated_techniques": ["5 Whys"],
    }
    loop = {
        "loop_type": "command",
        "command_or_path": "python -c \"print('e2e')\"",
        "matches_user_report": True,
        "minimal_repro_steps": ["run command"],
        "artifact_paths": [],
    }
    five = {
        "version": 1,
        "symptom": "E2E synthetic failure",
        "chains": [
            {
                "id": "chain-1",
                "hypothesis_id": None,
                "layers": [
                    {
                        "level": 1,
                        "because": "Handler raises when config key missing",
                        "why_question": "Why does the handler raise?",
                        "evidence": "e2e",
                        "verdict": "confirmed",
                    },
                    {
                        "level": 2,
                        "because": "Config loader skips optional keys without defaults",
                        "why_question": "Why is the config key missing?",
                        "evidence": "e2e",
                        "verdict": "confirmed",
                    },
                    {
                        "level": 3,
                        "because": "Deploy template omitted the key after rename",
                        "why_question": "Why did the loader skip without defaults?",
                        "evidence": "e2e",
                        "verdict": "confirmed",
                    },
                ],
                "root_cause": "Deploy template omitted renamed config key",
                "stop_reason": "defect",
                "but_for": "Without the omitted key, the handler would not raise",
            }
        ],
    }

    for t in targets:
        (t / ".diagnose-problem-spec.json").write_text(json.dumps(problem), encoding="utf-8")
        (t / ".diagnose-feedback-loop.json").write_text(json.dumps(loop), encoding="utf-8")
        (t / ".diagnose-five-whys.json").write_text(json.dumps(five), encoding="utf-8")

    def mut(data: dict) -> None:
        c = data.setdefault("custom", {})
        for key in (
            "problem_spec_override_reason",
            "repro_loop_override_reason",
            "hypothesis_override_reason",
            "five_whys_override_reason",
            "technique_coverage_override_reason",
            "quartet_override_reason",
            "barriers_override_reason",
        ):
            c[key] = "e2e prompt-walk override"

    _patch_state(state_path, mut)


def _inject_implement_docs_gate(state_path: Path) -> None:
    side = state_path.parent
    gate = {
        "complete": True,
        "audience_matrix": [
            {"audience": "users", "artifact": "README.md", "status": "done"},
        ],
    }
    (side / ".implement-documentation-gate.json").write_text(
        json.dumps(gate), encoding="utf-8"
    )
    def mut(data: dict) -> None:
        c = data.setdefault("custom", {})
        c["docs_override_reason"] = "e2e prompt-walk"
        c["docs_override_requested_by"] = "e2e"
        c["docs_override_follow_up"] = "n/a"

    _patch_state(state_path, mut)


def _inject_plan_markers_cleared(state_path: Path) -> None:
    """Plan step 7 refuses completion while skeleton markers remain — patch plan file if present."""
    data = json.loads(state_path.read_text(encoding="utf-8"))
    plan_path = (data.get("custom") or {}).get("plan_path")
    if not plan_path:
        return
    p = Path(plan_path)
    if not p.is_file():
        return
    text = p.read_text(encoding="utf-8")
    # Replace common section markers with filler so gate can complete.
    cleaned = re.sub(r"<!--\s*FORGE_.*?-->", "E2E filled", text)
    cleaned = re.sub(r"\{\{[^}]+\}\}", "E2E filled", cleaned)
    if cleaned != text:
        p.write_text(cleaned, encoding="utf-8")


def _markers_for(skill_key: str, step: int) -> list[str]:
    table = PROMPT_MARKERS.get(skill_key, {})
    return table.get(step) or table.get(1) or [skill_key.split(":")[0]]


def _check_output(skill_key: str, step: int, stdout: str, stderr: str, code: int) -> StepResult:
    skill = skill_key.split(":")[0]
    low = stdout.lower()
    # Soft gates (ux-review): exit 1 but still render the prompt with a gate banner.
    soft_gate = code == 1 and (
        "plan gate" in low or "findings gate" in low or "gate — incomplete" in low
    )
    if code != 0 and not soft_gate:
        return StepResult(
            skill=skill_key,
            step=step,
            ok=False,
            exit_code=code,
            detail=f"exit {code}; stderr={stderr[-800:]}",
            out_chars=len(stdout),
        )
    if "traceback (most recent call last)" in low:
        return StepResult(skill_key, step, False, code, "traceback in stdout", len(stdout))
    if "error: template" in low or "filenotfounderror" in low:
        return StepResult(skill_key, step, False, code, "template load error", len(stdout))
    if "keyerror" in low:
        return StepResult(skill_key, step, False, code, "KeyError in output", len(stdout))
    # Header should mention skill
    header_ok = skill.replace("-", "") in low.replace("-", "") or skill in low
    if not header_ok and "forge" not in low:
        return StepResult(skill_key, step, False, code, "missing skill header", len(stdout))
    if len(stdout) < 200:
        return StepResult(skill_key, step, False, code, f"output too short ({len(stdout)})", len(stdout))
    markers = _markers_for(skill_key, step)
    missing = [m for m in markers if m.lower() not in low]
    # Allow partial: need at least one marker for the step
    if len(missing) == len(markers) and not soft_gate:
        return StepResult(
            skill_key,
            step,
            False,
            code,
            f"none of markers {markers!r} found",
            len(stdout),
        )
    detail = "ok (soft gate)" if soft_gate else "ok"
    return StepResult(skill_key, step, True, code, detail, len(stdout))


def _extract_state_path(stdout: str, stderr: str) -> Path | None:
    for text in (stderr, stdout):
        m = re.search(r"STATE FILE:\s*(.+\.json)", text)
        if m:
            p = Path(m.group(1).strip())
            if p.is_file():
                return p
        m = re.search(r"Resume context is saved at `([^`]+)`", text)
        if m:
            p = Path(m.group(1).strip())
            if p.is_file():
                return p
        m = re.search(r"\.forge[/\\]sessions[/\\]([a-zA-Z0-9_-]+)", text)
        if m:
            cand = REPO / ".forge" / "sessions" / m.group(1) / "session.json"
            if cand.is_file():
                return cand
    return None


def _inject_design_spec_sidecars(state_path: Path) -> None:
    side = state_path.parent
    spec_path = REPO / "docs" / "forge" / "specs" / "e2e-prompt-walk-design.md"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    if not spec_path.is_file():
        spec_path.write_text("# E2E design spec\n\nSynthetic spec for prompt walk.\n", encoding="utf-8")
    gate = {
        "spec_path": str(spec_path),
        "spec_written": True,
        "self_review_passed": True,
        "user_approved": True,
    }
    issues = {
        "spec_path": str(spec_path),
        "issues_written": True,
        "user_confirmed": True,
        "beads_mode": "none",
        "epic_id": None,
        "issues": [
            {
                "id": "e2e-1",
                "title": "E2E issue",
                "summary": "Synthetic issue for prompt walk",
                "spec_sections": ["Overview"],
                "acceptance_criteria": ["Prompt walk can complete design step 8"],
            }
        ],
    }
    # Prefer schema-shaped issues sidecar if required keys differ — write both names.
    (side / ".design-spec-gate.json").write_text(json.dumps(gate), encoding="utf-8")
    (side / ".design-spec-issues.json").write_text(json.dumps(issues), encoding="utf-8")

    def mut(data: dict) -> None:
        c = data.setdefault("custom", {})
        c["spec_required"] = True
        c["scope_tier"] = "medium"
        c["allow_spec_incomplete"] = True
        c["spec_override_reason"] = "e2e prompt-walk"
        c["spec_override_follow_up"] = "n/a"
        c["allow_issues_incomplete"] = True
        c["issues_override_reason"] = "e2e prompt-walk"
        c["issues_override_follow_up"] = "n/a"

    _patch_state(state_path, mut)


def _prepare_design(step: int, state_path: Path) -> None:
    if step >= 7:
        _inject_design_spec_sidecars(state_path)


def _prepare_flows(step: int, state_path: Path) -> None:
    """Inject recommendation sidecar so flows steps 3+ can render past the gate."""
    if step < 3:
        return
    sidecar = state_path.parent / ".test-recommendation-step2.json"
    if sidecar.is_file():
        return
    sidecar.write_text(
        json.dumps(
            {
                "chosen": "scenario",
                "reasoning": "e2e prompt-walk default scenario flows",
                "confidence": 0.9,
                "alternatives": ["bdd"],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    def mut(c: dict) -> None:
        c["mode"] = "flows"
        c["flow_type"] = "scenario"
        c.setdefault("framework", "pytest")
        c.setdefault("entry_point", "cli")
        c.setdefault("roles", ["anonymous"])

    _patch_state(state_path, mut)


def walk_skill(
    skill: str,
    *,
    label: str,
    max_step: int,
    extra_args: list[str] | None = None,
    skill_key: str | None = None,
    before_step=None,
) -> SkillResult:
    key = skill_key or skill
    script = SCRIPTS[skill]
    result = SkillResult(skill=key)
    extra = list(extra_args or [])
    state_path: Path | None = None
    session_id: str | None = None

    skill_out = OUT / key.replace(":", "_")
    skill_out.mkdir(parents=True, exist_ok=True)

    for step in range(1, max_step + 1):
        if before_step is not None and state_path is not None:
            before_step(step, state_path)

        args = ["--step", str(step), "--label", label, *extra]
        if session_id:
            args.extend(["--session", session_id])
        elif state_path is not None:
            args.extend(["--state", str(state_path)])

        # Design late-step overrides
        if skill == "design" and step >= 7:
            args.extend(
                [
                    "--allow-spec-incomplete",
                    "--spec-override-reason",
                    "e2e prompt-walk",
                    "--spec-override-follow-up",
                    "n/a",
                    "--allow-issues-incomplete",
                    "--issues-override-reason",
                    "e2e prompt-walk",
                    "--issues-override-follow-up",
                    "n/a",
                ]
            )
        if skill == "code-review":
            args.extend(
                [
                    "--allow-structural-probes-incomplete",
                    "--structural-probes-override-reason",
                    "e2e prompt-walk",
                    "--structural-probes-override-follow-up",
                    "n/a",
                ]
            )
        if skill == "implement" and step >= 7:
            args.extend(
                [
                    "--allow-docs-incomplete",
                    "--docs-override-reason",
                    "e2e prompt-walk",
                    "--docs-override-follow-up",
                    "n/a",
                ]
                if _has_flag(script, "--allow-docs-incomplete")
                else []
            )

        try:
            proc = _run(script, args)
        except subprocess.TimeoutExpired:
            result.steps.append(
                StepResult(key, step, False, -1, "timeout", 0)
            )
            break

        (skill_out / f"step-{step}.out.txt").write_text(proc.stdout or "", encoding="utf-8")
        (skill_out / f"step-{step}.err.txt").write_text(proc.stderr or "", encoding="utf-8")

        step_res = _check_output(key, step, proc.stdout or "", proc.stderr or "", proc.returncode)
        result.steps.append(step_res)

        # Resolve session/state after each step (evaluate uses plan-adjacent flat state).
        extracted = _extract_state_path(proc.stdout or "", proc.stderr or "")
        if extracted is not None:
            state_path = extracted
            if extracted.name == "session.json":
                session_id = extracted.parent.name
            else:
                # Prefer --state for flat evaluate files (session id not applicable).
                session_id = None

        if state_path is None:
            found = _find_session(skill, label)
            if found is not None:
                state_path = found
                session_id = found.parent.name if found.name == "session.json" else None

        if not step_res.ok:
            # Continue only if we still have state for diagnosis; else stop skill
            if state_path is None or not state_path.exists():
                break
            # For hard failures continue trying later steps only when session survives
            if "ERROR" in (proc.stderr or "") and "gate" in (proc.stderr or "").lower():
                break

    return result


_FLAG_CACHE: dict[str, bool] = {}


def _has_flag(script: Path, flag: str) -> bool:
    key = f"{script}:{flag}"
    if key in _FLAG_CACHE:
        return _FLAG_CACHE[key]
    try:
        proc = _run(script, ["--help"], timeout=30)
        ok = flag in (proc.stdout or "") + (proc.stderr or "")
    except Exception:
        ok = False
    _FLAG_CACHE[key] = ok
    return ok


def _prepare_diagnose(step: int, state_path: Path) -> None:
    if step >= 2:
        _inject_diagnose_overrides(state_path)


def _prepare_implement(step: int, state_path: Path) -> None:
    if step >= 7:
        _inject_implement_docs_gate(state_path)


def _prepare_plan(step: int, state_path: Path) -> None:
    if step >= 7:
        _inject_plan_markers_cleared(state_path)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    label_base = "e2e-prompt-walk"
    results: list[SkillResult] = []

    plan_file = REPO / ".forge/memory/plans/20260730-1520-plan.md"
    if not plan_file.is_file():
        # Any plan-like markdown for evaluate
        plans = list((REPO / ".forge/memory/plans").glob("*.md")) if (REPO / ".forge/memory/plans").is_dir() else []
        plan_file = plans[0] if plans else REPO / "README.md"

    walk_specs: list[tuple] = [
        ("sketch", 3, [], None, None),
        ("ship", 1, [], None, None),
        ("ux-review", 6, [], None, None),
        ("plan", 7, ["--mode", "lite", "--force"], None, _prepare_plan),
        ("implement", 8, [], None, _prepare_implement),
        ("code-review", 6, ["--mode", "deep"], None, None),
        ("takeover", 6, ["--goal", "e2e prompt-walk ship-ready check"], None, None),
        ("design", 8, [], None, _prepare_design),
        (
            "evaluate",
            7,
            ["--mode", "pre", "--plan", str(plan_file)],
            "evaluate:pre",
            None,
        ),
        (
            "evaluate",
            8,
            ["--mode", "post", "--plan", str(plan_file)],
            "evaluate:post",
            None,
        ),
        ("test", 6, ["--mode", "run"], "test:run", None),
        (
            "test",
            7,
            ["--mode", "flows", "--flow-type", "scenario"],
            "test:flows",
            _prepare_flows,
        ),
        (
            "plan",
            2,
            ["--mode", "lite", "--force", "--ceremony", "light"],
            "plan:ceremony-light",
            None,
        ),
        ("diagnose", 7, [], None, _prepare_diagnose),
    ]

    print("E2E skill prompt walk")
    print("=" * 60)
    print(f"Artifacts: {OUT}")
    print()

    for skill, max_step, extra, skill_key, before in walk_specs:
        key = skill_key or skill
        label = f"{label_base}-{key.replace(':', '-')}"
        print(f"--- {key} (steps 1..{max_step}) ---")
        try:
            res = walk_skill(
                skill,
                label=label,
                max_step=max_step,
                extra_args=extra,
                skill_key=key,
                before_step=before,
            )
        except Exception as exc:
            res = SkillResult(skill=key)
            res.steps.append(
                StepResult(key, 0, False, -1, f"exception: {exc}\n{traceback.format_exc()}", 0)
            )
        results.append(res)
        for s in res.steps:
            mark = "PASS" if s.ok else "FAIL"
            print(f"  [{mark}] step {s.step}: {s.detail} ({s.out_chars} chars, exit={s.exit_code})")
        print()

    summary = OUT / "summary.json"
    payload = {
        "skills": [
            {
                "skill": r.skill,
                "ok": r.ok,
                "steps": [
                    {
                        "step": s.step,
                        "ok": s.ok,
                        "exit_code": s.exit_code,
                        "detail": s.detail,
                        "out_chars": s.out_chars,
                    }
                    for s in r.steps
                ],
            }
            for r in results
        ]
    }
    summary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    failed = [r for r in results if not r.ok]
    print("=" * 60)
    if not failed:
        print(f"ALL PASS — {len(results)} skill walks")
        return 0
    print(f"FAILED {len(failed)}/{len(results)} skill walks:")
    for r in failed:
        bad = [s for s in r.steps if not s.ok]
        print(f"  - {r.skill}: " + "; ".join(f"step {s.step} ({s.detail})" for s in bad))
    return 1


if __name__ == "__main__":
    sys.exit(main())
