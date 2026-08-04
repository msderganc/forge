## graphify

This project has a knowledge graph at `graphify-out/` with god nodes, community structure, and cross-file relationships.

### Repo rules (always)

- ALWAYS read `graphify-out/GRAPH_REPORT.md` before reading source files, running grep/glob searches, or answering architecture questions. The graph is your primary map of the codebase.
- IF `graphify-out/wiki/index.md` EXISTS, navigate it instead of reading raw files.
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse EXTRACTED + INFERRED edges instead of scanning files.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
- **Corpus hygiene:** Graphify reads **`.graphifyignore`**, not `.gitignore`. Always exclude runtime/tooling dumps (`.forge/`, `.codex/`, `.pyscn/`, `.skylos/`, `.serena/`, `.venv/`, `graphify-out/`, `dist/`/`build/`, caches). Add new dump dirs to `.graphifyignore`; after changes, purge `graphify-out/cache` and run `graphify update . --force`.

### Forge workflow skills (`forge:*` slash commands)

When you run a Forge workflow (`/forge:design`, `/forge:plan`, etc.):

1. **Graphify refresh at ship** — run `forge ship --step 1` or `/forge:ship` before commit/PR (not on every workflow `--step`).
2. You may still use the graph during investigation when helpful (`graphify query`, `path`, `explain`).
3. Claude hooks (if installed via `forge claude-graphify`) may remind on search tools; workflow steps no longer print GRAPHIFY banners.

Install or refresh hooks after upgrading **forge-next**:

```bash
pipx upgrade forge-next
forge claude-graphify
```

Full documentation: [`docs/graphify.md`](docs/graphify.md).  
CI: set `FORGE_SKIP_GRAPHIFY=1` to suppress ship-time GRAPHIFY refresh/banners.
