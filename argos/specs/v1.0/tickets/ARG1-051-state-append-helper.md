# ARG1-051 — `argos state-append` CLI helper

**Status:** Queued
**Created:** 2026-04-26
**Priority:** P0
**Epic:** 6 (STATE.md migration + config split)

## Intent

Implement `argos state-append --section <name> --ticket <id> --author <agent> --session <id> --body-file <path>`: generates a unique block `id` (UTC ISO timestamp + ticket ID), wraps the body in canonical `<!-- argos:entry ... -->` comments, and appends to the named STATE.md section. Atomic write (write to temp + rename). The single chokepoint for STATE.md mutations — every writer (verifier, cycle-close) goes through here, not direct edits.

## Context

ARCHITECTURE.md §Contracts/Session→STATE.md specifies that all writes go through `argos state-append`. ARCHITECTURE.md §Invariants names atomic, append-only writes as load-bearing for concurrent-safe operation.

## Non-goals

- No section creation. If the named section is absent, the command fails (init owns scaffolding).
- No block deletion (cycle close has its own command, ARG1-054).
- No editing of existing blocks (forbidden by spec).
- No author validation beyond passing the value through to the block attribute (the pre-commit hook ARG1-032 enforces author=verifier).

## Acceptance criteria

- [ ] `argos state-append --section "Done this cycle" --ticket ARG1-099 --author verifier --session sess-test --body-file /tmp/body.md` exits 0; `argos/specs/STATE.md` contains a new block whose `id` matches `^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:]+Z-ARG1-099$` and whose other attributes match the flags.
- [ ] The new block appears under the `## Done this cycle` heading and not in any other section; verified by parsing STATE.md and checking the block's enclosing section.
- [ ] Two concurrent `argos state-append` calls (distinct tickets) both succeed; both blocks present in the final file (`grep -c '<!-- argos:entry' argos/specs/STATE.md` increases by 2).
- [ ] Two concurrent `argos state-append` calls (same ticket, same second) produce distinct `id`s (random suffix tiebreaker); no block is overwritten.
- [ ] `argos state-append --section "Nonexistent" --ticket ARG1-099 --author verifier --session sess-test --body-file /tmp/body.md; echo $?` prints non-zero; stderr contains `section not found`.
- [ ] After interrupting `argos state-append` mid-write (kill -9), `argos/specs/STATE.md` is unchanged and parses cleanly via ARG1-050's parser (atomic write proven).
- [ ] `argos state-append --dry-run ...` prints the block that would be written to stdout and does not modify any file.

## Depends on

- ARG1-001 (CLI scaffold)
- ARG1-050 (block schema)

## Touches

- `argos/cli/commands/state_append.py` (or equivalent — new)
- `argos/cli/tests/test_state_append.py` (or equivalent)

## Parallelizable with

- ARG1-002 (init)
- ARG1-003 (status)
- ARG1-005 (attend)
- ARG1-010 (orchestrator agent)
- ARG1-011 (orchestrate slash command)
- ARG1-012 (dispatch log writer)
- ARG1-013 (auto-fix retry)
- ARG1-020 (worktree spawn)
- ARG1-021 (independence detection)
- ARG1-023 (worktree merge)
- ARG1-040 (escalation schema)
- ARG1-052 (merge driver)
- ARG1-053 (config split)
