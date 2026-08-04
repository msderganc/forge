"""Wave 4 gate-heavy migrations: takeover, design, evaluate, test."""

from __future__ import annotations

import json
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


def test_takeover_step1_phase_and_max_step(forge_runtime, monkeypatch, capsys):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("takeover", REPO_ROOT)
    assert manifest.max_step == 6
    assert manifest.steps[0].phase == "Initialize + route"
    gate_ids = [g.id for g in manifest.gates]
    assert "takeover_gate_waits" in gate_ids
    assert any(
        g.callable and "takeover_gates" in g.callable for g in manifest.gates
    )

    code = _run("takeover", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Initialize + route" in out


def test_design_step1_gates_and_cli_flags(forge_runtime, monkeypatch, capsys):
    from scripts.shared.skill_manifest import load_manifest

    manifest = load_manifest("design", REPO_ROOT)
    assert manifest.max_step == 8
    flag_names = {f.name for f in manifest.cli_flags}
    assert "--allow-spec-incomplete" in flag_names
    assert "--allow-issues-incomplete" in flag_names
    assert "--spec-override-reason" in flag_names
    assert "--issues-override-follow-up" in flag_names

    by_id = {g.id: g for g in manifest.gates}
    assert by_id["design_spec_shape"].kind == "schema"
    assert by_id["design_spec_gate"].kind == "python"
    assert by_id["design_spec_gate"].callable == (
        "scripts.design.spec_gate:validate_spec_gate"
    )
    assert by_id["design_spec_issues_shape"].kind == "schema"
    assert by_id["design_spec_issues_gate"].callable == (
        "scripts.design.spec_issues:validate_spec_issues_gate"
    )
    assert set(by_id["design_spec_gate"].steps) == {6, 7, 8}

    code = _run("design", ["--step", "1"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Startup" in out


def test_evaluate_pre_and_post_variants(forge_runtime, monkeypatch, capsys):
    from scripts.shared.skill_manifest import ManifestVariant, load_manifest

    manifest = load_manifest("evaluate", REPO_ROOT)
    assert manifest.variants is not None
    assert set(manifest.variants) >= {"pre", "post", "review"}
    assert all(isinstance(v, ManifestVariant) for v in manifest.variants.values())
    assert manifest.variants["pre"].max_step == 7
    assert manifest.variants["post"].max_step == 8

    # Plan must live inside the repo (validate_state_path enforces this).
    plan_dir = REPO_ROOT / ".forge" / "memory" / "_gate_heavy_eval"
    plan_dir.mkdir(parents=True, exist_ok=True)
    plan = plan_dir / "plan.md"
    plan.write_text("# Eval Plan\n\n## Architecture Overview\nStub.\n", encoding="utf-8")
    state_sidecar = plan_dir / ".evaluate-state.json"
    if state_sidecar.exists():
        state_sidecar.unlink()

    try:
        code = _run(
            "evaluate",
            ["--step", "1", "--mode", "pre", "--plan", str(plan)],
            monkeypatch=monkeypatch,
        )
        assert code == 0
        out = capsys.readouterr().out
        assert "Plan Parsing" in out
    finally:
        state_sidecar.unlink(missing_ok=True)
        plan.unlink(missing_ok=True)

    from scripts.shared.skill_runner import _effective_view, _select_variant_name

    class NS:
        mode = "post"

    name = _select_variant_name(manifest, NS(), state=None)
    view = _effective_view(manifest, name)
    assert view.max_step == 8


def test_evaluate_findings_sidecar_ingest(forge_runtime, tmp_path, monkeypatch):
    from scripts.evaluate.evaluate_vars import ingest_findings_sidecars
    from scripts.shared.orchestrator import SkillState

    state = SkillState(skill_name="evaluate", max_step=7)
    state.custom["mode"] = "pre"
    sidecar = tmp_path / ".evaluate-findings-step2.json"
    sidecar.write_text(
        json.dumps(
            [
                {
                    "phase": "feasibility",
                    "severity": "critical",
                    "title": "Test F1",
                    "detail": "stub",
                }
            ]
        ),
        encoding="utf-8",
    )
    # malformed sidecar — warn-and-skip
    bad = tmp_path / ".evaluate-findings-step1.json"
    bad.write_text("{not-json", encoding="utf-8")

    ingested = ingest_findings_sidecars(state, tmp_path, current_step=3)
    assert ingested == 1
    assert not sidecar.exists()
    assert bad.exists()  # malformed left in place (skipped)
    assert state.findings[0]["title"] == "Test F1"


def test_test_run_and_flows_variants(forge_runtime, monkeypatch, capsys):
    from scripts.shared.skill_manifest import ManifestVariant, load_manifest

    manifest = load_manifest("test", REPO_ROOT)
    assert manifest.variants is not None
    assert set(manifest.variants) >= {"run", "flows"}
    assert all(isinstance(v, ManifestVariant) for v in manifest.variants.values())
    assert manifest.variants["run"].max_step == 6
    assert manifest.variants["flows"].max_step == 7
    assert manifest.pre_run == "scripts.test.test_cli:reject_ux_mode" or (
        manifest.pre_run and "test_cli" in manifest.pre_run
    )
    flag_names = {f.name for f in manifest.cli_flags}
    for required in (
        "--target",
        "--mode",
        "--flow-type",
        "--re-record",
        "--framework",
        "--entry-point",
        "--no-db",
        "--roles",
    ):
        assert required in flag_names

    code = _run("test", ["--step", "1", "--mode", "run"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Context Detection" in out

    code = _run("test", ["--step", "1", "--mode", "flows"], monkeypatch=monkeypatch)
    assert code == 0
    out = capsys.readouterr().out
    assert "Flow Context Detection" in out


def test_test_ux_mode_rejected_via_test_cli(forge_runtime, monkeypatch, capsys):
    with pytest.raises(SystemExit) as ei:
        _run("test", ["--step", "1", "--mode", "ux"], monkeypatch=monkeypatch)
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "ux-review" in err

    from scripts.test import test_cli

    assert callable(test_cli.reject_ux_mode)


def test_phase_keys_removed_from_skill_phases():
    from scripts.shared import skill_phases as sp

    for key in ("takeover", "design", "evaluate", "test"):
        assert key not in sp._SKILL_PHASE_NAMES
    # Still resolvable via manifest
    assert sp.phase_names_for("takeover")[1] == "Initialize + route"
    assert sp.phase_names_for("design")[1] == "Startup"
    assert sp.phase_names_for("evaluate", "pre")[2] == "Feasibility"
    assert sp.phase_names_for("test", "flows")[1] == "Flow Context Detection"
