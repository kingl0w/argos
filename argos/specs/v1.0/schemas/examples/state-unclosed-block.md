---
name: state-unclosed-block-fixture
description: Negative fixture — block opened but never closed before EOF
status: fixture
version: 1.0
---

# Example STATE.md (unclosed block)

## Done this cycle

<!-- argos:entry id=2026-04-26T15:01:00Z-ARG-043 ticket=ARG-043 author=verifier session=sess-c3d4 -->
- **[2026-04-26T15:01:00Z] ARG-043 — verified** (session sess-c3d4, worktree `.argos/worktrees/ARG-043-7e2a/`)
  - Files changed: `src/bar.ts`
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass

(no closing argos:entry tag follows — parser must scan to EOF and raise)
