## Graphify (codebase map)

When **`graphify-out/`** exists:

1. **Refresh at ship** — run **`forge ship --step 1`** or **`$forge:ship`** before commit/PR/publish (background `forge graphify refresh` + GRAPHIFY banner; do not wait).
2. During investigation you may read **`graphify-out/GRAPH_REPORT.md`** or use **`graphify query`**, **`graphify path`**, **`graphify explain`** instead of blind grep — optional, not injected on every workflow step.
3. If **`graphify-out/wiki/index.md`** exists, prefer the wiki over bulk raw reads when navigating.
4. **Corpus hygiene** — Graphify does **not** honor `.gitignore`. Maintain repo-root **`.graphifyignore`** so runtime/analyzer dumps never enter the graph: `.forge/`, `.codex/`, `.pyscn/`, `.skylos/`, `.serena/`, `.venv/`, `graphify-out/`, `dist/`, `build/`, tool caches, secrets. When a new dump directory appears, add it to `.graphifyignore` before refresh; after ignore changes, purge `graphify-out/cache` and run `graphify update . --force`.

Workflow skills (`develop`, `plan`, `implement`, `code-review`, `test`, `diagnose`, `evaluate`) **do not** print per-step GRAPHIFY blocks.

Disable: **`FORGE_SKIP_GRAPHIFY=1`** or **`forge graphify off`**.
