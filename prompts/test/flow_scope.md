# Phase 3: Scope Definition

**Lead: QA**

You will capture a structured definition of what this mock flow will test. This becomes the contract that the developer will implement against in steps 4 and 5.

## Your Task

Answer the following questions and save your answers as a structured dictionary. The orchestrator will save them to session state.

### 1. User Journey (journey)

Describe the main flow as a sequence of steps from the user's perspective:

Example: "Admin logs in \u2192 clicks 'Upload' \u2192 selects file \u2192 system validates \u2192 redirects to report \u2192 admin exports CSV"

**Your answer:**

```
[paste your journey]
```

### 2. Entry Point (entry_point)

How should this flow start? Prefer the most realistic option available.

Options: `ui` (browser) | `http` (API) | `cli` (command line) | `module` (call code directly)

Your choice: ___________

### 3. Roles and Permissions Matrix (roles)

Which user roles should this flow cover?

**Default from project detection:** {{ROLES}}

**Options:**
- All discovered roles
- A subset (e.g. `admin, member`)
- One role only (public/anonymous flows use `["anonymous"]`)

Answer (comma-separated, or "all"):

```
[paste your choice]
```

### 4. External Services to Mock (external_services_to_mock)

List the external services or APIs your flow will encounter and need to stub. These are things *outside* the SUT (system under test):

Examples: email service, Stripe API, LLM (ChatGPT), slow scheduled job, third-party webhook.

**Important:** Do NOT list core app logic, DB, permission checks, ingestion, retrieval \u2014 those should be exercised with real calls (use test DB).

```
- [external service 1]: [reason it's mocked, e.g., "not in scope, returns non-deterministic result"]
- [external service 2]: [reason]
```

If none: reply "none" or leave blank.

### 5. Real Components to Exercise (real_components_to_exercise)

List the core app components your flow will exercise *without* mocking:

Examples: database writes/reads, permission checks, validation, file processing, API response formatting.

```
- [component 1]: [why it's important to test real]
- [component 2]: [why]
```

### 6. Failure Paths (failure_paths)

At least one failure scenario your flow will test. Examples:

- Bad input (malformed file, missing field, oversized payload)
- Missing permission (user role lacks access)
- Partial failure (first step succeeds, second fails)
- Conflicting data (duplicate IDs, version conflict)
- Retry recovery (transient failure then success)

```
- [failure path 1]: [what goes wrong, expected behavior]
- [failure path 2]: [what goes wrong, expected behavior]
```

**Minimum:** At least 1 failure path required. (Step 5 gates on this.)

### 7. Sample Inputs (sample_inputs)

Provide 1\u20132 real examples the flow will use. These become the templates for data-pack variants (clean, messy, edge-cases, duplicates).

If the flow uploads a CSV:
```
[copy a real sample CSV here or describe what a row looks like]
```

If the flow makes an HTTP request:
```
POST /api/endpoint
{
  "field1": "value1",
  "field2": "value2"
}
```

If the flow is CLI-driven:
```
$ command --flag value --data @file.json
```

These samples will be used to generate data-pack variants:
- **clean:** exactly your samples (control)
- **messy:** with encoding issues, duplicates, extra whitespace
- **edge-cases:** empty, oversized, malformed variants
- **duplicates:** intentional duplicate records

---

## Codex Runtime Instructions

1. **Read the plan:** Review step 3 in the plan file to understand the scope-capture requirements.

2. **Ask the user:** Follow `templates/user-questions.md` (plain English, short context). For each question above:
   - Present the question in everyday language
   - Add one sentence of context when the choice isn't obvious
   - Offer concrete options if applicable
   - Wait for the user's reply
   - Record the answer in the section above

3. **Build the structured dict:** Once all answers are collected, construct a Python dict:

   ```python
   flow_scope = {
     "journey": "...",
     "entry_point": "http",
     "roles": ["admin", "member"],
     "external_services_to_mock": ["email", "payment_processor"],
     "real_components_to_exercise": ["db_write", "permission_check"],
     "failure_paths": [
       "bad_input: invalid CSV triggers validation error",
       "missing_permission: member role is 403 forbidden"
     ],
     "sample_inputs": [
       "CSV with 3 rows, each with id,name,email",
       "CSV with encoding issue (UTF-16 instead of UTF-8)"
     ]
   }
   ```

4. **Persist:** Write the dict to the state sidecar file `.test-scope-step3.json`:

   ```
   exec_command echo '<json>' > /path/to/state/.test-scope-step3.json
   ```

   Or use `apply_patch` if you prefer declarative syntax.

5. **Verify:** Run `exec_command cat /path/to/state/.test-scope-step3.json` to confirm.

The next step (Scaffolding) will read this scope and create the file layout, data packs, and role-parameterization harness.
