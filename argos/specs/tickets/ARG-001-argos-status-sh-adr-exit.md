# ARG-001 — argos-status.sh exits non-zero when ADRs are present

**Status:** Done
**Created:** 2026-07-01
**Priority:** P2
**Closed:** 2026-07-12

## Intent

`argos/scripts/argos-status.sh` treats the presence of ADR files under `argos/specs/decisions/` as an error condition and exits non-zero, even when every ADR is decided. A decided ADR is normal project history, not an inconsistency.

## Context

Filed from the v0.5 queue (this ticket predates the file; the file was backfilled 2026-07-01 so the queue entry resolves). Note the script is now superseded by `argos status` (`argos/cli/commands/status.py`) — resolving this ticket may simply mean deprecating or deleting the shell script instead of patching it.

## Non-goals

- Changing `argos status` (the Python integrity oracle) semantics.

## Acceptance criteria

- [x] A repo containing only accepted/decided ADRs gets exit 0 from the supported status entry point.
- [x] The chosen disposition for `argos-status.sh` (fix vs. deprecate) is recorded in this ticket.

## Resolution

Closed 2026-07-12 (audit batch, out-of-loop). The premise no longer reproduced: with accepted ADR-001 on disk, `argos-status.sh` printed "Proposed ADRs: (none)" and exited 0. Disposition: **deleted** — `argos-status.sh` (along with `argos-sync.sh` and `argos-init.sh`) was removed as superseded by the CLI (`argos status` / `argos sync` / `argos init`), which is the supported entry point and exits 0 on decided ADRs (verified live: all four integrity checks pass with ADR-001 present).
