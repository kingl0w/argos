# ARG1-003 — `argos status` integrity oracle

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 1 (CLI installer)

## Intent

Implement `argos status` as the single command that proves spec integrity. Exit 0 iff: STATE.md parses against the v1.0 block schema; every block's referenced ticket exists; `argos/config.toml` and `.argos/local.toml` parse; `argos/specs/escalations/` is empty (no undrained blocking escalations); and STATE.md's "Done this cycle" entries line up with the recent git log on the current branch. Exit non-zero with a one-screen diagnosis otherwise. This is PRD success criterion #5.

## Context

ARCHITECTURE.md §Invariants names `argos status` as the integrity oracle. v0.5 has `argos/scripts/argos-status.sh` (which ARG-001 fixed for exit codes); v1.0 reimplements inside the CLI binary so it can read the new block schema and config files.

## Non-goals

- No auto-fix. Status only diagnoses; `argos sync` reconciles.
- No network calls (no GitHub Issues check — that's `argos sync`'s job).
- No replacement of the v0.5 shell script in this ticket; deprecation/removal is a follow-up after migration.

## Acceptance criteria

- [ ] In a clean post-`argos init` repo with no tickets, `argos status; echo $?` prints `0`.
- [ ] After hand-corrupting `argos/specs/STATE.md` (delete a closing `<!-- /argos:entry -->` tag), `argos status; echo $?` prints a non-zero number; stderr contains `STATE.md` and `unclosed entry`.
- [ ] After dropping a malformed file at `argos/specs/escalations/blocking.md` (no frontmatter), `argos status; echo $?` prints a non-zero number; stderr names the file path.
- [ ] After dropping a well-formed blocking escalation at `argos/specs/escalations/ARG1-099-2026-04-26T12:00:00Z.md`, `argos status; echo $?` prints a non-zero number; stderr contains `undrained escalation`.
- [ ] `argos status --json` exits with the same code and emits a JSON object on stdout containing keys `state_md`, `config`, `escalations`, `git_alignment`, each with a `pass`/`fail` value.
- [ ] `argos status` completes in under 2 seconds on this repo (`time argos status` user+sys < 2.0).

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-040 (escalation schema — needed to validate escalation files)
- ARG1-050 (STATE.md block schema — needed to parse blocks)
- ARG1-053 (config split — needed to parse config files)

## Touches

- `argos/cli/commands/status.py` (or equivalent)
- `argos/cli/integrity.py` (or equivalent — checker module)
- `argos/cli/tests/test_status.py` (or equivalent)

## Parallelizable with

- ARG1-002 (init — separate command)
- ARG1-004 (sync — separate command)
- ARG1-005 (attend — separate command)
- ARG1-011 (/orchestrate slash command)
- ARG1-022 (parallel dispatch — separate module)
- ARG1-054 (cycle close — separate command)
