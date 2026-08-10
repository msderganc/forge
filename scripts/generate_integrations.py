#!/usr/bin/env python3
"""Generate Cursor/Claude command packs and Codex skill wrappers from commands.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "integrations" / "spec" / "commands.json"
CURSOR_DIR = REPO_ROOT / "integrations" / "cursor-plugin" / "commands"
CLAUDE_DIR = REPO_ROOT / "integrations" / "claude" / "commands"
CODEX_DIR = REPO_ROOT / "integrations" / "codex" / "skills"

GRAPHIFY_BLOCK = """\
## Graphify

Runs at **ship** only (`forge ship --step 1`). This workflow does not print GRAPHIFY per step.
"""

WORKFLOW_HARD_RULE = """\
## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it. Follow the active skill's orchestrator output for what may be written.
"""

# Per-command overrides for "What to tell the user" / agent run hints
COMMAND_OVERRIDES: dict[str, dict[str, str]] = {
    "sketch": {
        "tell_user": (
            "- **Sketch** is a **1:1 iterative conversation** — reflect, confirm, revise — "
            "before design investigates solutions (no agent team dispatch).\n"
            "- Optional: domain glossary (`CONTEXT.md`) and ADRs when domain-docs mode is on."
        ),
        "agent_run": (
            "Run **sketch** at step one. Synthesis every few exchanges; re-run step 2 to continue; "
            "step 3 only after the user confirms ready for design."
        ),
        "codex_extra": (
            "Do **not** write `docs/forge/specs/*-design.md` in sketch.\n\n"
            "**No agent team** — 1:1 dialogue only. Re-run step 2 to continue; step 3 only after user confirms."
        ),
    },
    "design": {
        "tell_user": (
            "- **Design** explores problems, options, and evidence before formal planning.\n"
            "- Medium/large scope requires a named spec at `docs/forge/specs/` before handoff."
        ),
        "agent_run": "Run **design** at step one. Summarize phases without quoting invocation lines.",
        "codex_extra": "Do not modify tracked files without user permission. Spec gate for medium/large scope.",
    },
    "plan": {
        "tell_user": "- **Plan** turns an approved direction into tasks — no code edits during planning.",
        "agent_run": "Run **plan** at step one. Planning-only — no git mutations.",
        "codex_extra": "See `templates/plan-modes.md` for ceremony bands (`light`…`comprehensive`).",
    },
    "evaluate": {
        "tell_user": (
            "- **Evaluate** critiques a plan (pre) or audits implementation vs plan (post).\n"
            "- For full-team code review, use **code-review** (not evaluate --mode review)."
        ),
        "agent_run": "Run **evaluate** with `--mode pre` or `--mode post` and `--plan` on step 1.",
        "codex_extra": (
            "<invoke cmd=\"forge evaluate --mode pre --plan '<plan path>'\" />\n"
            "<invoke cmd=\"forge evaluate --mode post --plan '<plan path>'\" />"
        ),
    },
    "diagnose": {
        "tell_user": "- **Diagnose** runs structured RCA when root cause is unclear.",
        "agent_run": "Run **diagnose** at step one. Follow playbook sidecars and gates.",
        "codex_extra": "Read `templates/diagnose-execution-playbooks.md` per phase.",
    },
    "ux-review": {
        "tell_user": (
            "- **UX review** is a real-browser **product UX audit** (every page/control/state), "
            "not automated test execution or mock-flow authoring.\n"
            "- Pass `--base-url` when known; capture screenshots and keep the coverage checklist live."
        ),
        "agent_run": (
            "Run **ux-review** at step one. Orient → plan → walkthrough → states → findings → report. "
            "Prefer cursor-ide-browser MCP. Do not fix product code unless asked."
        ),
        "codex_extra": (
            "Read `templates/ux-review-criteria.md`. Maintain coverage checklist while testing.\n\n"
            "Prefer a real browser. Suite runs / mock flows use `forge test`, not this skill."
        ),
    },
    "graphify": {
        "tell_user": (
            "- **Graphify** feeds codebase structure into `forge takeover` (optional).\n"
            "- Refresh at ship (`forge ship --step 1`); install/uninstall post-commit hook from this command."
        ),
        "agent_run": "Run `forge graphify refresh` or hook install/uninstall per user request.",
    },
}

UTILITY_COMMANDS = frozenset({"takeover", "status", "doctor", "graphify", "ship"})


def _load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _agent_invoke_line(sub: str) -> str:
    """Explicit "must run the orchestrator" instruction (agent-facing, not shown to the user)."""
    if sub == "evaluate":
        return (
            "**Must run:** `forge evaluate --mode pre --plan '<plan path>' --step 1` "
            "(or `--mode post`) — the orchestrator script — before any other work."
        )
    return (
        f"**Must run:** `forge {sub} --step 1` (the orchestrator script) before any other "
        "work — do not skip straight to manual investigation/analysis."
    )


def _workflow_command_md(cmd: dict) -> str:
    sub = cmd["cli_subcommand"]
    ov = COMMAND_OVERRIDES.get(sub, {})
    tell = ov.get(
        "tell_user",
        f"- Run the **{sub}** workflow from the repo root.\n- Follow orchestrator phase output.",
    )
    agent = ov.get(
        "agent_run",
        f"Run **{sub}** at step one. Summarize phases without quoting invocation lines.",
    )
    agent = f"{_agent_invoke_line(sub)}\n\n{agent}"
    hard_rule = WORKFLOW_HARD_RULE
    if sub == "design":
        hard_rule = """\
## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the user **explicitly** allows that change. Session memory and `docs/forge/specs/` only when directed.
"""
    elif sub == "sketch":
        hard_rule = """\
## Hard rule — what the user sees

**Never show terminal commands** for this workflow.

**Never edit the repository** unless the phase allows it (session memory always; `CONTEXT.md` / `docs/adr/` only when domain-docs mode is on). **Do not** write `docs/forge/specs/` design specs.
"""
    return f"""---
name: {cmd['id']}
description: {cmd['description']}
---

{hard_rule}

{GRAPHIFY_BLOCK}

## What to tell the user first

{tell}

## What you run (agent)

{agent}
"""


def _codex_skill_md(cmd: dict) -> str:
    sub = cmd["cli_subcommand"]
    ov = COMMAND_OVERRIDES.get(sub, {})
    extra = ov.get("codex_extra", "")
    graphify = (
        "When `graphify-out/` exists, read `graphify-out/GRAPH_REPORT.md` before search; "
        "refresh at ship (`forge ship --step 1`)."
    )
    body = f"{extra}\n\n{graphify}\n\n" if extra else f"{graphify}\n\n"
    if sub not in ("evaluate",):
        body += f'<invoke cmd="forge {sub}" />\n'
    return f"""---
name: {cmd['id']}
description: {cmd['description']}
---

{body}"""


def generate(*, check_only: bool = False) -> list[str]:
    spec = _load_spec()
    changed: list[str] = []
    for cmd in spec["commands"]:
        sub = cmd["cli_subcommand"]
        if sub in UTILITY_COMMANDS:
            continue
        cursor_path = CURSOR_DIR / f"{sub}.md"
        claude_path = CLAUDE_DIR / f"{sub}.md"
        codex_path = CODEX_DIR / f"forge-{sub}" / "SKILL.md"
        content = _workflow_command_md(cmd)
        for path, text in (
            (cursor_path, content),
            (claude_path, content),
        ):
            existing = path.read_text(encoding="utf-8") if path.is_file() else None
            if existing != text:
                changed.append(str(path.relative_to(REPO_ROOT)))
                if not check_only:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text, encoding="utf-8")
        codex_text = _codex_skill_md(cmd)
        existing_codex = (
            codex_path.read_text(encoding="utf-8") if codex_path.is_file() else None
        )
        if existing_codex != codex_text:
            changed.append(str(codex_path.relative_to(REPO_ROOT)))
            if not check_only:
                codex_path.parent.mkdir(parents=True, exist_ok=True)
                codex_path.write_text(codex_text, encoding="utf-8")
    return changed


def main() -> int:
    check_only = "--check" in sys.argv
    changed = generate(check_only=check_only)
    if check_only and changed:
        print("Generated integration files drift from commands.json:")
        for p in changed:
            print(f"  {p}")
        return 1
    if not check_only:
        print(f"Updated {len(changed)} integration file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
