---
name: state-duplicate-id-fixture
description: Negative fixture — two complete blocks with identical id attribute values
status: fixture
version: 1.0
---

# Example STATE.md (duplicate id)

## Done this cycle

<!-- argos:entry id=2026-04-26T16:00:00Z-ARG-044 ticket=ARG-044 author=verifier session=sess-e5f6 -->
- **[2026-04-26T16:00:00Z] ARG-044 — verified** (session sess-e5f6)
  - Files changed: `src/baz.ts`
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass
<!-- /argos:entry -->

Some prose between blocks to exercise the section-ordering invariant.

<!-- argos:entry id=2026-04-26T16:00:00Z-ARG-044 ticket=ARG-044 author=verifier session=sess-g7h8 -->
- **[2026-04-26T16:00:00Z] ARG-044 — verified (second write — same id, intentional collision)** (session sess-g7h8)
  - Files changed: `src/baz.ts`
  - Findings: 0 critical, 0 major, 0 minor
  - Decision: pass
<!-- /argos:entry -->
