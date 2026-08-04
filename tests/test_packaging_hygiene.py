"""Packaging / measurement hygiene: ignore build/ artifacts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_gitignore_includes_build() -> None:
    text = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    lines = {line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")}
    assert "build/" in lines or "build" in lines, ".gitignore must ignore build/"


def test_pytest_ini_norecursedirs_includes_build() -> None:
    text = (REPO_ROOT / "pytest.ini").read_text(encoding="utf-8")
    match = re.search(r"^norecursedirs\s*=\s*(.+)$", text, re.MULTILINE)
    assert match, "pytest.ini must define norecursedirs"
    dirs = match.group(1).split()
    assert "build" in dirs, "pytest.ini norecursedirs must list build"


def test_pytest_collect_only_excludes_build_lib() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    assert "build/lib" not in combined and "build\\lib" not in combined, (
        "pytest collect-only must not pick up build/lib:\n" + combined[:2000]
    )
