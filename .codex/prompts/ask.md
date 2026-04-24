---
description: File an ADR when a product or architectural decision is blocking progress
argument-hint: "[short description]"
---

File an Architectural Decision Record. This is Argos's "pause and ask the human" — use it whenever a subagent hits a decision it shouldn't make alone.

Steps:
1. Find next ADR number from argos/specs/decisions/ADR-*.md.
2. Create argos/specs/decisions/ADR-NNN-<kebab-slug>.md with sections: Context, Options (A/B/C with Pros/Cons/Cost), Recommendation, Decision (blank, for user), Consequences (blank).
3. Update blocked ticket's verification section to reference this ADR.
4. Add entry to argos/specs/STATE.md under ## Open decisions.
5. Stop. Print path to ADR. Do not proceed until user fills in ## Decision.
