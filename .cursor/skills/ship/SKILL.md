---
name: ship
description: >-
  Finalize coding work: preflight, commit, push, open/update PR, merge, and
  publish (PyPI/npm/etc.). Use when the user says ship, finalize, release,
  commit and push, open a PR, merge, or publish — or after implement/code-review
  when they want changes on the remote without retyping git instructions.
---

# Ship — finalize coding (commit / PR / push / merge / publish)

Run this skill end-to-end unless the user narrows scope (e.g. "commit only", "open PR", "publish PyPI").

## Scope (confirm once if ambiguous)

| User intent | Do |
|-------------|-----|
| **ship** / **finalize** / **get this merged** | Preflight → commit (if needed) → push → PR → stop before merge/publish unless they already asked |
| **commit** | Commit only; no push/PR unless asked |
| **push** | Push current branch; commit first only if they ask |
| **PR** / **pull request** | Push if needed, then `gh pr create` or update existing PR |
| **merge** | Only when explicitly requested; never force-push `main`/`master` |
| **publish** / **release** | Version bump + registry upload per repo signals below |

If multiple repos or no changes, say so and stop.

## Hard rules (always)

- **Never** change git config.
- **Never** commit `.env`, credentials, tokens, or other secrets — warn if staged.
- **Never** `git push --force` to `main`/`master` without explicit user request (warn first).
- **Never** `git commit --amend` unless user rules allow (explicit amend request, your commit, not pushed).
- **Never** skip hooks (`--no-verify`) unless the user explicitly asks.
- **Only commit when the user asked** to commit or ship (shipping implies commit when there are changes).
- **Only push/merge/publish when the user asked** or chose full **ship**.
- Use **`gh`** for GitHub (PR, checks, merge). If `gh` is unavailable, say so and give manual steps.
## Phase 0 — Graphify (when `graphify-out/` exists)

Run **once** before git preflight — refreshes the index for the code you are about to ship:

```bash
forge ship --step 1
```

Or invoke **`$forge:ship`** / this skill with graphify first. Workflow skills no longer run graphify per step.

Skip with `FORGE_SKIP_GRAPHIFY=1` or `forge graphify off`.

## pstack companion

Optionally run `/unslop` on commit/PR prose and `/technical-writing` for the PR body. Forge ship still owns merge/publish; never pstack babysit or autopilot. Canonical map: `templates/pstack-contract.md`. If pstack is not installed, skip.

## Phase 1 — Preflight

Run in parallel when possible:

- `git status`
- `git diff` (staged + unstaged)
- `git log -5 --oneline` (commit message style)
- Current branch and tracking: `git branch -vv`
- If PR path: `gh pr view` (ignore error if none)

Summarize: what will ship, target branch, blockers (dirty tree, wrong branch, no upstream).

Optional (ask or infer): run project tests / lint the user cares about before commit.

## Phase 2 — Commit

Skip if nothing to commit and user did not ask for an empty commit.

1. Stage only relevant paths (not caches, `__pycache__`, local graphify cache unless intentional).
2. Draft a **1–2 sentence** message focused on **why**, matching recent `git log` style.
3. Commit:
   - Prefer a single `-m` with a full message, or `-F` with a temp file on Windows if the message is multi-line.
   - Do **not** use interactive git (`-i`).

## Phase 3 — Push

```bash
git push -u origin HEAD
```

Use `-u` when the branch has no upstream. If push is rejected, report and suggest rebase/merge — do not force without explicit approval.

## Phase 4 — Pull request

If a PR already exists for this branch, summarize `gh pr view` and offer to update title/body or push new commits.

Otherwise create (after push):

```bash
gh pr create --title "..." --body "$(cat <<'EOF'
## Summary
- ...

## Test plan
- [ ] ...

EOF
)"
```

On Windows PowerShell without heredoc, use `gh pr create` with `--body-file` pointing at a short temp markdown file.

**Test plan** should be concrete checkboxes from what actually changed.

## Phase 5 — Merge (explicit only)

- Prefer **`gh pr merge`** with the repo’s usual method (`--squash`, `--merge`, or `--rebase`) when the user named it; otherwise ask once.
- Wait for required checks when the user wants a green merge; report failing checks with `gh pr checks`.
- Do **not** merge if the user only asked to open a PR.

## Phase 6 — Publish / release

Detect from the repo root:

| Signal | Action |
|--------|--------|
| `pyproject.toml` + user/release intent for **forge-next** | Follow **AGENTS.md** / **Versioning**: bump `project.version` in same change set when shipping user-facing package changes; `rm -rf dist/` (or `Remove-Item -Recurse dist`), `python -m build`, `python -m twine check dist/*`, `python -m twine upload dist/*` (or `scripts/release/publish_pypi.sh`). Skip PyPI if version was not bumped for a release. |
| `package.json` + `publishConfig` / npm scripts | `npm publish` only when user asked and version was bumped per project convention |
| GitHub Release | `gh release create` when user asked |

Never upload without credentials; report missing `TWINE_*` or `GITHUB_TOKEN` clearly.

## Reporting

End with a short checklist:

- Commit SHA (if any)
- Branch / remote
- PR URL (if any)
- Merge status (if requested)
- Publish version (if any)

## Forge workflow handoff

After **code-review**, **test**, or **implement**, the orchestrator may suggest **`$forge:ship`**. Treat that the same as this skill.
