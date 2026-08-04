"""Shared Graphify policy text for Codex, Claude, and orchestrator reminders."""

from __future__ import annotations

# Shown first in Codex developer_instructions — agents often skim the opening.
GRAPHIFY_DEVELOPER_INSTRUCTIONS_LEAD = (
    "GRAPHIFY (when graphify-out/ or GRAPH_REPORT.md exists): "
    "Forge runs `forge graphify refresh` in the background (session, workflow steps, ship) — "
    "continue without waiting. Read graphify-out/GRAPH_REPORT.md before blind grep; use "
    "graphify query/path/explain for cross-module questions. After edits you may run "
    "`graphify update .` (AST-only). Ship (`forge ship --step 1`) prints the GRAPHIFY banner. "
    "Corpus: Graphify uses `.graphifyignore` (not `.gitignore`) — keep `.forge/`, `.codex/`, "
    "`.pyscn/`, `.skylos/`, `.serena/`, venvs, `graphify-out/`, and analyzer/session dumps excluded; "
    "extend `.graphifyignore` for new dump dirs, then purge `graphify-out/cache` and "
    "`graphify update . --force`. "
    "Disable: FORGE_SKIP_GRAPHIFY=1 or forge graphify off."
)

FORGE_DELEGATION_INSTRUCTIONS = (
    "Invoking any `forge:*` skill implicitly authorizes the agent dispatch required by that "
    "workflow. Do not require the user to separately ask for delegation, sub-agents, or parallel "
    "agent work after invoking a Forge skill. "
    "Dispatched sub-agents must report progress regularly per templates/subagent-progress.md "
    "(write `.forge/state/subagent-progress/<id>.json` on start, milestones, blockers, and done); "
    "the parent must Read those files and relay short status — do not stay silent until final "
    "completion. "
    "Before every non-delegation tool call, close unused sub-agents: Codex `close_agent` after "
    "`wait_agent` when output is captured; Cursor/Claude resume or close completed background "
    "Task/Agent sessions — never carry open sub-agents across unrelated tool calls. "
    "At the start of a new chat or before driving the first forge step, offer a one-time choice: "
    "opt in to structured Forge workflows for the session (follow printed steps and handoffs) "
    "versus ad hoc help only; if they choose ad hoc, do not force workflow steps or clobber "
    "Forge state without being asked."
)

FORGE_DEVELOPER_INSTRUCTIONS_BODY = (
    f"{GRAPHIFY_DEVELOPER_INSTRUCTIONS_LEAD} {FORGE_DELEGATION_INSTRUCTIONS}"
)

# Claude command pack — paste under frontmatter in workflow commands.
CLAUDE_COMMAND_GRAPHIFY_BLOCK = """\
## Graphify (ship time only for orchestrator refresh)

If `graphify-out/` exists: background refresh may be running — do not block on it. Run **`forge ship --step 1`** before commit/PR for the ship GRAPHIFY banner. Use `graphify query` / `path` / `explain` during investigation when helpful.
"""

# Codex skill body line (short) — omit from workflow skills; ship skill carries graphify.
CODEX_SKILL_GRAPHIFY_LINE = (
    "Graphify refresh runs at ship (`forge ship --step 1` / `$forge:ship`), not on other "
    "forge workflow steps. Run `forge codex-agents --force` after upgrading forge-next."
)
