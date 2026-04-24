# Argos — State

**Last updated:** 2026-04-24
**Updated by:** _verifier (automated) or human (on hotfix)_

This file is the project's short-term memory. Every subagent reads it first. Only the verifier writes it during the loop; humans write it on out-of-loop edits.

## Current focus

v0.5 layout consolidation shipped (commit `330ec3f`). Argos now self-hosts — tickets tracked under `argos/specs/tickets/`, starting with ARG-001.

## Queue

Tickets ready to be worked, in rough priority order. The planner picks the top one on `/next` unless told otherwise.

- ARG-001 — argos-status.sh exits non-zero when ADRs are present (P2)

## In progress

Tickets currently being executed by the loop or paused mid-cycle. At most one per operator.

- [ ] _none_

## Done this cycle

Tickets completed since the last cycle close. Cleared when you close a cycle (weekly, by default). Append-only within a cycle.

- v0.5 consolidation — runtime files moved under `argos/`; migration script for v0.4 users shipped (commit `330ec3f`)

## Open decisions

Product or architecture calls that are pending and block one or more queued tickets. Each becomes an ADR once decided.

- _none_

## Known drift

Places the code and `argos/specs/ARCHITECTURE.md` disagree. Each entry should name the file or module, one sentence on the mismatch, and a disposition (fix code, update docs, file ADR).

- `argos-init.sh` refuses to render when a non-template `STATE.md` exists, which now blocks fork users who start from this template — fix code (probably by skipping the `STATE_FILE` existence check if `STATE.md.template` is also present) or file ADR.
