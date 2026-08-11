"""Shared download/extract helpers for forge install."""

from __future__ import annotations

import os
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def default_cursor_local_plugins_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    return home / ".cursor" / "plugins" / "local"


def default_claude_commands_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    return home / ".claude" / "commands"


def default_claude_skills_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    return home / ".claude" / "skills"


def default_codex_skills_dir() -> Path:
    home = Path(os.environ.get("USERPROFILE") or str(Path.home()))
    return home / ".codex" / "skills"


def download_repo_zip(repo_url: str, ref: str, out_path: Path) -> None:
    zip_url = repo_url.rstrip("/") + f"/archive/refs/heads/{ref}.zip"
    req = urllib.request.Request(zip_url, headers={"User-Agent": "forge-next"})
    with urllib.request.urlopen(req, timeout=30) as resp, out_path.open("wb") as f:
        shutil.copyfileobj(resp, f)


def extract_zip(zip_path: Path, out_dir: Path) -> None:
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)


def copytree_replace(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src, dst)


def repo_top_from_extract(extract_dir: Path) -> Path:
    top = next((p for p in extract_dir.iterdir() if p.is_dir()), None)
    if top is None:
        raise RuntimeError("Failed to locate extracted repo folder.")
    return top


def with_downloaded_repo(repo_url: str, ref: str, fn: Callable[[Path], T]) -> T:
    """Download GitHub archive zip and invoke fn(repo_root)."""
    try:
        with tempfile.TemporaryDirectory(prefix="forge-install-") as td:
            td_path = Path(td)
            zip_path = td_path / "repo.zip"
            extract_dir = td_path / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            download_repo_zip(repo_url, ref, zip_path)
            extract_zip(zip_path, extract_dir)
            return fn(repo_top_from_extract(extract_dir))
    except SystemExit:
        raise
    except Exception as e:
        raise SystemExit(f"forge install failed (download/unpack): {e}") from e
