from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


def _run(argv: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    # Ensure consistent encoding on Windows.
    env.setdefault("PYTHONUTF8", "1")
    return subprocess.run(
        argv,
        cwd=str(cwd),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_forge_launcher_can_run_against_foreign_repo(tmp_path: Path) -> None:
    """Smoke test: run `forge` launcher against a repo without vendored scripts."""
    foreign = tmp_path / "foreign-repo"
    foreign.mkdir(parents=True, exist_ok=True)

    # Minimal repo marker for repo-root detection.
    (foreign / "README.md").write_text("# Foreign Repo\n", encoding="utf-8")

    # Run `forge status` against it: should not crash and should print the repo path.
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-c",
        "import sys; sys.path.insert(0, r'"
        + str(repo_root)
        + "'); from forge_next.cli import main; main(['status','--repo',r'"
        + str(foreign)
        + "'])",
    ]
    res = _run(cmd, cwd=foreign)
    assert res.returncode == 0, res.stderr
    # Avoid Unicode punctuation in asserts; Windows console encodings vary.
    assert "forge" in res.stdout.lower()
    assert "status" in res.stdout.lower()


def test_launcher_parser_accepts_plan_ceremony_flags() -> None:
    from forge_next.cli import build_parser

    parser = build_parser()
    plan_args = parser.parse_args(
        ["plan", "--step", "1", "--ceremony", "medium", "--save-ceremony-preference"]
    )
    assert plan_args.ceremony == "medium"
    assert plan_args.save_ceremony_preference is True


def test_launcher_rejects_plan_mode_flag() -> None:
    from forge_next.cli import build_parser

    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["plan", "--step", "1", "--mode", "lite"])


def test_launcher_forwards_plan_ceremony_to_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    import forge_next.cli as cli
    import forge_next.cli_dispatch as dispatch

    captured: dict[str, object] = {}

    def fake_repo_root(_: str | None) -> Path:
        return Path.cwd()

    def fake_run_module(module_name: str, argv: list[str], repo_root: Path) -> int:
        captured["module_name"] = module_name
        captured["argv"] = argv
        return 0

    monkeypatch.setattr(dispatch, "repo_root_from_args", fake_repo_root)
    monkeypatch.setattr(dispatch, "run_module_main", fake_run_module)

    with pytest.raises(SystemExit) as exc:
        cli.main(
            ["plan", "--step", "1", "--ceremony", "light", "--save-ceremony-preference"]
        )

    assert exc.value.code == 0
    assert captured["module_name"] == "scripts.plan.plan"
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv == ["--step", "1", "--ceremony", "light", "--save-ceremony-preference"]


def test_launcher_parser_accepts_multi_token_targets() -> None:
    from forge_next.cli import build_parser

    parser = build_parser()
    code_review_args = parser.parse_args(
        ["code-review", "--step", "1", "--target", "scripts/a.py", "scripts/b.py"]
    )
    test_args = parser.parse_args(
        ["test", "--step", "1", "--target", "tests/a.py", "tests/b.py"]
    )

    assert code_review_args.target == ["scripts/a.py", "scripts/b.py"]
    assert test_args.target == ["tests/a.py", "tests/b.py"]


def test_launcher_forwards_target_once_for_multi_token_input(monkeypatch: pytest.MonkeyPatch) -> None:
    import forge_next.cli as cli
    import forge_next.cli_dispatch as dispatch

    captured: dict[str, object] = {}

    def fake_repo_root(_: str | None) -> Path:
        return Path.cwd()

    def fake_run_module(module_name: str, argv: list[str], repo_root: Path) -> int:
        captured["module_name"] = module_name
        captured["argv"] = argv
        captured["repo_root"] = repo_root
        return 0

    monkeypatch.setattr(dispatch, "repo_root_from_args", fake_repo_root)
    monkeypatch.setattr(dispatch, "run_module_main", fake_run_module)

    with pytest.raises(SystemExit) as exc:
        cli.main(["code-review", "--step", "1", "--target", "scripts/a.py", "scripts/b.py"])

    assert exc.value.code == 0
    argv = captured["argv"]
    assert isinstance(argv, list)
    assert argv.count("--target") == 1
    idx = argv.index("--target")
    assert argv[idx + 1: idx + 3] == ["scripts/a.py", "scripts/b.py"]


def test_code_review_script_accepts_multi_token_target(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    state_path = repo_root / ".codex" / "forge" / "state" / f"code-review-{tmp_path.name}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "code_review" / "code_review.py"),
        "--step",
        "1",
        "--state",
        str(state_path),
        "--target",
        "scripts/a.py",
        "scripts/b.py",
    ]
    try:
        res = _run(cmd, cwd=repo_root)
        assert res.returncode == 0, res.stderr
    finally:
        if state_path.exists():
            state_path.unlink()


def test_test_script_accepts_multi_token_target(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    state_path = repo_root / ".codex" / "forge" / "state" / f"test-{tmp_path.name}.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(repo_root / "scripts" / "test" / "test.py"),
        "--step",
        "1",
        "--state",
        str(state_path),
        "--target",
        "tests/a.py",
        "tests/b.py",
    ]
    try:
        res = _run(cmd, cwd=repo_root)
        assert res.returncode == 0, res.stderr
    finally:
        if state_path.exists():
            state_path.unlink()

