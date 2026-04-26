# ARG1-054 — Cycle close: archive "Done this cycle" blocks

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P1
**Epic:** 6 (STATE.md migration + config split)

## Intent

Implement `argos sync --close-cycle` (the only operation that *removes* blocks from STATE.md, per ARCHITECTURE.md §Contracts/STATE.md format). Move every block currently under `## Done this cycle` into a dated archive at `argos/specs/cycles/{YYYY-MM-DD}.md` (UTC date of the close), then clear the section in STATE.md. Single-writer operation; runs the pre-commit hook bypass (`ARGOS_CYCLE_CLOSE=1`) to commit the deletions.

## Context

ARCHITECTURE.md §Contracts/STATE.md format names cycle close as the only block-removal path. PRD §Target user (solo developers) implies cycle close is a manual operation, not scheduled.

## Non-goals

- No automatic scheduling (operator runs the command).
- No partial-close (e.g., archive only N blocks). All-or-nothing.
- No restoration / unarchive command (operators can `git revert` the close commit).
- No closing of the "In progress" section (those tickets are still in flight).

## Acceptance criteria

- [ ] With three blocks in `## Done this cycle`, `argos sync --close-cycle` exits 0; `argos/specs/cycles/YYYY-MM-DD.md` (today's UTC date) exists and contains all three blocks verbatim (`grep -c '<!-- argos:entry' argos/specs/cycles/YYYY-MM-DD.md` returns `3`).
- [ ] After cycle close, the `## Done this cycle` section in STATE.md is empty (between the heading and the next heading, no `<!-- argos:entry` strings); verified by parsing STATE.md and asserting the section's block list is `[]`.
- [ ] After cycle close, the "In progress" section is unchanged (block IDs match before-and-after).
- [ ] `argos sync --close-cycle` produces exactly one git commit; commit message matches `^cycle close \d{4}-\d{2}-\d{2}$`; commit was made with `ARGOS_CYCLE_CLOSE=1` env (verified by the pre-commit hook ARG1-032 not rejecting the deletion).
- [ ] Running `argos sync --close-cycle` twice on the same UTC date: the second run exits 0 with stdout `nothing to close` and creates no new commit.
- [ ] If `argos/specs/cycles/YYYY-MM-DD.md` already exists from an earlier same-day close, blocks are appended (not overwritten); verified by total block count growing.
- [ ] `argos sync --close-cycle --dry-run` prints what would happen and exits 0; STATE.md and the cycles directory are unchanged.

## Depends on

- ARG1-050 (block schema — needs to identify section boundaries and block IDs)
- ARG1-051 (state-append helper — used to scaffold the cycles archive file consistently)

## Touches

- `argos/cli/commands/cycle_close.py` (or equivalent — new)
- `argos/specs/cycles/.gitkeep` (new)
- `argos/cli/tests/test_cycle_close.py` (or equivalent)

## Parallelizable with

- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-010 (orchestrator agent)
- ARG1-013 (auto-fix retry)
- ARG1-020 (worktree spawn)
- ARG1-021 (independence detection)
- ARG1-022 (parallel dispatch)
- ARG1-023 (worktree merge)
- ARG1-031 (verifier writeback)
- ARG1-032 (pre-commit hook)
- ARG1-041 (escalation writer)
- ARG1-052 (merge driver)
- ARG1-053 (config split)
