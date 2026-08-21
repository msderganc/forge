from __future__ import annotations

from pathlib import Path

from scripts.implement.plan_waves import (
    custom_to_wave_rows,
    parse_parallelization_table,
    parse_parallelization_table_with_diagnostics,
    sync_waves_from_plan_file,
    wave_rows_to_custom,
)


def test_parse_parallelization_table_extracts_waves():
    md = """
## 4. Parallelization Map

| Task | Agent | Depends On | Wave | Can Parallel With |
|------|-------|-----------|------|-------------------|
| Task 1 | Dev-1 | none | 1 | Task 2, Task 3 |
| Task 2 | Dev-2 | none | 1 | Task 1, Task 3 |
| Task 3 | QA | none | 1 | Task 1, Task 2 |
| Task 4 | Dev-1 | Task 1 | 2 | Task 5 |
| Task 5 | Dev-2 | Task 2 | 2 | Task 4 |
| Task 6 | Dev-1 | Task 4, Task 5 | 3 | none |
"""
    total, rows = parse_parallelization_table(md)
    assert total == 3
    assert len(rows) == 6
    assert sum(1 for r in rows if r.wave == 1) == 3
    assert sum(1 for r in rows if r.wave == 2) == 2


def test_parse_parallelization_table_empty_when_no_wave_column():
    md = "| A | B |\n|---|---|\n| x | y |\n"
    total, rows = parse_parallelization_table(md)
    assert total == 0
    assert rows == []


def test_parse_parallelization_table_narrative_waves_with_bullets():
    md = """
## Implementation Waves
Wave 1:
- Task 1: build parser (agent: Backend)
- Task 2: add tests (agent: QA; depends on: Task 1)

Wave 2:
- Task 3: docs
"""
    total, rows = parse_parallelization_table(md)
    assert total == 2
    assert len(rows) == 3
    assert [r.wave for r in rows] == [1, 1, 2]
    assert rows[1].depends_on.lower() == "task 1"


def test_parse_parallelization_table_ignores_non_task_bullets():
    md = """
## Parallelization Map

Wave 1:
- Scope notes for this wave
- Risk: validate branch protection and naming conventions
- Task 1: implement parser guardrails (agent: Backend)
"""
    total, rows = parse_parallelization_table(md)
    assert total == 1
    assert len(rows) == 1
    assert rows[0].task == "Task 1: implement parser guardrails"


def test_parse_parallelization_table_narrative_inline_wave_map():
    md = """
## Parallelization Map
Wave 1: Task 1, Task 2
Wave 2: Task 3
"""
    total, rows = parse_parallelization_table(md)
    assert total == 2
    assert len(rows) == 3
    assert [r.task for r in rows] == ["Task 1", "Task 2", "Task 3"]


def test_sync_waves_from_plan_file_reads_repo_template(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    sample = tmp_path / "plan.md"
    sample.write_text(
        (repo_root / "templates/writing-plans.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    total, rows = sync_waves_from_plan_file(sample)
    assert total >= 3
    assert len(rows) >= 6


def test_parse_parallelization_table_with_diagnostics_applies_coverage_policy():
    md = """
| Task | Agent | Wave |
|------|-------|------|
| Task 1 | Dev-1 | TBD |
| Task 2 | Dev-2 | TBD |
| Task 3 | Dev-3 | 1 |

Wave 1:
- Task 1: do work (agent: Dev-1)
- Task 2: do more work (agent: Dev-2)
"""
    total, rows, diag = parse_parallelization_table_with_diagnostics(
        md,
        policy={"min_table_coverage": 0.75, "transcript_theme_limit": 2},
    )
    assert total == 1
    assert [r.task for r in rows] == ["Task 1: do work", "Task 2: do more work"]
    assert diag.source == "narrative"
    assert "table_coverage_reject" in diag.buckets
    assert len(diag.transcript_themes) <= 2


def test_wave_rows_round_trip_preserves_raw_metadata():
    md = """
| Task | Agent | Depends On | Wave | Can Parallel With | Priority |
|------|-------|------------|------|-------------------|----------|
| Task 1 | Dev-1 | none | 1 | Task 2 | high |
"""
    _total, rows = parse_parallelization_table(md)
    custom = wave_rows_to_custom(rows)
    restored = custom_to_wave_rows(custom)
    assert restored and restored[0].raw.get("priority") == "high"


def test_parser_skips_rows_without_numeric_wave():
    md = """
| Task | Wave |
|------|------|
| Bad | not-a-number |
| Good | 1 |
"""
    total, rows, diag = parse_parallelization_table_with_diagnostics(md)
    assert total == 1
    assert len(rows) == 1
    assert rows[0].task == "Good"
    assert "table_wave_value_missing" in diag.buckets
