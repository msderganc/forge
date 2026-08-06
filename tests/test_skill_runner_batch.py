"""Wave 3 batch migrations: ship, ux-review, plan, implement, code-review."""

from __future__ import annotations

import re
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


def _run(skill: str, argv: list[str], *, monkeypatch: pytest.MonkeyPatch):
    from scripts.shared.skill_runner import run_skill

    return run_skill(skill, argv, repo_root=REPO_ROOT)


def test_ship_step1_invokes_graphify_and_deferred_probes(
    forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys
):
    refresh_calls: list[tuple] = []
    probe_calls: list[Path] = []

    monkeypatch.setattr(
        "forge_next.graphify_enforcement.graphify_fully_disabled",
        lambda _root: False,
    )

    def fake_refresh(repo_root, **kwargs):
        refresh_calls.append((repo_root, kwargs))

    def fake_probes(repo_root):
        probe_calls.append(repo_root)
        return ["probe-line-ok"]

    monkeypatch.setattr("forge_next.graphify.refresh", fake_refresh)
    monkeypatch.setattr(
        "scripts.shared.structural_probes_gate.run_ship_deferred_probe_passes",
        fake_probes,
    )

    code = _run("ship", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Graphify preflight" in out
    assert refresh_calls, "forge_next.graphify.refresh must be invoked on ship step 1"
    assert probe_calls, "run_ship_deferred_probe_passes must be invoked on ship step 1"


def test_ux_review_step1_orient(forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys):
    code = _run("ux-review", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Orient" in out


def test_plan_step1_and_max_step(forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("plan", REPO_ROOT)
    assert manifest.max_step == 7

    code = _run("plan", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Frame" in out


def test_implement_step1_and_max_step(forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("implement", REPO_ROOT)
    assert manifest.max_step == 8

    code = _run("implement", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Plan Detection" in out


def test_code_review_step1_and_max_step(forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("code-review", REPO_ROOT)
    assert manifest.max_step == 6

    code = _run("code-review", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Target Detection" in out


def test_implement_docs_gate_escape_invoked(
    forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys
):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("implement", REPO_ROOT)
    docs_gates = [g for g in manifest.gates if g.id == "docs_gate"]
    assert docs_gates, "implement manifest must declare docs_gate"
    gate_step = docs_gates[0].steps[0]

    called: list[dict] = []

    def fake_gate(*, state, step, state_path, gate):
        called.append(
            {"step": step, "state_path": state_path, "gate_id": gate.id}
        )

    monkeypatch.setattr(
        "scripts.implement.docs_gate_escape.exit_if_documentation_gate_fails",
        fake_gate,
    )

    code1 = _run("implement", ["--step", "1"], monkeypatch=monkeypatch)
    assert code1 == 0
    err = capsys.readouterr().err
    m = re.search(r"STATE FILE:\s*(.+)", err)
    assert m, err
    state_path = m.group(1).strip()

    import json

    data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    custom = data.setdefault("custom", {})
    custom.setdefault("current_wave", 1)
    custom.setdefault("total_waves", 1)
    custom.setdefault("waves_completed", 1)
    custom.setdefault("plan_path", str(REPO_ROOT / "README.md"))
    custom.setdefault("feature_branch", "feat/test")
    Path(state_path).write_text(json.dumps(data), encoding="utf-8")

    code = _run(
        "implement",
        ["--step", str(gate_step), "--state", state_path],
        monkeypatch=monkeypatch,
    )
    assert code == 0
    assert called, "docs gate escape must be invoked at configured step"
    assert called[0]["step"] == gate_step
    assert called[0]["gate_id"] == "docs_gate"


def test_code_review_structural_probes_gate_escape_invoked(
    forge_runtime, monkeypatch: pytest.MonkeyPatch, capsys
):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("code-review", REPO_ROOT)
    probe_gates = [g for g in manifest.gates if g.id == "structural_probes_gate"]
    assert probe_gates, "code-review manifest must declare structural_probes_gate"
    gate = probe_gates[0]
    gate_step = min(gate.steps)

    called: list[dict] = []

    def fake_gate(*, state, step, state_path, gate):
        called.append({"step": step, "gate_id": gate.id})

    callable_spec = gate.callable or ""
    assert ":" in callable_spec
    mod_name, fn_name = callable_spec.split(":", 1)
    monkeypatch.setattr(f"{mod_name}.{fn_name}", fake_gate)

    code1 = _run("code-review", ["--step", "1"], monkeypatch=monkeypatch)
    assert code1 == 0
    err = capsys.readouterr().err
    m = re.search(r"STATE FILE:\s*(.+)", err)
    assert m, err
    state_path = m.group(1).strip()

    import json

    data = json.loads(Path(state_path).read_text(encoding="utf-8"))
    data.setdefault("custom", {})["structural_enabled"] = True
    data["custom"]["mode"] = "pr"
    data["custom"]["target"] = "HEAD"
    Path(state_path).write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(
        "scripts.shared.structural_probes.inject_structural_probes_section",
        lambda body, **_k: (body, None, {}),
    )
    code = _run(
        "code-review",
        ["--step", str(gate_step), "--state", state_path],
        monkeypatch=monkeypatch,
    )
    assert code == 0
    assert called, "structural probes gate escape must be invoked"
    assert called[0]["step"] == gate_step


def test_batch_phase_keys_removed_from_skill_phases():
    from scripts.shared import skill_phases as sp

    for skill in ("ship", "ux-review", "plan", "implement", "code-review"):
        assert skill not in sp._SKILL_PHASE_NAMES, (
            f"{skill} must be removed from _SKILL_PHASE_NAMES after migration"
        )


def test_batch_vars_do_not_import_skill_runner():
    import scripts.ship.ship_effects as ship_effects
    import scripts.ship.ship_vars as ship_vars
    import scripts.ux_review.ux_review_vars as ux_vars
    import scripts.plan.plan_vars as plan_vars
    import scripts.implement.implement_vars as impl_vars
    import scripts.code_review.code_review_vars as cr_vars

    import_re = re.compile(
        r"^\s*(?:from\s+scripts\.shared\.skill_runner\s+import|"
        r"import\s+scripts\.shared\.skill_runner)\b",
        re.M,
    )
    for mod in (ship_effects, ship_vars, ux_vars, plan_vars, impl_vars, cr_vars):
        assert "scripts.shared.skill_runner" not in getattr(mod, "__dict__", {})
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert not import_re.search(src), f"{mod.__file__} imports skill_runner"
