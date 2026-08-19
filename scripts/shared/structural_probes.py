"""Structural probes (knip, madge, jscn, pyscn, skylos) with agent-selected execution."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SIDECAR_NAME = ".structural-probes.json"
INVENTORY_NAME = ".structural-probes-inventory.json"
PLAN_NAME = ".structural-probes-plan.json"
VALID_PROBE_TOOLS = frozenset({"knip", "madge", "jscn", "pyscn", "skylos"})
NODE_PROBE_TOOLS = frozenset({"knip", "madge", "jscn"})
PYTHON_PROBE_TOOLS = frozenset({"pyscn", "skylos"})
_JS_SUFFIXES = frozenset({".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"})

_NODE_MARKERS = (
    "package.json",
    "pnpm-workspace.yaml",
    "lerna.json",
    "nx.json",
)
_NODE_LOCKFILES = (
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
)
_NODE_SUBDIRS = (
    "apps",
    "packages",
    "integrations",
    "frontend",
    "web",
    "app",
    "client",
    "ui",
    "server",
)
_SKIP_PROBE_PARTS = frozenset({
    "node_modules",
    ".venv",
    "venv",
    ".git",
    "dist",
    "build",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "graphify-out",
    ".pyscn",
    ".skylos",
    ".forge",
    ".codex",
    ".cursor",
    ".claude",
    "htmlcov",
    ".eggs",
    "site-packages",
    ".nox",
    ".ruff_cache",
    ".hypothesis",
    "coverage",
})

# Repo-root trees that make ``pyscn check .`` / ``skylos .`` prohibitively slow.
_LARGE_IGNORED_DIR_NAMES = frozenset({
    ".venv",
    "venv",
    "node_modules",
    "graphify-out",
    ".pyscn",
})

# Default skylos excludes when a broad (repo-root) scan is unavoidable.
_SKYLOS_DEFAULT_EXCLUDE_FOLDERS = (
    ".venv",
    "node_modules",
    ".pyscn",
    "graphify-out",
)

_PYSCN_MIN_COMPLEXITY = 15

_COUNT_SUFFIXES = (".py", ".ts", ".tsx", ".js")


def _is_vendored_forge_snapshot_dir(part: str) -> bool:
    """PyPI extract trees like ``forge_next-0.14.9/`` (not the live ``forge_next/`` package)."""
    return part.startswith("forge_next-") and part != "forge_next"


PROBE_GIT_TIMEOUT_SEC = 8
PROBE_INVENTORY_WALK_MAX = 8000
PROBE_SCOPE_PATH_MAX = 200
PROBE_PYSCN_MAX_FILES = 40
# Per-tool / per-file subprocess budget (pyscn runs one file per invocation).
PROBE_TOOL_TIMEOUT_SEC = 90
PROBE_PYSCN_FILE_TIMEOUT_SEC = 90
# Sentinel exit code for launch crashes / timeouts — distinct from the normal
# 0 (clean) / 1 (tool ran, reported findings) convention most probe CLIs use.
PROBE_CRASH_EXIT_CODE = 124


def _probe_progress(message: str) -> None:
    """stderr progress so step output is not silent while inventory scans run."""
    print(f"forge: {message}", file=sys.stderr, flush=True)


def skip_structural_probes() -> bool:
    v = os.environ.get("FORGE_SKIP_STRUCTURAL_TOOLS", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def auto_run_structural_probes() -> bool:
    """When set, run probes immediately from heuristics/plan (CI/automation)."""
    v = os.environ.get("FORGE_STRUCTURAL_PROBES_AUTO", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def manual_structural_probes() -> bool:
    """When set, step 3 only writes inventory/plan; agent must run ``forge structural-probes run``."""
    v = os.environ.get("FORGE_STRUCTURAL_PROBES_MANUAL", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _is_auto_probe_skill_step(slug: str, step: int) -> bool:
    """Shared skill/step gate for structural probe auto-run and run eligibility."""
    if slug == "code-review" and step == 3:
        return True
    if slug == "implement" and step == 4:
        return True
    if slug == "plan" and step == 2:
        return True
    return False


def should_auto_run_structural_probes(
    skill_name: str,
    step: int,
    mode: str | None = None,
) -> bool:
    """Whether the orchestrator runs probes before printing the step body.

    ``mode`` is accepted for API parity with ``should_run_probes`` but ignored:
    evaluate auto-run is gated by ``FORGE_STRUCTURAL_PROBES_AUTO``, not mode.
    """
    _ = mode
    if manual_structural_probes() or skip_structural_probes():
        return False
    if auto_run_structural_probes():
        return True
    slug = skill_name.strip().lower()
    return _is_auto_probe_skill_step(slug, step)


def inventory_stack_capabilities(
    inventory: dict[str, Any],
) -> tuple[bool, bool]:
    """Return ``(node_capable, python_capable)`` from probe inventory."""
    hints = inventory.get("stack_hints") or {}
    markers = inventory.get("markers") or {}
    counts = inventory.get("counts") or {}
    node_capable = bool(hints.get("node"))
    python_capable = bool(
        hints.get("python")
        or markers.get("pyproject")
        or markers.get("setup_py")
        or counts.get("py", 0) >= 5
    )
    return node_capable, python_capable


def filter_applicable_probe_tools(
    tools: list[str],
    inventory: dict[str, Any],
) -> list[str]:
    """Drop stack-inapplicable tools (e.g. knip on Python-only repos)."""
    node_capable, python_capable = inventory_stack_capabilities(inventory)
    out: list[str] = []
    for tool in normalize_probe_tools(tools):
        if tool in NODE_PROBE_TOOLS and not node_capable:
            continue
        if tool in PYTHON_PROBE_TOOLS and not python_capable:
            continue
        out.append(tool)
    return out


def _merge_plan_reasoning(prior: str, note: str, *, replace: bool = False) -> str:
    """Dedupe sentence-level reasoning; orchestrator may replace stale heuristic text."""
    if replace or not prior.strip():
        return note.strip()
    parts: list[str] = []
    seen: set[str] = set()
    for chunk in (prior, note):
        for sentence in re.split(r"(?<=[.!?])\s+", chunk.strip()):
            s = sentence.strip()
            if not s or s in seen:
                continue
            seen.add(s)
            parts.append(s)
    return " ".join(parts)


def skylos_full_audit_enabled() -> bool:
    v = os.environ.get("FORGE_SKYLOS_AUDIT", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def skylos_use_quick_scan(
    skill_name: str | None,
    step: int | None,
    *,
    scope_paths: list[str] | None = None,
) -> bool:
    """Dead-code-only skylos unless FORGE_SKYLOS_AUDIT=1 (code-review step 3 or scoped runs)."""
    if skylos_full_audit_enabled():
        return False
    if skill_name is not None and skill_name.strip().lower() == "code-review" and step == 3:
        return True
    return bool(scope_paths)


def repo_has_large_ignored_dirs(repo_root: Path) -> bool:
    """True when expensive ignored trees sit at the repo root."""
    root = repo_root.resolve()
    return any((root / name).is_dir() for name in _LARGE_IGNORED_DIR_NAMES)


def _normalize_scope_token(token: str) -> str:
    return token.strip().replace("\\", "/").rstrip("/")


def _is_git_rev_range(token: str) -> bool:
    """True for ``sha..sha`` / ``main...HEAD`` — not relative paths like ``../src``."""
    tok = _normalize_scope_token(token)
    if not tok or tok in (".", "./"):
        return False
    if tok.startswith("../"):
        return False
    return "..." in tok or ".." in tok


def _scope_token_exists(repo_root: Path, token: str) -> bool:
    tok = _normalize_scope_token(token)
    if not tok or _is_git_rev_range(tok):
        return False
    candidate = Path(tok)
    if not candidate.is_absolute():
        candidate = repo_root / tok
    try:
        return candidate.exists()
    except OSError:
        return False


def _is_slow_cross_mount(path: Path) -> bool:
    """WSL 9p mounts (``/mnt/<drive>/...``) stall inventory walks and probe CLIs."""
    try:
        parts = path.resolve().parts
    except OSError:
        parts = path.parts
    return len(parts) >= 2 and parts[0] == "/" and parts[1] == "mnt"


def is_broad_probe_scope(scope_paths: list[str] | None) -> bool:
    """True when scope would scan repo root or an unspecified whole tree."""
    if not scope_paths:
        return True
    for raw in scope_paths:
        tok = _normalize_scope_token(str(raw))
        if tok in ("", ".", "./"):
            return True
    return False


def _probe_ignore_policy(repo_root: Path):
    from scripts.shared.probe_ignore import get_probe_ignore_policy

    key = "\0".join(sorted(_SKIP_PROBE_PARTS))
    return get_probe_ignore_policy(str(repo_root.resolve()), key)


def _filter_scope_paths(
    repo_root: Path,
    paths: list[str],
    *,
    allow_file: Callable[[Path], bool],
) -> list[str]:
    """Keep review-relevant paths; drop gitignored/graphifyignored trees."""
    root = repo_root.resolve()
    policy = _probe_ignore_policy(root)
    candidates: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        tok = _normalize_scope_token(str(raw))
        if not tok or tok in (".", "./"):
            continue
        candidate = (root / tok).resolve()
        if not candidate.exists():
            continue
        if candidate.is_file() and not allow_file(candidate):
            continue
        rel = _rel_path(candidate, root).replace("\\", "/")
        if rel in seen:
            continue
        seen.add(rel)
        candidates.append(rel)
    return policy.filter_paths(candidates, for_scope=True)


def filter_python_scope_paths(repo_root: Path, paths: list[str]) -> list[str]:
    """Keep review-relevant Python paths; drop gitignored/graphifyignored trees."""
    return _filter_scope_paths(
        repo_root, paths, allow_file=lambda p: p.suffix == ".py"
    )


def filter_javascript_scope_paths(repo_root: Path, paths: list[str]) -> list[str]:
    """Keep review-relevant JS/TS paths; drop gitignored/graphifyignored trees."""
    return _filter_scope_paths(
        repo_root,
        paths,
        allow_file=lambda p: p.suffix.lower() in _JS_SUFFIXES,
    )


def _git_run_names(repo_root: Path, args: list[str], *, timeout: int | None = None) -> list[str]:
    import subprocess

    effective_timeout = PROBE_GIT_TIMEOUT_SEC if timeout is None else timeout
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=effective_timeout,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def _git_default_merge_base(repo_root: Path) -> str | None:
    for ref in ("origin/main", "origin/master", "main", "master"):
        names = _git_run_names(repo_root, ["rev-parse", "--verify", ref])
        if names:
            return ref
    return None


def _dedupe_extend_paths(paths: list[str], seen: set[str], rows: list[str]) -> None:
    for row in rows:
        if row in seen:
            continue
        seen.add(row)
        paths.append(row)


def _git_collect_merge_base_diffs(repo_root: Path, base: str | None) -> list[str]:
    if not base:
        return []
    rows: list[str] = []
    rows.extend(_git_run_names(repo_root, ["diff", "--name-only", f"{base}...HEAD"]))
    rows.extend(_git_run_names(repo_root, ["diff", "--name-only", "--cached"]))
    rows.extend(_git_run_names(repo_root, ["diff", "--name-only"]))
    return rows


def _git_collect_range_diffs(repo_root: Path, tokens: list[str]) -> list[str]:
    """Expand ``sha..sha`` / ``ref...ref`` tokens via ``git diff --name-only``."""
    rows: list[str] = []
    for tok in tokens:
        if _is_git_rev_range(tok):
            rows.extend(_git_run_names(repo_root, ["diff", "--name-only", tok]))
    return rows


def _git_collect_token_diffs(
    repo_root: Path,
    tokens: list[str],
    base: str | None,
) -> list[str]:
    rows: list[str] = []
    for tok in tokens:
        if tok in ("", ".", "./") or _is_git_rev_range(tok):
            continue
        if tok.endswith(".py") or "/" in tok:
            rows.extend(_git_run_names(repo_root, ["diff", "--name-only", "--", tok]))
            if base:
                rows.extend(
                    _git_run_names(repo_root, ["diff", "--name-only", f"{base}...{tok}"])
                )
        elif base:
            rows.extend(_git_run_names(repo_root, ["diff", "--name-only", f"{base}...{tok}"]))
    return rows


def _gh_pr_changed_paths(repo_root: Path, pr_number: str) -> list[str]:
    """Changed files for a PR number via ``gh pr diff --name-only`` (best effort)."""
    import subprocess

    try:
        proc = subprocess.run(
            ["gh", "pr", "diff", pr_number, "--name-only"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=PROBE_GIT_TIMEOUT_SEC,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def _gh_collect_pr_number_diffs(repo_root: Path, tokens: list[str]) -> list[str]:
    """Resolve numeric / ``#123`` style PR tokens to changed paths via ``gh``."""
    rows: list[str] = []
    for tok in tokens:
        candidate = tok.lstrip("#").strip()
        if candidate.isdigit():
            rows.extend(_gh_pr_changed_paths(repo_root, candidate))
    return rows


def _prefer_source_scope_paths(paths: list[str]) -> list[str]:
    source_suffixes = (".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
    preferred = [
        p for p in paths if Path(p).suffix.lower() in source_suffixes or p.endswith("/")
    ]
    return preferred if preferred else paths


def _cap_scope_paths(paths: list[str], *, max_count: int, label: str) -> list[str]:
    if len(paths) <= max_count:
        return paths
    _probe_progress(
        f"structural Pass B — capping {label} "
        f"({len(paths)} → {max_count})"
    )
    return paths[:max_count]


def _git_changed_paths_for_review(
    repo_root: Path,
    target_tokens: list[str] | None,
    *,
    mode: str | None = None,
) -> list[str]:
    """Collect changed file paths from git for PR/code-review structural probes."""
    tokens = [_normalize_scope_token(str(t)) for t in (target_tokens or []) if str(t).strip()]
    existing = [t for t in tokens if _scope_token_exists(repo_root, t)]
    if (
        tokens
        and not is_broad_probe_scope(tokens)
        and existing == tokens
        and not any(_is_git_rev_range(t) for t in tokens)
    ):
        return tokens

    paths: list[str] = []
    seen: set[str] = set()
    base = _git_default_merge_base(repo_root)

    _dedupe_extend_paths(paths, seen, _git_collect_range_diffs(repo_root, tokens))
    _dedupe_extend_paths(paths, seen, _git_collect_merge_base_diffs(repo_root, base))
    _dedupe_extend_paths(paths, seen, _git_collect_token_diffs(repo_root, tokens, base))
    _dedupe_extend_paths(paths, seen, _gh_collect_pr_number_diffs(repo_root, tokens))

    if mode == "pr" and not paths:
        _dedupe_extend_paths(
            paths,
            seen,
            _git_run_names(repo_root, ["diff", "--name-only", "HEAD~1..HEAD"]),
        )

    _dedupe_extend_paths(
        paths,
        seen,
        _git_run_names(repo_root, ["ls-files", "--others", "--exclude-standard"]),
    )

    paths = _prefer_source_scope_paths(paths)
    paths = _cap_scope_paths(
        paths,
        max_count=PROBE_SCOPE_PATH_MAX,
        label="git scope candidates",
    )
    return _probe_ignore_policy(repo_root).filter_paths(paths, for_scope=True)


def resolve_effective_scope_paths(
    repo_root: Path,
    scope_paths: list[str] | None,
    *,
    skill_name: str,
    step: int,
    mode: str | None = None,
) -> tuple[list[str], str]:
    """Scope Python probes to changed files; avoid repo-root scans when unsafe.

    ``scope_paths`` may contain non-path tokens (``HEAD``, PR numbers, branch
    names — e.g. from ``code-review --target``). Those tokens are resolved to
    changed files via git/gh; this never returns a raw non-path token as a
    probe scope path. When nothing can be resolved, returns an empty scope.
    """
    slug = skill_name.strip().lower()
    scoped_skills = (
        (slug == "code-review" and step == 3)
        or (slug == "evaluate" and step == 4 and mode == "post")
        or (slug == "evaluate" and step == 1 and mode == "review")
    )
    if not scoped_skills:
        existing = list(scope_paths or [])
        return existing, ""

    tokens = list(scope_paths or [])
    note_parts: list[str] = []
    broad = is_broad_probe_scope(tokens)

    if not broad:
        # Tokens may already be real file paths (e.g. explicit --target file list).
        filtered = filter_python_scope_paths(repo_root, tokens)
        if filtered:
            if filtered != tokens:
                note_parts.append("Filtered probe scope_paths to existing Python paths.")
            return filtered, " ".join(note_parts)

    changed = _git_changed_paths_for_review(repo_root, tokens, mode=mode)
    py_changed = filter_python_scope_paths(repo_root, changed)
    if py_changed:
        note_parts.append(
            f"Scoped Python probes to {len(py_changed)} changed .py file(s) from git diff."
        )
        return py_changed, " ".join(note_parts)

    if repo_has_large_ignored_dirs(repo_root):
        p_root = python_probe_root(repo_root)
        if p_root.resolve() != repo_root.resolve():
            rel = _rel_path(p_root, repo_root)
            note_parts.append(
                f"Avoided repo-root Python scan (large ignored dirs); using python root `{rel}`."
            )
            return [rel], " ".join(note_parts)
        note_parts.append(
            "Skipped broad Python probe scope: repo root has large ignored dirs "
            "and no changed Python files were detected."
        )
        return [], " ".join(note_parts)

    if not broad and tokens:
        note_parts.append(
            "Scope tokens were not filesystem paths (ref/PR/branch) and no changed "
            "Python files were resolved via git/gh; skipping Python probe scope "
            "rather than passing non-path tokens through."
        )
        return [], " ".join(note_parts)

    return [], " ".join(note_parts)


def _ensure_plan_baseline_probe_plan(
    merged: dict[str, Any],
    inventory: dict[str, Any],
    *,
    scope_paths: list[str] | None,
    scope_note: str | None,
) -> dict[str, Any]:
    """Plan/2: jscn and/or pyscn only (complexity/clones baseline)."""
    node_capable, python_capable = inventory_stack_capabilities(inventory)
    tools: list[str] = []
    if node_capable:
        tools.append("jscn")
    if python_capable:
        tools.append("pyscn")
    merged["tools"] = tools
    roots = inventory.get("suggested_probe_roots") or {}
    if "pyscn" in tools and not merged.get("python_root") and roots.get("python"):
        merged["python_root"] = roots["python"]
    if "jscn" in tools and not merged.get("node_root") and roots.get("node"):
        merged["node_root"] = roots["node"]
    if scope_paths:
        merged["scope_paths"] = list(scope_paths)
    elif "scope_paths" in merged and is_broad_probe_scope(merged.get("scope_paths")):
        merged["scope_paths"] = []
    note = (
        "Plan step 2 baseline: jscn and/or pyscn only (complexity/clones). "
        "Advisory — does not block architecture. "
        "Full stack probes run at implement wave review and code-review."
    )
    if scope_note:
        note = f"{scope_note} {note}"
    merged["reasoning"] = _merge_plan_reasoning(
        str(merged.get("reasoning") or ""),
        note,
        replace=True,
    )
    merged["source"] = "orchestrator"
    merged["stack_applicable"] = {
        "node": node_capable,
        "python": python_capable,
    }
    return merged


def _is_review_stack_scope(skill_name: str, step: int, mode: str | None) -> bool:
    slug = skill_name.strip().lower()
    return (
        (slug == "code-review" and step == 3)
        or (slug == "evaluate" and step == 4 and mode == "post")
        or (slug == "evaluate" and step == 1 and mode == "review")
    )


def _resolve_review_stack_scope(
    repo_root: Path,
    merged: dict[str, Any],
    *,
    skill_name: str,
    step: int,
    mode: str | None,
    scope_paths: list[str] | None,
    scope_note: str | None,
) -> tuple[list[str], str]:
    if scope_note is not None:
        return list(scope_paths or []), scope_note
    return resolve_effective_scope_paths(
        repo_root,
        scope_paths or merged.get("scope_paths"),
        skill_name=skill_name,
        step=step,
        mode=mode,
    )


def _assemble_review_stack_tools(
    merged: dict[str, Any],
    inventory: dict[str, Any],
    *,
    node_capable: bool,
    python_capable: bool,
) -> list[str]:
    tools = filter_applicable_probe_tools(
        normalize_probe_tools(merged.get("tools")),
        inventory,
    )
    if node_capable:
        for required in ("knip", "madge", "jscn"):
            if required not in tools:
                tools.append(required)
    if python_capable:
        for required in ("pyscn", "skylos"):
            if required not in tools:
                tools.append(required)
    return tools


def _maybe_assign_fallback_python_root(
    merged: dict[str, Any],
    roots: dict[str, Any],
    *,
    effective_scope: list[str],
    repo_root: Path,
    python_capable: bool,
) -> None:
    if not (python_capable and not effective_scope and repo_has_large_ignored_dirs(repo_root)):
        return
    py_root = roots.get("python")
    if py_root and not merged.get("python_root"):
        merged["python_root"] = py_root


def _assign_python_probe_root(
    merged: dict[str, Any],
    roots: dict[str, Any],
    tools: list[str],
    effective_scope: list[str],
) -> None:
    if not tools or not any(t in PYTHON_PROBE_TOOLS for t in tools):
        return
    if effective_scope:
        merged["python_root"] = "."
    elif not merged.get("python_root") and roots.get("python"):
        merged["python_root"] = roots["python"]


def _assign_node_probe_root(
    merged: dict[str, Any],
    roots: dict[str, Any],
    tools: list[str],
) -> None:
    if not tools or not any(t in NODE_PROBE_TOOLS for t in tools):
        return
    if not merged.get("node_root") and roots.get("node"):
        merged["node_root"] = roots["node"]


def _assign_review_scope_paths(
    merged: dict[str, Any],
    effective_scope: list[str],
) -> None:
    merged["scope_paths"] = list(effective_scope)


def _ensure_skylos_exclude_paths(merged: dict[str, Any]) -> None:
    exclude_paths = merged.get("exclude_paths")
    if not isinstance(exclude_paths, list) or not exclude_paths:
        merged["exclude_paths"] = list(_SKYLOS_DEFAULT_EXCLUDE_FOLDERS)


def _assign_review_stack_roots(
    merged: dict[str, Any],
    inventory: dict[str, Any],
    *,
    tools: list[str],
    effective_scope: list[str],
    repo_root: Path,
    python_capable: bool,
) -> None:
    roots = inventory.get("suggested_probe_roots") or {}
    _maybe_assign_fallback_python_root(
        merged,
        roots,
        effective_scope=effective_scope,
        repo_root=repo_root,
        python_capable=python_capable,
    )
    _assign_python_probe_root(merged, roots, tools, effective_scope)
    _assign_node_probe_root(merged, roots, tools)
    _assign_review_scope_paths(merged, effective_scope)
    _ensure_skylos_exclude_paths(merged)


def _review_stack_reasoning_note(slug: str, resolved_note: str) -> str:
    skill_label = "Code-review step 3" if slug == "code-review" else "Evaluate"
    note = (
        f"{skill_label} runs stack-applicable probes only "
        "(knip/madge/jscn when Node; pyscn/skylos when Python). "
        "Python probes prefer changed-file scope; repo-root scans are skipped when "
        "large ignored dirs exist (.venv, node_modules, graphify-out, .pyscn). "
        "Gitignored and graphifyignored paths are never scanned. "
        "Skylos uses dead-code scan unless FORGE_SKYLOS_AUDIT=1."
    )
    if resolved_note:
        return f"{resolved_note} {note}"
    return note


def _ensure_review_stack_probe_plan(
    merged: dict[str, Any],
    inventory: dict[str, Any],
    *,
    skill_name: str,
    step: int,
    scope_paths: list[str] | None,
    mode: str | None,
    scope_note: str | None,
) -> dict[str, Any]:
    """Code-review/evaluate: stack-applicable full probe tool set."""
    if not _is_review_stack_scope(skill_name, step, mode):
        return merged

    repo_root = Path(str(inventory.get("repo_root") or ".")).resolve()
    effective_scope, resolved_note = _resolve_review_stack_scope(
        repo_root,
        merged,
        skill_name=skill_name,
        step=step,
        mode=mode,
        scope_paths=scope_paths,
        scope_note=scope_note,
    )

    node_capable, python_capable = inventory_stack_capabilities(inventory)
    tools = _assemble_review_stack_tools(
        merged,
        inventory,
        node_capable=node_capable,
        python_capable=python_capable,
    )
    merged["tools"] = tools
    _assign_review_stack_roots(
        merged,
        inventory,
        tools=tools,
        effective_scope=effective_scope,
        repo_root=repo_root,
        python_capable=python_capable,
    )

    slug = skill_name.strip().lower()
    merged["reasoning"] = _merge_plan_reasoning(
        str(merged.get("reasoning") or ""),
        _review_stack_reasoning_note(slug, resolved_note),
        replace=True,
    )
    merged["source"] = "orchestrator"
    merged["stack_applicable"] = {
        "node": node_capable,
        "python": python_capable,
    }
    return merged


def ensure_primary_probe_plan(
    plan: dict[str, Any],
    inventory: dict[str, Any],
    *,
    skill_name: str,
    step: int,
    scope_paths: list[str] | None = None,
    mode: str | None = None,
    scope_note: str | None = None,
) -> dict[str, Any]:
    """Dispatch to plan baseline or review-stack helpers."""
    merged = dict(plan or {})
    slug = skill_name.strip().lower()
    if slug == "plan" and step == 2:
        return _ensure_plan_baseline_probe_plan(
            merged,
            inventory,
            scope_paths=scope_paths,
            scope_note=scope_note,
        )
    return _ensure_review_stack_probe_plan(
        merged,
        inventory,
        skill_name=skill_name,
        step=step,
        scope_paths=scope_paths,
        mode=mode,
        scope_note=scope_note,
    )


def should_run_probes(skill_name: str, step: int, mode: str | None = None) -> bool:
    slug = skill_name.strip().lower()
    if _is_auto_probe_skill_step(slug, step):
        return True
    if slug == "evaluate" and step == 4 and mode == "post":
        return True
    if slug == "evaluate" and step == 1 and mode == "review":
        return True
    return False


def _should_prune_walk_path(path: Path, repo_root: Path) -> bool:
    """True if ``os.walk`` must not descend into or yield this path."""
    # Inventory walks use fast dir skips only (not per-path git check-ignore).
    return _probe_ignore_policy(repo_root).is_ignored(path, for_scope=False)


def _walk_repo_files(
    repo_root: Path,
    *,
    suffix: str | None = None,
    basename: str | None = None,
    max_files: int | None = None,
) -> Iterator[Path]:
    """Walk the repo without descending into gitignored/graphifyignored trees.

    ``Path.rglob`` matches files inside ignored trees first (very slow on ``.venv``).
    This prunes directory names in ``os.walk`` before recursion.
    ``max_files`` caps yields (default ``PROBE_INVENTORY_WALK_MAX``).
    """
    root = repo_root.resolve()
    limit = PROBE_INVENTORY_WALK_MAX if max_files is None else max_files
    yielded = 0
    listed = _git_run_names(root, ["ls-files"])
    listed.extend(_git_run_names(root, ["ls-files", "--others", "--exclude-standard"]))
    if listed:
        for rel in listed:
            path = root / rel
            if _should_prune_walk_path(path, root):
                continue
            if basename is not None and path.name != basename:
                continue
            if suffix is not None and not path.name.endswith(suffix):
                continue
            yield path
            yielded += 1
            if limit > 0 and yielded >= limit:
                return
        return
    for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
        current = Path(dirpath)
        if _should_prune_walk_path(current, root):
            dirnames.clear()
            continue
        dirnames[:] = [
            d for d in dirnames if not _should_prune_walk_path(current / d, root)
        ]
        for name in filenames:
            if basename is not None and name != basename:
                continue
            if suffix is not None and not name.endswith(suffix):
                continue
            path = current / name
            if _should_prune_walk_path(path, root):
                continue
            yield path
            yielded += 1
            if limit > 0 and yielded >= limit:
                return


def _source_suffix_counts(
    repo_root: Path,
    *,
    limit_per_suffix: int = 250,
) -> dict[str, int]:
    """Count ``.py`` / ``.ts`` / ``.tsx`` / ``.js`` files in one pruned walk."""
    counts = {s: 0 for s in _COUNT_SUFFIXES}
    for path in _walk_repo_files(repo_root):
        suf = path.suffix
        if suf not in counts:
            continue
        if counts[suf] >= limit_per_suffix:
            if all(counts[s] >= limit_per_suffix for s in _COUNT_SUFFIXES):
                break
            continue
        counts[suf] += 1
    return counts


def _rel_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return str(path)


def _count_source_files(repo_root: Path, suffix: str, *, limit: int = 250) -> int:
    if suffix in _COUNT_SUFFIXES:
        return _source_suffix_counts(repo_root, limit_per_suffix=limit).get(suffix, 0)
    count = 0
    for _path in _walk_repo_files(repo_root, suffix=suffix):
        count += 1
        if count >= limit:
            return count
    return count


def _find_shallow_package_json(repo_root: Path, *, max_depth: int = 4) -> Path | None:
    best: Path | None = None
    best_depth = max_depth + 1
    root = repo_root.resolve()
    for pkg in _walk_repo_files(repo_root, basename="package.json"):
        try:
            depth = len(pkg.parent.relative_to(root).parts)
        except ValueError:
            continue
        if depth > max_depth:
            continue
        if depth < best_depth:
            best = pkg.parent
            best_depth = depth
    return best


def _list_package_json_roots(repo_root: Path, *, limit: int = 12) -> list[str]:
    roots: list[tuple[int, str]] = []
    root = repo_root.resolve()
    for pkg in _walk_repo_files(repo_root, basename="package.json"):
        try:
            depth = len(pkg.parent.relative_to(root).parts)
        except ValueError:
            continue
        if depth > 5:
            continue
        roots.append((depth, _rel_path(pkg.parent, repo_root)))
    roots.sort(key=lambda item: (item[0], item[1]))
    seen: set[str] = set()
    out: list[str] = []
    for _, rel in roots:
        if rel in seen:
            continue
        seen.add(rel)
        out.append(rel)
        if len(out) >= limit:
            break
    return out


def _has_node_project(repo_root: Path) -> bool:
    root = repo_root.resolve()
    for name in _NODE_MARKERS:
        if (root / name).is_file():
            return True
    for name in _NODE_LOCKFILES:
        if (root / name).is_file():
            return True
    if (root / "tsconfig.json").is_file() or (root / "jsconfig.json").is_file():
        return True
    for sub in _NODE_SUBDIRS:
        subdir = root / sub
        if subdir.is_dir() and (subdir / "package.json").is_file():
            return True
    return _find_shallow_package_json(root) is not None


def detect_stack(
    repo_root: Path,
    *,
    suffix_counts: dict[str, int] | None = None,
) -> dict[str, bool]:
    """Heuristic stack flags (hints only — agents choose tools via plan)."""
    root = repo_root.resolve()
    node = _has_node_project(root)
    counts = suffix_counts if suffix_counts is not None else _source_suffix_counts(root)
    py_count = counts.get(".py", 0)
    ts_count = counts.get(".ts", 0) + counts.get(".tsx", 0)
    has_py_project = (root / "pyproject.toml").is_file() or (root / "setup.py").is_file()

    if has_py_project:
        if node and ts_count > py_count:
            python = py_count >= 10
        else:
            python = True
    elif py_count >= 5:
        python = not node or py_count > ts_count
    else:
        python = False

    return {"python": python, "node": node}


def node_probe_root(repo_root: Path) -> Path:
    root = repo_root.resolve()
    if (root / "package.json").is_file():
        return root
    for sub in _NODE_SUBDIRS:
        candidate = root / sub
        if (candidate / "package.json").is_file():
            return candidate
    shallow = _find_shallow_package_json(root)
    return shallow if shallow is not None else root


def python_probe_root(repo_root: Path) -> Path:
    root = repo_root.resolve()
    if (root / "pyproject.toml").is_file() or (root / "setup.py").is_file():
        return root
    per_dir: dict[Path, int] = {}
    # Sample only — full-tree .py walks hang on large monorepos without pyproject.
    for path in _walk_repo_files(repo_root, suffix=".py", max_files=500):
        per_dir[path.parent] = per_dir.get(path.parent, 0) + 1
    if not per_dir:
        return root
    best_dir, best_count = max(per_dir.items(), key=lambda item: item[1])
    return best_dir if best_count >= 3 else root


def _resolve_probe_root(repo_root: Path, hint: str | None, default: Path) -> Path:
    if not hint:
        return default
    candidate = Path(hint)
    if not candidate.is_absolute():
        candidate = repo_root / candidate
    return candidate.resolve()


def build_stack_inventory(repo_root: Path) -> dict[str, Any]:
    """Factual repo signals for the agent to choose probes."""
    root = repo_root.resolve()
    suffix_counts = _source_suffix_counts(root)
    stack = detect_stack(root, suffix_counts=suffix_counts)
    n_root = node_probe_root(root)
    p_root = python_probe_root(root)
    graphify_report = root / "graphify-out" / "GRAPH_REPORT.md"
    return {
        "repo_root": str(root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stack_hints": stack,
        "counts": {
            "py": suffix_counts.get(".py", 0),
            "ts": suffix_counts.get(".ts", 0),
            "tsx": suffix_counts.get(".tsx", 0),
            "js": suffix_counts.get(".js", 0),
        },
        "markers": {
            "package_json_roots": _list_package_json_roots(root),
            "pyproject": (root / "pyproject.toml").is_file(),
            "setup_py": (root / "setup.py").is_file(),
            "tsconfig": (root / "tsconfig.json").is_file(),
            "workspace_files": [
                name for name in _NODE_MARKERS if (root / name).is_file()
            ],
        },
        "suggested_probe_roots": {
            "node": _rel_path(n_root, root),
            "python": _rel_path(p_root, root),
        },
        "graphify_report": str(graphify_report) if graphify_report.is_file() else None,
    }


def suggest_probe_plan(
    inventory: dict[str, Any],
    *,
    scope_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Heuristic starting plan — agents should confirm or override."""
    hints = inventory.get("stack_hints") or {}
    tools: list[str] = []
    notes: list[str] = []
    if hints.get("node"):
        tools.extend(["knip", "madge", "jscn"])
        notes.append(
            "Node/TS markers present → knip (dead exports) + madge (cycles) + jscn (complexity/clones)."
        )
    if hints.get("python"):
        tools.extend(["pyscn", "skylos"])
        notes.append(
            "Python markers present → pyscn (clones/complexity) + skylos (dead code / SAST)."
        )
    if not tools:
        notes.append("No strong stack signal — consider skipping all probes or scoping manually.")

    roots = inventory.get("suggested_probe_roots") or {}
    return {
        "tools": tools,
        "node_root": roots.get("node"),
        "python_root": roots.get("python")
        if any(t in PYTHON_PROBE_TOOLS for t in tools)
        else None,
        "scope_paths": list(scope_paths or []),
        "reasoning": " ".join(notes) or "Heuristic suggestion only.",
        "source": "heuristic",
    }


def normalize_probe_tools(tools: object) -> list[str]:
    if not isinstance(tools, list):
        return []
    out: list[str] = []
    for item in tools:
        if not isinstance(item, str):
            continue
        slug = item.strip().lower()
        if slug in VALID_PROBE_TOOLS and slug not in out:
            out.append(slug)
    return out


def plan_path(state_dir: Path | None) -> Path | None:
    if state_dir is None:
        return None
    return Path(state_dir) / PLAN_NAME


def inventory_path(state_dir: Path | None) -> Path | None:
    if state_dir is None:
        return None
    return Path(state_dir) / INVENTORY_NAME


def load_probe_plan(state_dir: Path | None) -> dict[str, Any] | None:
    path = plan_path(state_dir)
    if path is None or not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_probe_plan(state_dir: Path, plan: dict[str, Any]) -> Path:
    path = Path(state_dir) / PLAN_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    return path


def write_stack_inventory(
    state_dir: Path,
    inventory: dict[str, Any],
    suggestion: dict[str, Any],
) -> Path:
    path = Path(state_dir) / INVENTORY_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"inventory": inventory, "heuristic_suggestion": suggestion}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def merge_plan_with_scope(
    plan: dict[str, Any] | None,
    *,
    scope_paths: list[str] | None,
) -> dict[str, Any]:
    merged = dict(plan or {})
    if scope_paths and not merged.get("scope_paths"):
        merged["scope_paths"] = list(scope_paths)
    merged["tools"] = normalize_probe_tools(merged.get("tools"))
    return merged


def _kill_process_tree(proc: Any) -> None:
    """Best-effort kill of ``proc`` and any children (Windows pyscn spawns a helper)."""
    import subprocess

    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
            )
        else:
            import os
            import signal

            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except (OSError, ProcessLookupError, AttributeError):
                proc.kill()
    except (OSError, subprocess.TimeoutExpired):
        try:
            proc.kill()
        except OSError:
            pass


def _windows_image_listed(image: str) -> bool:
    import subprocess

    try:
        listing = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image}"],
            capture_output=True,
            text=True,
            timeout=5,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    text = (listing.stdout or "") + (listing.stderr or "")
    return image.lower() in text.lower()


def _cleanup_orphaned_pyscn_workers() -> None:
    """Kill leftover pyscn helper processes that block later probe runs on Windows."""
    if sys.platform != "win32":
        return
    import subprocess

    if not any(
        _windows_image_listed(image)
        for image in ("pyscn-windows-amd64.exe", "pyscn.exe")
    ):
        return

    for image in ("pyscn-windows-amd64.exe", "pyscn.exe"):
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", image],
                capture_output=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass


def _run_cmd(cmd: list[str], *, cwd: Path, timeout: int) -> tuple[int, str]:
    """Run a probe tool with a hard timeout that kills the full process tree.

    On Windows, ``pyscn`` launches ``pyscn-windows-amd64``; ``subprocess.run(...,
    timeout=)`` only kills the parent, leaving orphans that stall later probes.
    """
    import subprocess

    # Clear orphans before pyscn so a prior Ctrl-C / timeout does not serialize forever.
    if any("pyscn" in str(part).lower() for part in cmd):
        _cleanup_orphaned_pyscn_workers()

    popen_kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if sys.platform != "win32":
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        # Distinct from exit 1 (tool ran, reported findings) — this is a launch crash.
        return PROBE_CRASH_EXIT_CODE, str(exc)

    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree(proc)
        if any("pyscn" in str(part).lower() for part in cmd):
            _cleanup_orphaned_pyscn_workers()
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except (subprocess.TimeoutExpired, OSError, ValueError):
            stdout, stderr = "", ""
        return (
            PROBE_CRASH_EXIT_CODE,
            f"TimeoutExpired: command exceeded {timeout}s: {' '.join(cmd)}",
        )
    except OSError as exc:
        _kill_process_tree(proc)
        return PROBE_CRASH_EXIT_CODE, str(exc)

    out = (stdout or "") + (stderr or "")
    return proc.returncode, out.strip()


def _tool_findings(tool: str, code: int, out: str, *, max_findings: int = 8) -> list[dict[str, Any]]:
    if code == 0 and len(out) < 200:
        return []
    findings: list[dict[str, Any]] = []
    prefix = {"knip": "K", "madge": "M", "jscn": "J", "pyscn": "P", "skylos": "Y"}.get(tool, "X")
    lines = [ln for ln in out.splitlines() if ln.strip()]
    for i, line in enumerate(lines[:max_findings], start=1):
        path = ""
        m = re.search(r"([\w./\\-]+\.(?:py|ts|tsx|js|jsx|mjs|cjs))", line)
        if m:
            path = m.group(1)
        findings.append(
            {
                "id": f"{prefix}{i}",
                "severity": "warning" if code != 0 else "suggestion",
                "path": path,
                "detail": line[:500],
            }
        )
    if not findings and code != 0:
        findings.append(
            {
                "id": f"{prefix}0",
                "severity": "warning",
                "path": "",
                "detail": out[:1500] or f"{tool} exited {code}",
            }
        )
    return findings


def _extract_stdout_json(raw: str) -> dict[str, Any] | None:
    """Parse the first JSON object from tool stdout (tolerates uv install lines after JSON)."""
    text = raw.strip()
    if not text:
        return None
    decoder = json.JSONDecoder()
    start = 0
    while True:
        idx = text.find("{", start)
        if idx < 0:
            return None
        try:
            data, _end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError:
            start = idx + 1
            continue
        return data if isinstance(data, dict) else None


def _skylos_scan_targets(
    *,
    repo_root: Path,
    python_root: Path,
    scope_paths: list[str] | None,
) -> list[str]:
    policy = _probe_ignore_policy(repo_root)
    if scope_paths:
        existing = [
            str(p).strip()
            for p in scope_paths
            if str(p).strip()
            and not _is_git_rev_range(str(p))
            and _scope_token_exists(repo_root, str(p))
        ]
        return policy.filter_paths(existing, for_scope=True)
    if python_root != repo_root:
        try:
            rel = str(python_root.relative_to(repo_root))
        except ValueError:
            rel = str(python_root)
        return [] if policy.rel_is_ignored(rel, for_scope=True) else [rel]
    return ["."]


def _skylos_needs_default_excludes(targets: list[str]) -> bool:
    if not targets:
        return True
    return any(_normalize_scope_token(t) in (".", "./") for t in targets)


def _skylos_scan_command(
    resolved: list[str],
    targets: list[str],
    *,
    quick_scan: bool = True,
    exclude_folders: list[str] | None = None,
    repo_root: Path | None = None,
) -> list[str]:
    """Dead-code JSON scan by default; full audit with ``-a`` when ``quick_scan`` is false."""
    base = [*resolved, *targets]
    extras: list[str] = []
    if quick_scan:
        extras.append("--json")
    else:
        extras.extend(["-a", "--json"])
    folders = list(exclude_folders or ())
    if _skylos_needs_default_excludes(targets):
        base_defaults = tuple(folders) if folders else _SKYLOS_DEFAULT_EXCLUDE_FOLDERS
        if repo_root is not None:
            folders = _probe_ignore_policy(repo_root).skylos_exclude_folders(base_defaults)
        elif not folders:
            folders = list(_SKYLOS_DEFAULT_EXCLUDE_FOLDERS)
    for folder in folders:
        extras.extend(["--exclude-folder", folder])
    return [*base, *extras]


def _skylos_item_to_finding(item: dict[str, Any], *, category: str) -> dict[str, Any] | None:
    path = str(item.get("file") or item.get("path") or "").replace("\\\\", "/")
    if path.startswith("/") and len(path) > 2 and path[2] == ":":
        path = path.lstrip("/")
    line = item.get("line")
    if path and line:
        path = f"{path}:{line}"
    name = str(item.get("name") or item.get("simple_name") or item.get("rule_id") or category)
    message = str(item.get("message") or item.get("dead_code_classification") or category)
    conf = item.get("confidence")
    detail_parts = [message, f"name={name}"]
    if conf is not None:
        detail_parts.append(f"conf={conf}")
    severity = str(item.get("severity") or "warning").lower()
    if severity in ("low", "info"):
        severity = "suggestion"
    return {
        "severity": severity,
        "path": path,
        "detail": " — ".join(detail_parts)[:500],
    }


def _skylos_json_candidates(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    for category in (
        "unused_functions",
        "unused_imports",
        "unused_classes",
        "unused_variables",
        "unused_parameters",
        "unused_files",
    ):
        chunk = data.get(category)
        if not isinstance(chunk, list):
            continue
        for item in chunk:
            if isinstance(item, dict):
                candidates.append((category, item))
    definitions = data.get("definitions")
    if isinstance(definitions, dict):
        for item in definitions.values():
            if not isinstance(item, dict):
                continue
            if item.get("dead") or item.get("dead_code_classification") in (
                "likely_dead",
                "dead",
            ):
                candidates.append(("definitions", item))
    return candidates


def _parse_skylos_json_findings(raw: str, *, max_findings: int = 8) -> list[dict[str, Any]]:
    data = _extract_stdout_json(raw)
    if not data:
        return []
    candidates = _skylos_json_candidates(data)
    findings: list[dict[str, Any]] = []
    for i, (category, item) in enumerate(candidates[:max_findings], start=1):
        row = _skylos_item_to_finding(item, category=category)
        if not row:
            continue
        detail = row.get("detail") or ""
        if "Installed " in detail and "packages" in detail:
            continue
        row["id"] = f"Y{i}"
        findings.append(row)
    return findings


def _pyscn_check_command(resolved: list[str], *, target: str = ".") -> list[str]:
    if resolved[:1] == ["pyscn"] or (resolved and resolved[0].endswith("pyscn")):
        return ["pyscn", "check", target]
    if resolved and resolved[0] in ("uvx", "uv"):
        return [resolved[0], "pyscn@latest", "check", target]
    return [*resolved, "check", target]


def _pyscn_analyze_command(
    resolved: list[str],
    *,
    targets: list[str],
    min_complexity: int = _PYSCN_MIN_COMPLEXITY,
) -> list[str]:
    """Targeted complexity/clone scan — preferred over ``check .`` on large repos."""
    args = [
        "analyze",
        "--json",
        f"--min-complexity={min_complexity}",
        *targets,
    ]
    if resolved[:1] == ["pyscn"] or (resolved and resolved[0].endswith("pyscn")):
        return ["pyscn", *args]
    if resolved and resolved[0] in ("uvx", "uv"):
        return [resolved[0], "pyscn@latest", *args]
    return [*resolved, *args]


def _cap_pyscn_targets(paths: list[str]) -> list[str]:
    if len(paths) <= PROBE_PYSCN_MAX_FILES:
        return paths
    _probe_progress(
        f"structural Pass B — capping pyscn targets "
        f"({len(paths)} → {PROBE_PYSCN_MAX_FILES})"
    )
    return paths[:PROBE_PYSCN_MAX_FILES]


def _relative_probe_root_path(repo_root: Path, probe_root: Path) -> list[str]:
    if probe_root.resolve() != repo_root.resolve():
        try:
            return [str(probe_root.relative_to(repo_root))]
        except ValueError:
            return [str(probe_root)]
    return ["."]


def _pyscn_effective_scope_targets(
    repo_root: Path,
    effective_scope: list[str],
) -> list[str]:
    py_paths = filter_python_scope_paths(repo_root, effective_scope)
    if py_paths:
        return _cap_pyscn_targets(py_paths)
    policy = _probe_ignore_policy(repo_root)
    scoped = [
        p
        for p in (_normalize_scope_token(x) for x in effective_scope if str(x).strip())
        if p
        and p not in (".", "./")
        and not _is_git_rev_range(p)
        and not policy.rel_is_ignored(p, for_scope=True)
        and _scope_token_exists(repo_root, p)
    ]
    return _cap_pyscn_targets(scoped)


def _pyscn_probe_targets(
    repo_root: Path,
    *,
    python_root: Path,
    effective_scope: list[str] | None,
) -> list[str]:
    """Resolve pyscn path arguments; never return repo root when unsafe."""
    if effective_scope:
        return _pyscn_effective_scope_targets(repo_root, effective_scope)

    if repo_has_large_ignored_dirs(repo_root):
        if python_root.resolve() != repo_root.resolve():
            return _relative_probe_root_path(repo_root, python_root)
        return []

    return _relative_probe_root_path(repo_root, python_root)


def _jscn_analyze_command(
    resolved: list[str],
    *,
    targets: list[str],
    min_complexity: int = 15,
) -> list[str]:
    args = [
        "analyze",
        "--output",
        "-",
        "--json",
        "--min-complexity",
        str(min_complexity),
        *targets,
    ]
    if resolved[:1] == ["jscn"] or (resolved and resolved[0].endswith("jscn")):
        return [*resolved, *args]
    if len(resolved) >= 2 and resolved[1] == "--yes":
        return [*resolved, *args]
    return [*resolved, *args]


def _parse_jscn_json_findings(raw: str, *, max_findings: int = 8) -> list[dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    findings: list[dict[str, Any]] = []
    issues = data.get("issues") or []
    if isinstance(issues, list):
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            if len(findings) >= max_findings:
                break
            path = str(issue.get("file") or issue.get("path") or "")
            detail = str(issue.get("message") or issue.get("detail") or issue)[:240]
            findings.append(
                {
                    "id": f"J{len(findings) + 1}",
                    "severity": str(issue.get("severity") or "warning"),
                    "path": path,
                    "detail": detail,
                }
            )
    summary = data.get("summary") or {}
    if isinstance(summary, dict) and not findings:
        q = summary.get("qualityIssueCount") or summary.get("totalIssues") or 0
        if q:
            findings.append(
                {
                    "id": "J1",
                    "severity": "warning",
                    "path": "",
                    "detail": f"jscn reported {q} quality issue(s)",
                }
            )
    return findings


def _jscn_probe_targets(
    repo_root: Path,
    *,
    node_root: Path,
    effective_scope: list[str] | None,
) -> list[str]:
    """Resolve jscn path arguments; never return repo root when unsafe."""
    policy = _probe_ignore_policy(repo_root)
    if effective_scope:
        js_paths = filter_javascript_scope_paths(repo_root, effective_scope)
        if js_paths:
            return js_paths
        scoped = [
            p
            for p in (_normalize_scope_token(x) for x in effective_scope if str(x).strip())
            if p
            and p not in (".", "./")
            and not _is_git_rev_range(p)
            and not policy.rel_is_ignored(p, for_scope=True)
            and _scope_token_exists(repo_root, p)
        ]
        return scoped

    if repo_has_large_ignored_dirs(repo_root):
        if node_root.resolve() != repo_root.resolve():
            try:
                return [str(node_root.relative_to(repo_root))]
            except ValueError:
                return [str(node_root)]
        return []

    if node_root.resolve() != repo_root.resolve():
        try:
            return [str(node_root.relative_to(repo_root))]
        except ValueError:
            return [str(node_root)]
    return ["."]


def _madge_entry(node_root: Path, scope_paths: list[str] | None) -> str:
    if scope_paths:
        for raw in scope_paths:
            tok = _normalize_scope_token(str(raw))
            if not tok or tok in (".", "./") or _is_git_rev_range(tok):
                continue
            candidate = Path(tok)
            if not candidate.is_absolute():
                candidate = node_root / tok
            try:
                if candidate.exists():
                    return tok
            except OSError:
                continue
    for candidate in ("src", "lib", "app", "."):
        if (node_root / candidate).exists():
            return candidate
    return "."


def _skip_probe(tool: str, reason: str) -> dict[str, Any]:
    return {
        "tool": tool,
        "status": "skip",
        "command": [],
        "summary": reason,
        "findings": [],
    }


def _unscoped_knip_skip_reason(
    repo_root: Path, effective_scope: list[str] | None
) -> str | None:
    """knip always walks node_root — refuse that on 9p / large trees without JS scope."""
    js_paths = filter_javascript_scope_paths(repo_root, list(effective_scope or []))
    if _is_slow_cross_mount(repo_root):
        return "skipped: slow cross-mount; refusing full-tree knip"
    if js_paths:
        return None
    if effective_scope and not is_broad_probe_scope(effective_scope):
        return "skipped: review scope has no JavaScript/TypeScript files"
    if repo_has_large_ignored_dirs(repo_root):
        return "skipped: refusing unscoped full-tree knip (large ignored dirs)"
    return None


def _append_probe_or_skip(
    probes: list[dict[str, Any]],
    selected: list[str],
    tool: str,
    run_fn: Callable[[], dict[str, Any]],
) -> None:
    if tool in selected:
        _probe_progress(f"structural Pass B — running {tool}…")
        probes.append(run_fn())
    else:
        probes.append(_skip_probe(tool, "not selected in probe plan"))


def run_probes(
    repo_root: Path,
    *,
    scope_paths: list[str] | None = None,
    state_dir: Path | None = None,
    timeout_per_tool: int = PROBE_TOOL_TIMEOUT_SEC,
    quick_mode: bool = False,
    tools: list[str] | None = None,
    plan: dict[str, Any] | None = None,
    skill_name: str | None = None,
    step: int | None = None,
) -> dict[str, Any]:
    """Run only the probes listed in ``plan`` / ``tools``; write results sidecar."""
    from forge_next.structural_tools import skip_structural_tools
    from scripts.shared.structural_probe_runners import (
        run_jscn_probe,
        run_knip_probe,
        run_madge_probe,
        run_pyscn_probe,
        run_skylos_probe,
        select_probe_tools,
        skipped_all_payload,
    )

    root = repo_root.resolve()
    merged_plan, selected = select_probe_tools(
        root, scope_paths=scope_paths, tools=tools, plan=plan
    )
    node_root = _resolve_probe_root(
        root, merged_plan.get("node_root"), node_probe_root(root)
    )
    python_root = _resolve_probe_root(
        root, merged_plan.get("python_root"), python_probe_root(root)
    )
    effective_scope = merged_plan.get("scope_paths") or scope_paths

    if skip_structural_tools() or skip_structural_probes():
        return skipped_all_payload(
            root,
            merged_plan,
            selected,
            reason="FORGE_SKIP_STRUCTURAL_TOOLS=1",
            state_dir=state_dir,
        )

    # Write an in-progress sidecar early so Ctrl-C / hangs still leave a trail.
    if state_dir is not None:
        _write_sidecar(
            state_dir,
            {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "IN_PROGRESS",
                "stack": detect_stack(root),
                "plan": merged_plan,
                "selected_tools": selected,
                "probe_roots": {"node": str(node_root), "python": str(python_root)},
                "probes": [],
            },
        )

    probes: list[dict[str, Any]] = []
    skip_knip_reason = _unscoped_knip_skip_reason(root, effective_scope)
    if skip_knip_reason and "knip" in selected:
        _probe_progress(f"structural Pass B — skipping knip ({skip_knip_reason})")
        probes.append(_skip_probe("knip", skip_knip_reason))
    else:
        _append_probe_or_skip(
            probes,
            selected,
            "knip",
            lambda: run_knip_probe(node_root=node_root, timeout=timeout_per_tool),
        )
    _append_probe_or_skip(
        probes,
        selected,
        "madge",
        lambda: run_madge_probe(
            node_root=node_root,
            effective_scope=effective_scope,
            timeout=timeout_per_tool,
        ),
    )
    _append_probe_or_skip(
        probes,
        selected,
        "jscn",
        lambda: run_jscn_probe(
            repo_root=root,
            node_root=node_root,
            effective_scope=effective_scope,
            timeout=timeout_per_tool,
        ),
    )

    exclude_paths = merged_plan.get("exclude_paths")
    if not isinstance(exclude_paths, list):
        exclude_paths = None

    _append_probe_or_skip(
        probes,
        selected,
        "pyscn",
        lambda: run_pyscn_probe(
            repo_root=root,
            python_root=python_root,
            effective_scope=effective_scope,
            timeout=min(timeout_per_tool, PROBE_PYSCN_FILE_TIMEOUT_SEC),
        ),
    )
    _append_probe_or_skip(
        probes,
        selected,
        "skylos",
        lambda: run_skylos_probe(
            repo_root=root,
            python_root=python_root,
            effective_scope=effective_scope,
            timeout=timeout_per_tool,
            quick_mode=quick_mode,
            skill_name=skill_name,
            step=step,
            exclude_paths=exclude_paths,
        ),
    )

    _probe_progress("structural Pass B — writing results sidecar…")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stack": detect_stack(root),
        "plan": merged_plan,
        "selected_tools": selected,
        "probe_roots": {"node": str(node_root), "python": str(python_root)},
        "probes": probes,
    }
    _write_sidecar(state_dir, payload)
    return payload


def _write_sidecar(state_dir: Path | None, payload: dict[str, Any]) -> Path | None:
    if state_dir is None:
        return None
    path = Path(state_dir) / SIDECAR_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def sidecar_path(state_dir: Path | None) -> Path | None:
    if state_dir is None:
        return None
    p = Path(state_dir) / SIDECAR_NAME
    return p if p.is_file() else None


def load_probe_payload(path: Path | str | None) -> dict[str, Any] | None:
    """Load ``.structural-probes.json`` from disk."""
    if path is None:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _collect_probe_finding_rows(payload: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for probe in payload.get("probes") or []:
        if probe.get("status") == "skip":
            continue
        tool = str(probe.get("tool") or "?")
        for finding in probe.get("findings") or []:
            if not isinstance(finding, dict):
                continue
            rows.append(
                {
                    "tool": tool,
                    "id": str(finding.get("id") or ""),
                    "severity": str(finding.get("severity") or "warning"),
                    "path": str(finding.get("path") or ""),
                    "detail": str(finding.get("detail") or ""),
                }
            )
    return rows


def format_probe_summary_markdown(
    sidecar: Path | str | None = None,
    payload: dict[str, Any] | None = None,
    *,
    style: str = "brief",
) -> str:
    """Markdown summary of structural probe results for reports and step completion."""
    if skip_structural_probes():
        return "_Structural probes suppressed (`FORGE_SKIP_STRUCTURAL_TOOLS=1`)._\n"

    sidecar_path_obj: Path | None = Path(sidecar) if sidecar else None
    if payload is None and sidecar_path_obj is not None:
        payload = load_probe_payload(sidecar_path_obj)

    if not payload:
        return "_Structural probes: not run (no `.structural-probes.json` sidecar)._\n"

    lines = ["## Structural probes (Pass B)", ""]
    selected = payload.get("selected_tools") or []
    if selected:
        lines.append(f"**Tools:** {', '.join(str(t) for t in selected)}")
    if sidecar_path_obj and sidecar_path_obj.is_file():
        lines.append(f"**Sidecar:** `{sidecar_path_obj}`")
    plan = payload.get("plan") or {}
    if isinstance(plan, dict) and plan.get("reasoning"):
        lines.append(f"**Plan:** {str(plan['reasoning'])[:240]}")
    lines.append("")
    for probe in payload.get("probes") or []:
        tool = probe.get("tool", "?")
        status = probe.get("status", "?")
        n = len(probe.get("findings") or [])
        summary = str(probe.get("summary") or "")[:120]
        lines.append(f"- **{tool}**: {status} — {n} finding(s) — {summary}")

    rows = _collect_probe_finding_rows(payload)
    if not rows:
        lines.append("")
        lines.append("_No individual findings recorded._")
        return "\n".join(lines) + "\n"

    lines.extend(_probe_finding_rows_markdown(rows, style=style))
    return "\n".join(lines) + "\n"


def _probe_finding_rows_markdown(rows: list[dict[str, str]], *, style: str) -> list[str]:
    if style == "full":
        out = [
            "",
            "| ID | Tool | Severity | Path | Detail |",
            "|----|------|----------|------|--------|",
        ]
        for row in rows:
            detail = (row["detail"] or "").replace("|", "\\|").replace("\n", " ")[:200]
            out.append(
                f"| {row['id'] or '—'} | {row['tool']} | {row['severity']} | "
                f"{row['path'] or '—'} | {detail} |"
            )
        return out

    out = ["", "**Top findings:**"]
    for row in rows[:5]:
        fid = row["id"] or "—"
        path = row["path"] or "(no path)"
        out.append(f"- `{fid}` ({row['tool']}) {path}")
    if len(rows) > 5:
        out.append(f"- _…and {len(rows) - 5} more (see sidecar)._")
    return out


def resolve_probe_summary_for_state(
    state_custom: dict[str, Any],
    state_dir: Path | None,
    *,
    style: str = "brief",
) -> str:
    """Resolve sidecar from skill state and format probe summary markdown."""
    path_str = (state_custom.get("structural_probes_sidecar") or "").strip()
    sidecar = Path(path_str) if path_str else None
    if sidecar is None or not sidecar.is_file():
        sidecar = sidecar_path(state_dir)
    payload = load_probe_payload(sidecar) if sidecar else None
    return format_probe_summary_markdown(sidecar, payload, style=style)


def _probe_results_banner_bar() -> str:
    return ("=" * 60) if os.environ.get("FORGE_ASCII") == "1" else ("━" * 60)


def _probe_results_banner_header(
    sidecar: Path | None,
    payload: dict[str, Any],
) -> list[str]:
    bar = _probe_results_banner_bar()
    lines = [
        bar,
        "STRUCTURAL PROBES — results detail (Pass B)",
        bar,
        "",
        "Read `templates/structural-quality-probes.md` and the results sidecar before structural findings.",
        "",
    ]
    if sidecar:
        lines.append(f"Results: `{sidecar}`")
    plan = payload.get("plan") or {}
    if plan.get("reasoning"):
        lines.append(f"Plan reasoning: {plan['reasoning'][:300]}")
    lines.append(f"Selected tools: {', '.join(payload.get('selected_tools') or []) or '(none)'}")
    return lines


def _probe_results_banner_probe_lines(payload: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for probe in payload.get("probes") or []:
        tool = probe.get("tool", "?")
        status = probe.get("status", "?")
        summary = probe.get("summary", "")
        n = len(probe.get("findings") or [])
        lines.append(f"- {tool}: {status} ({n} finding(s)) — {summary[:120]}")
    return lines


def _insert_primary_review_hints(lines: list[str], payload: dict[str, Any]) -> None:
    js_rows = [
        p
        for p in (payload.get("probes") or [])
        if p.get("tool") in ("knip", "jscn") and p.get("status") == "pass"
    ]
    if js_rows:
        lines.insert(
            6,
            "**Primary (Node/TS):** review **jscn** and **knip** output first; "
            "cite `J*` / `K*` finding IDs in Pass B.",
        )
    py_rows = [
        p
        for p in (payload.get("probes") or [])
        if p.get("tool") in ("pyscn", "skylos") and p.get("status") == "pass"
    ]
    if py_rows:
        lines.insert(
            6,
            "**Primary (Python):** review **pyscn** and **skylos** output first; "
            "cite `P*` / `Y*` finding IDs in Pass B.",
        )


def format_probe_results_banner(
    payload: dict[str, Any],
    sidecar: Path | None,
    *,
    state_dir: Path | None = None,
    advisory: bool = False,
) -> str:
    from scripts.shared.structural_probes_gate import (
        finalize_probe_outcome,
        resolve_probe_status_from_payload,
    )

    probe_status, reason = resolve_probe_status_from_payload(payload)
    if payload is not None:
        payload["status"] = probe_status
        payload["status_reason"] = reason
    gate_dir = state_dir or (sidecar.parent if sidecar else Path.cwd())
    extra, _ = finalize_probe_outcome(
        gate_dir,
        status=probe_status,
        reason=reason,
        sidecar=sidecar,
        advisory=advisory,
    )
    lines = [extra.rstrip(), *_probe_results_banner_header(sidecar, payload)]
    lines.extend(_probe_results_banner_probe_lines(payload))
    lines.append("")
    _insert_primary_review_hints(lines, payload)
    lines.append("_Suppress: `FORGE_SKIP_STRUCTURAL_TOOLS=1`._")
    lines.append("_Planning-only (no auto-run): `FORGE_STRUCTURAL_PROBES_MANUAL=1`._")
    lines.append("")
    return "\n".join(lines)


def format_probe_planning_banner(
    state_dir: Path,
    inventory: dict[str, Any],
    suggestion: dict[str, Any],
    *,
    advisory: bool = False,
) -> str:
    from scripts.shared.structural_probes_gate import (
        STATUS_DEFERRED,
        finalize_probe_outcome,
    )

    extra, _ = finalize_probe_outcome(
        state_dir,
        status=STATUS_DEFERRED,
        reason="probe plan drafted; run `forge structural-probes run` or enable auto-run",
        policy="manual",
        advisory=advisory,
    )
    bar = ("=" * 60) if os.environ.get("FORGE_ASCII") == "1" else ("━" * 60)
    inv_file = Path(state_dir) / INVENTORY_NAME
    plan_file = Path(state_dir) / PLAN_NAME
    run_cmd = f"forge structural-probes run --state-dir {state_dir}"
    lines = [
        extra.rstrip(),
        bar,
        "STRUCTURAL PROBES — agent selects tools (Pass B)",
        bar,
        "",
        "Do **not** assume knip/madge/jscn/pyscn all apply. Use repo facts + your judgment.",
        "",
        "1. Read the inventory (and graphify report if listed):",
        f"   `{inv_file}`",
        "2. Edit the probe plan (start from the heuristic draft):",
        f"   `{plan_file}`",
        "",
        "   Plan fields:",
        "   - `tools`: subset of `knip`, `madge`, `jscn`, `pyscn`, `skylos` (empty `[]` = skip all)",
        "   - `node_root` / `python_root`: relative paths when not repo root",
        "   - `scope_paths`: optional paths for madge/knip/jscn/pyscn/skylos (e.g. changed files)",
        "   - `exclude_paths`: optional folder names for skylos `--exclude-folder` on broad scans",
        "   - `reasoning`: one short paragraph (required — documents your choice)",
        "",
        f"   Heuristic draft tools: {suggestion.get('tools')}",
        f"   Draft reasoning: {str(suggestion.get('reasoning', ''))[:240]}",
        "",
        "3. Run only the selected probes:",
        f"   `{run_cmd}`",
        "",
        "4. Read results sidecar before dispatching reviewers:",
        f"   `{Path(state_dir) / SIDECAR_NAME}`",
        "",
        "Full guide: `templates/structural-quality-probes.md`.",
        "",
        "_Code-review step 3 runs stack-applicable probes (pyscn+skylos when Python; knip+madge+jscn when Node)._",
        "_Planning-only: `FORGE_STRUCTURAL_PROBES_MANUAL=1`._",
        "_Force auto on other steps: `FORGE_STRUCTURAL_PROBES_AUTO=1`._",
        "_Skip eight subagents: `FORGE_SKIP_STRUCTURAL_EIGHT_AGENTS=1`._",
        "_Full eight-agent dispatch (not default quick trio): `FORGE_STRUCTURAL_EIGHT_AGENTS_FULL=1`._",
        "",
    ]
    counts = inventory.get("counts") or {}
    hints = inventory.get("stack_hints") or {}
    lines.insert(
        8,
        f"Stack hints: node={hints.get('node')} python={hints.get('python')} "
        f"(counts: py={counts.get('py')} ts={counts.get('ts')} tsx={counts.get('tsx')})",
    )
    pkg_roots = (inventory.get("markers") or {}).get("package_json_roots") or []
    if pkg_roots:
        lines.insert(9, f"package.json roots: {', '.join(pkg_roots[:6])}")
    return "\n".join(lines)


def inject_structural_probes_section(
    body: str,
    *,
    skill_name: str,
    step: int,
    repo_root: Path,
    state_dir: Path,
    mode: str | None = None,
    scope_paths: list[str] | None = None,
    quick_mode: bool = False,
    advisory: bool = False,
    force_full_eight: bool = False,
) -> tuple[str, Path | None, dict[str, Any] | None]:
    """Append planning or results banner; auto-run when policy says so.

    ``advisory=True`` (plan step 2): non-OK probe status does not write a pending
    gate or request confirmation — architecture continues with a banner only.
    ``force_full_eight=True`` (e.g. thorough code-review) dispatches all S1–S8.
    """
    if not should_run_probes(skill_name, step, mode):
        return body, None, None

    from scripts.shared.repo_paths import equivalent_path_in_repo, resolve_repo_root
    from scripts.shared.structural_probes_gate import (
        STATUS_SKIPPED,
        finalize_probe_outcome,
    )

    scan_root = resolve_repo_root(repo_root)
    write_dir = equivalent_path_in_repo(Path(state_dir), scan_root)
    write_dir.mkdir(parents=True, exist_ok=True)

    if skill_name.strip().lower() == "plan" and step == 2:
        advisory = True

    if skip_structural_probes():
        extra, _ = finalize_probe_outcome(
            write_dir,
            status=STATUS_SKIPPED,
            reason="FORGE_SKIP_STRUCTURAL_TOOLS=1",
            advisory=advisory,
        )
        return body + "\n\n" + extra, None, None

    _probe_progress(
        f"structural Pass B — scanning repo inventory ({skill_name} step {step})…"
    )
    inventory = build_stack_inventory(scan_root)
    counts = inventory.get("counts") or {}
    hints = inventory.get("stack_hints") or {}
    _probe_progress(
        "structural Pass B — inventory ready "
        f"(py={counts.get('py')} ts={counts.get('ts')} "
        f"node={hints.get('node')} python={hints.get('python')})"
    )
    _probe_progress("structural Pass B — resolving changed-file scope…")
    effective_scope, scope_note = resolve_effective_scope_paths(
        scan_root,
        scope_paths,
        skill_name=skill_name,
        step=step,
        mode=mode,
    )
    scope_suffix = f"; {scope_note[:80]}" if scope_note else ""
    _probe_progress(
        f"structural Pass B — scope resolved "
        f"({len(effective_scope or [])} path(s){scope_suffix})"
    )
    suggestion = suggest_probe_plan(inventory, scope_paths=effective_scope)
    write_stack_inventory(write_dir, inventory, suggestion)

    plan_file = write_dir / PLAN_NAME
    draft_plan = ensure_primary_probe_plan(
        load_probe_plan(write_dir) or suggestion,
        inventory,
        skill_name=skill_name,
        step=step,
        scope_paths=effective_scope,
        mode=mode,
        scope_note=scope_note or "",
    )
    write_probe_plan(write_dir, draft_plan)

    from scripts.shared.structural_eight_agents import (
        default_eight_agents_quick_mode,
        format_eight_agents_dispatch_banner,
        should_dispatch_eight_agents,
    )

    eight_banner = ""
    if should_dispatch_eight_agents(skill_name, step, mode):
        eight_quick = default_eight_agents_quick_mode(
            user_quick=quick_mode,
            force_full=force_full_eight,
        )
        eight_banner = "\n\n" + format_eight_agents_dispatch_banner(quick_mode=eight_quick)

    if should_auto_run_structural_probes(skill_name, step, mode):
        plan = draft_plan
        _probe_progress(
            "structural Pass B — running probes "
            f"({', '.join(plan.get('tools') or []) or 'none'})…"
        )
        payload = run_probes(
            scan_root,
            scope_paths=list(plan.get("scope_paths") or effective_scope),
            state_dir=write_dir,
            quick_mode=quick_mode,
            plan=plan,
            skill_name=skill_name,
            step=step,
        )
        sc = sidecar_path(write_dir)
        banner = format_probe_results_banner(
            payload, sc, state_dir=write_dir, advisory=advisory
        )
        return body + "\n\n" + banner + eight_banner, sc, payload

    banner = format_probe_planning_banner(
        write_dir, inventory, draft_plan, advisory=advisory
    )
    return body + "\n\n" + banner + eight_banner, None, None


def run_probes_from_state_dir(
    repo_root: Path,
    state_dir: Path,
    *,
    tools: list[str] | None = None,
    scope_paths: list[str] | None = None,
) -> dict[str, Any]:
    plan = load_probe_plan(state_dir)
    if plan is None:
        inv_path = inventory_path(state_dir)
        if inv_path and inv_path.is_file():
            try:
                inv_payload = json.loads(inv_path.read_text(encoding="utf-8"))
                plan = inv_payload.get("heuristic_suggestion")
            except (OSError, json.JSONDecodeError):
                plan = None
    if plan is None:
        inventory = build_stack_inventory(repo_root)
        plan = suggest_probe_plan(inventory, scope_paths=scope_paths)
    return run_probes(
        repo_root,
        state_dir=state_dir,
        scope_paths=scope_paths,
        tools=tools,
        plan=plan,
    )


def probe_payload_exit_code(payload: dict[str, Any]) -> int:
    """Return 1 when any probe reported ``status: fail``."""
    failed = [p for p in payload.get("probes") or [] if p.get("status") == "fail"]
    return 1 if failed else 0


def cli_run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agent-selected structural probes")
    parser.add_argument(
        "--state-dir",
        type=str,
        required=True,
        help="Workflow state directory (writes .structural-probes.json here)",
    )
    parser.add_argument(
        "--repo",
        type=str,
        default=None,
        help="Target repo root (default: auto-detect from cwd)",
    )
    parser.add_argument(
        "--tools",
        type=str,
        default=None,
        help="Override plan tools (comma-separated: knip,madge,jscn,pyscn,skylos)",
    )
    args = parser.parse_args(argv)

    state_dir = Path(args.state_dir).resolve()
    if not state_dir.is_dir():
        print(f"ERROR: state directory not found: {state_dir}", file=sys.stderr)
        return 1

    if args.repo:
        repo_root = Path(args.repo).resolve()
    else:
        from scripts.shared.orchestrator import _detect_repo_root

        repo_root = _detect_repo_root(Path.cwd())

    tools = None
    if args.tools:
        tools = normalize_probe_tools(args.tools.split(","))

    payload = run_probes_from_state_dir(repo_root, state_dir, tools=tools)
    sc = sidecar_path(state_dir)
    print(format_probe_results_banner(payload, sc))
    return probe_payload_exit_code(payload)


if __name__ == "__main__":
    raise SystemExit(cli_run())
