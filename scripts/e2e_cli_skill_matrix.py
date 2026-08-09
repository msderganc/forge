#!/usr/bin/env python3
"""Comprehensive forge CLI matrix: 3+ scenarios per skill.

Runs against the `forge` binary on PATH (or FORGE_BIN). Writes a JSON report
and exits non-zero on any failure.

This exercises the outer CLI path agents actually use — not scripts/*.py.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

FORGE = os.environ.get("FORGE_BIN", "forge")
OUT = Path(os.environ.get("MATRIX_OUT", ".forge/e2e-cli-matrix"))


@dataclass
class CaseResult:
    skill: str
    case: str
    ok: bool
    exit_code: int
    detail: str
    evidence: list[str] = field(default_factory=list)
    state: dict = field(default_factory=dict)


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env["FORGE_SKIP_SESSION_OPTIN"] = "1"
    env["FORGE_SKIP_GRAPHIFY"] = "1"
    env["FORGE_SKIP_GRAPHIFY_REFRESH"] = "1"
    env["FORGE_SKIP_STRUCTURAL_TOOLS"] = "1"
    env["FORGE_SKIP_AUTO_CLOSE"] = "1"
    return env


def _run(argv: list[str], cwd: Path, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [FORGE, *argv, "--repo", str(cwd)],
        cwd=cwd,
        env=_env(),
        capture_output=True,
        text=True,
        timeout=timeout,
        encoding="utf-8",
        errors="replace",
    )


def _init_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / "README.md").write_text("# matrix\n", encoding="utf-8")
    (root / "foo.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md", "foo.py"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=root,
        check=True,
    )
    plans = root / ".forge" / "memory" / "plans"
    plans.mkdir(parents=True, exist_ok=True)
    plan = plans / "matrix-plan.md"
    plan.write_text(
        "# Matrix plan\n\n## Goal\nCLI matrix validation.\n\n## Tasks\n\n"
        "| Task | Files | Verify | Expected |\n"
        "|------|-------|--------|----------|\n"
        "| T1 write foo | foo.py | python -c \"import foo\" | imports |\n"
        "| T2 docs | README.md | test -f README.md | exists |\n",
        encoding="utf-8",
    )
    return plan


def _wipe_sessions(root: Path) -> None:
    sess = root / ".forge" / "sessions"
    if sess.exists():
        shutil.rmtree(sess)
    # evaluate sidecar
    for p in (root / ".forge").rglob(".evaluate-state.json"):
        p.unlink(missing_ok=True)


def _load_state(root: Path) -> dict:
    """Load ceremony-bearing state from session.json or evaluate sidecar."""
    sessions = []
    sess_root = root / ".forge" / "sessions"
    if sess_root.exists():
        sessions = sorted(
            [p for p in sess_root.glob("*/session.json") if "_archive" not in str(p)],
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    if sessions:
        data = json.loads(sessions[0].read_text(encoding="utf-8"))
        custom = data.get("custom") or {}
        return {
            "path": str(sessions[0]),
            "skill": data.get("skill_name"),
            "ceremony": custom.get("ceremony"),
            "ceremony_source": custom.get("ceremony_source"),
            "plan_mode": custom.get("plan_mode"),
            "mode": custom.get("mode"),
        }
    eval_state = root / ".forge" / "memory" / "plans" / ".evaluate-state.json"
    if eval_state.is_file():
        data = json.loads(eval_state.read_text(encoding="utf-8"))
        custom = data.get("custom") or {}
        return {
            "path": str(eval_state),
            "skill": "evaluate",
            "ceremony": custom.get("ceremony"),
            "ceremony_source": custom.get("ceremony_source"),
            "plan_mode": custom.get("plan_mode"),
            "mode": custom.get("mode"),
        }
    return {}


def _evidence(text: str, patterns: list[str]) -> list[str]:
    hits: list[str] = []
    for i, line in enumerate(text.splitlines(), 1):
        for pat in patterns:
            if re.search(pat, line, re.I):
                hits.append(f"{i}:{line.strip()[:140]}")
                break
    return hits[:20]


def check(
    root: Path,
    *,
    skill: str,
    case: str,
    argv: list[str],
    expect_exit: set[int] | None = None,
    require_substrings: list[str] | None = None,
    forbid_substrings: list[str] | None = None,
    expect_ceremony: str | None = None,
    expect_ceremony_source: str | None = None,
    expect_plan_mode: str | None = None,
    expect_reject_ceremony: bool = False,
) -> CaseResult:
    _wipe_sessions(root)
    expect_exit = expect_exit or {0, 1}  # 1 = soft gates / continuation prompts ok
    try:
        proc = _run(argv, root)
    except subprocess.TimeoutExpired:
        return CaseResult(skill, case, False, -1, "timeout")
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    low = text.lower()
    evidence = _evidence(
        text,
        [
            r"ceremony",
            r"Active:",
            r"unrecognized arguments",
            r"Frame",
            r"Orient",
            r"selection \(required\)",
            r"STATE FILE",
            r"error:",
        ],
    )
    state = _load_state(root)
    problems: list[str] = []

    if expect_reject_ceremony:
        if "unrecognized arguments: --ceremony" not in low:
            problems.append("expected CLI to reject --ceremony")
        ok = proc.returncode != 0 and not problems
        return CaseResult(
            skill,
            case,
            ok,
            proc.returncode,
            "ok" if ok else "; ".join(problems) or f"exit {proc.returncode}",
            evidence,
            state,
        )

    if proc.returncode not in expect_exit:
        problems.append(f"exit {proc.returncode} not in {sorted(expect_exit)}")
    if "traceback (most recent call last)" in low:
        problems.append("traceback in output")
    for s in require_substrings or []:
        if s.lower() not in low:
            problems.append(f"missing substring {s!r}")
    for s in forbid_substrings or []:
        if s.lower() in low:
            problems.append(f"forbidden substring {s!r}")
    if expect_ceremony is not None and state.get("ceremony") != expect_ceremony:
        problems.append(
            f"ceremony want={expect_ceremony!r} got={state.get('ceremony')!r}"
        )
    if expect_ceremony_source is not None and state.get("ceremony_source") != expect_ceremony_source:
        problems.append(
            f"source want={expect_ceremony_source!r} got={state.get('ceremony_source')!r}"
        )
    if expect_plan_mode is not None and state.get("plan_mode") != expect_plan_mode:
        problems.append(
            f"plan_mode want={expect_plan_mode!r} got={state.get('plan_mode')!r}"
        )

    ok = not problems
    return CaseResult(
        skill,
        case,
        ok,
        proc.returncode,
        "ok" if ok else "; ".join(problems),
        evidence,
        state,
    )


def build_cases(root: Path, plan: Path) -> list[CaseResult]:
    rel_plan = str(plan.relative_to(root))
    cases: list[CaseResult] = []

    # ---- sketch (3+) ----
    cases.append(check(root, skill="sketch", case="step1", argv=["sketch", "--step", "1"],
                       require_substrings=["sketch"]))
    cases.append(check(root, skill="sketch", case="domain-docs",
                       argv=["sketch", "--step", "1", "--with-domain-docs"],
                       require_substrings=["sketch"]))
    cases.append(check(root, skill="sketch", case="reject-ceremony",
                       argv=["sketch", "--step", "1", "--ceremony", "light"],
                       expect_reject_ceremony=True))

    # ---- design (3+) ----
    for band in ("light", "detailed", "comprehensive"):
        cases.append(check(
            root, skill="design", case=f"ceremony-{band}",
            argv=["design", "--step", "1", "--ceremony", band, "--label", f"d-{band}"],
            require_substrings=["design"],
            expect_ceremony=band, expect_ceremony_source="cli",
        ))
    cases.append(check(
        root, skill="design", case="estimated-no-flag",
        argv=["design", "--step", "1", "--label", "d-est"],
        require_substrings=["design"],
    ))

    # ---- plan (5) ----
    cases.append(check(
        root, skill="plan", case="ceremony-light",
        argv=["plan", "--step", "1", "--ceremony", "light", "--force", "--label", "p-light"],
        require_substrings=["**Active:** `light`", "no confirmation needed"],
        forbid_substrings=["Ceremony selection (required)"],
        expect_ceremony="light", expect_ceremony_source="cli", expect_plan_mode="lite",
    ))
    cases.append(check(
        root, skill="plan", case="ceremony-medium",
        argv=["plan", "--step", "1", "--ceremony", "medium", "--force", "--label", "p-med"],
        require_substrings=["**Active:** `medium`", "no confirmation needed"],
        forbid_substrings=["Ceremony selection (required)"],
        expect_ceremony="medium", expect_ceremony_source="cli", expect_plan_mode="default",
    ))
    cases.append(check(
        root, skill="plan", case="ceremony-comprehensive",
        argv=["plan", "--step", "1", "--ceremony", "comprehensive", "--force", "--label", "p-comp"],
        require_substrings=["**Active:** `comprehensive`"],
        forbid_substrings=["Ceremony selection (required)"],
        expect_ceremony="comprehensive", expect_ceremony_source="cli", expect_plan_mode="default",
    ))
    cases.append(check(
        root, skill="plan", case="prompt-selection",
        argv=["plan", "--step", "1", "--force", "--label", "p-ask"],
        require_substrings=[
            "Ceremony selection (required)",
            "`light`",
            "`medium`",
            "`detailed`",
            "`comprehensive`",
            "Do **not** offer only",
        ],
    ))
    cases.append(check(
        root, skill="plan", case="legacy-mode-lite",
        argv=["plan", "--step", "1", "--mode", "lite", "--force", "--label", "p-mode"],
        require_substrings=["Ceremony", "no confirmation needed"],
        forbid_substrings=["Ceremony selection (required)"],
        expect_ceremony="light",
        expect_plan_mode="lite",
    ))
    cases.append(check(
        root, skill="plan", case="legacy-mode-default",
        argv=["plan", "--step", "1", "--mode", "default", "--force", "--label", "p-def"],
        require_substrings=["Ceremony", "no confirmation needed"],
        forbid_substrings=["Ceremony selection (required)"],
        expect_ceremony="medium",
        expect_plan_mode="default",
    ))

    # ---- develop alias (3+) ----
    for band in ("light", "medium", "detailed"):
        cases.append(check(
            root, skill="develop", case=f"ceremony-{band}",
            argv=["develop", "--step", "1", "--ceremony", band, "--label", f"dv-{band}"],
            require_substrings=["design"],
            expect_ceremony=band, expect_ceremony_source="cli",
        ))

    # ---- evaluate (3+) ----
    for band, mode in (("light", "pre"), ("medium", "post"), ("detailed", "pre")):
        cases.append(check(
            root, skill="evaluate", case=f"{mode}-ceremony-{band}",
            argv=["evaluate", "--step", "1", "--mode", mode, "--plan", rel_plan,
                  "--ceremony", band, "--label", f"e-{mode}-{band}"],
            require_substrings=["evaluate", "plan"],
            expect_ceremony=band, expect_ceremony_source="cli",
        ))
    cases.append(check(
        root, skill="evaluate", case="pre-estimated",
        argv=["evaluate", "--step", "1", "--mode", "pre", "--plan", rel_plan, "--label", "e-est"],
        require_substrings=["evaluate"],
    ))

    # ---- implement (3+) ----
    for band in ("light", "medium", "detailed"):
        cases.append(check(
            root, skill="implement", case=f"ceremony-{band}",
            argv=["implement", "--step", "1", "--plan", rel_plan, "--ceremony", band,
                  "--label", f"i-{band}"],
            require_substrings=["implement"],
            expect_ceremony=band, expect_ceremony_source="cli",
        ))

    # ---- code-review (3+) ----
    cases.append(check(
        root, skill="code-review", case="ceremony-light",
        argv=["code-review", "--step", "1", "--ceremony", "light", "--target", ".",
              "--no-structural", "--label", "c-light"],
        require_substrings=["code-review"],
        expect_ceremony="light", expect_ceremony_source="cli",
    ))
    cases.append(check(
        root, skill="code-review", case="ceremony-comprehensive",
        argv=["code-review", "--step", "1", "--ceremony", "comprehensive", "--target", ".",
              "--no-structural", "--label", "c-comp"],
        require_substrings=["code-review"],
        expect_ceremony="comprehensive", expect_ceremony_source="cli",
    ))
    cases.append(check(
        root, skill="code-review", case="effort-thorough-alias",
        argv=["code-review", "--step", "1", "--effort", "thorough", "--target", ".",
              "--no-structural", "--label", "c-effort"],
        require_substrings=["code-review"],
        # effort maps to comprehensive when ceremony not set
        expect_ceremony="comprehensive",
    ))

    # ---- test (3+) ----
    for band in ("light", "medium", "detailed"):
        cases.append(check(
            root, skill="test", case=f"run-ceremony-{band}",
            argv=["test", "--step", "1", "--mode", "run", "--ceremony", band,
                  "--label", f"t-{band}"],
            require_substrings=["test"],
            expect_ceremony=band, expect_ceremony_source="cli",
        ))
    cases.append(check(
        root, skill="test", case="flows-ceremony-light",
        argv=["test", "--step", "1", "--mode", "flows", "--ceremony", "light",
              "--label", "t-flows"],
        require_substrings=["flow"],
        expect_ceremony="light", expect_ceremony_source="cli",
    ))

    # ---- diagnose (3+) ----
    for band in ("light", "medium", "comprehensive"):
        cases.append(check(
            root, skill="diagnose", case=f"ceremony-{band}",
            argv=["diagnose", "--step", "1", "--ceremony", band, "--label", f"g-{band}"],
            require_substrings=["diagnose"],
            expect_ceremony=band, expect_ceremony_source="cli",
        ))

    # ---- ux-review (3+) ----
    cases.append(check(root, skill="ux-review", case="step1",
                       argv=["ux-review", "--step", "1"], require_substrings=["ux"]))
    cases.append(check(root, skill="ux-review", case="quick",
                       argv=["ux-review", "--step", "1", "--quick"], require_substrings=["ux"]))
    cases.append(check(root, skill="ux-review", case="base-url",
                       argv=["ux-review", "--step", "1", "--base-url", "http://127.0.0.1:3999"],
                       require_substrings=["ux"]))
    cases.append(check(root, skill="ux-review", case="reject-ceremony",
                       argv=["ux-review", "--step", "1", "--ceremony", "light"],
                       expect_reject_ceremony=True))

    # ---- ship (3+) ----
    cases.append(check(root, skill="ship", case="step1",
                       argv=["ship", "--step", "1"], require_substrings=["ship"],
                       expect_exit={0, 1}))
    cases.append(check(root, skill="ship", case="json",
                       argv=["ship", "--step", "1", "--json"], expect_exit={0, 1}))
    cases.append(check(root, skill="ship", case="reject-ceremony",
                       argv=["ship", "--step", "1", "--ceremony", "light"],
                       expect_reject_ceremony=True))

    # ---- takeover (3+) ----
    cases.append(check(root, skill="takeover", case="goal",
                       argv=["takeover", "--step", "1", "--goal", "matrix ship-ready check"],
                       require_substrings=["takeover"]))
    cases.append(check(root, skill="takeover", case="cleanup-dry",
                       argv=["takeover", "--cleanup"], expect_exit={0, 1}))
    cases.append(check(root, skill="takeover", case="reject-ceremony",
                       argv=["takeover", "--step", "1", "--ceremony", "light"],
                       expect_reject_ceremony=True))

    # ---- status / doctor / graphify (3 each) ----
    cases.append(check(root, skill="status", case="plain",
                       argv=["status"], expect_exit={0, 1}))
    cases.append(check(root, skill="status", case="json",
                       argv=["status", "--json"], expect_exit={0, 1}))
    cases.append(check(root, skill="status", case="ascii",
                       argv=["status", "--ascii"], expect_exit={0, 1}))

    cases.append(check(root, skill="doctor", case="plain",
                       argv=["doctor"], expect_exit={0, 1}))
    cases.append(check(root, skill="doctor", case="json",
                       argv=["doctor", "--json"], expect_exit={0, 1}))
    cases.append(check(root, skill="doctor", case="ascii",
                       argv=["doctor", "--ascii"], expect_exit={0, 1}))

    # graphify may fail if graphify CLI missing — accept soft failure with clear message
    for case, argv in (
        ("refresh", ["graphify", "refresh"]),
        ("status-ish", ["graphify", "--help"]),
        ("install-hook-dry", ["graphify", "install-hook", "--help"]),
    ):
        # graphify subcommands don't all take --repo the same way; call help without repo wrapper
        if "--help" in argv or case.endswith("help") or "help" in argv[-1]:
            proc = subprocess.run(
                [FORGE, *argv], capture_output=True, text=True, env=_env(), timeout=60
            )
            text = (proc.stdout or "") + (proc.stderr or "")
            ok = proc.returncode == 0 and "graphify" in text.lower()
            cases.append(CaseResult(
                "graphify", case, ok, proc.returncode,
                "ok" if ok else f"exit {proc.returncode}",
                _evidence(text, [r"graphify", r"usage"]),
                {},
            ))
        else:
            cases.append(check(
                root, skill="graphify", case=case, argv=argv,
                expect_exit={0, 1, 2},
            ))

    return cases


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="forge-cli-matrix-") as tmp:
        root = Path(tmp)
        plan = _init_repo(root)
        print(f"FORGE_BIN={FORGE}")
        print(f"ROOT={root}")
        print("=" * 72)
        results = build_cases(root, plan)

    # Summarize
    by_skill: dict[str, list[CaseResult]] = {}
    for r in results:
        by_skill.setdefault(r.skill, []).append(r)

    failed = [r for r in results if not r.ok]
    lines = []
    for skill, rows in by_skill.items():
        n_ok = sum(1 for r in rows if r.ok)
        print(f"\n### {skill}  ({n_ok}/{len(rows)} pass)")
        lines.append(f"### {skill} ({n_ok}/{len(rows)})")
        for r in rows:
            mark = "PASS" if r.ok else "FAIL"
            print(f"  [{mark}] {r.case}: {r.detail}")
            lines.append(f"  [{mark}] {r.case}: {r.detail}")
            if not r.ok and r.state:
                print(f"         state={r.state}")
            if not r.ok and r.evidence:
                for e in r.evidence[:5]:
                    print(f"         {e}")

    report = {
        "forge": FORGE,
        "total": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "skills": {
            skill: {
                "passed": sum(1 for r in rows if r.ok),
                "total": len(rows),
                "cases": [asdict(r) for r in rows],
            }
            for skill, rows in by_skill.items()
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "=" * 72)
    print(f"{report['passed']}/{report['total']} passed — report: {OUT / 'report.json'}")
    if failed:
        print(f"FAILED: {len(failed)}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
