"""Assert aligned skill manifests use shared process-spine phase vocabulary."""

from __future__ import annotations

import re
from pathlib import Path

from scripts.shared.skill_manifest import load_manifest

REPO = Path(__file__).resolve().parent.parent

# Slot tokens from templates/skill-process-spine.md
_SLOT = re.compile(
    r"\b(Frame|Orient|Deepen|Decide|Act|Verify|Handoff)\b",
    re.IGNORECASE,
)

ALIGNED = ("design", "plan", "diagnose", "test", "evaluate", "implement", "code-review")


def test_phase_labels_use_spine_slots() -> None:
    missing: list[str] = []
    for skill in ALIGNED:
        manifest = load_manifest(skill, REPO)
        phases: list[str] = []
        if manifest.variants:
            for variant in manifest.variants.values():
                phases.extend(s.phase for s in variant.steps)
        else:
            phases.extend(s.phase for s in manifest.steps)
        assert phases, f"{skill} has no steps"
        bad = [p for p in phases if not _SLOT.search(p)]
        if bad:
            missing.append(f"{skill}: {bad}")
        if skill == "design":
            labels = [s.phase for s in manifest.steps]
            assert labels[0].startswith("Frame")
            assert labels[-1].startswith("Handoff")
    assert not missing, f"phases missing spine slots: {missing}"


def test_preamble_and_using_forge_honor_light_stop() -> None:
    preamble = (REPO / "templates" / "workflow-skill-preamble.md").read_text(
        encoding="utf-8"
    )
    assert "5–10 min" in preamble
    assert "Honor ceremony as a duration hint" in preamble
    using = (
        REPO / "integrations" / "claude" / "skills" / "using-forge" / "SKILL.md"
    ).read_text(encoding="utf-8")
    assert "do not auto-continue" in using.lower()
    assert "Frame+Orient" in using
