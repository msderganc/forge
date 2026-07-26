"""Install Codex skill pack and optional developer_instructions merge."""

from __future__ import annotations

import shutil
from pathlib import Path

from forge_next.cli_install_io import copytree_replace, default_codex_skills_dir
from forge_next.cli_install_templates import bundle_skill_templates


def install_codex_skills(
    repo_root: Path,
    *,
    codex_dir: str | None,
) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    src = repo_root / "integrations" / "codex" / "skills"
    if not src.is_dir():
        warnings.append("Codex skills folder not found in downloaded repo.")
        return None, warnings
    base = (
        Path(codex_dir).expanduser()
        if codex_dir
        else default_codex_skills_dir()
    )
    dst = base / "forge"
    copytree_replace(src, dst)
    bundle_skill_templates(repo_root, dst)
    return str(dst), warnings


def apply_codex_agents_config() -> tuple[str | None, list[str]]:
    from forge_next.codex_agents import apply_codex_agents_config, default_codex_config_path

    warnings: list[str] = []
    cfg = default_codex_config_path()
    rc = apply_codex_agents_config(cfg, force=False)
    if rc == 0:
        return str(cfg), warnings
    if rc == 1:
        warnings.append(
            "Codex developer_instructions not updated in "
            f"{cfg} (existing value differs). "
            "`forge install` does not pass --force. "
            "Run: forge codex-agents --force"
        )
    return None, warnings
