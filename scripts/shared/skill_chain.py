"""Canonical skill-chain mapping for inter-skill handoff menus.

Used by build_skill_handoff_menu() in orchestrator.py at every skill's
final-step. The default is the conventional next; alternatives let the user
pick a different path without remembering the flag syntax.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SkillTransition:
    """A skill's default next command and alternatives."""
    default: str | None              # "evaluate --mode pre" etc; None = terminal
    alternatives: list[str] = field(default_factory=list)


SKILL_CHAIN: dict[str, SkillTransition] = {
    "takeover":    SkillTransition("ship",                   ["plan", "implement", "diagnose", "design"]),
    "sketch":      SkillTransition("design",               ["plan", "diagnose"]),
    "design":      SkillTransition("plan",                 ["sketch", "evaluate --mode pre", "implement", "diagnose"]),
    "plan":        SkillTransition("evaluate --mode pre",  ["implement", "design", "code-review"]),
    "evaluate":    SkillTransition("implement",            ["plan", "code-review", "test"]),
    "implement":   SkillTransition("code-review",          ["ship", "test", "ux-review", "evaluate --mode post", "diagnose"]),
    "code-review": SkillTransition("test",                 ["ship", "implement", "ux-review", "diagnose"]),
    "test":        SkillTransition("ship",                 ["diagnose", "test --mode flows", "ux-review", "code-review", "implement"]),
    "ux-review":   SkillTransition("ship",                 ["diagnose", "implement", "code-review", "test"]),
    "diagnose":    SkillTransition(None,                   ["plan", "implement", "design", "sketch"]),
}

# Deprecated CLI alias — handoff menus use "design" only
DEVELOP_ALIAS_OF = "design"


# Optional descriptions for each command, rendered as "(why)" inline in the menu
COMMAND_DESCRIPTIONS: dict[str, str] = {
    "takeover":              "pick up where we left off and drive work until it's ready to ship",
    "plan":                  "turn the design into a concrete implementation plan",
    "evaluate --mode pre":   "review the plan before coding starts",
    "evaluate --mode post":  "check the implementation against the plan",
    "implement":             "build the planned changes",
    "code-review":           "review the code changes in depth",
    "test":                  "run the test suite and check coverage",
    "test --mode flows":     "write end-to-end mock user journeys",
    "ux-review":             "walk the product UI and report prioritized UX issues",
    "sketch":                "clarify goals and open decisions before design",
    "design":                "investigate options, pick a direction, and write a design spec when needed",
    "diagnose":              "find the root cause of a bug or regression",
    "ship":                  "commit, push, open/merge a PR, and publish if needed",
}
