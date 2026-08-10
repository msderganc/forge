"""Tests for forge_next.structural_tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forge_next import structural_tools as st


def test_default_prefix_windows_uses_home_forge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st.sys, "platform", "win32")
    monkeypatch.setattr(st.Path, "home", lambda: tmp_path)
    assert st.default_prefix() == tmp_path / ".forge" / "structural-tools"


def test_default_prefix_windows_env_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st.sys, "platform", "win32")
    monkeypatch.setenv("FORGE_STRUCTURAL_TOOLS_PREFIX", str(tmp_path / "custom"))
    assert st.default_prefix() == tmp_path / "custom"


def test_load_manifest_falls_back_to_legacy_windows_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    legacy = tmp_path / "legacy" / "structural-tools.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text('{"version": 1, "knip": "/old/knip"}', encoding="utf-8")
    monkeypatch.setattr(st, "manifest_path", lambda: tmp_path / "missing.json")
    monkeypatch.setattr(st, "_legacy_manifest_paths", lambda: [legacy])
    loaded = st.load_manifest()
    assert loaded is not None
    assert loaded["knip"] == "/old/knip"


def test_skip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_SKIP_STRUCTURAL_TOOLS", "1")
    assert st.skip_structural_tools() is True
    result = st.install_structural_tools()
    assert any("skipped" in w.lower() for w in result.warnings)


def test_write_and_load_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "default_prefix", lambda: tmp_path / "npm")
    monkeypatch.setattr(st, "manifest_path", lambda: tmp_path / "structural-tools.json")
    result = st.StructuralToolsInstallResult(
        ok=True,
        prefix=str(tmp_path / "npm"),
        manifest_path="",
        knip=str(tmp_path / "npm" / "node_modules" / ".bin" / "knip"),
        madge=str(tmp_path / "npm" / "node_modules" / ".bin" / "madge"),
        pyscn="/usr/bin/pyscn",
        pyscn_via="pipx",
    )
    st.write_manifest(tmp_path / "npm", result)
    loaded = st.load_manifest()
    assert loaded is not None
    assert loaded["knip"] == result.knip
    assert loaded["pyscn_via"] == "pipx"


def test_resolve_knip_uses_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_KNIP_COMMAND", "/custom/knip --foo")
    assert st.resolve_knip_command() == ["/custom/knip", "--foo"]


def test_install_npm_skips_without_node(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(st, "_node_available", lambda: (False, "missing"))
    result = st.StructuralToolsInstallResult(ok=True, prefix=str(tmp_path), manifest_path="")
    st._install_npm_tools(tmp_path, result)
    assert any("Node" in w for w in result.warnings)


def test_install_structural_tools_mocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(st, "default_prefix", lambda: tmp_path / "npm")
    monkeypatch.setattr(st, "manifest_path", lambda: tmp_path / "manifest.json")

    def fake_npm(prefix: Path, result: st.StructuralToolsInstallResult) -> None:
        result.knip = str(prefix / "knip")
        result.madge = str(prefix / "madge")
        result.jscn = str(prefix / "jscn")
        result.steps.append("fake npm")

    def fake_pyscn(result: st.StructuralToolsInstallResult) -> None:
        result.pyscn = "/bin/pyscn"
        result.pyscn_via = "pipx"

    def fake_skylos(result: st.StructuralToolsInstallResult) -> None:
        result.skylos = "/bin/skylos"
        result.skylos_via = "pipx"

    monkeypatch.setattr(st, "_install_npm_tools", fake_npm)
    monkeypatch.setattr(st, "_install_pyscn", fake_pyscn)
    monkeypatch.setattr(st, "_install_skylos", fake_skylos)

    result = st.install_structural_tools()
    assert result.ok
    assert result.knip and result.madge and result.jscn and result.pyscn and result.skylos
    assert tmp_path.joinpath("manifest.json").is_file()
    data = json.loads(tmp_path.joinpath("manifest.json").read_text(encoding="utf-8"))
    assert data["knip"] == result.knip


def test_doctor_checks_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(st, "load_manifest", lambda: None)
    monkeypatch.setattr(st, "_npx_executable", lambda: None)
    monkeypatch.setattr(st.shutil, "which", lambda name: None)
    checks = st.doctor_checks()
    assert checks["knip"] is None
    warnings = st.structural_tools_warnings_for_doctor()
    assert len(warnings) == 5
    assert any("knip" in w for w in warnings)
    assert any("madge" in w for w in warnings)
    assert any("jscn" in w for w in warnings)
    assert any("pyscn" in w for w in warnings)
    assert any("skylos" in w for w in warnings)


def test_missing_warnings_empty_when_skip_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FORGE_SKIP_STRUCTURAL_TOOLS", "1")
    assert st.structural_tools_missing_warnings() == []


def test_install_notice_marks_present_and_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FORGE_SKIP_STRUCTURAL_TOOLS", raising=False)
    monkeypatch.setenv("FORGE_ASCII", "1")
    result = st.StructuralToolsInstallResult(
        ok=True,
        prefix="/prefix",
        manifest_path="/m.json",
        knip="/prefix/knip",
        madge=None,
        jscn="/prefix/jscn",
        pyscn=None,
        skylos="/bin/skylos",
        skylos_via="path",
    )
    text = "\n".join(st.structural_tools_install_notice_lines(result))
    assert "[OK] knip: /prefix/knip" in text
    assert "[X] madge: not found" in text
    assert "[OK] jscn: /prefix/jscn" in text
    assert "[X] pyscn: not found" in text
    assert "[OK] skylos: /bin/skylos (path)" in text
