## Graphify — end-of-session refresh

{{REFRESH_NOTE}}

The knowledge graph should now match the tree you are about to commit or open in a PR.

{{DEFERRED_PROBES_SECTION}}

## Next — agent-driven ship

Follow **`.cursor/skills/ship/SKILL.md`** (or the user’s narrowed scope: commit only, PR, publish, etc.):

1. **Preflight** — `git status`, diff, branch tracking, optional tests.
2. **Commit** — stage relevant paths only; never commit secrets.
3. **Push / PR / merge / publish** — only when the user asked.

Graphify is **not** re-run on other `forge <skill> --step` invocations; refresh happens here at ship time.
Repo: `{{REPO_ROOT}}`
