---
description: Full sync of tickets, STATE, and git history. Run after returning to a project.
argument-hint: "[--fix]"
---

Reconcile drift between argos/specs/tickets/, STATE.md, and git history.

Steps:
1. Inventory tickets — for each argos/specs/tickets/*.md file: ID, Status from frontmatter, verification status, whether it has Implementation notes.
2. Inventory STATE.md — parse Queue, In progress, Done this cycle sections, note all ticket IDs referenced.
3. Inventory git log (last 50 commits) — extract commit messages referencing ticket IDs.
4. Cross-check and identify: tickets marked Done in file but not in STATE Done, tickets in Queue but verified, stale in-progress (14+ days no commits), orphan commits, ADRs Proposed older than 7 days, architecture drift not in ARCHITECTURE.md.
5. Invoke chaos probe: bash argos/scripts/argos-chaos-probe.sh state.
6. Produce reconciliation report with: drift detected, proposed STATE.md diff, proposed ARCHITECTURE updates, tickets to close.
7. If --fix: apply STATE diff, update ARCHITECTURE if proposed, move closed tickets to Done. Print what was applied.
8. If no --fix: show report, ask if user wants to run /reconcile --fix.

Never modify ticket files themselves. Never close ADRs automatically. Never run /next at the end.
