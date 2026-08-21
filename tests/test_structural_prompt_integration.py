"""Prompt parity and orchestrator smoke tests for structural quality probes."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

STRUCTURAL_PROMPT_RELS = [
    "code-review/mode_selection.md",
    "code-review/diff_analysis.md",
    "code-review/architecture_check.md",
    "code-review/deep_dive.md",
    "post/code_quality.md",
    "review/team_dispatch.md",
    "pre/risk_dependencies.md",
]

STRUCTURAL_MARKER = "structural-quality-probes.md"


@pytest.fixture(autouse=True)
def _repo_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


def test_structural_prompts_reference_template() -> None:
    missing: list[str] = []
    for rel in STRUCTURAL_PROMPT_RELS:
        text = (REPO_ROOT / "prompts" / rel).read_text(encoding="utf-8")
        if STRUCTURAL_MARKER not in text and ".structural-probes.json" not in text:
            missing.append(rel)
    assert not missing, f"prompts missing structural marker: {missing}"


def test_eval_state_custom_roundtrip(tmp_path: Path) -> None:
    from scripts.evaluate.state import EvalState, load_state, save_state

    sp = tmp_path / ".evaluate-state.json"
    state = EvalState(plan_path="/tmp/plan.md", plan_name="plan")
    state.custom["structural_probes_sidecar"] = "/tmp/.structural-probes.json"
    save_state(state, sp)
    loaded = load_state(sp)
    assert loaded.custom.get("structural_probes_sidecar") == "/tmp/.structural-probes.json"


def test_evaluate_post_step4_injects_structural_banner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Orchestrator step 4 (post) must append STRUCTURAL PROBES when probes run."""
    import io

    import scripts.evaluate.evaluate as ev
    from scripts.evaluate.state import EvalState, save_state
    from scripts.shared import structural_probes as sp

    state_dir = REPO_ROOT / ".forge" / "state" / "evaluate-post-step4-smoke"
    state_dir.mkdir(parents=True, exist_ok=True)
    plan = state_dir / "plan.md"
    plan.write_text("# Plan\n\n## Task 1\n\nDo thing.\n", encoding="utf-8")
    sp_file = state_dir / ".evaluate-state.json"
    st = EvalState(plan_path=str(plan), plan_name="plan", mode="post")
    st.current_step = 3
    st.last_completed_step = 3
    save_state(st, sp_file)

    fake = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "stack": {"python": True, "node": False},
        "probes": [],
    }
    sidecar = state_dir / ".structural-probes.json"

    def fake_run(*_a, **_k):
        sidecar.write_text(json.dumps(fake), encoding="utf-8")
        return fake

    monkeypatch.setattr(sp, "run_probes", fake_run)
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_MANUAL", raising=False)
    monkeypatch.setenv("FORGE_STRUCTURAL_PROBES_AUTO", "1")
    monkeypatch.setenv("FORGE_SKIP_GRAPHIFY", "1")
    monkeypatch.setenv("FORGE_SKIP_SESSION_OPTIN", "1")

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    reloaded: dict = {}
    try:
        ev.handle_step_n(4, state_file=str(sp_file))
        out = buf.getvalue()
        reloaded = json.loads(sp_file.read_text(encoding="utf-8"))
    finally:
        sp_file.unlink(missing_ok=True)
        plan.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)
        try:
            state_dir.rmdir()
        except OSError:
            pass

    assert "STRUCTURAL PROBES" in out
    assert "custom" in reloaded
    assert "structural_probes_sidecar" in reloaded.get("custom", {})


def test_code_review_step3_real_template_probe_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Step 3 loads real team-dispatch template + probe gate multiselect."""
    import io

    import scripts.code_review.code_review as cr
    from scripts.shared.orchestrator import SkillState, save_state

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    sess = tmp_path / ".forge" / "sessions" / "cr3" / "session.json"
    sess.parent.mkdir(parents=True)
    state = SkillState(skill_name="code-review", max_step=6)
    state.current_step = 2
    state.last_completed_step = 2
    state.custom["mode"] = "deep"
    state.custom["target"] = "feat/runtime-probe-gates"
    state.custom["target_tokens"] = []
    state.custom["structural_enabled"] = True
    save_state(state, sess)

    monkeypatch.setenv("FORGE_STRUCTURAL_PROBES_MANUAL", "1")
    monkeypatch.setenv("FORGE_SKIP_GRAPHIFY", "1")
    monkeypatch.setenv("FORGE_SKIP_SESSION_OPTIN", "1")
    monkeypatch.setenv("FORGE_SKIP_STRUCTURAL_EIGHT_AGENTS", "1")

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    try:
        cr.handle_step_n(3, state_file=str(sess))
        out = buf.getvalue()
    finally:
        pass

    assert "CODE-REVIEW — Team Dispatch" in out
    assert "STRUCTURAL PROBES — DEFERRED" in out
    assert "STRUCTURAL PROBES GATE" in out
    assert "forge_probe_gate_multiselect" in out
    assert "Dispatch all reviewers" in out or "trace code paths" in out
    assert (sess.parent / ".structural-probes-gate.json").is_file()


def test_implement_step4_real_template_structural_probes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Wave review step 4 appends real structural probe banners to template body."""
    import io

    import scripts.implement.implement as imp
    from scripts.shared.orchestrator import SkillState, save_state

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".git").mkdir()
    plan = tmp_path / "docs" / "plans" / "smoke.plan.md"
    plan.parent.mkdir(parents=True)
    plan.write_text("# Smoke\n\n## Task 1\n\nDo thing.\n", encoding="utf-8")
    sess = tmp_path / ".forge" / "sessions" / "imp4" / "session.json"
    sess.parent.mkdir(parents=True)
    state = SkillState(skill_name="implement", max_step=8)
    state.current_step = 3
    state.last_completed_step = 3
    state.custom.update(
        {
            "plan_path": str(plan),
            "current_wave": 1,
            "total_waves": 1,
            "waves_completed": 0,
            "implementation_mode": "direct",
        }
    )
    save_state(state, sess)

    monkeypatch.setenv("FORGE_STRUCTURAL_PROBES_MANUAL", "1")
    monkeypatch.setenv("FORGE_SKIP_GRAPHIFY", "1")
    monkeypatch.setenv("FORGE_SKIP_SESSION_OPTIN", "1")

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    imp.handle_step_4(state, sess)
    out = buf.getvalue()

    assert "IMPLEMENT — Wave Review" in out
    assert "Wave Review" in out
    assert "STRUCTURAL PROBES" in out
    assert "Per-task review loop" in out or "Review Protocol" in out
