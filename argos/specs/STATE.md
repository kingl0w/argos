# Argos — State

**Last updated:** 2026-04-26
**Updated by:** _verifier (automated) or human (on hotfix)_

This file is the project's short-term memory. Every subagent reads it first. Only the verifier writes it during the loop; humans write it on out-of-loop edits.

## Current focus

v0.5 layout consolidation shipped (commit `330ec3f`); init guard regression fixed in `d409774`. Argos now self-hosts — tickets tracked under `argos/specs/tickets/`, starting with ARG-001 and ARG-002. v1.0 spec tree work in progress: ARG1-040 (escalation schema) verified.

## Queue

Tickets ready to be worked, in rough priority order. The planner picks the top one on `/next` unless told otherwise.

- ARG-001 — argos-status.sh exits non-zero when ADRs are present (P2)
- ARG-002 — Document self-hosting setup in README (P2)
- ARG-003 — Ship editor config for visual collapse of harness-required directories (P2)
- ARG-004 — Investigate relocatable config for Cursor / Codex / Gemini (P2)
- ARG-005 — Scan-report generator for retrofit onto existing codebases (P2)

## In progress

Tickets currently being executed by the loop or paused mid-cycle. At most one per operator.

- [ ] _none_

## Done this cycle

Tickets completed since the last cycle close. Cleared when you close a cycle (weekly, by default). Append-only within a cycle.

- v0.5 consolidation — runtime files moved under `argos/`; migration script for v0.4 users shipped (commit `330ec3f`)
- Init guard fix — removed redundant `STATE.md` heuristic; sentinel is sole source of truth for "already initialized" (commit `d409774`). Resolves the drift flagged after `7cd81f2`.
- ARG1-040 — Escalation file schema and `escalations/` directory contract verified 2026-04-26 (manual session, no worktree dispatch — v0.5 loop run on the v1.0 spec tree). New files: `argos/specs/v1.0/schemas/escalation.md`, `argos/specs/v1.0/schemas/examples/escalation-{blocking,malformed}.md`, `argos/specs/escalations/{.gitkeep,README.md}`, `argos/cli/{__init__.py,escalation_validator.py,escalation-validate,tests/__init__.py,tests/test_escalation_validator.py}`. 7 unit tests pass; all 6 acceptance criteria covered. 0 critical / 0 major / 0 minor findings. Decision: pass. Validator language is provisional Python pending ADR-001; stdlib only, no deps added.

## Open decisions

Product or architecture calls that are pending and block one or more queued tickets. Each becomes an ADR once decided.

- _none_

## Known drift

Places the code and `argos/specs/ARCHITECTURE.md` disagree. Each entry should name the file or module, one sentence on the mismatch, and a disposition (fix code, update docs, file ADR).

- `argos/cli/escalation_validator.py` ships in Python without an executed ADR — provisional pending ADR-001 (cross-CLI language decision). Disposition: file ADR-001 (cross-CLI language); if non-Python is chosen, port the validator as part of the ADR's migration step.
