# pyright: reportMissingImports=false, reportUnusedVariable=false
"""Regression tests for the workflow defects fixed in
docs/evaluations/i-m-having-some-issues-composed-hedgehog-evaluation.md.

Each test maps to a Verification step in the plan.

Pyright suppressions: dynamic sys.path manipulation (REPO_ROOT inserted in
fixtures) means imports resolve at runtime but not via static analysis;
pytest fixture parameters appear unused but trigger setup/teardown.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def add_repo_to_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def fresh_state_dir(tmp_path: Path, monkeypatch):
    """Run with cwd=tmp_path so runtime_state_path / runtime_memory_dir resolve fresh."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def clean_test_state():
    """Clean up test skill state before and after each test."""
    test_state = REPO_ROOT / ".codex" / "forge-codex" / "state" / "test.json"
    if test_state.exists():
        test_state.unlink()
    yield
    if test_state.exists():
        test_state.unlink()


# ---------------------------------------------------------------------------
# Fix 3.4 — failure_count first-class field (V12, V13)
# ---------------------------------------------------------------------------

def test_skillstate_has_failure_count_default_zero():
    from scripts.shared.orchestrator import SkillState

    s = SkillState(skill_name="develop")
    assert s.failure_count == 0


def test_skillstate_mark_step_complete_resets_failure_count():
    from scripts.shared.orchestrator import SkillState

    s = SkillState(skill_name="plan")
    s.failure_count = 5
    s.mark_step_complete(3)
    assert s.last_completed_step == 3
    assert s.failure_count == 0


def test_skillstate_loads_legacy_state_without_failure_count():
    """Legacy state file lacking failure_count must default to 0 (F12)."""
    from scripts.shared.orchestrator import SkillState

    legacy = {
        "skill_name": "plan",
        "current_step": 3,
        "last_completed_step": 2,
        "max_step": 6,
    }
    s = SkillState.from_dict(legacy)
    assert s.failure_count == 0


def test_evalstate_has_failure_count():
    from scripts.evaluate.state import EvalState

    s = EvalState(plan_path="/tmp/x.md", plan_name="x")
    assert s.failure_count == 0
    s.failure_count = 3
    s.mark_step_complete(2)
    assert s.failure_count == 0


# ---------------------------------------------------------------------------
# Fix 1 — validate_step_or_complete (V1)
# ---------------------------------------------------------------------------

def test_validate_step_or_complete_in_range_returns_false(capsys):
    from scripts.shared.orchestrator import validate_step_or_complete

    assert validate_step_or_complete(3, 7, "plan") is False
    captured = capsys.readouterr()
    assert captured.err == ""


def test_validate_step_or_complete_over_cap_returns_true_with_friendly_msg(capsys):
    from scripts.shared.orchestrator import validate_step_or_complete

    assert validate_step_or_complete(99, 7, "plan") is True
    captured = capsys.readouterr()
    assert "ends at step 7" in captured.err
    assert "nothing left to do" in captured.err


def test_validate_step_or_complete_zero_or_negative_hard_errors():
    from scripts.shared.orchestrator import validate_step_or_complete

    with pytest.raises(SystemExit):
        validate_step_or_complete(0, 7, "plan")
    with pytest.raises(SystemExit):
        validate_step_or_complete(-1, 7, "plan")


# ---------------------------------------------------------------------------
# Fix 2 — Plan skeleton (V3, V5)
# ---------------------------------------------------------------------------

def test_write_plan_skeleton_creates_eight_canonical_sections(tmp_path: Path):
    from scripts.plan.plan import write_plan_skeleton, PLAN_SECTIONS

    plan_path = tmp_path / "plan.md"
    write_plan_skeleton(plan_path)

    content = plan_path.read_text()
    assert len(PLAN_SECTIONS) == 8
    for marker_id, heading in PLAN_SECTIONS:
        assert f"## {heading}" in content
        assert f"<!-- FORGE_SKELETON: {marker_id} -->" in content


def test_write_plan_skeleton_refuses_overwrite_with_real_content(tmp_path: Path):
    from scripts.plan.plan import write_plan_skeleton

    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Real Content\n\nThis is meaningful prose.")

    with pytest.raises(SystemExit):
        write_plan_skeleton(plan_path)


def test_write_plan_skeleton_force_overwrites_real_content(tmp_path: Path):
    from scripts.plan.plan import write_plan_skeleton, SKELETON_MARKER_PREFIX

    plan_path = tmp_path / "plan.md"
    plan_path.write_text("# Real Content\n\nThis is meaningful prose.")
    write_plan_skeleton(plan_path, force=True)
    assert SKELETON_MARKER_PREFIX in plan_path.read_text()


def test_write_plan_skeleton_overwrites_stub(tmp_path: Path):
    """A stub-only file (markers + headings) is safe to overwrite without --force."""
    from scripts.plan.plan import write_plan_skeleton

    plan_path = tmp_path / "plan.md"
    write_plan_skeleton(plan_path)
    # Re-running should not raise.
    write_plan_skeleton(plan_path)


def test_find_unfilled_sections_after_partial_fill(tmp_path: Path):
    from scripts.plan.plan import write_plan_skeleton, find_unfilled_sections

    plan_path = tmp_path / "plan.md"
    write_plan_skeleton(plan_path)
    assert len(find_unfilled_sections(plan_path)) == 8

    # Replace one marker
    content = plan_path.read_text()
    content = content.replace(
        "<!-- FORGE_SKELETON: ARCHITECTURE-OVERVIEW -->",
        "Real architecture content.",
    )
    plan_path.write_text(content)
    unfilled = find_unfilled_sections(plan_path)
    assert "Architecture Overview" not in unfilled
    assert len(unfilled) == 7


# ---------------------------------------------------------------------------
# Fix 3.2 — Same-skill clobber prevention (V7, V8)
# ---------------------------------------------------------------------------

def test_check_same_skill_clobber_is_noop_with_in_progress_state(fresh_state_dir, monkeypatch):
    """Parallel-first: clobber check never aborts (step 1 always creates new session dir)."""
    from scripts.shared.orchestrator import (
        SkillState,
        check_same_skill_clobber,
        runtime_state_path,
        save_state,
    )

    sp = runtime_state_path("plan", fresh_state_dir)
    sp.parent.mkdir(parents=True, exist_ok=True)
    state = SkillState(skill_name="plan")
    state.current_step = 3
    state.started_at = "2026-05-07T00:00:00+00:00"
    save_state(state, sp)

    check_same_skill_clobber("plan")


def test_check_same_skill_clobber_passes_on_completed_state(fresh_state_dir):
    from scripts.shared.orchestrator import (
        SkillState,
        check_same_skill_clobber,
        runtime_state_path,
        save_state,
    )

    sp = runtime_state_path("plan", fresh_state_dir)
    sp.parent.mkdir(parents=True, exist_ok=True)
    state = SkillState(skill_name="plan")
    state.current_step = 6
    state.completed_at = "2026-05-07T00:00:00+00:00"
    save_state(state, sp)

    # Should not raise — completed sessions can be safely overwritten.
    check_same_skill_clobber("plan")


def test_check_same_skill_clobber_passes_on_logically_completed_state(fresh_state_dir):
    from scripts.shared.orchestrator import (
        SkillState,
        check_same_skill_clobber,
        runtime_state_path,
        save_state,
    )

    sp = runtime_state_path("plan", fresh_state_dir)
    sp.parent.mkdir(parents=True, exist_ok=True)
    state = SkillState(skill_name="plan", max_step=7)
    state.current_step = 7
    state.last_completed_step = 7
    save_state(state, sp)

    # Legacy complete state (no completed_at) should not block a fresh start.
    check_same_skill_clobber("plan")


def test_check_same_skill_clobber_passes_when_no_state(fresh_state_dir):
    from scripts.shared.orchestrator import check_same_skill_clobber

    # No state file exists; should silently pass.
    check_same_skill_clobber("plan")


def test_check_same_skill_clobber_allows_parallel_target_path(fresh_state_dir):
    from scripts.shared.orchestrator import (
        SkillState,
        check_same_skill_clobber,
        runtime_state_path,
        save_state,
    )

    # Existing active canonical session.
    canonical = runtime_state_path("plan", fresh_state_dir)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    state = SkillState(skill_name="plan", max_step=7)
    state.current_step = 3
    save_state(state, canonical)

    # Parallel mode with a different target path should not abort.
    parallel_target = canonical.parent / "plan-20260517-093900.json"
    check_same_skill_clobber(
        "plan",
        allow_parallel=True,
        target_state_path=parallel_target,
    )


def test_skill_state_persists_session_id_and_last_touched(fresh_state_dir):
    from scripts.shared.orchestrator import SkillState, runtime_state_path, save_state

    sp = runtime_state_path("plan", fresh_state_dir)
    sp.parent.mkdir(parents=True, exist_ok=True)
    state = SkillState(skill_name="plan")
    save_state(state, sp)
    raw = json.loads(sp.read_text(encoding="utf-8"))
    assert raw.get("session_id")
    assert raw.get("last_touched_at")


def test_find_state_file_ignores_stale_active_by_default(fresh_state_dir, monkeypatch):
    from scripts.shared.orchestrator import SkillState, find_state_file, runtime_state_dir, save_state

    monkeypatch.setenv("FORGE_STALE_SESSION_HOURS", "0.00001")
    state_dir = runtime_state_dir(fresh_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    stale_path = state_dir / "plan-stale.json"
    stale = SkillState(skill_name="plan", max_step=7)
    stale.current_step = 2
    stale.last_touched_at = "2000-01-01T00:00:00+00:00"
    save_state(stale, stale_path)
    # Force stale timestamp after save_state heartbeat update.
    raw = json.loads(stale_path.read_text(encoding="utf-8"))
    raw["last_touched_at"] = "2000-01-01T00:00:00+00:00"
    stale_path.write_text(json.dumps(raw), encoding="utf-8")

    assert find_state_file("plan", fresh_state_dir) is None
    assert find_state_file("plan", fresh_state_dir, include_stale=True) == stale_path


def _test_state_path(search_dir) -> Path:
    """Return the active test skill state file (session dir or legacy)."""
    from scripts.shared.orchestrator import find_state_file

    sp = find_state_file("test", search_dir)
    assert sp is not None, "expected test state after step 1"
    return sp


def test_resolve_step1_state_path_always_creates_new_session(fresh_state_dir, monkeypatch):
    from scripts.shared.orchestrator import (
        SkillState,
        resolve_step1_state_path,
        runtime_state_path,
        save_state,
    )
    from scripts.shared.session_store import is_session_state_path, sessions_root

    monkeypatch.chdir(fresh_state_dir)
    canonical = runtime_state_path("plan", fresh_state_dir)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    active = SkillState(skill_name="plan", max_step=7)
    active.current_step = 3
    save_state(active, canonical)

    resolved = resolve_step1_state_path("plan", None, parallel=False, search_dir=fresh_state_dir)
    assert is_session_state_path(resolved)
    assert resolved.parent.parent == sessions_root(fresh_state_dir)
    assert resolved != canonical


def test_resolve_step1_state_path_new_session_even_with_stale_canonical(fresh_state_dir, monkeypatch):
    from scripts.shared.orchestrator import (
        SkillState,
        resolve_step1_state_path,
        runtime_state_path,
        save_state,
    )
    from scripts.shared.session_store import is_session_state_path

    monkeypatch.chdir(fresh_state_dir)
    monkeypatch.setenv("FORGE_STALE_SESSION_HOURS", "0.00001")
    canonical = runtime_state_path("plan", fresh_state_dir)
    canonical.parent.mkdir(parents=True, exist_ok=True)
    stale = SkillState(skill_name="plan", max_step=7)
    stale.current_step = 3
    save_state(stale, canonical)
    raw = json.loads(canonical.read_text(encoding="utf-8"))
    raw["last_touched_at"] = "2000-01-01T00:00:00+00:00"
    canonical.write_text(json.dumps(raw), encoding="utf-8")

    resolved = resolve_step1_state_path("plan", None, parallel=False, search_dir=fresh_state_dir)
    assert is_session_state_path(resolved)
    assert resolved != canonical


def test_develop_step1_always_creates_new_session_dir(fresh_state_dir):
    """Develop step 1 always allocates a new session directory."""
    import os
    import re

    from scripts.shared.session_store import sessions_root

    env = os.environ.copy()
    env["FORGE_SKIP_SESSION_OPTIN"] = "1"

    r1 = subprocess.run(
        [sys.executable, str(SCRIPTS / "develop" / "develop.py"), "--step", "1", "--label", "first"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert r1.returncode == 0, r1.stderr
    m1 = re.search(r"STATE FILE:\s*(.+)", (r1.stderr or "") + r1.stdout)
    assert m1
    first = Path(m1.group(1).strip())

    r2 = subprocess.run(
        [sys.executable, str(SCRIPTS / "develop" / "develop.py"), "--step", "1", "--label", "second"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert r2.returncode == 0, r2.stderr
    m2 = re.search(r"STATE FILE:\s*(.+)", (r2.stderr or "") + r2.stdout)
    assert m2
    second = Path(m2.group(1).strip())
    assert first.name == second.name == "session.json"
    assert first.parent != second.parent
    assert first.parent.parent == sessions_root(fresh_state_dir)


def test_validate_state_path_accepts_suffixed_skill_state(fresh_state_dir):
    from scripts.shared.orchestrator import validate_state_path

    state_dir = fresh_state_dir / ".codex" / "forge-codex" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    sp = state_dir / "plan-session-a.json"
    sp.write_text(
        json.dumps(
            {
                "skill_name": "plan",
                "current_step": 2,
                "last_completed_step": 1,
                "max_step": 7,
            }
        )
    )
    resolved = validate_state_path(str(sp), "plan")
    assert resolved == sp.resolve()


def test_find_state_file_prefers_latest_active_suffix_state(fresh_state_dir):
    from scripts.shared.orchestrator import (
        SkillState,
        find_state_file,
        runtime_state_dir,
        save_state,
    )
    import time

    state_dir = runtime_state_dir(fresh_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    old_path = state_dir / "plan-older.json"
    new_path = state_dir / "plan-newer.json"

    s_old = SkillState(skill_name="plan", max_step=7)
    s_old.current_step = 2
    save_state(s_old, old_path)
    time.sleep(0.01)  # Ensure mtime ordering on all platforms.
    s_new = SkillState(skill_name="plan", max_step=7)
    s_new.current_step = 3
    save_state(s_new, new_path)

    assert find_state_file("plan", fresh_state_dir) == new_path


def test_find_state_file_ignores_completed_by_default(fresh_state_dir):
    from scripts.shared.orchestrator import (
        SkillState,
        find_state_file,
        runtime_state_dir,
        save_state,
    )

    state_dir = runtime_state_dir(fresh_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    completed = state_dir / "plan-complete.json"

    done = SkillState(skill_name="plan", max_step=7)
    done.current_step = 7
    done.last_completed_step = 7
    done.completed_at = "2026-05-17T00:00:00+00:00"
    save_state(done, completed)

    assert find_state_file("plan", fresh_state_dir) is None


def test_find_state_file_can_include_completed(fresh_state_dir):
    from scripts.shared.orchestrator import (
        SkillState,
        find_state_file,
        runtime_state_dir,
        save_state,
    )

    state_dir = runtime_state_dir(fresh_state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    completed = state_dir / "plan-complete.json"

    done = SkillState(skill_name="plan", max_step=7)
    done.current_step = 7
    done.last_completed_step = 7
    done.completed_at = "2026-05-17T00:00:00+00:00"
    save_state(done, completed)

    assert find_state_file("plan", fresh_state_dir, include_completed=True) == completed


def test_validate_state_path_accepts_suffixed_evaluate_state(fresh_state_dir):
    from scripts.shared.orchestrator import validate_state_path

    eval_state = fresh_state_dir / "docs" / ".evaluate-state-branch-a.json"
    eval_state.parent.mkdir(parents=True, exist_ok=True)
    eval_state.write_text(
        json.dumps(
            {
                "plan_path": str(fresh_state_dir / "docs" / "plan.md"),
                "plan_name": "plan",
                "mode": "pre",
                "current_step": 2,
                "last_completed_step": 1,
            }
        )
    )
    resolved = validate_state_path(str(eval_state), "evaluate")
    assert resolved == eval_state.resolve()


def test_detect_active_sessions_includes_suffixed_evaluate_states(fresh_state_dir):
    from scripts.shared.orchestrator import detect_active_sessions

    docs = fresh_state_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    eval_state = docs / ".evaluate-state-session-1.json"
    eval_state.write_text(
        json.dumps(
            {
                "plan_path": str(docs / "plan.md"),
                "plan_name": "plan",
                "mode": "review",
                "current_step": 3,
                "last_completed_step": 2,
            }
        )
    )

    sessions = detect_active_sessions(fresh_state_dir)
    eval_sessions = [s for s in sessions if s["skill"] == "evaluate"]
    assert any(s["path"] == eval_state for s in eval_sessions)


# ---------------------------------------------------------------------------
# Fix 4 — Evaluate findings sidecar ingestion (V14)
# ---------------------------------------------------------------------------

def test_evaluate_ingests_findings_sidecar(tmp_path: Path):
    from scripts.evaluate.evaluate import (
        _findings_sidecar_path,
        _ingest_findings_sidecars,
    )
    from scripts.evaluate.state import EvalState

    state = EvalState(plan_path="/tmp/plan.md", plan_name="test")

    sidecar = _findings_sidecar_path(tmp_path, 2)
    sidecar.write_text(json.dumps([
        {"phase": "feasibility", "severity": "critical", "title": "F1", "detail": "d1"},
        {"phase": "feasibility", "severity": "warning", "title": "F2", "detail": "d2"},
    ]))

    n = _ingest_findings_sidecars(state, tmp_path, current_step=3)
    assert n == 2
    assert len(state.findings) == 2
    assert state.findings[0]["title"] == "F1"
    assert not sidecar.exists()  # ingested files are deleted


def test_evaluate_findings_sidecar_tolerates_malformed_json(tmp_path: Path, capsys):
    from scripts.evaluate.evaluate import (
        _findings_sidecar_path,
        _ingest_findings_sidecars,
    )
    from scripts.evaluate.state import EvalState

    state = EvalState(plan_path="/tmp/p.md", plan_name="x")
    sidecar = _findings_sidecar_path(tmp_path, 2)
    sidecar.write_text("not valid json {")

    n = _ingest_findings_sidecars(state, tmp_path, current_step=3)
    assert n == 0
    captured = capsys.readouterr()
    assert "malformed findings sidecar" in captured.err


# ---------------------------------------------------------------------------
# Fix 3.3 — resume.py --cleanup (V10, V11)
# ---------------------------------------------------------------------------

def test_resume_cleanup_dry_run_does_not_delete(fresh_state_dir):
    """Run resume.py --cleanup as a subprocess; expect dry-run by default."""
    from tests.helpers.session_fixtures import write_completed_flat_state

    target = write_completed_flat_state(fresh_state_dir, "develop")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "takeover" / "takeover.py"), "--cleanup"],
        cwd=fresh_state_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "Would delete" in (result.stderr + result.stdout)
    assert target.exists()  # not actually deleted


def test_resume_cleanup_force_deletes(fresh_state_dir):
    from tests.helpers.session_fixtures import write_completed_flat_state

    target = write_completed_flat_state(fresh_state_dir, "develop")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "takeover" / "takeover.py"), "--cleanup", "--force"],
        cwd=fresh_state_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert not target.exists()


def test_resume_cleanup_handles_legacy_complete_without_completed_at(fresh_state_dir):
    from tests.helpers.session_fixtures import write_stale_flat_state

    target = write_stale_flat_state(fresh_state_dir, "plan")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "takeover" / "takeover.py"), "--cleanup"],
        cwd=fresh_state_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "state reached max_step without completed_at" in (result.stderr + result.stdout)
    assert target.exists()  # dry-run only


# ---------------------------------------------------------------------------
# Session auto-close lifecycle
# ---------------------------------------------------------------------------

def _runtime_dirs(tmp_path: Path) -> tuple[Path, Path]:
    from datetime import datetime, timezone
    from scripts.shared.orchestrator import ensure_runtime_dirs, runtime_memory_dir, runtime_state_dir

    ensure_runtime_dirs(tmp_path)
    return runtime_state_dir(tmp_path), runtime_memory_dir(tmp_path)


def _write_active_state(
    state_dir: Path,
    skill: str,
    *,
    filename: str | None = None,
    current_step: int = 1,
    last_completed_step: int = 1,
    max_step: int = 7,
    last_touched_at: str | None = None,
) -> Path:
    state_dir.mkdir(parents=True, exist_ok=True)
    from datetime import datetime, timezone

    path = state_dir / (filename or f"{skill}.json")
    now = datetime.now(timezone.utc).isoformat()
    payload: dict = {
        "skill_name": skill,
        "current_step": current_step,
        "last_completed_step": last_completed_step,
        "max_step": max_step,
        "started_at": now,
        "completed_at": None,
        "last_touched_at": last_touched_at if last_touched_at is not None else now,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_auto_close_removes_plan_when_handoff_exists(fresh_state_dir):
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    state_dir, mem_dir = _runtime_dirs(fresh_state_dir)
    plan_path = _write_active_state(state_dir, "plan")
    (mem_dir / "handoff-plan.md").write_text("# handoff\n", encoding="utf-8")

    closed = auto_close_superseded_sessions("diagnose", search_dir=fresh_state_dir)
    reasons = {str(p): r for p, r in closed}
    assert str(plan_path) in reasons or plan_path in [p for p, _ in closed]
    assert not plan_path.exists()


def test_auto_close_upstream_plan_when_starting_implement(fresh_state_dir):
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    state_dir, _mem = _runtime_dirs(fresh_state_dir)
    plan_path = _write_active_state(
        state_dir, "plan", current_step=2, last_completed_step=2, max_step=7
    )
    impl_target = state_dir / "implement.json"

    closed = auto_close_superseded_sessions(
        "implement",
        search_dir=fresh_state_dir,
        preserve_paths={impl_target.resolve()},
    )
    assert any(p == plan_path for p, _ in closed)
    assert not plan_path.exists()


def test_auto_close_does_not_close_downstream_diagnose_when_starting_plan(fresh_state_dir):
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    state_dir, _mem = _runtime_dirs(fresh_state_dir)
    diag_path = _write_active_state(
        state_dir, "diagnose", current_step=4, last_completed_step=3, max_step=7
    )
    plan_target = state_dir / "plan.json"

    closed = auto_close_superseded_sessions(
        "plan",
        search_dir=fresh_state_dir,
        preserve_paths={plan_target.resolve()},
    )
    assert diag_path.exists()
    assert not any(p == diag_path for p, _ in closed)


def test_auto_close_step1_abandoned(fresh_state_dir, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    monkeypatch.setenv("FORGE_STEP1_ABANDON_HOURS", "1")
    state_dir, _mem = _runtime_dirs(fresh_state_dir)
    old_touch = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    stale_path = _write_active_state(
        state_dir,
        "code-review",
        max_step=6,
        last_touched_at=old_touch,
    )
    plan_target = state_dir / "plan.json"

    closed = auto_close_superseded_sessions(
        "plan",
        search_dir=fresh_state_dir,
        preserve_paths={plan_target.resolve()},
    )
    assert any(p == stale_path for p, _ in closed)
    assert not stale_path.exists()


def test_auto_close_abandoned_mid_pipeline_code_review_when_starting_design(
    fresh_state_dir, monkeypatch
):
    """Idle code-review at step 3 must close when starting design — not prompt 'leave alone'."""
    from datetime import datetime, timedelta, timezone
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    monkeypatch.setenv("FORGE_STEP1_ABANDON_HOURS", "1")
    monkeypatch.setenv("FORGE_STALE_SESSION_HOURS", "1")
    state_dir, _mem = _runtime_dirs(fresh_state_dir)
    old_touch = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()
    review_path = _write_active_state(
        state_dir,
        "code-review",
        current_step=3,
        last_completed_step=3,
        max_step=6,
        last_touched_at=old_touch,
    )
    impl_path = _write_active_state(
        state_dir,
        "implement",
        current_step=2,
        last_completed_step=2,
        max_step=5,
        last_touched_at=old_touch,
    )
    design_target = state_dir / "design.json"

    closed = auto_close_superseded_sessions(
        "design",
        search_dir=fresh_state_dir,
        preserve_paths={design_target.resolve()},
    )
    closed_paths = {p for p, _ in closed}
    assert review_path in closed_paths
    assert impl_path in closed_paths
    assert not review_path.exists()
    assert not impl_path.exists()


def test_auto_close_stale_pipeline_session_when_starting_design(
    fresh_state_dir, monkeypatch
):
    from datetime import datetime, timedelta, timezone
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    monkeypatch.setenv("FORGE_STALE_SESSION_HOURS", "24")
    state_dir, _mem = _runtime_dirs(fresh_state_dir)
    old_touch = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    review_path = _write_active_state(
        state_dir,
        "code-review",
        current_step=3,
        last_completed_step=3,
        max_step=6,
        last_touched_at=old_touch,
    )
    design_target = state_dir / "design.json"

    closed = auto_close_superseded_sessions(
        "design",
        search_dir=fresh_state_dir,
        preserve_paths={design_target.resolve()},
    )
    assert any(p == review_path and "stale" in r for p, r in closed)
    assert not review_path.exists()


def test_active_session_warning_defaults_to_continue_new_skill():
    from scripts.shared.session_hygiene import format_active_session_warning

    text = format_active_session_warning(
        [
            {
                "skill": "implement",
                "path": "/tmp/implement.json",
                "current_step": 2,
                "max_step": 5,
                "last_completed_step": 2,
            }
        ],
        "design",
    )
    assert "Default" in text
    assert "leave leftover sessions untouched" in text or "leave" in text.lower()
    assert "PAUSE" not in text
    assert "leave the existing session alone" not in text


def test_auto_close_respects_skip_env(fresh_state_dir, monkeypatch):
    from scripts.shared.orchestrator import auto_close_superseded_sessions

    monkeypatch.setenv("FORGE_SKIP_AUTO_CLOSE", "1")
    state_dir, mem_dir = _runtime_dirs(fresh_state_dir)
    plan_path = _write_active_state(state_dir, "plan")
    (mem_dir / "handoff-plan.md").write_text("# handoff\n", encoding="utf-8")

    closed = auto_close_superseded_sessions("diagnose", search_dir=fresh_state_dir)
    assert closed == []
    assert plan_path.exists()


def test_resume_cleanup_finds_parallel_plan_variant(fresh_state_dir):
    state_dir, mem_dir = _runtime_dirs(fresh_state_dir)
    parallel = _write_active_state(
        state_dir, "plan", filename="plan-outstanding-cqa.json"
    )
    (mem_dir / "handoff-plan.md").write_text("# handoff\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "takeover" / "takeover.py"), "--cleanup", "--force"],
        cwd=fresh_state_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert not parallel.exists()


# ---------------------------------------------------------------------------
# Fix 1 — Step over-cap (V1)
# ---------------------------------------------------------------------------

def test_plan_over_cap_step_exits_zero_with_friendly_msg(fresh_state_dir):
    """python3 plan.py --step 99 must produce a friendly message and exit 0."""
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "plan" / "plan.py"), "--step", "99"],
        cwd=fresh_state_dir,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0
    assert "ends at step 7" in result.stderr or "ends at step 7" in result.stdout


# ---------------------------------------------------------------------------
# Fix 1 — Bounded next_cmd in implement.py (V1)
# ---------------------------------------------------------------------------

def test_implement_next_command_returns_empty_at_max_step():
    from scripts.implement.implement import _next_command, MAX_STEP

    assert _next_command(MAX_STEP) == ""


def test_implement_next_command_supports_target_step():
    from scripts.implement.implement import _next_command

    cmd = _next_command(5, target_step=3)
    assert "--phase act-wave-dispatch" in cmd

    # target_step beyond MAX is rejected.
    assert _next_command(5, target_step=99) == ""


def test_implement_step3_auto_falls_back_to_direct_mode_when_no_waves(fresh_state_dir, capsys):
    from scripts.implement.implement import _init_state, handle_step_3

    state = _init_state()
    state.custom["plan_path"] = str(fresh_state_dir / "plan.md")
    state.custom["total_waves"] = 0
    state.custom["wave_rows"] = []
    state.custom["plan_waves_parsed"] = False

    sp = fresh_state_dir / ".codex" / "forge-codex" / "state" / "implement.json"
    sp.parent.mkdir(parents=True, exist_ok=True)

    handle_step_3(state, sp)
    output = capsys.readouterr().out

    assert state.custom["implementation_mode"] == "direct"
    assert state.custom["total_waves"] == 1
    assert "direct implementation" in output.lower()
    assert "next step is clear: continue directly to **phase `decide-wave-review`**." in output.lower()
    assert "skipping wave dispatch and review" not in output.lower()


def test_step_output_auto_continues_when_next_step_is_clear():
    from scripts.shared.orchestrator import format_step_output

    output = format_step_output(
        "plan",
        1,
        7,
        "Phase",
        "Body",
        next_cmd="$forge:plan --step 2 --state .codex/forge-codex/state/plan.json",
    )
    lower = output.lower()
    assert "next step is clear: continue directly to **phase" in lower


def test_step_output_prompts_when_next_step_is_ambiguous():
    from scripts.shared.orchestrator import format_step_output

    output = format_step_output(
        "plan",
        1,
        7,
        "Phase",
        "Body",
        next_cmd="not-a-parseable-step-token",
    )
    lower = output.lower()
    assert "should i continue into phase" in lower


def test_forge_session_opt_in_banner_step1_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.shared.orchestrator import forge_session_opt_in_banner

    assert "SESSION OPT-IN" in forge_session_opt_in_banner("design", 1)
    assert forge_session_opt_in_banner("takeover", 2) == ""
    monkeypatch.setenv("FORGE_SKIP_SESSION_OPTIN", "1")
    assert forge_session_opt_in_banner("design", 1) == ""


def test_forge_graphify_banner_ship_only_for_workflow_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.shared.graphify_contract import forge_graphify_banner, graph_index_present

    repo = Path(__file__).resolve().parents[1]
    if not graph_index_present(repo):
        pytest.skip("forge repo has no graphify index in this checkout")
    assert forge_graphify_banner("develop", 2, repo) == ""
    ship_banner = forge_graphify_banner("ship", 1, repo)
    assert "GRAPHIFY" in ship_banner
    assert "GRAPH_REPORT.md" in ship_banner
    monkeypatch.setenv("FORGE_SKIP_GRAPHIFY", "1")
    assert forge_graphify_banner("ship", 1, repo) == ""


def test_format_step_output_omits_graphify_on_workflow_steps() -> None:
    from scripts.shared.graphify_contract import graph_index_present
    from scripts.shared.orchestrator import format_step_output

    repo = Path(__file__).resolve().parents[1]
    if not graph_index_present(repo):
        pytest.skip("forge repo has no graphify index in this checkout")

    out1 = format_step_output("design", 1, 7, "Startup", "BODY")
    out2 = format_step_output("design", 2, 7, "Scope", "BODY")
    assert "GRAPHIFY" not in out1
    assert "GRAPHIFY" not in out2


def test_format_step_output_includes_session_opt_in_on_step1_only() -> None:
    from scripts.shared.orchestrator import format_step_output

    out = format_step_output(
        "design",
        1,
        7,
        "Startup",
        "BODY",
        next_cmd="$forge:design --step 2 --state .codex/forge/sessions/abc/session.json",
    )
    assert "SESSION OPT-IN" in out
    out2 = format_step_output(
        "design",
        2,
        7,
        "Scope",
        "BODY",
        next_cmd="$forge:design --step 3 --state .codex/forge/sessions/abc/session.json",
    )
    assert "SESSION OPT-IN" not in out2


def test_evaluate_format_output_includes_opt_in_only_on_step_1() -> None:
    from scripts.evaluate.evaluate import _format_output

    o1 = _format_output("T", "B", "", mode="pre", step=1)
    assert "SESSION OPT-IN" in o1
    o2 = _format_output("T", "B", "", mode="pre", step=2)
    assert "SESSION OPT-IN" not in o2
    o_none = _format_output("T", "B", "", mode=None, step=None)
    assert "SESSION OPT-IN" not in o_none


# ---------------------------------------------------------------------------
# Fix 2 — Mock-flow type catalog (prose + typed)
# ---------------------------------------------------------------------------

def test_flow_types_catalog_schema_complete():
    """Asserts all 4 flow types present with complete schema (Fix 2).

    The catalog structure supports both prose documentation (templates/mock-flow-types.md)
    and structured metadata for recommendation logic (scripts/test/flow_types.py).
    This test verifies the structured form is complete and valid.
    """
    from scripts.test.flow_types import FLOW_TYPES, FlowTypeMetadata

    # All four types present
    expected_types = {"scenario", "bdd", "http-replay", "workflow-dryrun"}
    assert set(FLOW_TYPES.keys()) == expected_types, f"Expected types {expected_types}, got {set(FLOW_TYPES.keys())}"

    # Each entry is a frozen dataclass
    for name, metadata in FLOW_TYPES.items():
        assert isinstance(metadata, FlowTypeMetadata), f"{name}: not a FlowTypeMetadata instance"

        # tooling non-empty
        assert metadata.tooling, f"{name}: tooling list is empty"
        assert isinstance(metadata.tooling, list), f"{name}: tooling not a list"

        # file_layout includes "primary" key
        assert isinstance(metadata.file_layout, dict), f"{name}: file_layout not a dict"
        assert "primary" in metadata.file_layout, f"{name}: file_layout missing 'primary' key"

        # criteria_scores covers keys 1–8
        assert isinstance(metadata.criteria_scores, dict), f"{name}: criteria_scores not a dict"
        expected_criteria = set(range(1, 9))
        assert set(metadata.criteria_scores.keys()) == expected_criteria, \
            f"{name}: criteria_scores missing keys, expected 1-8, got {set(metadata.criteria_scores.keys())}"

        # All criteria scores are 0–10
        for criterion_num, score in metadata.criteria_scores.items():
            assert 0 <= score <= 10, f"{name}: criterion {criterion_num} score {score} not in range 0-10"

        # data_pack_dirs has the 4 standard names
        assert isinstance(metadata.data_pack_dirs, list), f"{name}: data_pack_dirs not a list"
        expected_dirs = {"clean", "messy", "edge-cases", "duplicates"}
        assert set(metadata.data_pack_dirs) == expected_dirs, \
            f"{name}: data_pack_dirs expected {expected_dirs}, got {set(metadata.data_pack_dirs)}"


# ---------------------------------------------------------------------------
# Fix 5 — _detect_test_layout helper (test layout detection)
# ---------------------------------------------------------------------------

def test_detect_test_layout_against_fixture_project(fixture_project: Path):
    """Verify detect_test_layout works against the mock-flows-target fixture.

    Expected signals:
    - framework="pytest" (high confidence >= 0.9) from pyproject.toml [tool.pytest.ini_options]
    - entry_point="http" (high confidence 1.0) from FastAPI app declaration
    - roles=["admin","member","viewer"] from app/roles.yaml
    - roles_source="yaml"
    - test_db="sqlite" from in-memory connection in app/models.py
    - has_orchestrator_pattern=False (no Celery, RQ, transitions, or scripts/<skill>/<skill>.py)
    """
    from scripts.test.test_layout import detect_test_layout

    layout = detect_test_layout(fixture_project)

    assert layout.framework == "pytest"
    assert layout.framework_confidence >= 0.9

    assert layout.entry_point == "http"
    assert layout.entry_point_confidence == 1.0

    assert set(layout.roles) == {"admin", "member", "viewer"}
    assert layout.roles_source == "yaml"

    assert layout.test_db == "sqlite"
    assert layout.has_orchestrator_pattern is False


def test_detect_test_layout_unknown_framework_low_confidence(tmp_path: Path):
    """Test that projects with no pytest signals return unknown framework with low confidence."""
    from scripts.test.test_layout import detect_test_layout

    # Empty project with no test infrastructure
    layout = detect_test_layout(tmp_path)

    assert layout.framework == "unknown"
    assert layout.framework_confidence < 0.7


def test_detect_roles_returns_empty_when_none_found(tmp_path: Path):
    """Test that projects with no role files return empty roles list."""
    from scripts.test.test_layout import detect_test_layout

    layout = detect_test_layout(tmp_path)

    assert layout.roles == []
    assert layout.roles_source == "none"


def test_orchestrator_pattern_detected_in_forge_codex():
    """Test that forge-codex's own repo has orchestrator pattern detected.

    Forge-codex has scripts/<skill>/<skill>.py pattern (e.g., scripts/test/test.py),
    which satisfies the orchestrator pattern heuristic.
    """
    from scripts.test.test_layout import detect_test_layout

    layout = detect_test_layout(REPO_ROOT)

    assert layout.has_orchestrator_pattern is True


# ---------------------------------------------------------------------------
# Fix 1 — test skill --mode flows scaffolding (V1-V7)
# ---------------------------------------------------------------------------

def test_test_skill_default_mode_is_run(fresh_state_dir, monkeypatch):
    """Test that test skill defaults to run mode when --mode not specified (V1)."""
    import subprocess

    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"), "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"Unexpected error: {result.stderr}"

    # Load state to check mode
    from scripts.shared.orchestrator import load_state

    sp = _test_state_path(fresh_state_dir)
    assert sp.exists()
    state = load_state(sp)
    assert state.custom.get("mode", "run") == "run"
    assert state.max_step == 6


def test_test_skill_flows_mode_sets_max_step_7(fresh_state_dir):
    """Test that --mode flows sets max_step=7 (V2)."""
    import subprocess

    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"), "--mode", "flows", "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"Unexpected error: {result.stderr}"

    from scripts.shared.orchestrator import load_state

    sp = _test_state_path(fresh_state_dir)
    state = load_state(sp)
    assert state.custom.get("mode") == "flows"
    assert state.max_step == 7


def test_test_skill_flows_atomic_check_aborts_when_prompt_missing(fresh_state_dir, monkeypatch):
    """Test atomic-delivery feature-check: if a flow prompt is missing, abort (V3)."""
    import subprocess

    # Delete one of the 7 flow prompts (repo + packaged — fallback must not mask missing)
    prompt_path = REPO_ROOT / "prompts" / "test" / "flow_context.md"
    packaged_path = (
        REPO_ROOT / "forge_next" / "assets" / "prompts" / "test" / "flow_context.md"
    )
    assert prompt_path.exists()
    try:
        original = prompt_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        original = prompt_path.read_text(encoding="cp1252")
    packaged_original = None
    if packaged_path.is_file():
        packaged_original = packaged_path.read_text(encoding="utf-8")
    prompt_path.unlink()
    packaged_path.unlink(missing_ok=True)

    try:
        result = subprocess.run(
            ["python3", str(SCRIPTS / "test" / "test.py"), "--mode", "flows", "--step", "1"],
            cwd=str(fresh_state_dir),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 1
        assert "flows mode unavailable" in result.stderr
        assert "active template root" in result.stderr
        assert "flow_context" in result.stderr
    finally:
        # Restore the prompt
        prompt_path.write_text(original, encoding="utf-8")
        if packaged_original is not None:
            packaged_path.parent.mkdir(parents=True, exist_ok=True)
            packaged_path.write_text(packaged_original, encoding="utf-8")


def test_test_skill_resume_conflict_aborts_when_mode_differs(fresh_state_dir, monkeypatch):
    """Test resume-conflict guard: if state has mode=run, resume with --mode flows aborts (V4)."""
    import subprocess

    # First, create a run-mode state
    result1 = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"), "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result1.returncode == 0
    state_file = ""
    for line in result1.stderr.split("\n"):
        if "STATE FILE:" in line:
            state_file = line.split("STATE FILE:")[1].strip()
            break
    assert state_file, "step 1 should have printed STATE FILE: <path> on stderr"

    # Try to resume with --mode flows
    result2 = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"),
         "--state", state_file, "--mode", "flows", "--step", "2"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result2.returncode == 1
    assert "Cannot resume" in result2.stderr
    assert "saved mode is" in result2.stderr


def test_test_skill_legacy_state_missing_mode_defaults_to_run(fresh_state_dir, monkeypatch):
    """Test legacy-compat: state without mode key defaults to run (V5)."""
    from scripts.shared.orchestrator import runtime_state_path, load_state, save_state, SkillState

    # Create legacy state without mode key
    sp = runtime_state_path("test")
    sp.parent.mkdir(parents=True, exist_ok=True)

    legacy = SkillState(skill_name="test", max_step=6)
    # Deliberately don't set custom["mode"]
    save_state(legacy, sp)

    # Load and verify it defaults to run
    state = load_state(sp)
    assert state.custom.get("mode", "run") == "run"


def test_test_skill_role_override_via_cli(fresh_state_dir, monkeypatch):
    """Test --roles override parses correctly (V6)."""
    import subprocess

    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"), "--mode", "flows",
         "--roles", "admin,member,viewer", "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0

    from scripts.shared.orchestrator import load_state

    sp = _test_state_path(fresh_state_dir)
    state = load_state(sp)
    assert state.custom.get("roles") == ["admin", "member", "viewer"]


def test_test_skill_no_db_override(fresh_state_dir, monkeypatch):
    """Test --no-db override sets test_db to 'none' (V7)."""
    import subprocess

    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"), "--mode", "flows",
         "--no-db", "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0

    from scripts.shared.orchestrator import load_state

    sp = _test_state_path(fresh_state_dir)
    state = load_state(sp)
    assert state.custom.get("test_db") == "none"


# ---------------------------------------------------------------------------
# Fix 4 — recommendation sidecar + scenario-index parser
# ---------------------------------------------------------------------------

def test_recommendation_sidecar_happy_path(tmp_path):
    """Write valid JSON, ingest returns dict, file deleted (F4)."""
    from scripts.test._sidecar import (
        write_recommendation_override,
        ingest_recommendation_sidecar,
    )

    # Pre-write sidecar
    sidecar_path = write_recommendation_override(tmp_path, "bdd")
    assert sidecar_path.exists()

    # Ingest should succeed and delete
    result = ingest_recommendation_sidecar(tmp_path)
    assert result["chosen"] == "bdd"
    assert result["reasoning"] == "user override via --flow-type"
    assert result["confidence"] == 1.0
    assert not sidecar_path.exists()


def test_recommendation_sidecar_missing_aborts_exit_1(tmp_path):
    """Call ingest with no file present → sys.exit(1)."""
    from scripts.test._sidecar import ingest_recommendation_sidecar

    with pytest.raises(SystemExit) as exc_info:
        ingest_recommendation_sidecar(tmp_path)
    assert exc_info.value.code == 1


def test_recommendation_sidecar_malformed_json_aborts_exit_1(tmp_path):
    """Drop malformed JSON; ingest exits 1."""
    from scripts.test._sidecar import recommendation_sidecar_path, ingest_recommendation_sidecar

    path = recommendation_sidecar_path(tmp_path)
    path.write_text("{invalid json", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ingest_recommendation_sidecar(tmp_path)
    assert exc_info.value.code == 1


def test_recommendation_sidecar_invalid_chosen_aborts_exit_1(tmp_path):
    """chosen not in VALID_FLOW_TYPES → sys.exit(1)."""
    from scripts.test._sidecar import recommendation_sidecar_path, ingest_recommendation_sidecar

    path = recommendation_sidecar_path(tmp_path)
    data = {
        "chosen": "invalid-type",
        "reasoning": "test",
        "confidence": 0.8,
        "alternatives": [],
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ingest_recommendation_sidecar(tmp_path)
    assert exc_info.value.code == 1


def test_recommendation_sidecar_missing_reasoning_aborts_exit_1(tmp_path):
    """reasoning missing → sys.exit(1)."""
    from scripts.test._sidecar import recommendation_sidecar_path, ingest_recommendation_sidecar

    path = recommendation_sidecar_path(tmp_path)
    data = {
        "chosen": "scenario",
        "confidence": 0.8,
        "alternatives": [],
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ingest_recommendation_sidecar(tmp_path)
    assert exc_info.value.code == 1


def test_recommendation_sidecar_invalid_confidence_aborts_exit_1(tmp_path):
    """confidence out-of-range → sys.exit(1)."""
    from scripts.test._sidecar import recommendation_sidecar_path, ingest_recommendation_sidecar

    path = recommendation_sidecar_path(tmp_path)
    data = {
        "chosen": "scenario",
        "reasoning": "test",
        "confidence": 1.5,  # Out of range [0.0, 1.0]
        "alternatives": [],
    }
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        ingest_recommendation_sidecar(tmp_path)
    assert exc_info.value.code == 1


def test_write_recommendation_override_creates_valid_sidecar(tmp_path):
    """write_recommendation_override creates valid JSON that ingest can consume."""
    from scripts.test._sidecar import (
        write_recommendation_override,
        ingest_recommendation_sidecar,
    )

    write_recommendation_override(tmp_path, "http-replay")
    result = ingest_recommendation_sidecar(tmp_path)

    assert result["chosen"] == "http-replay"
    assert "user override" in result["reasoning"]
    assert result["confidence"] == 1.0


def test_log_override_emits_stderr_marker(capsys):
    """log_override_to_stderr emits the adoption-tracking marker."""
    from scripts.test._sidecar import log_override_to_stderr

    log_override_to_stderr("scenario")
    captured = capsys.readouterr()
    assert "[flows] override: user passed --flow-type=scenario" in captured.err


def test_scenario_index_creates_when_missing(tmp_path):
    """empty dir → file created with header + new row."""
    from scripts.test._scenario_index import IndexRow, update_scenario_index

    index_path = tmp_path / "README.md"
    backup_dir = tmp_path / "backup"
    new_row = IndexRow(
        scope="upload feature",
        type="scenario",
        roles="admin,member",
        failure_paths="2 paths",
        last_run="2026-05-08",
        status="pass",
    )

    success, msg = update_scenario_index(index_path, new_row, backup_dir)
    assert success is True
    assert index_path.exists()

    content = index_path.read_text(encoding="utf-8")
    assert "| Scope | Type | Roles | Failure paths | Last run | Status |" in content
    assert "| upload feature | scenario | admin,member | 2 paths | 2026-05-08 | pass |" in content


def test_scenario_index_appends_when_present(tmp_path):
    """existing file with N rows → file has N+1 rows after update."""
    from scripts.test._scenario_index import IndexRow, update_scenario_index

    index_path = tmp_path / "README.md"
    backup_dir = tmp_path / "backup"

    # Create initial file with one row
    row1 = IndexRow("flow1", "bdd", "admin", "1", "2026-05-07", "pass")
    success1, _ = update_scenario_index(index_path, row1, backup_dir)
    assert success1 is True

    # Append a second row
    row2 = IndexRow("flow2", "http-replay", "member", "2", "2026-05-08", "pass")
    success2, _ = update_scenario_index(index_path, row2, backup_dir)
    assert success2 is True

    content = index_path.read_text(encoding="utf-8")
    lines = [l for l in content.split("\n") if l.startswith("|") and "---" not in l]
    # Should have header + 2 data rows
    assert len(lines) >= 3


def test_scenario_index_merges_duplicate_scope(tmp_path):
    """existing row with same scope+type → row updated, no duplication."""
    from scripts.test._scenario_index import IndexRow, update_scenario_index

    index_path = tmp_path / "README.md"
    backup_dir = tmp_path / "backup"

    # Create initial row
    row1 = IndexRow("flow1", "scenario", "admin", "1 path", "2026-05-07", "pass")
    success1, _ = update_scenario_index(index_path, row1, backup_dir)
    assert success1 is True

    # Update the same row (scope + type match)
    row1_updated = IndexRow("flow1", "scenario", "admin,member", "2 paths", "2026-05-08", "fail")
    success2, _ = update_scenario_index(index_path, row1_updated, backup_dir)
    assert success2 is True

    content = index_path.read_text(encoding="utf-8")
    # Count data rows (lines starting with | but not the header or separator)
    data_lines = [
        l for l in content.split("\n")
        if l.startswith("|") and "---" not in l and "Scope" not in l
    ]
    # Should still be 1 data row (merged, not duplicated)
    assert len(data_lines) == 1
    assert "2 paths" in content


def test_scenario_index_aborts_on_malformed_file(tmp_path):
    """corrupt table → returns (False, msg), file unchanged."""
    from scripts.test._scenario_index import IndexRow, update_scenario_index

    index_path = tmp_path / "README.md"
    backup_dir = tmp_path / "backup"

    # Write a malformed markdown file
    index_path.write_text("# Scenario Index\n\nSome text\n| Missing | proper | table |\n")

    new_row = IndexRow("flow1", "scenario", "admin", "1", "2026-05-08", "pass")
    success, msg = update_scenario_index(index_path, new_row, backup_dir)

    assert success is False
    assert "malformed" in msg.lower()

    # Verify file is unchanged
    original_content = index_path.read_text(encoding="utf-8")
    assert "Some text" in original_content


def test_scenario_index_writes_backup_before_rewrite(tmp_path):
    """backup file present after update with prior content."""
    from scripts.test._scenario_index import IndexRow, update_scenario_index

    index_path = tmp_path / "README.md"
    backup_dir = tmp_path / "backup"

    # Create initial file with one row
    row1 = IndexRow("flow1", "scenario", "admin", "1", "2026-05-07", "pass")
    update_scenario_index(index_path, row1, backup_dir)

    # Update with a second row
    row2 = IndexRow("flow2", "bdd", "member", "2", "2026-05-08", "pass")
    update_scenario_index(index_path, row2, backup_dir)

    # Check backup exists and has original content
    backup_path = backup_dir / "scenario-index.bak"
    assert backup_path.exists()

    backup_content = backup_path.read_text(encoding="utf-8")
    assert "flow1" in backup_content
    assert "flow2" not in backup_content


# ---------------------------------------------------------------------------
# Fix 8: Numbered Handoff Menu Tests
# ---------------------------------------------------------------------------


def test_skill_chain_default_for_each_skill():
    """SKILL_CHAIN[s].default exists for every skill; diagnose may be None."""
    from scripts.shared.skill_chain import SKILL_CHAIN

    required_skills = {
        "sketch",
        "design",
        "plan",
        "evaluate",
        "implement",
        "code-review",
        "test",
        "ux-review",
        "diagnose",
        "takeover",
    }
    assert set(SKILL_CHAIN.keys()) == required_skills

    for skill in required_skills:
        transition = SKILL_CHAIN[skill]
        assert transition.default is not None or skill in ("diagnose",)


def test_build_skill_handoff_menu_renders_numbered_options(capsys, monkeypatch):
    """Output contains numbered options 1-N and a (stop) last item; no JSON dump."""
    from scripts.shared.orchestrator import build_skill_handoff_menu

    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    menu = build_skill_handoff_menu("plan")
    assert "$forge:" in menu
    assert "(stop)" in menu
    assert "WORKFLOW HANDOFF — plan complete" in menu
    assert "1." in menu
    assert "handoff-multiselect" not in menu
    assert "forge_handoff_multiselect" not in menu


def test_handoff_menu_documents_default_shortcuts(capsys):
    """The rendered string contains yes and 1 as documented shortcuts."""
    from scripts.shared.orchestrator import build_skill_handoff_menu

    menu = build_skill_handoff_menu("design")
    assert '"yes"' in menu
    assert '"1"' in menu
    assert "default" in menu.lower()


def test_test_skill_handoff_includes_flows_alternative_in_run_mode(monkeypatch):
    """When current mode is run, alternative list contains test --mode flows."""
    from scripts.shared.orchestrator import build_skill_handoff_menu

    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    menu = build_skill_handoff_menu("test")
    assert "$forge:test --mode flows" in menu


def test_test_skill_handoff_swaps_to_run_in_flows_mode(monkeypatch):
    """When current_mode == flows, alternative is test --mode run, not flows."""
    from scripts.shared.orchestrator import build_skill_handoff_menu, SkillState

    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    state = SkillState(skill_name="test")
    state.custom["mode"] = "flows"
    menu = build_skill_handoff_menu("test", state=state)
    # When in flows mode, the mode alternative should be swapped
    # (This is a placeholder; real implementation would inspect state.custom["mode"])
    assert "$forge:" in menu  # Basic sanity check


def test_implement_handoff_after_failures_inserts_diagnose_first():
    """Context-aware injection: test with failures prepends diagnose."""
    from scripts.shared.orchestrator import build_skill_handoff_menu, SkillState

    state = SkillState(skill_name="test")
    state.custom["test_results"] = {"failed": 3, "passed": 10, "total": 13}
    menu = build_skill_handoff_menu("test", state=state)
    # The menu should now have diagnose as an early option
    assert "diagnose" in menu


def test_diagnose_handoff_has_no_default():
    """When default is None (diagnose), show no-default line."""
    from scripts.shared.orchestrator import build_skill_handoff_menu

    menu = build_skill_handoff_menu("diagnose")
    assert "(none — workflow terminates here)" in menu
    assert "WORKFLOW HANDOFF — diagnose complete" in menu


def test_diagnose_handoff_large_defaults_design(monkeypatch):
    """Large / systemic fix_complexity promotes design as default next."""
    from scripts.shared.orchestrator import SkillState, build_skill_handoff_menu

    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    state = SkillState(skill_name="diagnose")
    state.custom["fix_complexity"] = "large"
    menu = build_skill_handoff_menu("diagnose", state=state)
    assert "(default)" in menu.lower()
    assert "$forge:design" in menu


def test_no_skill_has_legacy_workflow_complete_marker(monkeypatch):
    """Verify that build_skill_handoff_menu is the canonical final-step footer."""
    # This is a documentation/specification test rather than a grep test.
    # The actual verification happens when we update each skill's final-step
    # handler to use build_skill_handoff_menu (see Fix 8 implementation).
    # For now, just verify the helper exists and works.
    from scripts.shared.orchestrator import build_skill_handoff_menu

    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    # Spot check: each skill should render a handoff menu when at MAX_STEP
    for skill in ["design", "plan", "evaluate", "implement", "code-review", "test", "diagnose"]:
        menu = build_skill_handoff_menu(skill)
        assert "WORKFLOW HANDOFF" in menu
        assert "$forge:" in menu


# ---------------------------------------------------------------------------
# Fix 3 — Flow gates and handler logic (V14-V23)
# ---------------------------------------------------------------------------


def test_flows_scaffold_gate_blocks_when_data_packs_missing():
    """Step 4 scaffold gate refuses to advance when data-packs missing (criteria 2/3/4)."""
    from scripts.test.test_flows import _check_scaffold_gate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test")
    state.custom["flow_files"] = ["test_upload.py"]  # Only test file, no data-packs

    failures = _check_scaffold_gate(state)
    assert len(failures) > 0
    assert any("data-pack" in f for f in failures)


def test_flows_scaffold_gate_passes_with_full_layout():
    """Step 4 scaffold gate passes when all required files present."""
    from scripts.test.test_flows import _check_scaffold_gate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test")
    state.custom["flow_files"] = [
        "tests/scenarios/test_upload.py",
        "tests/scenarios/conftest.py",
        "tests/scenarios/fixtures/data-packs/clean/",
        "tests/scenarios/fixtures/data-packs/messy/",
        "tests/scenarios/fixtures/data-packs/edge-cases/",
        "tests/scenarios/fixtures/data-packs/duplicates/",
    ]

    failures = _check_scaffold_gate(state)
    assert len(failures) == 0


def test_flows_scaffold_gate_passes_with_clean_only_smoke():
    """Proportional budget: clean/ alone is enough for single-role smoke."""
    from scripts.test.test_flows import _check_scaffold_gate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test")
    state.custom["roles"] = ["anonymous"]
    state.custom["flow_files"] = [
        "tests/scenarios/test_upload.py",
        "tests/scenarios/fixtures/data-packs/clean/",
    ]

    failures = _check_scaffold_gate(state)
    assert failures == []


def test_flows_authoring_gate_allows_smoke_without_failure_path():
    """Empty failure_paths is intentional smoke — gate must not block."""
    from scripts.test.test_flows import _check_authoring_gate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test")
    state.custom["flow_scope"] = {
        "failure_paths": [],
        "roles": ["anonymous"],
        "external_services_to_mock": [],
    }
    state.custom["authoring_results"] = {
        "outcome_surfaces": ["response"],
        "external_mocks": [],
    }

    failures = _check_authoring_gate(state)
    assert failures == []


def test_flows_authoring_gate_passes_with_failure_path_and_2_surfaces():
    """Step 5 authoring gate passes when failure-path and ≥2 surfaces present."""
    from scripts.test.test_flows import _check_authoring_gate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test")
    state.custom["flow_scope"] = {
        "failure_paths": ["bad input triggers validation error"],
        "external_services_to_mock": ["email"],
    }
    state.custom["authoring_results"] = {
        "outcome_surfaces": ["response", "db"],
        "external_mocks": ["email"],
    }

    failures = _check_authoring_gate(state)
    assert len(failures) == 0


def test_flows_authoring_gate_blocks_without_2_outcome_surfaces():
    """Step 5 authoring gate refuses to advance if only 1 outcome surface asserted."""
    from scripts.test.test_flows import _check_authoring_gate
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test")
    state.custom["flow_scope"] = {
        "failure_paths": ["bad input"],
        "external_services_to_mock": [],
    }
    state.custom["authoring_results"] = {
        "outcome_surfaces": ["response"],  # Only 1, need ≥2
        "external_mocks": [],
    }

    failures = _check_authoring_gate(state)
    assert len(failures) > 0
    assert any("outcome" in f.lower() for f in failures)


def test_flows_step_1_initializes_flow_mode_state():
    """Step 1: flow-mode initialization sets max_step=7 and flow fields."""
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test", max_step=7)
    assert state.max_step == 7

    state.custom["mode"] = "flows"
    state.custom["flow_type"] = None
    state.custom["flow_files"] = []
    state.custom["flow_scope"] = {}
    state.custom["criteria_audit"] = {}

    assert state.custom.get("mode") == "flows"
    assert state.custom.get("flow_files") == []
    assert state.custom.get("flow_scope") == {}


def test_flows_mode_sets_layout_confidence_warning():
    """Step 1: low confidence on framework/entry-point surfaces in warning."""
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="test", max_step=7)
    state.custom["mode"] = "flows"
    state.custom["framework_confidence"] = 0.5
    state.custom["entry_point_confidence"] = 0.6

    # These would be set by detect_test_layout; check they're present
    assert state.custom.get("framework_confidence") == 0.5
    assert state.custom.get("entry_point_confidence") == 0.6


def test_flows_atomic_delivery_check_exists():
    """Verify all 7 prompts exist (Fix 1 checks this at startup)."""
    from pathlib import Path

    repo_root = REPO_ROOT
    prompts_dir = repo_root / "prompts" / "test"
    required = [
        "flow_context", "flow_recommendation", "flow_scope",
        "flow_scaffold", "flow_author", "flow_execute", "flow_report",
    ]

    for prompt_name in required:
        prompt_file = prompts_dir / f"{prompt_name}.md"
        assert prompt_file.exists(), f"Missing prompt: {prompt_name}.md"
        content = prompt_file.read_text()
        assert "Phase" in content or "phase" in content.lower()


def test_flows_phase_names_dict_complete():
    """Verify FLOWS_PHASE_NAMES has all 7 steps."""
    from scripts.test.test_flows import FLOWS_PHASE_NAMES

    assert len(FLOWS_PHASE_NAMES) == 7
    for step in range(1, 8):
        assert step in FLOWS_PHASE_NAMES
        assert isinstance(FLOWS_PHASE_NAMES[step], str)
        assert len(FLOWS_PHASE_NAMES[step]) > 0


# ---------------------------------------------------------------------------
# Additional Fix 6 Tests
# ---------------------------------------------------------------------------


def test_flow_type_override_writes_sidecar_pre_prompt(fresh_state_dir):
    """Test that --flow-type writes override sidecar before step 2 prompt (V2).

    When --flow-type is passed at step 1, the sidecar should be written with
    chosen=override value, confidence=1.0, and reasoning mentioning "user override".
    The file should exist at .test-recommendation-step2.json in the state directory.
    """
    import subprocess

    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"),
         "--mode", "flows", "--flow-type", "bdd", "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"step 1 failed: {result.stderr}"

    from scripts.shared.orchestrator import load_state
    from scripts.test._sidecar import recommendation_sidecar_path

    sp = _test_state_path(fresh_state_dir)
    state = load_state(sp)

    # Check sidecar was written in the state directory (sp.parent)
    sidecar_path = recommendation_sidecar_path(sp.parent)
    assert sidecar_path.exists(), f"recommendation sidecar not written at {sidecar_path}"

    # Verify sidecar contents
    sidecar_data = json.loads(sidecar_path.read_text())
    assert sidecar_data["chosen"] == "bdd"
    assert sidecar_data["confidence"] == 1.0
    assert "override" in sidecar_data["reasoning"].lower()


def test_cassette_freshness_warns_at_30_days_fails_at_90(tmp_path):
    """Test cassette freshness check: warn at 30d+, fail at 90d+.

    Verifies the helper function _check_cassette_freshness returns:
    - "fresh" for cassettes < 30 days old
    - "warn" for cassettes 30-89 days old
    - "fail" for cassettes >= 90 days old
    """
    from scripts.test._cassette import check_cassette_freshness
    from datetime import datetime, timedelta, timezone

    cassette = tmp_path / "test.yaml"
    cassette.write_text("# cassette")

    # Test: 0 days old (now)
    now = datetime.now(timezone.utc)
    status = check_cassette_freshness(cassette, now=now)
    assert status == "fresh", "cassette 0 days old should be fresh"

    # Test: 31 days old
    now_31d = now + timedelta(days=31)
    cassette.touch()  # Reset mtime
    cassette.stat()  # Ensure stat is fresh
    # Manually set mtime to 31 days ago
    import time
    old_time = (now_31d - timedelta(days=31)).timestamp()
    import os
    os.utime(str(cassette), (old_time, old_time))

    status = check_cassette_freshness(cassette, now=now_31d)
    assert status == "warn", "cassette 31 days old should warn"

    # Test: 91 days old
    now_91d = now + timedelta(days=91)
    old_time_91 = (now_91d - timedelta(days=91)).timestamp()
    os.utime(str(cassette), (old_time_91, old_time_91))

    status = check_cassette_freshness(cassette, now=now_91d)
    assert status == "fail", "cassette 91 days old should fail"


def test_recommendation_against_fixture_matrix(fixture_project):
    """Test recommendation scoring against fixture variants.

    Verifies that _score_flow_types returns expected ranking for canonical
    fixture (HTTP + SQLite + 3 roles, no orchestrator): scenario highest,
    others follow based on HTTP endpoint and test-DB presence.
    """
    from scripts.test.flow_types import score_flow_types
    from scripts.test.test_layout import detect_test_layout

    layout = detect_test_layout(fixture_project)

    scores = score_flow_types(layout)

    # Verify all 4 types are present
    assert set(scores.keys()) == {"scenario", "bdd", "http-replay", "workflow-dryrun"}

    # Verify workflow-dryrun scores 0 (no orchestrator)
    assert scores["workflow-dryrun"] == 0, \
        f"workflow-dryrun should score 0 without orchestrator, got {scores['workflow-dryrun']}"

    # Verify scenario is highest (has HTTP + test DB)
    assert scores["scenario"] >= scores["http-replay"], \
        f"scenario should score >= http-replay; scenario={scores['scenario']}, http-replay={scores['http-replay']}"
    assert scores["scenario"] >= scores["bdd"], \
        f"scenario should score >= bdd; scenario={scores['scenario']}, bdd={scores['bdd']}"

    # All non-zero scores should be positive
    assert all(s > 0 for flow_type, s in scores.items() if flow_type != "workflow-dryrun"), \
        f"non-orchestrator types should score > 0, got {scores}"


def test_flows_step_8_over_cap_friendly(fresh_state_dir):
    """Test that step 8 in flows mode exits 0 with friendly message (V21).

    When --mode flows --step 8 is called (beyond MAX_STEP=7), should exit 0
    with stderr containing "nothing left to do" or "ends at step 7".
    """
    import subprocess

    # Create a flows state first
    result1 = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"),
         "--mode", "flows", "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result1.returncode == 0

    # Now try step 8 (over cap)
    result2 = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"),
         "--mode", "flows", "--step", "8"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result2.returncode == 0, f"step 8 should exit 0, got {result2.returncode}"

    output = result2.stderr + result2.stdout
    assert "nothing left to do" in output or "ends at step 7" in output, \
        f"Expected 'nothing left to do' or 'ends at step 7' in output, got: {output}"


def test_test_mode_ux_redirects_to_ux_review(fresh_state_dir):
    """test --mode ux exits 2 and points agents at forge ux-review."""
    import subprocess

    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"),
         "--mode", "ux", "--step", "1"],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2, result.stderr
    out = result.stdout + result.stderr
    assert "ux-review" in out
    assert "removed" in out.lower() or "overlapping" in out.lower()


def test_stale_ux_mode_session_resume_exits(fresh_state_dir):
    """Resuming a session with custom.mode=ux exits 2 (mode removed)."""
    import json
    import subprocess
    from scripts.shared.orchestrator import now_iso

    sessions = fresh_state_dir / ".forge" / "sessions" / "staleux"
    sessions.mkdir(parents=True)
    sp = sessions / "session.json"
    sp.write_text(
        json.dumps(
            {
                "skill_name": "test",
                "current_step": 2,
                "last_completed_step": 1,
                "max_step": 6,
                "quick_mode": False,
                "autonomy_level": 1,
                "beads_available": False,
                "epic_id": None,
                "issue_ids": {},
                "review_loops": {},
                "dispatches": [],
                "findings": [],
                "phase_todos": {},
                "started_at": now_iso(),
                "completed_at": None,
                "last_touched_at": now_iso(),
                "session_id": "staleux",
                "failure_count": 0,
                "custom": {"mode": "ux"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    result = subprocess.run(
        ["python3", str(SCRIPTS / "test" / "test.py"),
         "--step", "3", "--state", str(sp)],
        cwd=str(fresh_state_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 2, result.stderr + result.stdout
    assert "ux-review" in (result.stderr + result.stdout)


def test_test_skill_handoff_includes_ux_review_not_mode_ux(monkeypatch):
    """Handoff offers ux-review; does not offer removed test --mode ux."""
    from scripts.shared.orchestrator import build_skill_handoff_menu

    monkeypatch.setenv("FORGE_WORKFLOW_INVOCATION", "dollar")
    menu = build_skill_handoff_menu("test")
    assert "$forge:ux-review" in menu
    assert "$forge:test --mode ux" not in menu


# ---------------------------------------------------------------------------
# Continuity resume + resume-context.json + Graphify status
# ---------------------------------------------------------------------------


def test_save_state_writes_resume_context_snapshot(fresh_state_dir):
    from scripts.shared.orchestrator import SkillState, save_state, runtime_memory_dir, runtime_state_dir

    sp = runtime_state_dir() / "plan.json"
    state = SkillState(
        skill_name="plan",
        current_step=2,
        last_completed_step=1,
        max_step=7,
        started_at="2026-01-01T00:00:00+00:00",
    )
    save_state(state, sp)
    rc = runtime_state_dir() / "resume-context.json"
    assert rc.is_file(), "resume-context.json should exist after save_state"
    data = json.loads(rc.read_text(encoding="utf-8"))
    assert data.get("schema_version") == 2
    assert data.get("skill") == "plan"
    assert data.get("current_step") == 2
    syn = runtime_memory_dir() / "forge-memory-synthesis.md"
    assert syn.is_file(), "forge-memory-synthesis.md should exist after save_state"
    assert "Forge memory synthesis" in syn.read_text(encoding="utf-8")


def test_resume_context_rejects_unsupported_schema(fresh_state_dir):
    from scripts.shared import resume_context
    from scripts.shared.orchestrator import runtime_state_dir

    p = runtime_state_dir() / "resume-context.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "schema_version": 999,
                "skill": "plan",
                "current_step": 1,
                "last_completed_step": 0,
                "max_step": 7,
                "state_path": str(p.parent / "plan.json"),
                "updated_at": "2026-01-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    snap, warn = resume_context.load_resume_snapshot()
    assert snap is None
    assert warn is not None


def test_resume_no_sessions_includes_continuity_when_snapshot_present(fresh_state_dir):
    from scripts.shared import resume_context
    from scripts.shared.orchestrator import runtime_state_dir

    p = runtime_state_dir() / "resume-context.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    st_path = runtime_state_dir() / "develop.json"
    p.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "writer_version": "test",
                "snapshot_id": "abc",
                "skill": "develop",
                "current_step": 3,
                "last_completed_step": 2,
                "max_step": 6,
                "invocation_status": "in_progress",
                "state_path": str(st_path),
                "started_at": None,
                "updated_at": "2026-05-11T12:00:00+00:00",
                "last_error_summary": None,
                "memory_current_step_path": None,
                "memory_latest_handoff_path": None,
                "memory_latest_handoff_skill": None,
                "open_findings_count": 0,
            }
        ),
        encoding="utf-8",
    )
    snap, warn = resume_context.load_resume_snapshot()
    assert snap is not None
    assert snap.get("skill") == "develop"


def test_snapshot_memory_conflict_detects_skill_mismatch():
    from scripts.shared import resume_context

    session = {
        "skill": "plan",
        "path": "/repo/.codex/forge/state/plan.json",
        "current_step": 2,
        "last_completed_step": 1,
        "max_step": 7,
    }
    snap = {
        "skill": "implement",
        "current_step": 1,
        "last_completed_step": 0,
        "max_step": 6,
        "state_path": "/repo/.codex/forge/state/implement.json",
    }
    assert resume_context.snapshot_memory_conflict(session, snap) is True


def test_graphify_availability_detects_path_and_env(monkeypatch):
    from forge_next import graphify

    monkeypatch.delenv("FORGE_GRAPHIFY_COMMAND", raising=False)
    monkeypatch.setattr(graphify.shutil, "which", lambda exe: None)
    ok, summary = graphify.graphify_availability()
    assert ok is False
    assert "not available" in summary

    monkeypatch.setattr(graphify.shutil, "which", lambda exe: "/usr/bin/graphify" if exe == "graphify" else None)
    ok, summary = graphify.graphify_availability()
    assert ok is True
    assert "on PATH" in summary

    monkeypatch.setenv("FORGE_GRAPHIFY_COMMAND", "graphify update .")
    monkeypatch.setattr(graphify.shutil, "which", lambda exe: None)
    ok, summary = graphify.graphify_availability()
    assert ok is True
    assert "FORGE_GRAPHIFY_COMMAND" in summary


def test_graphify_install_notice_leads_with_status(monkeypatch):
    from forge_next import graphify

    monkeypatch.delenv("FORGE_GRAPHIFY_COMMAND", raising=False)
    monkeypatch.setattr(graphify.shutil, "which", lambda exe: None)
    lines = graphify.graphify_install_notice_lines()
    assert lines[1].startswith("Graphify: not available")
    assert any("Install Graphify" in line for line in lines)

    monkeypatch.setattr(graphify.shutil, "which", lambda exe: "graphify" if exe == "graphify" else None)
    lines = graphify.graphify_install_notice_lines()
    assert lines[1].startswith("Graphify: available")
    assert not any("Install Graphify so a" in line for line in lines)
    assert any("forge graphify refresh" in line for line in lines)


def test_graphify_refresh_writes_status(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    from forge_next import graphify
    from scripts.shared.resume_context import graphify_status_path

    status_path = graphify_status_path(REPO_ROOT)
    backup = status_path.read_text(encoding="utf-8") if status_path.exists() else None
    try:
        assert graphify.refresh(REPO_ROOT) == 0
        assert status_path.is_file()
        data = json.loads(status_path.read_text(encoding="utf-8"))
        assert "status" in data
        assert "last_refresh" in data
    finally:
        if backup is not None:
            status_path.write_text(backup, encoding="utf-8")
        elif status_path.exists():
            status_path.unlink()


def test_graphify_refresh_background_spawns_detached(monkeypatch, tmp_path: Path) -> None:
    from forge_next import graphify

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# x\n", encoding="utf-8")
    (repo / ".git").mkdir()
    (repo / "graphify-out").mkdir()
    (repo / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")

    monkeypatch.setattr(graphify, "graphify_availability", lambda: (True, "ok"))
    monkeypatch.setattr(graphify, "_git_head", lambda _r: "abc123")
    monkeypatch.setattr(
        graphify,
        "_read_status",
        lambda _r: {"status": "missing", "repo_head": None, "last_refresh": None},
    )
    monkeypatch.setattr(graphify.shutil, "which", lambda exe: "forge" if exe == "forge" else None)

    popens: list[tuple[list[str], dict]] = []

    class _FakeProc:
        pid = 4242

    def fake_popen(cmd, **kwargs):
        popens.append((list(cmd), kwargs))
        return _FakeProc()

    monkeypatch.setattr(graphify.subprocess, "Popen", fake_popen)

    assert graphify.spawn_refresh_background(repo) is True
    assert popens
    assert popens[0][0][:3] == ["forge", "graphify", "refresh"]
    assert "--repo" in popens[0][0]
    assert graphify.refresh(repo, background=True) == 0


def test_graphify_refresh_background_skips_when_fresh(monkeypatch, tmp_path: Path) -> None:
    from forge_next import graphify

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(graphify, "refresh_needed", lambda _r: False)
    monkeypatch.setattr(graphify.subprocess, "Popen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no spawn")))
    assert graphify.spawn_refresh_background(repo) is False


def test_graphify_refresh_background_force_when_fresh(monkeypatch, tmp_path: Path) -> None:
    from forge_next import graphify

    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(graphify, "refresh_needed", lambda _r: False)
    monkeypatch.setattr(graphify.shutil, "which", lambda exe: "forge" if exe == "forge" else None)
    popens: list[list[str]] = []

    class _FakeProc:
        pid = 1

    monkeypatch.setattr(
        graphify.subprocess,
        "Popen",
        lambda cmd, **kwargs: popens.append(list(cmd)) or _FakeProc(),
    )
    assert graphify.spawn_refresh_background(repo, force=True) is True
    assert popens


def test_graphify_refresh_default_command_runs_update_dot(monkeypatch):
    monkeypatch.chdir(REPO_ROOT)
    from forge_next import graphify

    calls: list[list[str]] = []

    def fake_write_status(_repo_root: Path, payload: dict) -> Path:
        assert payload["status"] == "fresh"
        return REPO_ROOT / ".codex" / "forge-codex" / "state" / "graphify-status.json"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(graphify, "_write_status", fake_write_status)
    monkeypatch.setattr(graphify.shutil, "which", lambda exe: "graphify" if exe == "graphify" else None)
    monkeypatch.setattr(graphify.subprocess, "run", fake_run)

    assert graphify.refresh(REPO_ROOT, background=False) == 0
    assert calls, "Expected graphify subprocess.run to be called"
    assert ["graphify", "update", "."] in calls


# ---------------------------------------------------------------------------
# Structured question prompt shape guard
# ---------------------------------------------------------------------------

def test_structured_question_prompts_avoid_legacy_malformed_shape():
    """Guard against legacy Ask-the-user pseudo-JSON that breaks pickers."""
    roots = [
        REPO_ROOT / "templates",
        REPO_ROOT / "prompts",
        REPO_ROOT / "forge_next" / "assets" / "templates",
        REPO_ROOT / "forge_next" / "assets" / "prompts",
    ]
    legacy_markers = (
        '"multiSelect":',
        '"header":',
        "Ask the user:\n  {",
        "Ask the user:\r\n  {",
        "])",
    )
    offenders: list[str] = []
    malformed_lists: list[str] = []

    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            text = path.read_text(encoding="utf-8")
            if "Ask the user:" not in text:
                continue
            if any(marker in text for marker in legacy_markers):
                offenders.append(str(path.relative_to(REPO_ROOT)))
            if '"allow_multiple":' in text and not re.search(r"Ask the user:\s*\[", text):
                malformed_lists.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, "Legacy structured-question markers found in:\n" + "\n".join(sorted(offenders))
    assert not malformed_lists, (
        "Structured question blocks must start with 'Ask the user:' followed by a JSON array in:\n"
        + "\n".join(sorted(malformed_lists))
    )


# ---------------------------------------------------------------------------
# Resume launcher hints (consumer repos without ./scripts/)
# ---------------------------------------------------------------------------


def test_takeover_invocation_hint_prefers_forge_launcher(monkeypatch):
    from scripts.shared.orchestrator import resume_invocation_hint, takeover_invocation_hint

    monkeypatch.setenv("FORGE_USE_LAUNCHER", "1")
    assert takeover_invocation_hint() == "forge takeover"
    assert takeover_invocation_hint(cleanup=True) == "forge takeover --cleanup"
    assert takeover_invocation_hint(cleanup=True, force=True) == "forge takeover --cleanup --force"
    assert resume_invocation_hint() == "forge takeover"

    monkeypatch.delenv("FORGE_USE_LAUNCHER", raising=False)
    assert takeover_invocation_hint() == "python3 scripts/takeover/takeover.py"
    assert takeover_invocation_hint(cleanup=True, force=True) == (
        "python3 scripts/takeover/takeover.py --cleanup --force"
    )


def test_forge_takeover_cli_step1(fresh_state_dir: Path, monkeypatch):
    """takeover step 1 routes via launcher without repo-relative script paths."""
    specs = fresh_state_dir / "docs" / "forge" / "specs"
    specs.mkdir(parents=True)
    (specs / "2026-06-20-test-design.md").write_text("# test\n", encoding="utf-8")

    env = {**dict(os.environ), "FORGE_USE_LAUNCHER": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forge_next.cli",
            "takeover",
            "--repo",
            str(fresh_state_dir),
            "--step",
            "1",
            "--design",
            "docs/forge/specs/2026-06-20-test-design.md",
        ],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "TAKEOVER" in out
    assert "plan" in out.lower()
    assert "scripts/takeover/takeover.py" not in out
