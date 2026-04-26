---
name: state-valid-fixture
description: Positive fixture — one well-formed argos:entry block under a Done this cycle heading
status: fixture
version: 1.0
---

# Example STATE.md (valid)

## Done this cycle

<!-- argos:entry id=2026-04-26T14:33:01Z-ARG-042 ticket=ARG-042 author=verifier session=sess-a1b2 -->
- **[2026-04-26T14:33:01Z] ARG-042 — verified** (session sess-a1b2, worktree `.argos/worktrees/ARG-042-3f9c/`)
  - Files changed: `src/foo.ts`, `src/foo.test.ts`
  - Findings: 0 critical, 0 major, 1 minor (`src/foo.ts:42` unused import in changed region)
  - Decision: pass-with-minors
<!-- /argos:entry -->
