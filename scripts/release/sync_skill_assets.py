#!/usr/bin/env python3
"""Copy skills YAML + schemas JSON into forge_next/assets/ for wheel packaging.

Modeled on sync_prompt_assets.py / sync_template_assets.py. Authoring trees are
source of truth; do not hand-edit packaged mirrors as primary.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SKILLS_SRC = REPO_ROOT / "skills"
SKILLS_DST = REPO_ROOT / "forge_next" / "assets" / "skills"

SCHEMAS_SRC = REPO_ROOT / "schemas"
SCHEMAS_DST = REPO_ROOT / "forge_next" / "assets" / "schemas"


def _sync_tree(src: Path, dst: Path, pattern: str, label: str) -> int:
    """Mirror matching files from src → dst; remove stale packaged files.

    Returns number of files copied. Missing src is treated as empty (exit-friendly).
    """
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    if src.is_dir():
        for path in sorted(src.rglob(pattern)):
            rel = path.relative_to(src)
            out = dst / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, out)
            copied += 1

    # Remove packaged files removed from source (mirror, not append-only).
    if dst.is_dir():
        for path in sorted(dst.rglob(pattern)):
            rel = path.relative_to(dst)
            if not (src / rel).is_file():
                path.unlink()
                print(f"Removed stale packaged {label}: {rel}")

    print(f"Synced {copied} {label} file(s) to {dst}")
    return copied


def main() -> int:
    _sync_tree(SKILLS_SRC, SKILLS_DST, "*.yaml", "skill yaml")
    _sync_tree(SCHEMAS_SRC, SCHEMAS_DST, "*.json", "schema json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
