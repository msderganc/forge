"""Wave 6: diagnose on declarative skill_runner (python escapes only)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _repo_on_path():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture
def forge_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FORGE_CODEX_ROOT", str(tmp_path / ".codex" / "forge"))
    (tmp_path / ".codex" / "forge").mkdir(parents=True)
    monkeypatch.chdir(REPO_ROOT)
    monkeypatch.delenv("FORGE_SKILL_ENGINE", raising=False)
    return tmp_path


def test_diagnose_manifest_python_gates_only():
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("diagnose", REPO_ROOT)
    assert manifest.max_step == 7
    assert manifest.steps[0].phase == "Frame"
    assert all(g.kind == "python" for g in manifest.gates)
    assert not any(g.kind == "schema" for g in manifest.gates)
    assert all(g.callable and "diagnose_gates" in g.callable for g in manifest.gates)
    by_id = {g.id: g for g in manifest.gates}
    assert by_id["diagnose_repro_loop"].steps == (3,)
    assert by_id["diagnose_register_and_quartet"].steps == (4,)
    assert by_id["diagnose_step7_closure"].steps == (7,)


def test_diagnose_gate_escape_invoked(forge_runtime, monkeypatch, capsys):
    from scripts.shared import skill_runner
    from scripts.shared.orchestrator import find_state_file, load_state, save_state
    from scripts.shared.skill_manifest import load_manifest
    from scripts.shared.skill_runner import run_skill

    manifest = load_manifest("diagnose", REPO_ROOT)
    gate = next(g for g in manifest.gates if g.id == "diagnose_repro_loop")
    assert gate.callable == "scripts.diagnose.diagnose_gates:run_repro_loop_gate"

    calls: list[dict] = []
    real_resolve = skill_runner.resolve_callable

    def _fake_gate(*, state, step, state_path, gate):  # noqa: A002
        del state_path
        calls.append({"step": step, "gate_id": gate.id})
        state.custom["_await_same_step"] = True

    def _resolve(spec: str):
        if spec == gate.callable:
            return _fake_gate
        return real_resolve(spec)

    monkeypatch.setattr(skill_runner, "resolve_callable", _resolve)

    assert run_skill("diagnose", ["--step", "1"], repo_root=REPO_ROOT) == 0
    sp = find_state_file("diagnose")
    assert sp is not None and sp.exists()
    state = load_state(sp)
    state.mark_step_complete(1)
    state.mark_step_complete(2)
    state.current_step = 2
    save_state(state, sp)

    code = run_skill(
        "diagnose",
        ["--step", "3", "--state", str(sp)],
        repo_root=REPO_ROOT,
    )
    assert code == 0
    assert calls, "diagnose_repro_loop python escape was not invoked"
    assert calls[0]["step"] == 3
    assert calls[0]["gate_id"] == "diagnose_repro_loop"
    capsys.readouterr()


def test_diagnose_removed_from_skill_phases_map():
    from scripts.shared.skill_phases import _SKILL_PHASE_NAMES, phase_names_for

    assert "diagnose" not in _SKILL_PHASE_NAMES
    phases = phase_names_for("diagnose")
    assert phases[1] == "Frame"
    assert phases[7] == "Handoff"
