"""Tests for scripts.shared.structural_probes."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts.shared import structural_probes as sp


def _setup_inject_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("FORGE_SKIP_STRUCTURAL_EIGHT_AGENTS", raising=False)
    return state_dir


def test_should_run_probes_matrix() -> None:
    assert sp.should_run_probes("code-review", 3)
    assert not sp.should_run_probes("code-review", 2)
    assert sp.should_run_probes("evaluate", 4, mode="post")
    assert sp.should_run_probes("evaluate", 1, mode="review")
    assert not sp.should_run_probes("evaluate", 4, mode="pre")
    assert sp.should_run_probes("implement", 4)
    assert not sp.should_run_probes("implement", 3)
    assert sp.should_run_probes("plan", 2)
    assert not sp.should_run_probes("plan", 3)


def test_should_auto_run_structural_probes_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_AUTO", raising=False)
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_MANUAL", raising=False)
    monkeypatch.delenv("FORGE_SKIP_STRUCTURAL_TOOLS", raising=False)
    assert sp.should_auto_run_structural_probes("code-review", 3)
    assert sp.should_auto_run_structural_probes("implement", 4)
    assert sp.should_auto_run_structural_probes("plan", 2)
    assert not sp.should_auto_run_structural_probes("implement", 3)
    assert not sp.should_auto_run_structural_probes("evaluate", 4, mode="post")


def test_detect_stack_python_only(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    stack = sp.detect_stack(tmp_path)
    assert stack["python"] is True
    assert stack["node"] is False


def test_detect_stack_ts_primary_with_few_python_scripts(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"app"}', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='tooling'\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    for i in range(8):
        (src / f"mod{i}.ts").write_text("export {}\n", encoding="utf-8")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "gen.py").write_text("print('x')\n", encoding="utf-8")

    stack = sp.detect_stack(tmp_path)
    assert stack["node"] is True
    assert stack["python"] is False


def _make_pruned_noise_tree(
    tmp_path: Path,
    *,
    keep_name: str = "module.py",
    noise_dir: Path | None = None,
    noise_count: int = 100,
) -> Path:
    """Keep one top-level .py and fill an ignored subtree with noise files."""
    (tmp_path / keep_name).write_text("x = 1\n", encoding="utf-8")
    target = noise_dir or (tmp_path / ".venv" / "lib" / "python3.12" / "site-packages")
    target.mkdir(parents=True, exist_ok=True)
    for i in range(noise_count):
        (target / f"noise{i}.py").write_text("pass\n", encoding="utf-8")
    return target


def test_source_counts_skip_venv_without_descending(tmp_path: Path) -> None:
    """Regression: rglob walked .venv and timed out; pruned os.walk must not."""
    _make_pruned_noise_tree(tmp_path, keep_name="module.py", noise_count=500)

    assert sp._count_source_files(tmp_path, ".py") == 1
    inv = sp.build_stack_inventory(tmp_path)
    assert inv["counts"]["py"] == 1


def test_probe_ignore_skips_vendored_forge_next_snapshots(tmp_path: Path) -> None:
    live = tmp_path / "forge_next" / "pkg.py"
    live.parent.mkdir(parents=True)
    live.write_text("x = 1\n", encoding="utf-8")
    snap = tmp_path / "forge_next-0.14.9" / "duplicate.py"
    snap.parent.mkdir(parents=True)
    snap.write_text("y = 2\n", encoding="utf-8")

    assert sp._should_prune_walk_path(snap, tmp_path) is True
    assert sp._should_prune_walk_path(live, tmp_path) is False


def test_detect_stack_finds_package_json_under_client(tmp_path: Path) -> None:
    client = tmp_path / "client"
    client.mkdir()
    (client / "package.json").write_text('{"name":"ui"}', encoding="utf-8")
    (client / "src").mkdir()
    (client / "src" / "App.tsx").write_text("export default function App() {}\n", encoding="utf-8")

    stack = sp.detect_stack(tmp_path)
    assert stack["node"] is True
    assert sp.node_probe_root(tmp_path) == client.resolve()


def test_code_review_step3_uses_detected_repo_root_for_probes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = tmp_path / "consumer-app"
    app.mkdir()
    (app / "package.json").write_text('{"name":"consumer"}', encoding="utf-8")
    (app / "src").mkdir()
    (app / "src" / "index.ts").write_text("export const x = 1;\n", encoding="utf-8")

    captured: list[Path] = []

    def fake_inject(_body, *, repo_root, **kwargs):
        captured.append(Path(repo_root).resolve())
        return _body, None, {"stack": {"python": False, "node": True}, "probes": []}

    monkeypatch.chdir(app)
    monkeypatch.setattr(sp, "inject_structural_probes_section", fake_inject)

    import scripts.code_review.code_review as cr
    from scripts.shared.orchestrator import SkillState, save_state

    state_path = app / ".forge" / "state" / "code-review-probe-root.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    st = SkillState(skill_name="code-review", max_step=6, current_step=2)
    st.custom = {
        "mode": "pr",
        "target": ".",
        "target_tokens": ["."],
        "structural_enabled": True,
    }
    save_state(st, state_path)

    monkeypatch.setattr(cr, "load_template", lambda _name: "{{body}}")
    monkeypatch.setattr(cr, "render_template", lambda template, _vars: template)
    monkeypatch.setattr(cr, "format_step_output", lambda *a, **k: "ok")

    cr.handle_step_n(3, state_file=str(state_path))

    assert captured
    assert captured[0] == app.resolve()


def test_run_probes_skip_without_node(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "mod.py").write_text("def f():\n    pass\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_pyscn_command",
        lambda: None,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_knip_command",
        lambda: None,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_madge_command",
        lambda: None,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_jscn_command",
        lambda: None,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_skylos_command",
        lambda: None,
    )
    payload = sp.run_probes(tmp_path, state_dir=state_dir)
    knip = next(p for p in payload["probes"] if p["tool"] == "knip")
    assert knip["status"] == "skip"
    assert "not selected" in knip["summary"]
    sidecar = state_dir / sp.SIDECAR_NAME
    assert sidecar.is_file()
    loaded = json.loads(sidecar.read_text(encoding="utf-8"))
    assert loaded["stack"]["node"] is False


def test_inject_post_evaluate_step4_omits_eight_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = _setup_inject_tmp(tmp_path, monkeypatch)

    body, _, _ = sp.inject_structural_probes_section(
        "body",
        skill_name="evaluate",
        step=4,
        repo_root=tmp_path,
        state_dir=state_dir,
        mode="post",
    )
    assert "agent selects tools" in body
    assert "STRUCTURAL QUALITY — eight parallel subagents" not in body


def test_inject_code_review_step3_includes_eight_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = _setup_inject_tmp(tmp_path, monkeypatch)

    body, _, _ = sp.inject_structural_probes_section(
        "body",
        skill_name="code-review",
        step=3,
        repo_root=tmp_path,
        state_dir=state_dir,
    )
    assert "STRUCTURAL QUALITY — eight parallel subagents" in body
    assert "S3, S4, S8" in body


def test_inject_planning_banner_writes_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_AUTO", raising=False)
    monkeypatch.setenv("FORGE_STRUCTURAL_PROBES_MANUAL", "1")

    body, sidecar, payload = sp.inject_structural_probes_section(
        "body",
        skill_name="code-review",
        step=3,
        repo_root=tmp_path,
        state_dir=state_dir,
    )
    assert "agent selects tools" in body
    assert sidecar is None
    assert payload is None
    assert (state_dir / sp.PLAN_NAME).is_file()
    assert (state_dir / sp.INVENTORY_NAME).is_file()


def test_code_review_step3_auto_runs_without_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Code-review step 3 runs probes by default (pyscn when Python present)."""
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_AUTO", raising=False)
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_MANUAL", raising=False)
    monkeypatch.setattr("forge_next.structural_tools.resolve_knip_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_madge_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_jscn_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_pyscn_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_skylos_command", lambda: None)

    body, sidecar, payload = sp.inject_structural_probes_section(
        "body",
        skill_name="code-review",
        step=3,
        repo_root=tmp_path,
        state_dir=state_dir,
    )
    assert "STRUCTURAL PROBES — results" in body
    assert sidecar is not None
    assert payload is not None
    selected = payload.get("selected_tools") or []
    assert "pyscn" in selected
    assert "skylos" in selected


def test_filter_applicable_probe_tools_python_only(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    inv = sp.build_stack_inventory(tmp_path)
    filtered = sp.filter_applicable_probe_tools(
        ["knip", "madge", "pyscn", "skylos"],
        inv,
    )
    assert filtered == ["pyscn", "skylos"]


def test_filter_applicable_probe_tools_node_only(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"name":"app"}', encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "index.ts").write_text("export {}\n", encoding="utf-8")
    inv = sp.build_stack_inventory(tmp_path)
    filtered = sp.filter_applicable_probe_tools(
        ["knip", "madge", "pyscn", "skylos"],
        inv,
    )
    assert filtered == ["knip", "madge"]


def test_parse_skylos_json_empty_definitions_no_false_findings() -> None:
    payload = {"definitions": {}, "unused_functions": []}
    findings = sp._parse_skylos_json_findings(json.dumps(payload))
    assert findings == []


def test_parse_skylos_json_findings_definitions_dead() -> None:
    payload = {
        "definitions": {
            "pkg.fn": {
                "name": "dead_fn",
                "file": "pkg/mod.py",
                "line": 12,
                "dead": True,
                "dead_code_classification": "likely_dead",
            }
        }
    }
    findings = sp._parse_skylos_json_findings(json.dumps(payload))
    assert len(findings) == 1
    assert findings[0]["path"] == "pkg/mod.py:12"


def test_parse_skylos_json_findings_unused() -> None:
    payload = {
        "unused_functions": [
            {
                "name": "dead_fn",
                "file": "pkg/mod.py",
                "line": 10,
                "confidence": 90,
                "message": "unused function",
            }
        ],
        "analysis_summary": {"dead_code_evidence": {"classifications": {"likely_dead": 1}}},
    }
    findings = sp._parse_skylos_json_findings(json.dumps(payload))
    assert len(findings) == 1
    assert findings[0]["id"] == "Y1"
    assert findings[0]["path"] == "pkg/mod.py:10"
    assert "dead_fn" in findings[0]["detail"]


def test_extract_stdout_json_skips_uv_prefix() -> None:
    raw = "Installed 72 packages in 849ms\n" + json.dumps({"unused_files": []})
    data = sp._extract_stdout_json(raw)
    assert data is not None
    assert "unused_files" in data


def test_extract_stdout_json_tolerates_uv_suffix() -> None:
    raw = json.dumps({"unused_functions": []}) + "\nInstalled 72 packages in 849ms\n"
    data = sp._extract_stdout_json(raw)
    assert data is not None
    assert "unused_functions" in data


def test_skylos_scan_command_code_review_quick() -> None:
    cmd = sp._skylos_scan_command(
        ["uvx", "skylos@latest"],
        ["scripts/shared"],
        quick_scan=True,
    )
    assert "--json" in cmd
    assert "-a" not in cmd


def test_skylos_scan_command_adds_excludes_for_repo_root() -> None:
    cmd = sp._skylos_scan_command(
        ["skylos"],
        ["."],
        quick_scan=True,
    )
    assert "--exclude-folder" in cmd
    assert ".venv" in cmd
    assert "graphify-out" in cmd
    assert ".pyscn" in cmd


def test_pyscn_analyze_command_targets_files() -> None:
    cmd = sp._pyscn_analyze_command(
        ["pyscn"],
        targets=[
            "benchmark/dashboard/operator_editing_endpoints.py",
            "project_context/storage.py",
        ],
    )
    assert cmd[:4] == ["pyscn", "analyze", "--json", "--min-complexity=15"]
    assert "benchmark/dashboard/operator_editing_endpoints.py" in cmd
    assert "project_context/storage.py" in cmd
    assert "check" not in cmd


def test_repo_has_large_ignored_dirs(tmp_path: Path) -> None:
    assert sp.repo_has_large_ignored_dirs(tmp_path) is False
    (tmp_path / ".venv").mkdir()
    assert sp.repo_has_large_ignored_dirs(tmp_path) is True


def test_is_broad_probe_scope() -> None:
    assert sp.is_broad_probe_scope(None) is True
    assert sp.is_broad_probe_scope([]) is True
    assert sp.is_broad_probe_scope(["."]) is True
    assert sp.is_broad_probe_scope(["src/mod.py"]) is False


def test_resolve_effective_scope_paths_prefers_explicit_files(tmp_path: Path) -> None:
    target = tmp_path / "pkg" / "mod.py"
    target.parent.mkdir(parents=True)
    target.write_text("x = 1\n", encoding="utf-8")
    scope, note = sp.resolve_effective_scope_paths(
        tmp_path,
        ["pkg/mod.py"],
        skill_name="code-review",
        step=3,
        mode="pr",
    )
    assert scope == ["pkg/mod.py"]
    assert note == ""


def test_resolve_effective_scope_paths_blocks_root_with_venv(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    scope, note = sp.resolve_effective_scope_paths(
        tmp_path,
        ["."],
        skill_name="code-review",
        step=3,
        mode="pr",
    )
    assert scope == []
    assert "large ignored dirs" in note


def test_filter_python_scope_paths_skips_gitignored(
    tmp_path: Path,
) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "probe@test.local"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "probe"],
        cwd=tmp_path,
        capture_output=True,
    )
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    ignored = tmp_path / "ignored" / "secret.py"
    ignored.parent.mkdir(parents=True)
    ignored.write_text("x = 1\n", encoding="utf-8")
    ok = tmp_path / "ok.py"
    ok.write_text("x = 1\n", encoding="utf-8")

    scope = sp.filter_python_scope_paths(
        tmp_path,
        ["ignored/secret.py", "ok.py"],
    )
    assert scope == ["ok.py"]


def test_git_changed_paths_includes_untracked(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.email", "probe@test.local"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "probe"],
        cwd=tmp_path,
        capture_output=True,
    )
    (tmp_path / "tracked.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=tmp_path,
        capture_output=True,
        check=True,
    )
    (tmp_path / "new_module.py").write_text("y = 2\n", encoding="utf-8")

    paths = sp._git_changed_paths_for_review(tmp_path, [], mode="pr")
    assert "new_module.py" in paths


def test_run_pyscn_probe_runs_per_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "a.py").write_text("def a():\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("def b():\n    pass\n", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, *, cwd, timeout):
        calls.append(cmd)
        return 0, "{}"

    monkeypatch.setattr(
        "scripts.shared.structural_probe_runners._run_cmd",
        fake_run,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_pyscn_command",
        lambda: ["pyscn"],
    )
    from scripts.shared.structural_probe_runners import run_pyscn_probe

    result = run_pyscn_probe(
        repo_root=tmp_path,
        python_root=tmp_path,
        effective_scope=["a.py", "b.py"],
        timeout=300,
    )
    assert result["status"] == "pass"
    assert len(calls) == 1
    assert "check" in calls[0]
    assert "a.py" in calls[0]
    assert "b.py" in calls[0]


def test_filter_python_scope_paths_skips_graphifyignored(
    tmp_path: Path,
) -> None:
    (tmp_path / ".graphifyignore").write_text("vendor/\n", encoding="utf-8")
    vendor = tmp_path / "vendor" / "lib.py"
    vendor.parent.mkdir(parents=True)
    vendor.write_text("x = 1\n", encoding="utf-8")
    ok = tmp_path / "ok.py"
    ok.write_text("x = 1\n", encoding="utf-8")

    scope = sp.filter_python_scope_paths(tmp_path, ["vendor/lib.py", "ok.py"])
    assert scope == ["ok.py"]


def test_ensure_primary_probe_plan_keeps_python_with_scoped_root(
    tmp_path: Path,
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    inv = sp.build_stack_inventory(tmp_path)
    plan = sp.ensure_primary_probe_plan(
        {"tools": ["pyscn", "skylos"], "reasoning": "test"},
        inv,
        skill_name="code-review",
        step=3,
        scope_paths=["."],
        mode="pr",
    )
    assert "pyscn" in plan["tools"]
    assert "skylos" in plan["tools"]
    assert plan.get("python_root")
    assert plan.get("exclude_paths")


def test_ensure_primary_probe_plan_replaces_reasoning(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    inv = sp.build_stack_inventory(tmp_path)
    plan = sp.ensure_primary_probe_plan(
        {
            "tools": ["knip"],
            "reasoning": "Old heuristic. pyscn is required when Python is present.",
        },
        inv,
        skill_name="code-review",
        step=3,
    )
    assert "Old heuristic" not in plan["reasoning"]
    assert "stack-applicable" in plan["reasoning"]


def test_ensure_primary_probe_plan_python_only(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    probe = tmp_path / "scripts" / "shared" / "structural_probes.py"
    probe.parent.mkdir(parents=True)
    probe.write_text("x = 1\n", encoding="utf-8")
    scope = "scripts/shared/structural_probes.py"
    inv = sp.build_stack_inventory(tmp_path)
    plan = sp.ensure_primary_probe_plan(
        {"tools": ["knip"], "reasoning": "test"},
        inv,
        skill_name="code-review",
        step=3,
        scope_paths=[scope],
    )
    assert plan["tools"] == ["pyscn", "skylos"]
    assert "knip" not in plan["tools"]
    assert plan["scope_paths"] == [scope]


def test_ensure_primary_probe_plan_plan_step2_jscn_pyscn_only(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.ts").write_text("export const x = 1\n", encoding="utf-8")
    inv = sp.build_stack_inventory(tmp_path)
    plan = sp.ensure_primary_probe_plan(
        {"tools": ["knip", "madge", "skylos"], "reasoning": "heuristic"},
        inv,
        skill_name="plan",
        step=2,
    )
    assert set(plan["tools"]) <= {"jscn", "pyscn"}
    assert "knip" not in plan["tools"]
    assert "madge" not in plan["tools"]
    assert "skylos" not in plan["tools"]
    assert "baseline" in plan["reasoning"].lower() or "Plan step 2" in plan["reasoning"]


def test_finalize_probe_outcome_advisory_skips_gate(
    tmp_path: Path,
) -> None:
    from scripts.shared.structural_probes_gate import (
        STATUS_FAILED,
        finalize_probe_outcome,
        probe_gate_is_pending,
    )

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    extra, confirm = finalize_probe_outcome(
        state_dir,
        status=STATUS_FAILED,
        reason="tools missing",
        advisory=True,
    )
    assert confirm is False
    assert "Advisory" in extra
    assert not probe_gate_is_pending(state_dir)


def test_inject_auto_mode_runs_probes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    monkeypatch.setenv("FORGE_STRUCTURAL_PROBES_AUTO", "1")
    monkeypatch.delenv("FORGE_STRUCTURAL_PROBES_MANUAL", raising=False)
    monkeypatch.setattr("forge_next.structural_tools.resolve_knip_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_madge_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_jscn_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_pyscn_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_skylos_command", lambda: None)

    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    body, sidecar, payload = sp.inject_structural_probes_section(
        "body",
        skill_name="code-review",
        step=3,
        repo_root=tmp_path,
        state_dir=state_dir,
    )
    assert "results" in body.lower()
    assert sidecar is not None
    assert payload is not None


def test_run_pyscn_probe_uses_check_for_scoped_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = tmp_path / "pkg" / "mod.py"
    mod.parent.mkdir(parents=True)
    mod.write_text("def f():\n    pass\n", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(cmd, *, cwd, timeout):
        captured.append(cmd)
        return 0, "{}"

    monkeypatch.setattr(
        "scripts.shared.structural_probe_runners._run_cmd",
        fake_run,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_pyscn_command",
        lambda: ["pyscn"],
    )
    from scripts.shared.structural_probe_runners import run_pyscn_probe

    run_pyscn_probe(
        repo_root=tmp_path,
        python_root=tmp_path,
        effective_scope=["pkg/mod.py"],
        timeout=30,
    )
    assert captured
    cmd = captured[0]
    assert "check" in cmd
    assert "pkg/mod.py" in cmd
    assert "analyze" not in cmd

def test_run_jscn_probe_uses_analyze_for_scoped_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = tmp_path / "src" / "app.ts"
    mod.parent.mkdir(parents=True)
    mod.write_text("export const x = 1;\n", encoding="utf-8")
    captured: list[list[str]] = []

    def fake_run(cmd, *, cwd, timeout):
        captured.append(cmd)
        return 0, json.dumps({"issues": [], "summary": {"qualityIssueCount": 0}})

    monkeypatch.setattr(
        "scripts.shared.structural_probe_runners._run_cmd",
        fake_run,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_jscn_command",
        lambda: ["jscn"],
    )
    from scripts.shared.structural_probe_runners import run_jscn_probe

    result = run_jscn_probe(
        repo_root=tmp_path,
        node_root=tmp_path,
        effective_scope=["src/app.ts"],
        timeout=30,
    )
    assert captured
    cmd = captured[0]
    assert "analyze" in cmd
    assert "--json" in cmd
    assert "src/app.ts" in cmd
    assert result["tool"] == "jscn"
    assert result["status"] == "pass"


def test_run_skylos_probe_adds_excludes_on_root_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[list[str]] = []

    def fake_run(cmd, *, cwd, timeout):
        captured.append(cmd)
        return 0, json.dumps({"unused_functions": []})

    monkeypatch.setattr(
        "scripts.shared.structural_probe_runners._run_cmd",
        fake_run,
    )
    monkeypatch.setattr(
        "forge_next.structural_tools.resolve_skylos_command",
        lambda: ["skylos"],
    )
    from scripts.shared.structural_probe_runners import run_skylos_probe

    run_skylos_probe(
        repo_root=tmp_path,
        python_root=tmp_path,
        effective_scope=None,
        timeout=30,
        quick_mode=True,
        skill_name="code-review",
        step=3,
    )
    assert captured
    cmd = captured[0]
    assert "--exclude-folder" in cmd
    assert ".venv" in cmd


def test_run_probes_respects_plan_tools(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    sp.write_probe_plan(
        state_dir,
        {
            "tools": ["knip"],
            "node_root": ".",
            "reasoning": "Only knip for this test",
        },
    )
    monkeypatch.setattr("forge_next.structural_tools.resolve_knip_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_madge_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_jscn_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_pyscn_command", lambda: None)
    monkeypatch.setattr("forge_next.structural_tools.resolve_skylos_command", lambda: None)

    payload = sp.run_probes(tmp_path, state_dir=state_dir, plan=sp.load_probe_plan(state_dir))
    by_tool = {p["tool"]: p for p in payload["probes"]}
    assert by_tool["knip"]["status"] == "skip"
    assert "not selected" in by_tool["madge"]["summary"]
    assert "not selected" in by_tool["pyscn"]["summary"]
    assert "not selected" in by_tool["skylos"]["summary"]


def test_code_review_step3_mentions_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Smoke: step 3 output includes structural-probes when injection runs."""
    import io
    import sys

    import scripts.code_review.code_review as cr
    from scripts.shared.orchestrator import SkillState, save_state

    monkeypatch.chdir(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    state = tmp_path / ".forge" / "state" / "code-review-structural-smoke.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    st = SkillState(skill_name="code-review", max_step=6, current_step=2)
    st.custom = {
        "mode": "pr",
        "target": ".",
        "target_tokens": ["."],
        "structural_enabled": True,
    }
    save_state(st, state)

    fake_payload = {
        "generated_at": "2026-01-01T00:00:00+00:00",
        "stack": {"python": True, "node": False},
        "probes": [],
    }
    sidecar = state.parent / ".structural-probes.json"

    from scripts.shared.structural_eight_agents import format_eight_agents_dispatch_banner

    def fake_inject(body, **kwargs):
        banner = sp.format_probe_results_banner(fake_payload, sidecar)
        eight = format_eight_agents_dispatch_banner(quick_mode=True)
        return body + "\n\n" + banner + "\n\n" + eight, sidecar, fake_payload

    monkeypatch.setattr(sp, "inject_structural_probes_section", fake_inject)
    monkeypatch.setattr(cr, "load_template", lambda _name: "{{body}}")
    monkeypatch.setattr(cr, "render_template", lambda template, _vars: template)

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    try:
        cr.handle_step_n(3, state_file=str(state))
        out = buf.getvalue()
    finally:
        state.unlink(missing_ok=True)
        sidecar.unlink(missing_ok=True)

    assert "structural-probes" in out.lower() or "STRUCTURAL PROBES" in out
    assert "eight parallel subagents" in out.lower()
    assert "8 subagents" in out


def test_probe_ignore_filter_paths_batches_check_ignore(tmp_path: Path) -> None:
    """Large path lists must not spawn one git check-ignore per file."""
    import subprocess

    from scripts.shared.probe_ignore import ProbeIgnorePolicy

    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True, check=True)
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    (ignored / "a.py").write_text("x=1\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("x=1\n", encoding="utf-8")

    policy = ProbeIgnorePolicy(tmp_path, hard_skip_parts=frozenset())
    calls: list[list[str]] = []
    real_run = subprocess.run

    def tracking_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args")
        if isinstance(cmd, list) and "check-ignore" in cmd:
            calls.append(list(cmd))
        return real_run(*args, **kwargs)

    import scripts.shared.probe_ignore as pi

    monkey_attr = subprocess.run
    try:
        subprocess.run = tracking_run  # type: ignore[assignment]
        pi.subprocess.run = tracking_run  # type: ignore[attr-defined]
        paths = [f"ignored/f{i}.py" for i in range(50)] + ["ok.py"]
        # Create ignored files so check-ignore has something to match
        for i in range(50):
            (ignored / f"f{i}.py").write_text("x=1\n", encoding="utf-8")
        out = policy.filter_paths(paths, for_scope=True)
    finally:
        subprocess.run = monkey_attr  # type: ignore[assignment]
        pi.subprocess.run = monkey_attr  # type: ignore[attr-defined]

    assert out == ["ok.py"]
    assert calls, "expected at least one check-ignore invocation"
    assert all("check-ignore" in c for c in calls)
    # One batch for 51 paths (chunk size 80) — not one subprocess per path.
    assert len(calls) == 1
    assert calls[0].count("check-ignore") == 1
    assert "ok.py" in calls[0] or any("ok.py" in a for a in calls[0])
    assert len([a for a in calls[0] if a.endswith(".py")]) >= 50


def test_walk_repo_files_respects_max_and_prunes_codex(tmp_path: Path) -> None:
    noise = _make_pruned_noise_tree(
        tmp_path,
        keep_name="keep.py",
        noise_dir=tmp_path / ".codex" / "forge" / "sessions" / "abc",
        noise_count=100,
    )

    assert sp._should_prune_walk_path(tmp_path / ".codex", tmp_path) is True
    walked = list(sp._walk_repo_files(tmp_path, suffix=".py", max_files=10))
    assert len(walked) == 1
    assert walked[0].name == "keep.py"
    assert noise.is_dir()


def test_pyscn_probe_targets_caps_large_scope(tmp_path: Path) -> None:
    files = []
    for i in range(sp.PROBE_PYSCN_MAX_FILES + 15):
        p = tmp_path / f"m{i}.py"
        p.write_text("x=1\n", encoding="utf-8")
        files.append(p.name)
    targets = sp._pyscn_probe_targets(
        tmp_path,
        python_root=tmp_path,
        effective_scope=files,
    )
    assert len(targets) == sp.PROBE_PYSCN_MAX_FILES


def test_ensure_primary_probe_plan_reuses_scope_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    inv = {
        "repo_root": str(tmp_path),
        "stack_hints": {"python": True, "node": False},
        "markers": {"pyproject": True},
        "counts": {"py": 1},
        "suggested_probe_roots": {"python": ".", "node": "."},
    }
    calls: list[int] = []

    def boom(*_a, **_k):
        calls.append(1)
        raise AssertionError("resolve_effective_scope_paths should not re-run")

    monkeypatch.setattr(sp, "resolve_effective_scope_paths", boom)
    plan = sp.ensure_primary_probe_plan(
        {"tools": ["pyscn"]},
        inv,
        skill_name="code-review",
        step=3,
        scope_paths=["a.py"],
        scope_note="Scoped Python probes to 1 changed .py file(s) from git diff.",
    )
    assert calls == []
    assert plan["scope_paths"] == ["a.py"]
    assert "Scoped Python probes" in plan["reasoning"]


GIT_RANGE_TOKEN = "c79194e5..9cf18e96"


def test_git_revision_range_is_not_a_filesystem_probe_target(tmp_path: Path) -> None:
    """code-review --target SHA..SHA must not be handed to jscn/madge/skylos as a path."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "index.js").write_text("export const x = 1;\n", encoding="utf-8")
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")

    jscn = sp._jscn_probe_targets(
        tmp_path, node_root=tmp_path, effective_scope=[GIT_RANGE_TOKEN]
    )
    madge = sp._madge_entry(tmp_path, [GIT_RANGE_TOKEN])
    skylos = sp._skylos_scan_targets(
        repo_root=tmp_path, python_root=tmp_path, scope_paths=[GIT_RANGE_TOKEN]
    )
    git_paths = sp._git_changed_paths_for_review(
        tmp_path, [GIT_RANGE_TOKEN], mode="pr"
    )
    leaked = {
        "jscn": jscn,
        "madge": madge,
        "skylos": skylos,
        "git_paths": git_paths,
    }
    assert GIT_RANGE_TOKEN not in jscn, leaked
    assert madge != GIT_RANGE_TOKEN, leaked
    assert GIT_RANGE_TOKEN not in skylos, leaked
    assert GIT_RANGE_TOKEN not in git_paths, leaked


def test_inject_does_not_reintroduce_unresolved_git_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty resolved scope must not fall back to the raw --target revision range."""
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    inv = {
        "repo_root": str(tmp_path),
        "stack_hints": {"python": True, "node": True},
        "markers": {"pyproject": True, "package_json_roots": ["."]},
        "counts": {"py": 1, "js": 1},
        "suggested_probe_roots": {"python": ".", "node": "."},
    }
    plan = sp.ensure_primary_probe_plan(
        {"tools": ["jscn", "madge", "knip", "skylos"]},
        inv,
        skill_name="code-review",
        step=3,
        scope_paths=[GIT_RANGE_TOKEN],
        mode="pr",
    )
    effective_scope, _note = sp.resolve_effective_scope_paths(
        tmp_path,
        [GIT_RANGE_TOKEN],
        skill_name="code-review",
        step=3,
        mode="pr",
    )
    # Mirrors inject_structural_probes_section → run_probes scope selection.
    run_scope = list(plan.get("scope_paths") or effective_scope)
    assert GIT_RANGE_TOKEN not in (plan.get("scope_paths") or [])
    assert GIT_RANGE_TOKEN not in (run_scope or [])


def test_pass_b_hints_ignore_failed_probes() -> None:
    lines = ["0", "1", "2", "3", "4", "5", "6"]
    payload = {
        "probes": [
            {"tool": "knip", "status": "fail", "findings": []},
            {"tool": "jscn", "status": "fail", "findings": []},
            {"tool": "pyscn", "status": "fail", "findings": []},
            {"tool": "skylos", "status": "fail", "findings": []},
        ]
    }
    sp._insert_primary_review_hints(lines, payload)
    joined = "\n".join(lines)
    assert "cite" not in joined
    assert "Pass B" not in joined
